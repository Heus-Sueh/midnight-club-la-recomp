# AGENTS.md — Midnight Club: Los Angeles recompilation

## Project identity

This repository is for a native static recompilation of **Midnight Club: Los Angeles, Xbox 360**, using the ReXGlue SDK. The original request called it “Midnight Club 3 Los Angeles”; treat that as a naming mix-up. Midnight Club 3 is a different game and is not an Xbox 360 ReXGlue target. Stop and reconfirm before changing the target title or platform.

The project ships no retail game data. Users must supply files from their own legally obtained Xbox 360 copy. Never commit, upload, log, or distribute XEX/XEXP files, title updates, DLC, keys, extracted assets, decompiler databases, or other copyrighted game content.

All tracked project content must be written in English, including documentation,
skills, code comments, configuration comments, diagnostics, test names, and
commit messages. Upstream reference snapshots may retain their original text.

## Non-negotiable architecture

- Hosts: Windows x86_64 and Linux x86_64.
- Build: CMake 3.25+, Ninja, C++23, LLVM Clang 20 preferred (Clang 18 minimum).
- Host platform layer: SDL3 for windowing/events, input, and audio.
- Graphics API: Vulkan only on both hosts.
- GPU milestone: Project-owned Native Renderer (`src/native_renderer/`) with Vulkan presentation pipeline, microsecond-accurate host pacing, 1080p display scaling, and RAGE engine draw/swap interception at `sub_82419CB8` (`0x8241A0E4`), with `rexgpu-xenos` as command processor fallback.
- SDK baseline: pin exact ReXGlue v0.10.0 initially; upgrade only in an isolated, reviewed migration.
- No D3D12 fallback. Every Windows preset must explicitly set `REXGLUE_USE_D3D12=OFF` and `REXGLUE_USE_VULKAN=ON`.

The project is advancing along the Native Renderer Roadmap (Tier 1 Native Presenter & Swap Interop, moving towards Tier 2/3 shader and draw-command interception), decoupling host presentation pacing from guest simulation ticks to eliminate display judder and 30 FPS clamping.

## Skill routing

Project skills live under `.agents/skills/` and are automatically discoverable.

- Use `$agentic-reverse-engineering` for multi-stage subsystem discovery,
  evidence-driven investigation planning, focused Ghidra exports, structured RE
  knowledge, target prioritization, validation ladders, and investigation journals.
- Use `$rexglue-project` for scaffold/init/SDK upgrades, manifests, SDK pinning, modules, codegen, generated-file policy, and build-phase planning.
- Use `$xbox360-recomp-re` for unresolved calls, function discovery, switch tables, hooks, CRT mappings, guest crashes/hangs, title-update address maps, and possible PPC/codegen defects.
- Use `$sdl-vulkan-portability` for CMake presets, SDL3, Vulkan-only enforcement, GPU plugin staging, Windows/Linux CI, runtime libraries, and packaging.
- Use `$recomp-performance-debugging` for FPS/stutter regressions, repeatable benchmarks, Tracy/counter captures, hangs, crashes, debugger signals, and determining whether a fault belongs to guest code, ReXGlue, Vulkan, SDL, or host IO.
- When a task crosses boundaries, use the smallest relevant set. Use
  `$agentic-reverse-engineering` to coordinate an investigation spanning several
  subsystem boundaries, then load only the specialized skills needed by the
  current evidence. For example, a Windows-only black screen needs
  `$sdl-vulkan-portability` first; only invoke `$xbox360-recomp-re` if evidence
  moves the failure into guest GPU behavior.
- Record repeatable reverse-engineering, optimization, profiling, and debugging findings in the relevant skill reference. Add or extend a deterministic tool when the same parsing or validation logic would otherwise be recreated manually. Do not promote a one-off observation until its executable revision, configuration, scene, and validation are recorded.

## Intended layout

The ReXGlue CLI will create part of this tree after an owned `game/default.xex` is available:

```text
.
├── AGENTS.md
├── .agents/skills/
├── CMakeLists.txt
├── CMakePresets.json
├── midnight_club_la_manifest.toml
├── config/                       # revision-specific codegen knowledge
├── docs/investigations/          # evidence and reproducible findings
├── docs/reverse-engineering/     # public workflows, never proprietary exports
├── game/                         # gitignored user-owned dump
├── generated/                    # gitignored codegen output
├── patches/                      # focused, reproducible SDK patches
├── scripts/ghidra/               # pinned headless RE toolchain and focused exports
├── scripts/extract_xex.py        # dependency-free XDVDFS XEX extractor
├── src/
│   ├── main.cpp
│   └── midnight_club_la_app.h
└── thirdparty/rexglue-sdk/        # exact pinned SDK or submodule/package
```

Do not create fake XEX-derived config or placeholder guest addresses. Paths that do not exist yet are phase targets, not permission to fabricate their contents.

## Ownership and edit boundaries

- `src/midnight_club_la_app.h` and other normal `src/` helpers are project-owned customization points.
- `midnight_club_la_manifest.toml`, its included TOML configs, `CMakeLists.txt`, and presets are project configuration, but `rexglue init --force` can overwrite several of them. Review every forced-init diff.
- `generated/rexglue.cmake` is CLI-generated and must not be edited.
- `generated/<module>/` is codegen output and must not be hand-edited. Prefer manifest knowledge or app hooks. A last-resort generated patch must be deterministic, preimage-checked, revision-bound, and documented.
- SDK modifications belong in a focused upstreamable patch with tests. Do not casually fork SDK behavior inside game code.

## Initial execution plan

1. Inventory the user's legal Xbox 360 dump; record `default.xex` SHA-256, size, region/release, title-update state, and guest modules without committing the files.
2. Pin and build/install ReXGlue v0.10.0, then inspect `rexglue --help` from that exact binary.
3. Initialize `midnight_club_la` with the v0.10.0 `--scan-dll` option; review the generated manifest and module guest paths.
4. Add Windows/Linux presets with Vulkan ON, D3D12 OFF, and a pinned SDK path.
5. Configure, run the first codegen target, reconfigure to load generated sources, and build RelWithDebInfo.
6. Stage `rexgpu-xenos` with `rexglue_setup_target(midnight_club_la GPU_PLUGINS xenos)`; select `config.gpu_plugin = "xenos"` and SDL input in `OnPreSetup`.
7. Advance through deterministic gates: codegen, link, runtime/VFS, entrypoint, SDL window, Vulkan device/swapchain, first frame, input/audio, menus, gameplay, saves, packaging.
8. Support title updates only as explicit hash-checked variants. Never reuse vanilla addresses without proof.

## Definition of done for changes

- Prefer the root `justfile` for repeated build, plugin staging, extraction and
  capture/analysis tasks. Keep recipes thin wrappers over the existing scripts
  and CMake presets; retain Windows/Linux support and document host-only tasks.
- State which phase gate the change advances.
- Include commands run and concise observable evidence.
- Build or statically validate both Windows and Linux paths for shared changes; explain unavailable runtime coverage.
- Confirm Vulkan ON/D3D12 OFF rather than assuming platform defaults.
- For address-bearing changes, include the module and compatible executable hash/revision.
- Keep Ghidra installations, projects, databases, bulk disassembly, and
  decompiler exports under ignored `.tools/` and `.ghidra/`; commit only concise
  findings and original automation scripts.
- For hooks, document register/memory contracts and preserved control flow.
- Keep logs free of user paths, keys, and proprietary byte dumps before sharing.

## Reference baseline

These sources informed the project rules; verify current upstream before an SDK migration:

- ReXGlue SDK v0.10.0 (`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`): https://github.com/rexglue/rexglue-sdk
- Skate3Recomp (`f6e0ae87fdfecbadb5c1e36c55d66a744187a3cd`): https://github.com/mchughalex/skate3recomp
- NocturneRecomp (`5390d5ec91d4b0d0c87a6db35ea351343d04cd91`): https://github.com/birabittoh/NocturneRecomp
- hells-gate-recomp (`1867978834b58a0a1060df0fd919b6ac0890e23d`): https://github.com/florinp93/hells-gate-recomp
- UnleashedRecomp: https://github.com/hedge-dev/UnleashedRecomp

Transfer architecture and workflow patterns, not game addresses, SDK patches, or assumptions. ReXGlue is early software with breaking changes; the pinned local source and CLI are authoritative for this repository.
