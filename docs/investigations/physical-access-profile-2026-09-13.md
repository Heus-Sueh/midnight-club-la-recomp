# Physical write-watch alias profile

## Scope and reproduction

This advances host-memory bottleneck attribution, not a proven FPS optimization.
Baseline: project `e63a54d`, ReXGlue v0.10.0 at
`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`, existing documented SDK patches,
plus `patches/rexglue-physical-access-profiling.patch`. No guest code changed.
Linux Release, SDL Wayland, AMD Radeon RX 7600/RADV, existing owned Complete
Edition data and stock checked-in settings except executable-local
`log_level = "info"`, `physical_access_profile = true`, and
`vulkan_submission_diagnostics = true`.

```sh
just build
# Set the three diagnostic options in the executable-local TOML.
just profile /tmp/mcla-physical-access.csv 60
just analyze-profile /tmp/mcla-physical-access.csv 25
just analyze-memory out/build/linux-amd64-release/logs/midnight_club_la_054.log
just analyze-queue out/build/linux-amd64-release/logs/midnight_club_la_054.log
just config-reset
```

The local log and CSV are not committed. This was a fresh-launch sequence,
without a verified deterministic driving route or visual gameplay confirmation.
Do not compare its FPS directly with earlier manually driven race captures.
Runtime configuration was restored after capture.

## Results

Last-minus-first cumulative snapshots (786,432 enable calls per alias):

| Alias | Protection calls | Protected pages | Watched callbacks | Input pages/callback | Expanded pages/callback |
| --- | ---: | ---: | ---: | ---: | ---: |
| A0000000 | 733,784 | 1,605,106 | 63,633 | 1.00 | 63.98 |
| C0000000 | 0 | 0 | 0 | 0 | 0 |
| E0000000 | 2,282 | 46,274 | 2,112 | 1.00 | 43.74 |

These are attempted protection runs and watched callback requests, not success
checks or an exclusive count of CPU faults. Memory-counter deltas omit their
first snapshot, not exactly the first 25 seconds; do not equate them with the
host-profile warm-up window. Every snapshot is cumulative for one process.

After 25 seconds, the host capture had 71 samples through 60.4 seconds: mean
process CPU 360.1% (one core = 100%), hottest thread 90.6%, and GPU busy 60.8%.
GPU Commands was hottest in 34 samples and the guest thread in 29. Presentation
summary: six windows, mean 28.18 FPS, minimum 24.8 and maximum 30.0. Vulkan
diagnostics reported zero blocking fence waits. This does not establish
constant 30 FPS, an uninstrumented improvement, or long-duration stability.

## Decision

A0000000 accounts for over 99% of protection calls. A follow-up implemented a
restart-bound `shared_memory_access_invalidation_pages` cvar. The SDK default
of 64 pages preserves upstream behavior; the MCLA configuration selects 16.
The callback still preserves the directly requested pages, stops at existing
GPU-written boundaries, and only narrows excess invalidation within an aligned
window.

Four diagnostic runs were made in 64, 16, 64, 16 order. The first 64-page run
predated the configurable patch but is behaviorally identical to its default.

| Limit | Run | Mean FPS | Minimum window | A0000000 protection calls | Protected pages | Callbacks |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 64 | 054 | 28.18 | 24.8 | 733,784 | 1,605,106 | 63,633 |
| 16 | 055 | 29.15 | 26.3 | 340,888 | 586,833 | 80,311 |
| 64 | 056 | 28.68 | 27.0 | 726,711 | 1,545,317 | 61,181 |
| 16 | 057 | 29.95 | 29.6 | 337,475 | 553,540 | 75,194 |

The limit-16 runs roughly halved protection calls and reduced protected pages
by more than 60%, while increasing watched callbacks by about 23-31%. Their
mean FPS average was 29.55 versus 28.43 for limit 64. Since the counters can
perturb timing, one additional diagnostics-off pair kept only the existing
info-level presentation telemetry:

| Limit | Run | Mean FPS | Minimum window | Mean GPU busy |
| ---: | --- | ---: | ---: | ---: |
| 16 | 058 | 29.37 | 27.8 | 54.7% |
| 64 | 059 | 29.03 | 25.1 | 59.8% |

The clean pair supports the direction but the 0.34 FPS mean difference remains
small. Lower GPU occupancy is consistent with less shared-memory work but is
not causal proof. The project override is therefore provisional and must be
retested in a deterministic, visually checked driving route and longer soak.
Restore 64 immediately if corruption or a scene-specific regression appears.
Preserve GPU-written-region boundaries and arm watches before copying. No
alias can be removed merely because this run did not protect it.

The probe is default-off and restart-bound. Its fault-side path adds counters
under the existing lock, with no logging, allocation or time queries. Snapshots
are logged from the enable path after releasing its acquired lock.

## Validation

Linux integrated Release build and `just build` passed, including explicit GPU
plugin refresh from the selected Ninja target inventory. The patch passes
reverse-application checking against the tested SDK. Analyzer regression tests
cover alias isolation, warm-up subtraction, insufficient snapshots and process
counter resets. Recipe formatting and Windows build recipe dry-run passed;
Windows runtime was not available. Shared presets retain Vulkan ON/D3D12 OFF.
The probe is diagnostic-only and the 60-second runs are not stability soaks.
No run established constant 30 FPS or Windows runtime correctness.
