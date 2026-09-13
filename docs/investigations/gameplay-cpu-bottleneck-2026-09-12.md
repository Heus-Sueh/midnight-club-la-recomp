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
This did not initially support page faults as the primary source because Linux
procfs minor-fault counters do not count handled protection signals reliably.
The counters were supporting negative evidence, not a direct count of
ReXGlue's write-watch exceptions.

## Linux write-watch root cause and fix

A complete GDB stack, rather than the stopped guest PC alone, later exposed the
actual host work beneath the same hot path:

```text
read -> std::getline -> rex::memory::FindEntryForAddress
  -> rex::memory::QueryProtect -> MMIOHandler::ExceptionCallback
  -> signal delivery -> sub_82415EE8
```

On Linux, `QueryProtect` opened and scanned `/proc/self/maps` for every GPU
write-watch exception. `Memory::AccessViolationCallback` already checks the
physical heap's authoritative write-watch bitmap while holding the same global
lock, and it repairs stale page protection when another thread has cleared the
watch. The redundant host mapping query was removed on Linux only; Windows
retains its inexpensive `VirtualQuery` race check. The change is stored as
`patches/rexglue-linux-write-watch-fastpath.patch`.

In the same manually entered gameplay path, this moved the observed
presentation range from approximately 3.8–13.7 FPS to 18.3–29.8 FPS and GPU
occupancy from roughly 36% to 56–59%. Several stale-protection recoveries were
logged, but there was no fatal memory error or crash. This is the largest
measured improvement in the investigation.

## Post-fix GPU command processing

After the write-watch fix, `GPU Commands` became the hottest host thread in a
substantial fraction of samples. GDB repeatedly found
`RegisterFile::GetRegisterInfo` below `CommandProcessor::WriteRegister`. The
metadata lookup was executed for every register write solely to decide whether
to emit a debug message, even when GPU debug logging was disabled. The focused
command-processor patch now gates the lookup on the logger's debug level.

Sequential Type-0 packets now use the existing virtual
`WriteRegisterRangeFromRing` path. This lets the Vulkan backend bulk-copy float,
bool/loop, and fetch constants while preserving the original per-write path for
packets that repeatedly target one register. In comparable 25–75 second host
windows, these changes reduced process CPU from 387.9% to 360.4–366.4% and
kept GPU occupancy near 61%. The manual scene variance is too large to claim a
precise FPS delta, but builds and repeated gameplay smoke tests showed no
correctness regression.

## Updated target selection with Ghidra

A fresh 40-sample guest-thread profile after the SDK fixes produced:

- `0x82415DC8`: 7 samples;
- `0x8219A7D0`: 6;
- `0x82412F98`: 6;
- `0x82415EE8`: 5;
- `0x82411E98`: 3;
- `0x8244FEC8`: 3.

Focused Ghidra exports identified `0x82411E98` as a loop waiting for graphics
queue progress and `0x82412F98` as its polling helper. `0x8219A7D0` updates a
12-byte indexed object record and appends an 8-byte submission record. Complete
GDB stacks connect both groups to the main render traversal. The hotspots are
now distributed rather than dominated by one function.

Controlled negative experiments were removed rather than shipped:

- native replacements for `0x82415DC8`/`0x82415EE8` produced no measurable
  improvement after the write-watch fix;
- yielding after a positive `0x82412F98` poll reduced GPU occupancy to 52.6%
  and gameplay fell to 18.8–22.2 FPS late in the capture;
- a native equivalent of `0x8219A7D0` produced a 23.5 FPS late-window mean;
- the x86-64 small code model linked and reduced the executable from 72 to
  67 MiB, but its measured windows still ranged from 19.9 to 30.0 FPS.

## Vulkan descriptor reuse experiment

`VulkanCommandProcessor::UpdateBindings` unconditionally rewrites transient
vertex and pixel texture descriptor sets for every draw. A conservative
same-frame cache compared the pipeline descriptor-set layout plus the resolved
`VkImageView`, image layout, and `VkSampler` values. Frame startup retained the
SDK's existing invalidation so no transient descriptor set was reused after
frame reclamation.

The cache demonstrated substantial reuse potential: boot windows reached
99.0-99.8%, while late gameplay windows reused 48.4-57.1% of stage descriptor
sets. It did not improve throughput. The two final five-second gameplay windows
were 24.7 and 25.6 FPS without the cache versus 24.1 and 25.8 FPS with it;
process CPU did not decrease. The comparison and cache-maintenance work offset
the avoided allocation and `vkUpdateDescriptorSets` calls, or those calls were
not limiting the command thread. The experiment was removed rather than
shipping a plausible optimization without a measurable gain.

## Vulkan shared-memory upload target

The default-off diagnostic patch
`patches/rexglue-vulkan-shared-memory-profiling.patch` adds
`vulkan_shared_memory_profile`. It separates upload-buffer allocation,
`MakeRangeValid`, and `memcpy` time, and reports calls, ranges, chunks, pages,
and bytes in five-second windows. It must not be enabled for final FPS A/B
results because it reads the host clock around every upload phase.

In late gameplay the probe observed 97,629-120,560 upload calls per five
seconds, 99,511-122,578 ranges, and 216,000-272,284 pages. The uploads moved
approximately 0.88-1.12 GB per window. `MakeRangeValid`, which rearms physical
memory invalidation callbacks and reaches Linux `mprotect`, consumed
603.4-744.6 ms per window. The actual `memcpy` consumed only 98.7-116.9 ms and
upload-buffer allocation 6.0-6.6 ms. Most calls therefore cover only one or two
host pages, making protection syscall and handled-fault frequency the next
optimization boundary.

Any replacement must preserve the race invariant documented on
`SharedMemory::MakeRangeValid`: a range becomes watched before CPU-to-GPU copy
so a concurrent guest write cannot be missed. Measure protection calls per
physical alias and invalidation breadth before attempting wider watches,
batched protection, or an always-upload compatibility path.

## Conclusion and confidence

High confidence: the original severe regression was dominated by a redundant
Linux host-memory query in ReXGlue's write-watch handler. After fixing it, the
race path is a mixed bottleneck between the primary guest XThread and Vulkan
command processing, not persistent pipeline compilation, native presentation
pacing, or the measured texture-cache global lock.

High confidence: `sub_82415DC8` and `sub_82415EE8`, especially their common
command/state-record path, are a significant part of the dominant guest
thread's cost. Statistical sampling and inclusive timing agree.

High confidence: optimizing one sampled guest helper in isolation is
insufficient. Three semantics-preserving local experiments failed to produce a
repeatable throughput improvement after the host fix.

High confidence: transient texture descriptor rewrites have a high theoretical
reuse rate but are not a demonstrated FPS bottleneck with a compare-on-draw
cache. Shared-memory write-watch rearming now has the larger measured host-side
ceiling.

## Validation level and next target

Reached smoke gameplay plus repeatable host profiling and one controlled
negative test. This is not extended gameplay or a deterministic benchmark.

Next, count protection operations and handled invalidations per physical alias
inside `PhysicalHeap::EnableAccessCallbacks` and `TriggerCallbacks`. Test a
reversible coalescing strategy only if it preserves the pre-copy watch race
invariant. A deterministic gameplay input/replay window is still required
before claiming a precise throughput improvement. Do not add another
single-function native replacement unless a synchronized trace establishes an
optimization ceiling large enough to reach 30 FPS.

## Guest queue wait and Vulkan submission correlation

The next capture enabled the project hotspot probe for `0x82411E98` and the
default-off `vulkan_submission_diagnostics` SDK patch. The SDK probe reports
five-second totals for blocking fence waits, deferred-command translation,
`vkQueueSubmit`, and in-flight submission depth. It does not change queue or
synchronization behavior.

In the settled gameplay windows, `0x82411E98` consumed between roughly 52% and
68% of one guest thread's wall time. Over the same windows, Vulkan reported:

- zero blocking fence waits and zero time in blocking `vkWaitForFences` calls;
- an average queue depth close to 2, with a maximum of 3 to 5;
- about 550 ms per five seconds in `DeferredCommandBuffer::Execute` (11.0% of
  one CPU thread);
- about 22 ms per five seconds in queue acquisition plus `vkQueueSubmit`
  (0.44% of one CPU thread).

This rejects host GPU fence latency and queue submission as the cause of the
guest polling time. The guest is waiting for the `GPU Commands` worker to
consume and translate its PM4 stream. Driver-side command recording is real
work, but it is not large enough to explain the worker saturation by itself.

A temporary, more intrusive `IssueDraw` phase probe was used once and then
removed. In the lowest-FPS windows it observed approximately 812,000 to 837,000
`IssueDraw` calls per five seconds and 3.75 to 3.79 seconds of inclusive draw
translation time. Representative phase totals per five seconds were:

- pre-texture shader, primitive, and sampler work: 0.98 to 1.02 seconds;
- texture requests: 0.41 to 0.44 seconds;
- render-target update: about 0.30 seconds;
- pipeline lookup/configuration: about 0.12 seconds;
- dynamic state, constants, and descriptor bindings: 0.86 to 1.02 seconds;
- shared-memory and vertex/memexport preparation: 0.76 to 0.79 seconds;
- remaining draw recording: about 0.26 seconds.

The phase probe executes multiple host clock reads per draw and therefore must
not be used for an FPS comparison. Its values are target-selection evidence,
not production overhead measurements.

One sampled stack also found `IsReadbackMemexportEnabled` querying the global
cvar registry from every draw. Replacing this boolean compatibility query with
an equivalent direct expression removed the mutex/string lookup, but a
controlled run changed mean presentation from 25.68 to 25.46 FPS. The change
was removed because it had no measurable throughput benefit.

Run the retained low-overhead queue diagnostic with:

```console
./midnight_club_la --vulkan_submission_diagnostics=true \
  --log_level=info --log_file=/tmp/mcla-queue.log
python scripts/analyze_gpu_queue_log.py /tmp/mcla-queue.log --skip-windows 4
```

The highest-value next target is the per-draw descriptor/binding path. In
particular, `UpdateBindings` currently invalidates both texture descriptor-set
value bits on every draw and contains an explicit TODO to reuse unchanged
texture and sampler bindings. Any cache must include shader binding layout,
active image views, samplers, pipeline-layout compatibility, and frame/resource
lifetime; validate it with a cache hit counter and a visual negative control
before changing descriptor allocation or update behavior.
