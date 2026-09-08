# Investigation playbook

## Capture first

Record:

- host OS, CPU/GPU, driver, preset, commit, SDK pin, and build type;
- exact command line and relevant config;
- XEX/XEXP SHA-256 and whether a title update was baked or applied;
- last successful phase and first failing event;
- complete logs from process start through failure;
- exception/signal, host stack, and guest PC/LR/CTR/CR when available;
- minimal reliable reproduction and whether it reproduces on the other host OS.

Do not begin with broad patches. Establish whether the problem occurs during codegen, host startup, module loading, guest execution, GPU command processing, presentation, input, audio, or filesystem access.

## Common codegen checks

- unresolved direct or indirect calls;
- a `bctr`/`bcctr` that needs a switch-table or call-target hint;
- overlapping or truncated function extents;
- executable data mistaken for code, or code mistaken for data;
- guest DLL omitted from the manifest;
- missing import/export mapping;
- an incomplete `rexcrt` replacement group;
- a decoded instruction whose emitted C++ does not preserve PowerPC semantics;
- stale output after changing the CLI or SDK code generator.

Search generated sources by guest address and inspect the neighboring emitted labels and register operations. Compare against the original PPC, not against another game's generated output.

## Remedy hierarchy

1. Correct the game dump/revision or runtime path.
2. Add a manifest/module/include entry.
3. Add function, boundary, indirect-target, or switch-table evidence.
4. Map a complete known CRT group when signatures prove it.
5. Add a game-specific hook with a documented contract.
6. Fix a general SDK issue and add focused PPC regression coverage.
7. Use a deterministic generated-code patch only as a temporary last resort.

## Validation

A fix should demonstrate:

- codegen completes with understood diagnostics;
- the original reproduction no longer fails;
- at least one adjacent path still works;
- no new error appears in logs;
- shared runtime or codegen fixes pass the relevant SDK tests;
- cross-platform behavior is checked when the change is not OS-specific.

Preserve before/after evidence in `docs/investigations/` once that directory exists. Keep retail bytes, decompiler databases, and copyrighted disassembly out of the public repository.

## RAGE Engine Graphics & Presentation Patterns

When reverse engineering titles using Rockstar Advanced Game Engine (RAGE), such as Midnight Club: Los Angeles:

1. **Presentation Hook Boundary (`grcDevice::Present`)**:
   - The presentation wrapper is typically found in a subsystem function like `sub_82419CB8`.
   - The exact boundary before the host display swap is the `__imp__VdSwap` call at `0x8241A0E4`.
   - Hooking this address via a `[[midasm_hook]]` provides a clean callback hook to synchronize guest frame delivery with host display refresh without perturbing guest registers.
2. **VSync Divisor & 60 FPS Unclamping**:
   - RAGE games often enforce a 30 FPS ceiling by writing a divisor (e.g., `0x02` for 60Hz/2 = 30 FPS) to an internal interval variable in guest memory.
   - For MCLA, this is at virtual address `0x82419AA3`.
   - Patching this byte to `0x01` in guest memory during `OnPostLoadXex` unclamps the engine simulation to 60 FPS without desynchronizing physics when coupled with host frame pacing.
3. **Monotonic Frame Pacing Pattern**:
   - Never use relative sleep intervals (`sleep_for(1/fps)`), as scheduler quantization causes frame jitter to accumulate.
   - Use absolute scheduling: `next_target += interval`.
   - Use coarse sleep down to 1.5–2.0 ms before target, then a tight spin-yield loop with CPU pause (`__builtin_ia32_pause()`) for microsecond-accurate presentation.
4. **Benign 0x0 Empty Resolves in RAGE**:
   - Logs may report `[error] [gpu] Resolve region is empty` and `PM4_DRAW_INDX_2(3, 8, 2): Failed in backend (edram_mode=6)` during splash screens or video playback.
   - In RAGE, this occurs because video decode surfaces issue dummy resolve rectangles before geometry rendering starts; it is non-fatal and resolves once real scene rendering begins.

