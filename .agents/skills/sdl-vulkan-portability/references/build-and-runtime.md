# SDL3/Vulkan build and runtime

## CMake requirements

Every Windows and Linux configure preset must set:

```json
"REXGLUE_USE_VULKAN": "ON",
"REXGLUE_USE_D3D12": "OFF"
```

Keep `REXSDK_DIR` or `CMAKE_PREFIX_PATH` explicit and pinned. Prefer Clang 20 for matching CI behavior; the SDK floor is Clang 18, CMake 3.25, Ninja, and C++23.

The application target must request plugin staging:

```cmake
rexglue_setup_target(midnight_club_la GPU_PLUGINS xenos)
```

The app's `OnPreSetup` should select `config.gpu_plugin = "xenos"` and the SDL input backend. The SDK already supplies the SDL3 window/event entry point and SDL audio factory; do not create a second SDL main loop.

On configure, inspect the SDK summary and cache. Acceptance requires `D3D12=OFF Vulkan=ON` on Windows and Linux. Building Vulkan headers into the host is not enough: `rexgpu-xenos` must also contain its Vulkan backend and be loadable at runtime.

## Runtime boundary

Keep these concepts separate:

- SDL3 owns the host window, event loop, gamepads, keyboard/mouse, and audio device integration.
- `rexgpu-xenos` emulates the Xbox 360 Xenos command stream.
- Vulkan is the host graphics API used by that plugin and the ReXGlue presentation layer.
- The recompiled guest remains PowerPC-derived C++ and still issues Xbox 360 GPU commands.

This architecture satisfies the first cross-platform renderer milestone. A true native renderer replaces the game's Xenos-facing rendering path and requires game-specific shader/material/draw reconstruction.

## Platform notes

Windows:

- explicitly disable D3D12 because it is enabled by default in ReXGlue v0.10.0;
- stage the matching `rexruntime.dll`, SDL/runtime dependencies, and `rexgpu-xenos.dll` beside the executable;
- test outside a developer shell so missing DLLs are visible.

Linux:

- require a working Vulkan loader and driver plus the SDK's X11/Wayland/GTK build dependencies;
- use `$ORIGIN`-relative RPATH and stage matching `.so` files with the executable/package;
- test at least one X11 and one Wayland session when available, but do not block an early boot milestone on unavailable hardware.

Both:

- log selected SDL video/audio/input state, GPU plugin, Vulkan physical device, driver, queue selection, surface, swapchain format, and present mode;
- surface plugin/backend load failures as fatal actionable errors rather than silently running headless.
