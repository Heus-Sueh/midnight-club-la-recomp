---
name: recomp-performance-debugging
description: Measure and diagnose performance, frame pacing, hangs, crashes, and GPU/runtime stalls in a ReXGlue recompilation. Use for FPS regressions, stutter, profiling captures, Vulkan errors, benchmark comparisons, or deciding whether a fault belongs to guest code, the SDK, or the host integration.
---

# Recomp performance and debugging

Produce reproducible evidence before changing timing, guest hooks, or Vulkan
policy. A higher present count is not automatically a faster game: distinguish
guest simulation rate, presentation calls, swapchain presents, and displayed
frames.

## Measurement loop

1. Pin executable hash/revision, build type, configuration file, command line,
   driver/GPU, scene, cache state, and measurement duration.
2. Capture a baseline and change one variable at a time. Use Release for FPS
   conclusions and RelWithDebInfo for Tracy, counters, symbols, or debugger work.
3. Analyze ReXGlue logs with `scripts/analyze_present_log.py`; discard a stated
   warm-up interval when shader/pipeline startup would bias the comparison.
   On Linux, use `scripts/profile_linux_runtime.py` when process CPU, hottest
   thread, AMD GPU occupancy, VRAM, RSS, and thread count are needed alongside
   the log, then summarize its CSV with `scripts/analyze_runtime_profile.py`.
   Treat it as host-specific evidence, not a cross-platform benchmark.
4. Compare median and tail latency, not only average FPS. Record p95, p99,
   maximum interval, and counts over meaningful hitch thresholds.
5. Localize the boundary before fixing it: guest timing/hook, recompiled PPC,
   runtime synchronization, Xenos command processing, Vulkan driver, SDL, or IO.
6. Re-run the same scene and configuration after the change. Preserve useful
   results in `docs/investigations/` and promote only repeatable conclusions to
   a skill reference.

Read [measurement-and-triage.md](references/measurement-and-triage.md) before
benchmarking or interpreting FPS. Read [debugging-evidence.md](references/debugging-evidence.md)
for crashes, hangs, debugger signals, Vulkan failures, and SDK-versus-game
ownership decisions.

## Guardrails

- Do not enable a 60 FPS or delta-time patch solely because an uncapped present
  loop is fast. Validate gameplay speed, physics, animation, audio, and timers.
- Do not benchmark with stale executable-local configuration. Log the resolved
  config path and important cvar values.
- Do not call a debugger-caught write-watch signal a crash until ReXGlue's own
  handler is allowed to process it.
- Never publish retail bytes, shader microcode, memory dumps, save data, paths
  containing private identifiers, or logs containing secrets.
- Keep compatibility fallbacks configurable. Runtime code must not silently
  override TOML or CLI values needed for A/B testing.
