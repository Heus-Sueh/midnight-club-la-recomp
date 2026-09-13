# Xenos draw-translation bottleneck proof

## Target and hypothesis

Determine whether CPU-side Xbox 360 GPU emulation, specifically Xenos draw
translation in the Vulkan command processor, is the limiting boundary rather
than physical-GPU fence latency, the native presenter, or guest simulation.
The falsifiable prediction was that consuming the same PM4 draw packets while
bypassing `VulkanCommandProcessor::IssueDraw` would sharply reduce the
`GPU Commands` thread CPU load and restore the stock 30 FPS presentation rate.

## Revision and setup

- project baseline commit: `5daccde`;
- ReXGlue v0.10.0 at `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`;
- Linux Release, SDL Wayland, Vulkan-only Xenos plugin;
- Intel Core i7-8700K and AMD Radeon RX 7600 with RADV;
- FBO render-target path, 1280x720 internal output, 1920x1080 window;
- asynchronous pipeline compilation with four workers, warm cache;
- shared-memory invalidation limit 16, readback disabled;
- 25-second warm-up and 60-second capture.

The host profiler was extended to record the combined CPU use of threads whose
name starts with `GPU Commands`. The control patch adds restart-bound
`vulkan_diagnostic_skip_draws`, cached during context setup so the normal draw
path performs only a boolean branch. When enabled, PM4 packet parsing and
register updates remain active, but `IssueDraw` returns before Xenos state,
resource, shader, pipeline, descriptor and Vulkan draw translation. Rendered
output is intentionally invalid.

```sh
just build
# Baseline: log_level = "info", vulkan_diagnostic_skip_draws absent or false.
just profile /tmp/mcla-gpu-commands-baseline.csv 60
just analyze-profile /tmp/mcla-gpu-commands-baseline.csv 25
just analyze-present out/build/linux-amd64-release/logs/midnight_club_la_060.log 25

# Negative control: set vulkan_diagnostic_skip_draws = true and restart.
just profile /tmp/mcla-gpu-commands-bypass.csv 60
just analyze-profile /tmp/mcla-gpu-commands-bypass.csv 25
just analyze-present out/build/linux-amd64-release/logs/midnight_club_la_061.log 25
just config-reset
```

Local logs and CSV captures are not committed.

## Causal result

| Metric after warm-up | Normal draws | Draw bypass | Change |
| --- | ---: | ---: | ---: |
| Presentation FPS | 29.22 | 30.00 | +0.78 |
| Minimum five-second FPS window | 26.5 | 30.0 | +3.5 |
| Windows below 30 FPS | 3/6 | 0/6 | -3 |
| `GPU Commands` CPU | 84.1% | 25.4% | -58.7 points |
| Process CPU | 367.6% | 299.5% | -68.1 points |
| Physical GPU busy | 51.2% | 26.8% | -24.4 points |

`GPU Commands` was the hottest thread in 41 of 70 baseline samples and reached
97.1% CPU. With draw translation bypassed it was never hottest; the main thread
was hottest in all 70 samples. The bypass warning was present in the control
log, providing a positive configuration check.

## Triangulation and conclusion

This intervention supplies the causal evidence missing from earlier sampling.
The normal path spends about 59 percentage points of one CPU core on work below
the draw-translation boundary that disappears when the backend is bypassed.
The presentation rate simultaneously reaches the exact 30 FPS cap with no low
window. Therefore CPU-side Xenos-to-Vulkan draw translation is a proven
limiting boundary in the tested sequence.

Earlier manually entered gameplay evidence independently showed the guest
queue wait at `0x82411E98` consuming 52-68% of its thread while Vulkan had zero
blocking fence waits and shallow in-flight depth. A temporary draw-phase probe
placed most of a command thread inside `IssueDraw`. Together, the wait-side,
worker-side and intervention evidence support high confidence that the same
emulation boundary limits gameplay. Physical-GPU saturation, fence latency and
native presentation pacing are rejected as primary explanations for the
captured deficit.

The bypass changes rendered behavior and is not an optimization. This run was
a reproducible fresh-launch sequence, not a visually verified deterministic
driving route or extended gameplay soak. It proves the subsystem boundary, not
which `IssueDraw` sub-phase should be replaced or whether every scene has the
same bottleneck.

## Sub-phase sampling follow-up

The next pass extended `scripts/gdb_hot_thread_sampler.py` to retain up to 16
function names per sample and added `scripts/analyze_hot_thread_samples.py` to
rank both leaf functions and inclusive stack presence. Two bounded captures
produced 26 usable `GPU Commands` samples. GDB itself aborted after the sixth
sample of the second batch, so the evidence is suitable for selecting a target,
not for assigning precise percentages.

Of all samples, 16 (61.5%) contained `VulkanCommandProcessor::IssueDraw`.
Within the complete capture, the repeated draw sub-paths were:

| Inclusive path | Samples | All samples |
| --- | ---: | ---: |
| `VulkanRenderTargetCache::Update` | 4 | 15.4% |
| `PhysicalHeap::EnableAccessCallbacks` | 4 | 15.4% |
| `VulkanCommandProcessor::UpdateBindings` | 3 | 11.5% |
| `VulkanSharedMemory::UploadRanges` | 2 | 7.7% |
| `VulkanRenderTargetCache::Resolve` / `IssueCopy` | 2 | 7.7% |

Seven samples (26.9%) caught the command thread waiting for work. Idle samples
remain in the denominator because silently removing them would overstate the
cost of the active paths. Unknown leaf frames also remain because stripped
library or driver frames still have useful symbolized parents.

```sh
gdb -q -nx -batch -x scripts/gdb_hot_thread_sampler.py \
  -ex 'set debuginfod enabled off' \
  -ex 'handle SIGSEGV nostop noprint pass' -ex start \
  -ex 'hot-sample-loop /tmp/mcla-gpu-a.csv "GPU Commands" 20 0.15 25' \
  --args out/build/linux-amd64-release/midnight_club_la
python scripts/analyze_hot_thread_samples.py \
  /tmp/mcla-gpu-a.csv /tmp/mcla-gpu-b.csv --limit 30
```

Keep automated GDB batches at 20 samples or fewer and combine their CSV files;
long interrupt loops were not stable with the local GDB 17.2 build.

## Write-watch breadth control

The existing physical-access counters then quantified the memory side of the
sampled path. During one 35-second post-warm-up interval, alias `A0000000`
received 393,216 enable requests and issued 343,619 protection calls covering
579,171 pages, only 1.69 pages per `mprotect`. It also handled 78,355 one-page
callback requests, each expanded to the configured 16-page invalidation limit.
Alias `C0000000` received the same enable requests but issued no protection;
this single scene is not enough evidence to disable that alias globally.

A counter-enabled capture at 16 pages presented at 28.60 FPS, while the clean
16-page causal baseline above presented at 29.22 FPS. A clean 64-page control,
using the SDK default breadth, presented at 27.02 FPS with five of six windows
below 30 FPS and two below 25 FPS. It also kept `GPU Commands` near saturation
at 87.1% CPU. The 64-page run logged no fatal Vulkan or device-loss error, but
it was not visually compared frame-for-frame.

The control rejects wider invalidation as a throughput optimization for this
captured sequence. Fewer observed host faults did not reduce the limiting
thread; the wider dirty region plausibly increased excess shared-memory upload
and Vulkan work. This is an inference, not a directly measured byte comparison
for the same run.

## Next target

Retain the draw bypass solely as a negative-control tool and keep the project
at 16 invalidation pages. The next implementation target is reducing redundant
write-watch rearming or coalescing protection runs without widening uploaded
dirty ranges and without violating the arm-before-copy race invariant. Before
changing alias policy, collect multiple deterministic gameplay scenes because
an alias with zero activity in one capture may be required elsewhere. Do not
ship skipped draws or infer that one sampled sub-phase owns the full
58.7-point CPU ceiling.
