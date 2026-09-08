# Cross-platform verification

## CI matrix

Start with two release-producing jobs:

| Host | Architecture | Compiler | Graphics |
|---|---|---|---|
| Windows | x86_64 | LLVM Clang 20 | Vulkan only |
| Linux | x86_64 | LLVM Clang 20 | Vulkan only |

Add Debug or RelWithDebInfo compile coverage when build time permits. Keep proprietary game inputs outside public CI. Public CI can still validate skills, formatting, scripts, SDK-facing host code, and any tests that do not require retail data. A private full-build workflow requires explicit authorization and secret/data handling design.

## Static acceptance

- CMake configure succeeds from a clean tree.
- Configure summary/cache says Vulkan ON and D3D12 OFF.
- SDL3 is linked through the pinned SDK rather than a second incompatible copy.
- Target requests `GPU_PLUGINS xenos`.
- Compiler is supported Clang and the build is 64-bit.
- No proprietary input or generated retail-derived source enters the artifact unintentionally.

## Runtime acceptance

From the packaged directory on each OS:

1. executable finds the matching ReXGlue runtime and Xenos GPU plugin;
2. owned game-data path is resolved without assuming the current directory;
3. SDL window opens and reports the expected drawable size/DPI;
4. Vulkan instance, physical device, logical device, surface, and swapchain initialize;
5. at least one stable guest frame presents;
6. resize, focus loss/regain, fullscreen transition, and clean shutdown work;
7. SDL controller input, hotplug, and rumble work;
8. keyboard/mouse fallback and SDL audio output work;
9. logs contain no new validation, device-lost, loader, or missing-symbol errors.

## Packaging acceptance

Test on a clean VM or machine without the build tree on `PATH`. Archive only redistributable host binaries, configs, notices, and empty game-data guidance. Do not package the user's XEX, title updates, DLC, extracted assets, generated code derived from retail binaries unless distribution has been legally reviewed and explicitly approved.
