# Performance baseline — 2026-09-07

## Scope

This is a Linux Release smoke-test baseline for the boot/menu path, not a claim
about race gameplay performance.

- GPU: AMD Radeon RX 7600 (RADV/NAVI33)
- host: SDL3 Wayland, Vulkan-only Xenos plugin
- guest revision: `default.xex` SHA-256
  `c386f4001fa569e6ad4b982f441f67412f00b3f47c166134555cd4b59854a432`
- display/internal resolution: 1920x1080 / 1280x720
- render-target path: FBO
- pipeline creation: async, 4 workers, warm disk cache
- presentation target: stock 30 FPS

## Findings

The experimental intro-skip, imposter-shadow skip, 60 FPS, and delta-time hooks
reduced presentation throughput to roughly 8–13 FPS in controlled smoke tests.
After removing them, the same path produced roughly 138 presenter-hook calls per
second while uncapped. This indicates available host throughput but does not
prove correct 138 FPS gameplay simulation.

With the reviewed presenter hook capped to the stock rate, a 25-second run
produced:

- 701 presents;
- 29.66 average FPS;
- 33 ms median interval;
- 36 ms p95;
- 52 ms p99;
- 112 ms maximum interval;
- 9 intervals over 50 ms and 1 over 100 ms, primarily during startup.

The run logged no empty-resolve error, PM4 backend failure, fatal dispatch, or
orphaned `xenia_memory_*` shared-memory object.

## Changes retained

- Only `mcla_native_present_hook` at `0x8241A0E4` remains in codegen config.
- `mcla_target_fps=30` with monotonic host pacing.
- `clock_no_scaling=false` and `clock_source_raw=false`.
- Four Vulkan pipeline workers; automatic CPU-count selection was worse on the
  tested 12-thread host.
- Async pipeline creation no longer drains and waits at every submission when
  placeholder pipelines are allowed.
- A fully clipped resolve becomes a successful zero-extent no-op.
- `clear_memory_page_state=false` improved the instrumented boot benchmark by
  approximately 9%; set it back to `true` first when investigating GPU-written
  guest-memory corruption.

## Next required baseline

Capture a deterministic race segment with identical input, warm cache and
Release logging. Record simulation speed, audio synchronization and visual
correctness alongside frame-time percentiles before attempting 60 FPS patches.
