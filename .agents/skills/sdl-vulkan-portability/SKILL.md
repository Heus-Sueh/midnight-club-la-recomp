---
name: sdl-vulkan-portability
description: Implement or review Windows and Linux host integration for a ReXGlue port that deliberately uses SDL3 for windowing, input, and audio and Vulkan as its only graphics API. Use for CMake presets, runtime backend selection, shared-library staging, CI, packaging, or cross-platform regressions; do not use for guest PowerPC analysis.
---

# SDL3 and Vulkan portability

Maintain one portable host architecture rather than parallel Windows and Linux feature implementations.

## Required architecture

- Target Windows x86_64 and Linux x86_64 first.
- Use CMake 3.25+, Ninja, C++23, and LLVM Clang 20 where practical (ReXGlue requires Clang 18+).
- Use the SDK's SDL3 window/event loop, SDL input backend, and SDL audio backend. Add raw Win32, XInput, X11, or Wayland code only behind a narrow platform adapter with a demonstrated need.
- Compile Vulkan on both platforms with `REXGLUE_USE_VULKAN=ON` and `REXGLUE_USE_D3D12=OFF`. This is essential on Windows, where the SDK defaults to D3D12.
- Build and stage the `xenos` GPU plugin with `rexglue_setup_target(<target> GPU_PLUGINS xenos)`, and select `config.gpu_plugin = "xenos"`. A Vulkan build without the plugin is headless.
- Treat the initial renderer as the ReXGlue Xenos emulation plugin backed by Vulkan. A game-specific native renderer is a separate, later project with shader and draw-path reverse engineering.

Read [build-and-runtime.md](references/build-and-runtime.md) when editing presets, CMake, app startup, or package layout. Read [cross-platform-verification.md](references/cross-platform-verification.md) for CI and release acceptance. Read [native-renderer-architecture.md](references/native-renderer-architecture.md) for native renderer patterns (Skate3, Dante's Inferno, Unleashed), presentation pipelines, and GPU interop.

Use `$recomp-performance-debugging` when Vulkan initializes but the remaining
symptom is low FPS, stutter, a PM4/backend failure, or uncertain frame pacing.

## Review rules

- Keep common behavior in common source. Use `#if` only for unavoidable OS APIs and keep it local.
- Do not claim Vulkan-only from a Linux test. Inspect the Windows CMake cache or configure summary to prove D3D12 is disabled.
- Do not claim SDL input from SDL window creation alone. Verify `input_backend=sdl`, controller discovery, hotplug, rumble, and keyboard/mouse separately.
- Package the executable, matching ReXGlue runtime library, `rexgpu-xenos` plugin, and required licenses. Verify loader paths from the packaged directory, not only the build tree.
- Test windowed/fullscreen transitions, resize/DPI, focus, audio device changes, and at least one Xbox-compatible plus one non-Xbox SDL gamepad on both operating systems when available.
