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

## Texture-cache counter experiment

The default-off SDK diagnostic patch
`patches/rexglue-texture-cache-profiling.patch` measured `RequestTextures`
inclusive time and separated the wait for `global_critical_region_` from the
time holding it. It also counted prepared textures, loads, and shared-memory
ranges in five-second windows. The capture used
`--texture_cache_profile=true`; the option is disabled in normal runs.

During the low-FPS race path, the most expensive observed five-second window
reported:

- 214,928 requests taking 333.060 ms in total (6.7% of one CPU over the
  interval);
- 5,092 prepares and 5,055 actual loads;
- 89.489 ms waiting for the global lock (1.8% of one CPU);
- 0.322 ms holding the measured lock.

Across the same capture, the dominant guest thread still averaged 96.8% CPU,
GPU occupancy averaged 35.0%, and presentation ranged from 4.6 to 13.3 FPS in
the settled race windows. Texture processing is real work, but neither the
measured request path nor this mutex can account for the missing frame budget.
The texture-lock hypothesis is rejected as the primary bottleneck.

## Statistical guest-thread sampling

`scripts/gdb_hot_thread_sampler.py` was added because host policy
(`ptrace_scope=1`) rejects attaching an unrelated debugger. GDB launches the
game as its child, follows the game fork, passes expected ReXGlue write-watch
`SIGSEGV` signals, and appends the current PC of the XThread with the highest
accumulated Linux CPU time after each short interrupt.

A 40-sample gameplay capture produced 22 guest-code samples and 18 samples in
host/runtime code. Of the guest-code samples:

- `sub_82415DC8`: 8 (36.4%);
- `sub_82415EE8`: 4 (18.2%);
- all other individual functions: at most 2 samples.

Both leading functions were repeatedly sampled on the generated store that
updates the guest object field at offset `+13524`. Together they account for
12 of 22 symbolized guest samples (54.5%). This promotes the adjacent pair to
the next reverse-engineering target, but does not yet justify replacing it:
inclusive invocation counts and the semantics of the buffer managed through
offsets `+13524` and `+13528` must be established first.

A diagnostic-only strong-symbol probe (`MCLA_ENABLE_HOTSPOT_PROBE=ON`) then
wrapped both functions while preserving their original `__imp__` bodies. In
gameplay five-second windows it measured:

- `sub_82415DC8`: 27,482–51,265 calls/s, with 16.8–40.1% inclusive wall time;
- `sub_82415EE8`: 13,241–24,794 calls/s, with 10.3–34.7% inclusive wall time;
- combined peak rate: approximately 76,059 calls/s;
- combined observed inclusive share: 28.5–62.0% of one CPU in the captured
  gameplay windows.

The two wrappers do not call each other, so their inclusive times do not
double-count one another. The probe adds timing and atomic-accounting overhead
outside the measured original bodies, and is therefore unsuitable for FPS
comparison, but the inclusive figures establish a large optimization ceiling.

Static call-site inspection shows `r4` selecting state slots (including a
16-slot initialization loop) and both routines appending eight-byte records
through a cursor/end pair at offsets `+13524`/`+13528`. `sub_8241A630` allocates
or closes a 2008-byte block when that cursor fills. An attempted external
strong-symbol wrapper for `sub_8241A630` observed zero calls because generated
calls in the same translation unit bind directly to the local weak alias; this
is a probe limitation and not evidence that the slow path is unused. Measuring
that internal path requires generated-code instrumentation or an entry hook.

Because the repeated samples landed on guest stores, the host profiler was
extended with process and hottest-thread minor/major fault rates. In settled
gameplay (35 seconds onward), process minor faults averaged 156.6/s, but the
dominant XThread averaged only 1.9/s (57.7/s maximum), with zero major faults.
This does not support page faults or GPU write-watch as the primary source of
the saturated guest core. Linux procfs counters are supporting negative
evidence, not a direct count of ReXGlue's handled protection signals.

## Conclusion and confidence

High confidence: the current race path is CPU-bound and not limited by Vulkan
GPU occupancy, persistent pipeline compilation, native presentation pacing, or
the measured texture-cache global lock.

High confidence: `sub_82415DC8` and `sub_82415EE8`, especially their common
command/state-record path, are a significant part of the dominant guest
thread's cost. Statistical sampling and inclusive timing agree.

Low confidence: the guest store at offset `+13524` itself is expensive. The PC
concentration may reflect surrounding work or sampling behavior, so invocation
and inclusive-time counters are still required.

## Validation level and next target

Reached smoke gameplay plus repeatable host profiling and one controlled
negative test. This is not extended gameplay or a deterministic benchmark.

Next, identify the state-record format emitted by `sub_82415DC8` and
`sub_82415EE8`, then measure how often their cursor-full path enters
`sub_8241A630`. A semantics-preserving native replacement or redundant-state
elision has enough potential benefit to investigate, but it must retain record
ordering and dirty-state behavior. Do not relax memory watches or
synchronization: the measurements do not support either change.
