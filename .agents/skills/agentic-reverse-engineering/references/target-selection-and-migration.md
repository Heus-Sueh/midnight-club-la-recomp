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
