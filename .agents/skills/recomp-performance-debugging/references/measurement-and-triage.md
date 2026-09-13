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

On Linux, launch a controlled run with:

```console
python scripts/profile_linux_runtime.py --duration 120 \
  --output /tmp/recomp-host.csv -- ./path/to/game [arguments]
```

The sampler uses `/proc` for whole-process and hottest-thread CPU load, minor
and major fault rates, and, when available, `gpu_busy_percent` plus
`mem_info_vram_used` from DRM sysfs.
Select `--gpu-busy-path` explicitly on multi-GPU hosts. Correlate elapsed time
with the game log; total process CPU can exceed 100% because it includes all
threads. A nearly saturated hottest thread with low GPU occupancy supports a
CPU/serialization hypothesis, while sustained high GPU occupancy supports a
GPU-bound hypothesis. Neither proves causality without a controlled A/B test.
Summarize the capture by fixed time windows with:

```console
python scripts/analyze_runtime_profile.py /tmp/recomp-host.csv \
  --warmup-seconds 10 --window-seconds 5
```

If `ptrace_scope=1` prevents attaching to a running recomp, launch it under GDB
and follow the game child instead. On MCLA, load
`scripts/gdb_hot_thread_sampler.py`, pass expected ReXGlue write-watch
`SIGSEGV`, and use `hot-sample-once OUTPUT_CSV` after repeated short
interruptions. First verify in the host CSV that one XThread remains dominant;
the command selects the matching thread with the greatest accumulated CPU
time. Its optional second argument chooses another name prefix, such as
`hot-sample-once OUTPUT_CSV "GPU Commands"`. Rank many samples rather than
treating one stopped PC as a hotspot.
For repeatable short captures, use
`hot-sample-loop OUTPUT_CSV NAME_PREFIX COUNT INTERVAL_S [WARMUP_S]` and rank
both leaf and inclusive stack frequency with
`scripts/analyze_hot_thread_samples.py CAPTURE [CAPTURE ...]`. Keep GDB batches
bounded and aggregate their CSV files: repeated debugger interrupts may make
long loops unstable. Preserve idle samples in the denominator, and do not
discard unknown leaf frames when their symbolized parents still locate the
subsystem.

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
- When a stack shows a GPU command thread inside a mutex, measure total request
  time, lock-wait time, lock-hold time, and operation counts separately in
  fixed windows. A blocked snapshot proves the wait exists, not that it owns a
  meaningful fraction of the frame budget.
- A sample concentrated on a generated `REX_STORE_*` is not sufficient proof
  of write-watch overhead. Correlate it with fault rates or a direct handled-
  fault counter before changing page protection; the sampled instruction may
  simply be inside genuinely hot guest logic.
- On Linux, inspect the complete signal-handler stack when write-watch faults
  are frequent. Repeated samples in `read`/`getline` under
  `FindEntryForAddress` mean `MMIOHandler::ExceptionCallback` is scanning
  `/proc/self/maps` per fault. The physical heap's write-watch bitmap is already
  checked under the same global lock and its callback handles stale host
  protection. Removing the redundant host protection query increased MCLA's
  measured GPU occupancy from roughly 36% to 58% and moved a representative
  gameplay range from 3.8–13.7 FPS to 19.5–29.8 FPS. Preserve an A/B capture
  and test actual invalid-page faults before upstreaming this general SDK fix.
- Audit work performed only to prepare disabled logs. A logging macro may gate
  formatting correctly while a caller still performs an expensive lookup
  before entering the macro. In ReXGlue's command processor,
  `RegisterFile::GetRegisterInfo` was outside `REXGPU_DEBUG` and ran for every
  register write. Gate both the lookup and the message on the GPU logger's
  active debug level. When a packet writes a sequential range, prefer the
  backend's existing bulk register API so its constant-buffer invalidation can
  be coalesced; preserve the scalar path for repeated-single-register packets.
- Re-profile after a large host-runtime fix. MCLA's former leading guest setter
  pair fell from 54.5% to 30% of symbolized samples once Linux write-watch
  overhead was removed. Native replacements, scheduler yields in a guest GPU
  polling loop, and a smaller x86-64 code model all failed to deliver a stable
  post-fix FPS gain. A previously hot PC is not a permanent optimization target.
- A project strong-symbol wrapper can measure generated calls that cross
  translation units, but direct calls to a weak alias in the same generated
  translation unit may bind locally and bypass the wrapper. Treat a zero count
  as a probe-coverage result until verified with `nm`, call-site placement, or
  an entry/mid-assembly hook.
- Correlate guest ring-buffer polling with backend submission data before
  treating it as a physical-GPU wait. Long guest waits combined with zero
  blocking fence waits, shallow in-flight depth, and a saturated GPU-command
  thread identify command-stream consumption or translation as the boundary.
  Measure deferred-command execution and queue submission separately; neither
  should inherit the whole `EndSubmission` duration.
- High-frequency draw diagnostics can perturb the bottleneck. Multiple host
  clock reads per draw are acceptable for one target-selection capture, but not
  for an FPS A/B. Remove the granular probe afterward or keep it default-off,
  and use its phase totals only to choose a lower-overhead counter experiment.
- A hot stack may expose a logically redundant mutex or allocation without
  establishing a useful optimization ceiling. MCLA's per-draw legacy readback
  cvar lookup was removable by boolean equivalence, yet its controlled A/B was
  within run variance. Preserve the negative result and move to the next
  measured phase rather than accumulating plausible micro-optimizations.
- A high cache hit rate does not establish a performance win. A conservative
  Vulkan texture descriptor cache reused 48-57% of stage descriptor sets in
  MCLA gameplay and over 99% during boot, but per-draw comparison and cache
  maintenance produced no FPS or CPU improvement. Measure the complete A/B and
  remove the cache when avoided API calls do not improve the limiting thread.
- For Vulkan shared-memory upload stalls, separate upload-buffer allocation,
  write-watch rearming, and copying. MCLA issued roughly 98k-121k tiny uploads
  per five seconds; `MakeRangeValid`/Linux `mprotect` cost 603-745 ms while
  `memcpy` cost 99-117 ms. Optimize protection and handled-fault frequency only
  while preserving the invariant that the watch is armed before CPU-to-GPU
  copying. Use the project's default-off shared-memory profiling patch for
  target selection, not final FPS comparison.
- Before optimizing write-watch alias handling, count actual protection runs
  and callback range expansion per alias. An alias receiving every enable call
  may perform no protection in one capture; that does not prove it is unused
  by all scenes. MCLA's A0000000 alias dominated protection and expanded
  one-page callback requests to about 64 pages. See
  `docs/investigations/physical-access-profile-2026-09-13.md` for revision,
  configuration and limitations. Test narrower invalidation against increased
  fault frequency before keeping a change; never remove alias tracking based
  on a single run.
- Fault-side diagnostics must avoid clocks, allocation and logger calls. Cache
  the opt-in flag during initialization, update counters under the existing
  memory lock, and report snapshots from the non-fault enable path. Callback
  counts are not necessarily protection-fault counts. Analyze cumulative logs
  with `just analyze-memory`; reject counter resets instead of subtracting
  unrelated process runs.
- Treat invalidation breadth as a workload-specific trade-off, not a universal
  smaller-is-better rule. In MCLA fresh-launch captures, narrowing shared-memory
  access invalidation from 64 to 16 pages roughly halved protection calls and
  reduced protected pages by over 60%, while callbacks rose 23-31%. Two
  diagnostics-on pairs and one diagnostics-off pair favored 16 pages, but the
  clean mean gain was only 0.34 FPS and gameplay was not visually confirmed.
  Keep the SDK default conservative, place a reversible override in the game
  configuration, and require a deterministic driving route plus a longer
  corruption soak before treating it as broadly validated.
- Fewer host page faults do not establish a write-watch optimization. In a
  later MCLA control, widening invalidation from 16 to 64 pages reduced faults
  in one host run but left `GPU Commands` saturated and reduced presentation
  from the 29.22 FPS baseline to 27.02 FPS. Wider invalidation can trade fault
  overhead for excess shared-memory upload and Vulkan work. Measure FPS,
  limiting-thread CPU, faults, uploaded bytes, and visual correctness together;
  keep the narrower setting when the complete pipeline regresses.
- To prove a command-translation boundary causally, pair thread-specific CPU
  accounting with a destructive, default-off negative control that consumes
  packets but bypasses backend draws. Cache the control at initialization and
  emit a positive activation warning; never query the cvar per draw. A useful
  proof requires the targeted worker CPU and the observed frame deficit to
  collapse together, plus independent evidence rejecting fence waits or GPU
  saturation. The bypass makes output invalid and establishes an optimization
  ceiling only. In MCLA's tested sequence it moved `GPU Commands` from 84.1%
  to 25.4% CPU while presentation reached exactly 30.00 FPS; see
  `docs/investigations/xenos-draw-translation-bottleneck-2026-09-13.md`.
