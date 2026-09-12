# Gameplay CPU bottleneck investigation — 2026-09-12

## Target and hypothesis

Determine why presentation falls far below the stock 30 FPS target during a
race. The initial hypothesis was that sustained shader/pipeline compilation,
GPU saturation, or the project-owned presentation pacing hook caused the drop.

## Revision and environment

- project commit at capture start: `012fea1`;
- Linux Release executable, SDL3 Wayland, Vulkan-only Xenos plugin;
- guest `default.xex` SHA-256:
  `c386f4001fa569e6ad4b982f441f67412f00b3f47c166134555cd4b59854a432`;
- CPU: Intel Core i7-8700K, 6 cores / 12 threads;
- GPU: AMD Radeon RX 7600, RADV NAVI33;
- display/internal resolution: 1920x1080 / 1280x720, scale 1;
- FBO render-target path, no readback, async compilation with four workers;
- warm Vulkan pipeline cache; stock target of 30 FPS.

The race was entered manually, so these runs localize the bottleneck but are not
a deterministic input benchmark.

## Instrumentation

The host capture used `scripts/profile_linux_runtime.py` at 500 ms intervals.
It records process CPU, hottest and top-three host threads, AMD GPU occupancy,
VRAM, RSS, and thread count. `scripts/analyze_runtime_profile.py` summarized the
CSV in fixed five-second windows. ReXGlue's native-renderer information log
reported guest presentation calls every five seconds.

Baseline command:

```console
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json \
  ./scripts/profile_linux_runtime.py --duration 100 --interval 0.5 \
  --output /tmp/mcla-gameplay-host.csv -- \
  ./out/build/linux-amd64-release/midnight_club_la \
  --log_level=info --log_file=/tmp/mcla-gameplay-info.log
```

The underscore cvar spellings are significant for runtime overrides. The
hyphenated `--log-level`/`--log-file` attempt did not override the executable's
TOML `warn` setting and produced an automatically named log instead.

## Evidence

The menu/early path held 30.0–30.4 presentation calls per second. On entering
gameplay it transitioned through 19.5, 6.7, 13.8, 14.7, and 8.5 FPS, then the
last eight five-second windows stabilized at:

- mean: 6.12 FPS;
- range: 5.4–7.1 FPS.

From 25 seconds onward, host sampling reported:

- process CPU mean 286.0%, median 277.6%, p95 343.1%;
- hottest-thread mean 96.9%, median 97.4%, p95 99.5%;
- GPU occupancy mean 43.2%, median 42.0%, p95 53.0%;
- maximum VRAM 2379.6 MiB and maximum RSS 1283.2 MiB;
- 58 host threads.

The hottest thread was one guest `XThread` in 149 of 150 gameplay samples.
The GPU was not saturated. All 871 cached graphics pipelines were created at
startup; only two additional pipeline states appeared around the gameplay
transition, so continuous compilation cannot explain the sustained 5–7 FPS.

## Negative control: presentation pacing

The same test was repeated with only `--mcla_smooth_motion=false`. The early
path reached 406.3 presentation calls per second, proving that the override
disabled the limiter. After the race settled, however, the last eight windows
averaged 5.86 FPS (5.2–7.0), while the hottest thread remained at 96.8% and GPU
occupancy at 41.2%.

This rejects the project-owned pacing hook as the primary gameplay bottleneck.
The small baseline/control difference is within the variance of manual input.

## Focused debugger evidence

Direct `gstack` attachment was denied by the host ptrace policy. Launching the
sampler under GDB with `follow-fork-mode child` allowed GDB to follow the game
while the detached Python parent continued recording thread load. Expected
ReXGlue write-watch `SIGSEGV` signals were passed to the runtime after their
behavior was confirmed.

One focused sample caught the dominant guest thread in `sub_82415DC8` at guest
address `0x82415DC8`, specifically at generated storage of a state field. This
function is short and has 11 generated call sites, so the sample supports high
call frequency but does not prove that this setter itself is the root cost.

A separate stack sample caught `GPU Commands` waiting for a mutex in:

```text
TextureCache::PrepareTextureLoad
TextureCache::RequestTextures
VulkanTextureCache::RequestTextures
VulkanCommandProcessor::IssueDraw
```

This is evidence for investigating CPU-side texture-cache synchronization, but
a single stack is not evidence of sustained lock contention.

## Conclusion and confidence

High confidence: the current race path is CPU-bound and not limited by Vulkan
GPU occupancy, persistent pipeline compilation, or native presentation pacing.

Medium confidence: the critical boundary is the guest render/submission thread
plus CPU-side Xenos work. Texture-cache locking is a candidate contributor.

Low confidence: `sub_82415DC8` is a root hotspot. Statistical instruction/function
sampling is still required before changing or hooking it.

## Validation level and next target

Reached smoke gameplay plus repeatable host profiling and one controlled
negative test. This is not extended gameplay or a deterministic benchmark.

Next, collect statistical samples of the hottest guest thread and GPU command
thread, preserving guest PC/LR when possible. Rank the resulting functions by
sample count, then inspect `TextureCache::PrepareTextureLoad` lock ownership and
request/upload frequency. Do not patch `sub_82415DC8` or relax synchronization
until repeated samples or counters show attributable cost and a correctness
comparison exists.
