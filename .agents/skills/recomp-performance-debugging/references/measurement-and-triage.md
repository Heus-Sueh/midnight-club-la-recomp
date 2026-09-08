# Performance measurement and triage

## Define the experiment

Record these fields with every result:

- host OS, CPU, GPU, Vulkan driver and selected physical device;
- commit, executable build type, XEX SHA-256 and title-update state;
- resolved TOML path plus non-default CLI overrides;
- render-target path, resolution scale, vsync/present mode, pipeline worker
  count, readback policy, and whether caches are cold or warm;
- deterministic scene boundary, input sequence, warm-up, sample duration and
  whether logging/profiling instrumentation was enabled.

Do not compare Release directly with RelWithDebInfo. Tracy and lightweight
counters may materially alter CPU-bound results.

## Interpret the numbers

Use `scripts/analyze_present_log.py LOG [LOG ...] --warmup-seconds N` for logs
containing `XELOG_GPU PRESENT` timestamps.

- Average FPS describes throughput but hides uneven delivery.
- Median frame time describes the common frame.
- p95 and p99 expose shader compilation, synchronization, IO and scheduling
  hitches.
- Maximum is diagnostic only; correlate it with a timestamp and nearby log
  events before assigning a cause.
- Count intervals over 50 and 100 ms for a stable 30 FPS target. A single
  startup spike must not be reported as sustained gameplay performance.

An unusually high present rate can mean a guest loop is running too quickly or
that the observed hook is called multiple times per displayed frame. Validate
against guest simulation state and swapchain behavior before calling it FPS.

## Controlled A/B order

Change one item per run, generally in this order:

1. stock guest hooks and timing;
2. warm versus cold shader/pipeline cache;
3. async pipeline compilation and worker count;
4. FBO versus FSI render-target path;
5. readback/coherency settings;
6. resolution scale and presentation settings.

Keep an immediately reversible compatibility setting for optimizations that
relax memory coherency or skip readback. Visual correctness and forward
progress outrank a synthetic FPS gain.

## ReXGlue-specific findings

- Placeholder pipelines do not provide asynchronous behavior if
  `EndSubmission` drains the queue or waits for every busy worker. In async
  mode, notify workers and continue only if downstream handling of incomplete
  pipelines is explicitly supported.
- Performance CSV setup must occur after TOML and CLI resolution and before the
  first profiled frame. Flush it during clean shutdown.
- The runtime normally resolves configuration beside the executable. Stage the
  checked-in TOML on link or log the actual path to prevent stale-config tests.
- Avoid forcing tuning cvars from `OnPreSetup`; doing so invalidates CLI A/B
  experiments and hides machine-specific fallbacks.
