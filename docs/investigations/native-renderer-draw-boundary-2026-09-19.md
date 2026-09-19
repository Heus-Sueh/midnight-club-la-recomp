# Native renderer draw-boundary investigation — 2026-09-19

## Scope

This investigation starts the transition from Xenos command emulation to an
incremental project-owned native renderer. It applies only to `default.xex`
SHA-256:

```text
c386f4001fa569e6ad4b982f441f67412f00b3f47c166134555cd4b59854a432
```

The initial goal is observation, not replacement: prove a guest draw boundary,
capture its inputs per frame, and preserve the complete `rexgpu-xenos` path.

## Reference architecture decision

The three local references solve different layers:

| Reference | Reusable pattern | MCLA use |
| --- | --- | --- |
| Skate3Recomp | Build on the guest thread and publish an immutable `shared_ptr<const FrameScene>` | Frame-scene lifetime and thread boundary |
| UnleashedRecomp | Intercept state and draw methods, enqueue typed commands, translate shaders, and cache native pipelines | Long-term state/draw translation model |
| hells-gate-recomp / Dante's Inferno | Native Vulkan presentation and explicit interop/fallback | Presentation and fallback model, not a complete draw replacement |

MCLA therefore begins as a hybrid: immutable Skate-style frame publication,
Unleashed-style progressive command coverage, and Xenos fallback for everything
that is not yet reproduced natively.

## Rejected hypothesis: `0x82412990`

Focused Ghidra export and generated-code inspection show that
`sub_82412990` does not submit a draw. It:

1. writes `0x000005C8` and `0x00020000` into the device command buffer;
2. calls `sub_82411E98(device, *(device + 0x2A9C), 4, 0, 0)`; and
3. waits until `*(device + 0x2B00) == 0`.

This behavior is consistent with device synchronization or ring-buffer
wait/flush handling. Hooking it as a draw would mix synchronization with scene
capture and produce an invalid renderer contract.

## Proven boundary: `sub_82427898`

`scripts/find_pm4_draw_builders.py` found a direct packet construction in
generated code. A focused Ghidra export confirmed the complete function body at
`0x82427898..0x824278EF` and a direct caller at `0x82429F94`.

The scan also found larger functions containing direct draw packets:

| Function | Direct headers observed |
| --- | --- |
| `0x82413068` | `DRAW_INDX` |
| `0x82417538` | `DRAW_INDX_2` |
| `0x82418350` | `DRAW_INDX_2` |
| `0x8241CD88` | `DRAW_INDX` |
| `0x8241D230` | `DRAW_INDX` |
| `0x8241D620` | `DRAW_INDX` |
| `0x82422488` | `DRAW_INDX_2` |
| `0x824225E0` | `DRAW_INDX_2` |
| `0x8242DE08` | `DRAW_INDX_2` |

Those routines mix state setup, branches, and in some cases multiple packets,
so they require individual entry contracts and runtime selection before being
used as draw hooks. The first instrumented boundary was `sub_82427898` because
it is a small, dedicated, one-packet builder with a complete entry contract.

Entry contract:

- `r3`: RAGE device / command-buffer owner;
- `r4`: raw draw argument, semantics not yet assigned;
- `r5`: raw draw argument, semantics not yet assigned;
- no register or control-flow changes are made by the observation hook.

Original function behavior:

```text
if (*(r3 + 0x30) > *(r3 + 0x38))
    command_ptr = sub_82412710(r3)
else
    command_ptr = *(r3 + 0x30)

*(command_ptr + 4) = 0xC0003600
*(command_ptr + 8) = ((r5 & 0xFFFF) << 16) | r4 | 0x80
*(r3 + 0x30) = command_ptr + 8
```

`0xC0003600` is a Type-3 `PM4_DRAW_INDX_2` header. The second word is retained
verbatim in `NativeDrawRecord`; names such as primitive type or vertex count
must not be assigned until correlated against command-processor state.

## Implemented capture boundary

- `config/default.toml` installs an observation-only mid-assembly hook at the
  function entry and passes `r3`, `r4`, and `r5` by reference without changing
  them.
- Runtime probes selected three active logical draw entry points for full raw
  argument capture:
  - `0x8241CD88`: `r3..r6`, emits `0xC0012201`;
  - `0x8241D230`: `r3..r6`, emits `0xC0012201` and can split large draws;
  - `0x8241D620`: `r3..r7`, emits `0xC0032201` and consumes additional index
    buffer state.
- Focused decompilation and the final draw-state trace promoted the
  `0x8241CD88` arguments to a typed contract: `r4` is the primitive type, `r5`
  is the vertex count, and `r6` is the vertex stride in bytes. The function
  allocates `r5 * r6` bytes, emits the draw, and returns the writable guest
  vertex address in `r3`.
- An observation hook at `0x8241D204`, immediately after `mr r3,r28`, associates
  that returned address with the most recent `0x8241CD88` record. The caller
  fills the allocation after return, so capture copies the bytes only at
  Present, never at the entry or return hook.
- `NativeSceneCapture` accumulates bounded raw draw records and publishes a new
  immutable `NativeFrameScene` at the proven Present boundary `0x8241A0E4`.
  Vertex bytes are packed into one frame-owned slab capped at 16 MiB; individual
  buffers are capped at 1 MiB and carry an offset rather than a host pointer.
- Capture is default-off behind `mcla_native_scene_capture`.
- The normal Xenos packet builder, command processor, rendering, and
  presentation remain active. No draw suppression is enabled.

## Reproduction

```sh
just find-pm4-draws
just ghidra 0x82427898
just test-tools
just build
```

The static finder output must include:

```text
sub_82427898 DRAW_INDX_2 header=0xC0003600 ...
```

For runtime validation, set `mcla_native_scene_capture = true`, enter a stable
gameplay scene, and inspect the five-second NativeRenderer report. A useful
capture has a stable non-zero `native_scene_draws` count and zero
`dropped_draws`; it does not yet imply complete draw coverage.

## Runtime evidence

Linux/Vulkan smoke tests used the checked-in FBO configuration on an AMD Radeon
RX 7600. The dedicated `0x82427898` hook produced zero records during the boot
scene, rejecting it as a universal draw boundary. Default-off entry probes then
measured these active paths over five-second windows:

- `0x8241CD88`: up to 247,456 calls during initial loading, then approximately
  444 calls in a quiet window;
- `0x8241D230`: 13,673 calls when the later scene became active;
- `0x8241D620`: 115,840 calls in that same transition;
- `0x82418350`: approximately one call per guest Present in steady state.

After promoting the three logical draw entries to raw-argument capture, frame
snapshots reported 1,628 and 1,352 records in active frames, then one or two in
quiet frames. All reported `dropped_draws=0`; guest presentation remained at
30.0 FPS during the capture smoke test. This proves the snapshot transport and
frame publication path, not native image parity.

## Final command-processor state trace

`patches/rexglue-draw-state-trace.patch` adds a generic, default-off trace at
`CommandProcessor::ExecutePacketType3Draw`, immediately after `IssueDraw` so
shader ucode analysis has populated the used-resource metadata. The PM4 packet
has already been decoded and the emulated draw remains authoritative. Each CSV
row contains:

- primitive, vertex/index count, index-buffer metadata, and major mode;
- active vertex and pixel microcode hashes;
- hashes of the current fetch, float, bool, and loop constant banks;
- color/depth render-target state, masks, viewport, scissor, shader program
  control, clipping, and output-path registers.
- raw values for only the vertex fetches, texture fetches, and float constants
  referenced by the active shaders.

The trace uses a PM4 `XE_SWAP`-only frame counter. The normal command-processor
counter is not suitable because host vblank also increments it. Empty swap
frames do not consume `gpu_draw_state_trace_frame_count`, so a capture starting
at frame 1 deterministically waits for the first frame containing a draw.

Reproduction:

```sh
out/build/linux-amd64-release/midnight_club_la \
  --gpu_draw_state_trace=out/build/linux-amd64-release/draw_state.csv \
  --gpu_draw_state_trace_start_frame=1 \
  --gpu_draw_state_trace_frame_count=1
just analyze-draw-state out/build/linux-amd64-release/draw_state.csv 12
```

The 2026-09-19 Linux/Vulkan capture on an AMD Radeon RX 7600 contained exactly
one PM4 frame and 1,654 draws. Five pass signatures were observed. The dominant
signature accounted for 1,625 draws (98.2%):

```text
VS 0x88F617431F7D9C9B
PS 0x46BE7CEEBA3ECD76
primitive TriangleStrip (6)
auto-indexed, 4 vertices
RB_SURFACE_INFO 0x14000500
RB_COLOR_INFO[0] 0x000002D0
RB_DEPTH_INFO 0x00010000
```

The resource-aware capture showed that all 1,625 draws share the same pixel
texture fetch and VS constants `c8..c11`. Their only varying shader-used state
is vertex fetch constant 95. Every `vf95` describes 36 words (144 bytes), with
an unchanged 9-dword vertex layout and a different address. The vertex shader
reads position `float3`, packed color, and UV `float2`; the pixel shader samples
one 2D texture and multiplies it by interpolated color.

The command trace maps exactly to the high-level hook: the first active scene
frame contained 1,628 `0x8241CD88` records, while the dominant shader pair
contained 1,625 four-vertex triangle strips and three six-vertex triangle
lists, also totaling 1,628 draws. The entry contract predicts the precise
payload sizes: `1,625 * (4 * 36) + 3 * (6 * 36) = 234,648` bytes.

A second Linux/Vulkan smoke test captured exactly 1,628 of 1,628 returned
buffers and 234,648 bytes for that frame. All sampled frames reported zero
missing buffers, zero cap drops, and zero unmatched returns. Stable windows
remained at 30.0 FPS. Later 28.x FPS windows coincide with heavy activation of
the separate `0x8241D230` and `0x8241D620` paths and require an A/B test before
any overhead attribution. The nearest capture-disabled smoke log averaged 29.7
FPS across five windows versus 29.8 FPS across six vertex-capture windows, so
there is no current regression signal; this is not a controlled gameplay A/B.

Reproduce the snapshot validation with:

```sh
just analyze-present out/build/linux-amd64-release/logs/<log>.log 0
```

The summary reports sampled vertex-buffer matches, maximum per-frame bytes,
and missing, dropped, and unmatched counts.

## Remaining risks and next evidence

- This finder detects direct `lis` + `ori` constant construction. Dynamically
  assembled headers and indirect wrappers require separate discovery.
- Final draw state, shader identity, shader-used resources, and the transient
  `0x8241CD88` vertex contents are now retained. Texture contents and complete
  render-target lifetime/synchronization are not yet owned by the project.
- The next native prototype may coalesce the 1,625 ordered four-vertex buffers
  into one host upload and one or a few Vulkan submissions, but it must preserve
  blend/order semantics and remain a compare-only path until image parity.
- A native draw is not safe until its shader, vertex/index data, constants,
  textures, render targets, viewport/scissor, synchronization, and fallback
  contract are known.
- Emulated draws must remain enabled until native output is image-compared and
  failure recovery has been exercised.
