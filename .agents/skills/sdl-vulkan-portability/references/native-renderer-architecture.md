# Native Renderer Architecture & Implementation Patterns

While the primary initial milestone for ReXGlue targets is running stably under the emulated `rexgpu-xenos` plugin backed by Vulkan, long-term performance, visual quality, arbitrary display refresh rates, and ultrawide support benefit from a native renderer.

This document synthesizes the architectural approaches from three reference Xbox 360 recompilation projects:
1. **Skate3Recomp** (`skate3_native_scene.cpp`, `skate3_native_render.cpp`)
2. **hells-gate-recomp / Dante's Inferno** (`native_device.cpp`, `native_presenter.cpp`, `native_renderer_integration.cpp`)
3. **UnleashedRecomp** (`video.cpp`, `XenosRecomp`, PSO caching)

---

## 1. Architectural Tiers

Recompilation projects approach native rendering across three distinct tiers depending on engine architecture and project maturity:

```text
+-------------------------------------------------------------------------------+
| Tier 1: Native Presenter & Interop (hells-gate-recomp / Dante's Inferno)      |
| - Emulated Xenos draws guest frame                                            |
| - Intercepts final framebuffer / presentation loop                            |
| - Native Vulkan swapchain with aspect-ratio letterbox/pillarbox & scaling    |
| - Zero-copy GPU interop (D3D12 shared NT handles / VK external memory) or     |
|   CPU readback fallback                                                       |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Tier 2: Mid-Level D3D/Xenos Command Translation (UnleashedRecomp)             |
| - Hooks guest D3D9 / Xenos device methods (SetRenderState, DrawIndexedPrimitive)|
| - Uses XenosRecomp to translate guest microcode shaders into host SPIR-V     |
| - Asynchronous PSO compilation with disk cache (SDLEventListenerForPSOCaching)|
| - Native command buffer recording and swapchain presentation                  |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Tier 3: High-Level Scene Graph Reconstruction (Skate3Recomp)                  |
| - Hooks engine render world / scene graph (RenderWorld, DrawMesh, camera)    |
| - Extracts guest vertex/index buffers and textures directly into host Vulkan  |
| - Suppresses emulated Xenos draws via SDK cvar:                               |
|   `native_render_suppress_emulated_draws = true`                             |
| - Host motion smoothing / camera interpolation decoupled from guest sim tick  |
| - Front-to-back opaque sorting with early-Z rejection                         |
+-------------------------------------------------------------------------------+
```

---

## 2. Tier 1: Native Presenter & Interop Pattern (Dante's Inferno)

### Reference
- Commit: `2a934287a4c684df5ed38647712fc479465f3d90`
- Key Files:
  - `src/native_renderer/native_device.cpp` / `.h`
  - `src/native_renderer/native_presenter.cpp` / `.h`
  - `src/native_renderer/native_renderer_integration.cpp` / `.h`
  - `src/native_renderer/dantes_inferno_native_app.h`

### Core Concepts
1. **Separation via Derived App**:
   - Instead of modifying the baseline `ReXApp`, create a derived class (e.g. `MidnightClubLaNativeApp : public MidnightClubLaApp`).
   - Gated behind a cvar (e.g. `use_native_presenter`).
2. **Aspect-Fit Presentation**:
   - Calculates target viewport with letterboxing/pillarboxing to preserve the 16:9 aspect ratio across any host window resolution.
   - Dynamically updates scissor rects and handles window minimize/restore and resize events gracefully.
3. **D3D12-to-Vulkan Zero-Copy GPU Interop** (Windows):
   - Xenos emulated renderer writes to a D3D12 resource.
   - Resource is shared via `ID3D12Device1::CreateSharedHandle`.
   - Imported into Vulkan via `VK_KHR_external_memory_win32` / `VkImportMemoryWin32HandleInfoKHR`.
   - Adapter LUID matching ensures the Vulkan physical device is the exact same hardware adapter as D3D12.
   - Synchronization via `Flush` + `WaitForIdle` or timeline semaphores ensures zero presentation tearing.
4. **Color Swizzling & Format Conversion**:
   - Handles Xbox 360 framebuffer formats such as `k_2_10_10_10` / `A2R10G10B10` with BGR swizzling in a native fullscreen blit shader.
5. **CPU Readback Fallback**:
   - Automatically falls back to staging buffers and CPU readback if external memory extensions are unavailable or fail at runtime.

---

## 3. Tier 2: API Translation & PSO Caching (UnleashedRecomp)

### Reference
- Source: `UnleashedRecomp/gpu/video.cpp`
- Key Features:
  - Shader translation via `XenosRecomp`
  - PSO caching & async compilation
  - Aspect ratio and anamorphic ultrawide patches

### Core Concepts
1. **D3D9/Xenos Call Interception**:
   - Intercepts state setup: `SetRenderState`, `SetTexture`, `SetSamplerState`, `SetVertexDeclaration`, `SetStreamSource`, `SetIndices`, `SetVertexShader`, `SetPixelShader`.
   - Intercepts draws: `DrawPrimitive`, `DrawIndexedPrimitive`, `DrawPrimitiveUP`.
2. **Shader Translation Pipeline**:
   - Xbox 360 microcode is parsed and converted into SPIR-V (or HLSL/DXIL) at runtime or pre-compiled via an offline database.
3. **PSO Cache & Asynchronous Compilation**:
   - Pipeline creation hitches are eliminated by compiling PSOs on background worker threads (`PipelineTaskType`).
   - Serializes compiled pipelines to disk (`SDLEventListenerForPSOCaching`), eliminating shader compilation stutter on subsequent runs.
4. **Dynamic Aspect Ratio & Viewport**:
   - Dynamically adjusts projection matrices and guest FOV to support ultrawide and non-standard aspect ratios natively without image stretching.

---

## 4. Tier 3: High-Level Scene Graph Reconstruction (Skate3Recomp)

### Reference
- Commit: `c613ffacc8a8f859be0c5ab256fd2207db37fbcd`
- Key Files:
  - `src/skate3_native_scene.cpp`
  - `src/skate3_native_render.cpp`
  - `src/skate3_native_debug_dialog.cpp`

### Core Concepts
1. **Scene Publishing & Interception**:
   - Hooks high-level engine functions that publish draw lists or render queues.
   - Builds an immutable snapshot (`std::shared_ptr<const FrameScene>`) per guest frame containing:
     - View and projection matrices (`kViewCamViewProj`, `kViewCameraFromView`).
     - Mesh descriptors (vertex buffers, index buffers, vertex layouts).
     - Material & texture parameters.
2. **Emulated Draw Suppression**:
   - Tells ReXGlue to skip rendering the emulated Xenos draw commands when the native scene is active:
     ```cpp
     REXCVAR_SET(native_render_suppress_emulated_draws, true);
     ```
   - Eliminates redundant GPU work and prevents conflicting framebuffer clears.
3. **Host Motion Smoothing (Decoupling Tick Rates)**:
   - Guest simulation tick rate (e.g. ~170–240 Hz or fixed 30/60 Hz) often does not match the display refresh rate (144 Hz, 240 Hz, VRR), causing visual judder when panning.
   - Samples guest camera at 1 kHz and linearly interpolates / slerps camera matrices and entity poses based on host clock timestamps.
   - Teleports and camera cuts are detected (via distance/angle thresholds) to snap immediately rather than interpolating.
4. **Front-to-Back Opaque Sorting**:
   - Games frequently sort draws by state/material rather than depth.
   - The native renderer sorts opaque objects front-to-back by bounding-box center distance from the camera, allowing early-Z rejection to drastically reduce pixel shader workload.
5. **Background Prewarm Workers**:
   - Static world meshes and mipmapped textures are decoded and uploaded to the GPU asynchronously on worker threads (`PrewarmEntry`).
   - Only dynamic/skinned payloads (e.g. characters, cloth) are decoded inline on the render thread.

---

## 5. Roadmap for Midnight Club: Los Angeles

1. **Tier 1 Native Presenter (Completed)**:
   - Run stably under `rexgpu-xenos` with Vulkan backend.
   - Stock-rate host frame pacing at `0x8241A0E4` (`grcDevice::Present`) with monotonic scheduling.
   - Keep experimental delta-time and 60 FPS patches disabled until gameplay benchmarks prove both simulation correctness and a performance win.
2. **Tier 2 D3D/Xenos Command Translation & Shaders (Active)**:
   - Validated FBO path by default; Fragment Shader Interlock (ROV) remains an opt-in experiment.
   - Zero readback stalls (`readback_resolve = "none"`).
   - Multi-threaded pipeline compilation (`vulkan_pipeline_creation_threads = 4`).
   - 330 RAGE microcode shaders dumped and cataloged into SPIR-V.
3. **Tier 3 Engine-Level Scene Graph RE (Next Phase)**:
   - Identify RAGE graphics subsystems in MCLA: `grcDevice`, `grcViewport`, `rmcDrawable`, `rmcMesh`.
   - Extract vertex/index buffers and submit directly to Vulkan command buffers.

### MCLA hybrid starting point

For the target XEX hash recorded in `AGENTS.md`, `sub_82427898` is a proven
direct `PM4_DRAW_INDX_2` builder. The project captures its raw `r3/r4/r5`
inputs into an immutable scene at Present while leaving the packet and
`rexgpu-xenos` behavior unchanged. `sub_82412990` is a rejected draw boundary;
it performs ring-buffer synchronization/wait behavior instead.

This is the safe bridge between Tier 2 and Tier 3: preserve raw command evidence
like Unleashed, publish frame-owned immutable state like Skate3, and retain the
Dante-style fallback principle. Do not enable draw suppression until the
corresponding native pass has complete resource/state coverage and image parity.

### Backend-final state tracing

For an incremental Vulkan migration, a default-off trace immediately before the
emulated backend's `IssueDraw` is a useful truth boundary. Capture raw Xenos
state and shader hashes there, then cluster draws offline by shader pair,
primitive, render targets, viewport/scissor, and program control. Exclude
per-object fetch/constant hashes from the cluster key so repeated passes remain
visible.

Use a command-stream swap counter for trace frame boundaries. Host vblank may
advance an emulator's general counter independently, and copy-only frames may
have no draw calls. Count only non-empty draw frames so short captures remain
deterministic across Windows and Linux. The trace must be disabled by default,
must not alter draw submission, and should use portable file APIs for Unicode
paths.

### Transient vertex uploads at the guest/native boundary

DrawPrimitiveUP-style engine helpers often return a guest allocation that the
caller fills after the helper has already emitted its command. Capture the
returned guest address at the proven post-assignment instruction, but defer the
copy until Present or another lifetime boundary after the caller has written
the data. Publish a single bounded byte slab with integer offsets in the
immutable scene. This keeps snapshots portable across Windows and Linux,
avoids dangling guest pointers, and prevents one heap allocation per draw.

Before building a native batch, require the engine byte formula to agree with
the backend fetch constant and shader layout. A repeated pass with invariant
pipeline, texture, constants, render targets, and 144-byte four-vertex uploads
is a batching candidate; it is not permission to reorder transparent/blended
draws. Concatenate in original order first, preserve fallback, and validate via
image comparison before suppressing emulated commands.

Build the host batch without Vulkan first. Decode `k8in32` by byte-swapping
every fetched dword, follow the shader's actual attribute offsets and result
swizzles, and reject non-finite float attributes. Keep the host vertex type
plain and platform-independent so the same code runs on Windows and Linux.

Resolve Xenos texture layouts and effective sampler state through the SDK that
will consume them. Shader fetch instructions can override fields in the raw
fetch constant, so native Vulkan descriptors must be derived from the resolved
pair rather than the constant alone. Keep guest physical ranges in the capture
contract, but do not read or upload them until their producer and coherence
boundary are proven. With GPU readback disabled, a stable CPU-side address is
not evidence that GPU-resolved contents are visible to the CPU.

For a CPU-authored texture, the safe diagnostic hash point is immediately
before the backend copies guest physical pages into its Vulkan upload buffer.
Track CPU invalidation and GPU-write provenance separately. Never insert a GPU
wait merely to fingerprint a candidate: if a range is GPU-authored, preserve
the emulated resource or design explicit interop instead of reading stale guest
RAM. Partial page uploads may repeat one full-range hash and should be
coalesced logically by invalidation/version, not counted as distinct textures.

Mirror the complete output-merger contract in an offscreen prototype: color
write masks, separate color/alpha blend factors and operations, alpha testing,
depth compare/write, stencil, target formats, MSAA, viewport, and scissor. Xbox
360 titles frequently use reversed depth (`greater`/`greater-equal`); assuming
Vulkan's common `less` default can yield an empty or inverted result while all
geometry and shader inputs are otherwise correct.

Independent triangle strips need explicit separation. Converting each
four-vertex strip to `0,1,2, 2,1,3` triangle-list indices preserves winding and
prevents accidental cross-draw triangles when payloads share one upload. Track
the source draw index and validate the candidate partition and vertex/index
count equations before allocating Vulkan resources. A CPU batch is still only
a compare boundary; it does not justify draw suppression.

---

## 6. Tier 2 Practical Implementation Learnings (FSI, Zero-Readback, and AOT Shader Pipeline)

These lessons apply to any Xbox 360 title ported via ReXGlue targeting modern Vulkan hardware:

### 6.1 Fragment Shader Interlock (ROV / FSI Mode)
- **Setting**: `render_target_path_vulkan = "fsi"` (requires `VK_EXT_fragment_shader_interlock` support, present on modern AMD RDNA, Intel Arc, and Nvidia GPUs).
- **Mechanism**: Replaces host framebuffers with a single unified Vulkan Storage Buffer (`VK_BUFFER_USAGE_STORAGE_BUFFER_BIT`) representing the 10 MB eDRAM. Pixel packing, depth/stencil testing, and color blending are executed via atomic fragment interlocks directly in the SPIR-V fragment shaders.
- **Benefits**:
  - Eliminates eDRAM tile copy passes (`PM4_DRAW_INDX_2(edram_mode=6)`).
  - Eliminates Vulkan render pass teardown and reconstruction when the game switches render targets.
  - Automatically handles all non-standard Xbox 360 pixel formats in software without driver fallback warnings.
  - Caches pipeline state objects into `<title_id>.fsi.vk.xpso`.

### 6.2 Elimination of Host Readback Stalls
- **Settings**: `readback_resolve = "none"`, `vulkan_readback_resolve = false`.
- **Mechanism**: In vanilla emulation, resolve commands can request GPU-to-CPU synchronization to read back rendered surfaces. Setting these cvars to `"none"`/`false` forces resolve passes to execute purely GPU-side or skip CPU staging, keeping the host graphics queue completely asynchronous.

### 6.3 Multi-Threaded Pipeline Compilation & Prewarming
- **Settings**: `vulkan_pipeline_creation_threads = 4`, `async_shader_compilation = true`.
- **Mechanism**: The Vulkan pipeline cache maintains a pool of worker threads (`"Vulkan Pipelines"`) that compile `VkPipeline` handles in parallel.
- **Prewarming Contract**: In ReXGlue's `VulkanPipelineCache::InitializeShaderStorage(cache_root, title_id, blocking = true)`:
  1. It reads all stored pipeline descriptions from `<title_id>.fsi.vk.xpso`.
  2. It reads guest shader microcode from `<title_id>.xsh`.
  3. It invokes `SpirvShaderTranslator` to translate any missing shaders in memory.
  4. It dispatches pipeline creation tasks to the thread pool and blocks until all stored pipelines are compiled before the main thread resumes.
  5. Subsequent gameplay runs have 100% of previously encountered pipelines pre-compiled in memory, eliminating runtime stutter.

### 6.4 Validated Runtime Lessons

- Async pipeline creation is only truly asynchronous if the frame-boundary path
  does not drain the queue or wait for every worker. When placeholder pipelines
  are supported, notify workers and allow the current frame to continue; retain
  the synchronous wait as the compatibility path when async compilation is off.
- Do not overwrite tuning cvars from a game integration layer. TOML and CLI
  overrides must remain authoritative so GPU behavior can be isolated with A/B
  tests without recompiling.
- Initialize performance CSV output only after configuration and CLI values have
  been resolved, and close it during normal runtime shutdown.
- A fully clipped resolve may be treated as a successful no-op only when every
  backend consumer explicitly accepts a zero extent. Otherwise preserve the
  failure so a malformed resolve is not silently hidden.
- Stage the runtime configuration beside the executable as a build dependency.
  A stale executable-local TOML can silently invalidate benchmark conclusions.

### 6.5 Shader Extraction and SPIR-V Translation Parity Patch
- **SDK Gap in v0.10.0**: While D3D12 implemented `translation.Dump()` when `dump_shaders` was set, the Vulkan backend (`src/graphics/vulkan/pipeline_cache.cpp`) lacked the equivalent call in `TranslateAnalyzedShader()`.
- **Remedy**: Apply `patches/rexglue-vulkan-shader-dump.patch` to invoke `translation.Dump(REXCVAR_GET(dump_shaders), ...)` in Vulkan's `TranslateAnalyzedShader()`. This outputs `.vk.bin.vert` and `.vk_fsi.bin.frag` binary files containing valid SPIR-V bytecode that can be validated with `spirv-val` and disassembled with `spirv-dis`.
