# Target selection and native migration

## Select targets by milestone value

Do not process functions in address order. Rank candidates by their connection
to the current milestone, known callers/callees, imports, strings, runtime
frequency, data touched, and whether resolving them unlocks further work.

A scoring tool may weight signals such as presentation calls, shader or PM4
access, render-target use, per-frame execution, or proximity to a known engine
anchor. Scores are queue-order hints, never semantic evidence. Penalize already
understood, weakly supported, or milestone-unrelated candidates.

Expand outward from proven anchors. For example, a validated presentation
function can guide investigation toward its frame-loop caller and host-swap
callee; an established device method can lead to adjacent state, target, shader,
material, and mesh paths. Re-evaluate confidence at every edge.

## Instrument before replacing

Use this progression:

```text
original behavior -> instrument -> capture -> understand -> reproduce -> compare -> replace
```

For graphics, correlate RAGE-level activity with Xenos commands, PM4 state,
shaders, render targets, and displayed output before implementing the Vulkan
equivalent. Keep unknown operations on `rexgpu-xenos` until the native path has
an explicit behavioral contract and comparison evidence.

Prefer incremental replacement boundaries:

- native presentation while emulated rendering remains active;
- understood command/state/draw operations with fallback for unknown commands;
- high-level scene publication only after structures and lifetime are proven.

Do not suppress the emulated path until the native path covers the required
operation and failure recovery is understood.

### Proving PM4 draw boundaries

Do not label a device-adjacent function as a draw solely because it writes the
ring buffer. Prove the packet header and the write-pointer update. For direct
Type-3 construction in ReXGlue generated code, `lis` plus `ori` commonly forms
`0xC0000000 | (opcode << 8)`; use `scripts/find_pm4_draw_builders.py` to rank
candidates, then verify the full function and callers with focused Ghidra
exports. A wait/flush packet writer is a rejected draw candidate even when it
runs every frame.

At the first verified boundary, capture raw registers and the exact emitted
packet word. Do not assign semantic field names until command-processor traces
correlate them. Publish bounded immutable frame snapshots and leave the
original packet builder and Xenos consumer active. This produces a measurable
capture contract without committing prematurely to a renderer ABI.

A statically clean packet builder may be inactive in the target scene. Add
default-off entry counters across the verified candidate set, run a bounded
scene-specific smoke test, and promote only active paths to argument capture.
Report both per-frame snapshot size and overflow count: a non-zero candidate
counter with an empty frame snapshot usually means the hook is still attached
to discovery telemetry rather than the actual scene publication path.

### Capturing final GPU state

When engine-level hooks expose draw intent but not all surrounding state,
instrument the common command processor immediately before its backend
`IssueDraw`. At that point packet decoding, register writes, shader selection,
and index-buffer setup have converged. Record stable identities and raw values:
shader microcode hashes, primitive/index metadata, render-target state,
viewport/scissor, program control, and hashes of large constant banks.

Bound the trace by non-empty PM4 frames, not wall time or a generic frame
counter. Emulator frame counters may also advance on host vblank, while intro
video or copy-only swaps may contain no draw packets. Maintain a trace-local
counter advanced only by the command-stream swap packet and let empty frames
wait without consuming the requested capture count.

Group rows by a pass signature that excludes per-object resource addresses and
constant hashes. A dominant signature identifies a migration candidate, not a
safe replacement. Before native rendering, retain the shader-used fetch
constants and referenced resource lifetime, then correlate the final state back
to the high-level hook. Keep the emulated draw active throughout this stage.

Prefer resolving texture and sampler descriptors with the emulator SDK's own
validated helpers after shader instruction overrides have been applied. Raw
fetch constants are valuable evidence, but reimplementing their bitfields in
an offline script can silently disagree on dimensions, mip allocation, tiling,
or effective filtering. Record both raw and resolved forms. Treat a descriptor
that is invariant across frames as proof of layout and binding stability only;
it does not prove that the referenced bytes are static, CPU-coherent, or not a
GPU resolve destination. Establish content lifetime at a synchronization point
before a native upload reads guest memory.

For a first Vulkan pipeline contract, capture blend controls, blend constants,
alpha reference, color/depth controls, write masks, render-target formats and
eDRAM bases together. Alpha test and reversed-depth compare modes are easy to
miss when shader, texture, and topology already appear correct, and either can
make a geometrically correct native image diverge completely.

For DrawPrimitiveUP-style helpers, separate allocation observation from payload
capture. A builder may emit the draw packet and return writable guest memory;
the caller populates it only after the function returns. Prove the returned
register and byte-size formula statically, hook after the return value is
formed, and copy the bytes at a later proven frame boundary. Store them in a
bounded frame-owned slab with per-draw offsets, not thousands of allocations or
borrowed guest pointers. Track expected, captured, missing, cap-dropped, and
unmatched-return counts. Exact agreement between `(vertex count * stride)` and
the backend fetch size is strong cross-layer evidence.

Correlate boundaries by identity as well as count. A high-level frame count that
equals one shader pair's primitive breakdown, payload size formula, and used
fetch layout is substantially stronger than frequency alone. Record the scene
and executable revision; boot/intro evidence must not be generalized to
gameplay without another capture.

Before a native submission, make a compare-only CPU batch falsifiable. Filter
on the complete proven signature rather than a shader hash alone, decode guest
endianness explicitly, reject malformed or non-finite inputs, and retain source
draw indices. Partition telemetry should satisfy
`accepted + unsupported + missing + invalid == candidates`; topology counts
should also be deterministic. This exposes incorrect assumptions before they
become Vulkan synchronization or image-parity bugs.

Never concatenate triangle strips as one longer strip unless restart semantics
are proven. A safe first representation converts every strip independently to
triangle-list indices while preserving draw order. Add a negative test that
would fail if a triangle crossed two source draws.

## Simulation and presentation

Treat guest simulation frequency and host presentation frequency as independent
systems. A faster present hook does not prove faster gameplay, and a global
delta-time or tick-rate change can alter physics, animation, AI, scripts, audio,
and timers. Where justified, interpolate validated render states while keeping
the guest simulation unchanged; detect discontinuities such as teleports and
camera cuts. Use `$recomp-performance-debugging` for the measurement protocol.

## Portable boundaries

Keep recompiled/game logic separate from host filesystem, input, audio, window,
renderer, lifecycle, and packaging services. Guest serialized structures must
not inherit the host ABI: preserve field sizes, alignment, packing, endianness,
and 32-bit guest pointer representation, then translate to host-native types at
an explicit boundary.
