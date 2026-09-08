# Manifest and ownership boundaries

## Project-owned versus generated

Expected ownership after `rexglue init`:

| Path | Ownership | Rule |
|---|---|---|
| `src/main.cpp` | Project-owned after first init | Keep minimal; migration should preserve it. |
| `src/midnight_club_la_app.h` | Project-owned | Put ReXApp lifecycle customization here or split helpers into normal `src/` files. |
| `midnight_club_la_manifest.toml` | Project configuration | Review every address and module; `init --force` may overwrite it. |
| Included config TOML files | Project-owned RE knowledge | Prefer these for functions, switch tables, CRT mappings, and hooks. |
| `CMakeLists.txt`, `CMakePresets.json` | Project build configuration | `init --force` may overwrite; preserve Vulkan-only decisions. |
| `generated/rexglue.cmake` | CLI-generated | Never hand-edit. |
| `generated/<module>/` | Codegen-generated | Never hand-edit or commit unless repository policy deliberately vendors codegen. |
| `game/`, update packages, DLC | User-owned copyrighted input | Gitignore; never distribute. |

## Manifest shape

The v0.10.0 manifest has `[project]`, `[entrypoint]`, and optional `[[modules]]`. Each binary may load one or more included TOML configuration files. Keep large address maps in focused includes rather than turning the manifest into an investigation diary.

Use the exact schema accepted by the pinned SDK. In v0.10.0 configuration files use `[functions]`, `[[switch_tables]]`, `[rexcrt]`, and `[[midasm_hook]]`; do not copy the stale `[[mid_asm_hooks]]` spelling from third-party notes.

## Address-bearing data

Every config file with guest addresses must name the compatible executable hash or revision in a nearby comment or companion note. When supporting multiple revisions, use separate configs/manifests and validate the selected hash before launch. Never apply a title-update address map to vanilla code.

Map guest DLL paths exactly as the game requests them. ReXGlue modules are separate generated targets and must be colocated with the host executable as required by the generated CMake integration.

## Generated-code exception

If no supported manifest or app hook can express a required correction:

1. prove why a higher-level fix is insufficient;
2. create a deterministic script or patch with exact preimage checks;
3. fail closed when the generated output differs;
4. run it after every codegen;
5. document the SDK version, executable hash, root cause, and removal condition.

Prefer contributing a general correction upstream when the fault belongs to ReXGlue.

## CVar lifecycle and plugin registration order

ReXGlue has a strict initialization order that affects CVar manipulation:

1. **Config Load (`LoadConfig`)**: `rex_app` searches for `<app_name>.toml` in `exe_dir` and parses it into the CVar registry. Any key in TOML that belongs to an unregistered CVar is stored in `GetPendingValuesStorage()` as deferred.
2. **`OnPreSetup(config)`**: Runs before dynamic plugins are loaded.
   - **Critical Trap**: Calling `rex::cvar::SetFlagByName()` here for flags defined inside `rexgpu-xenos` (such as `render_target_path_vulkan`, `dump_shaders`, `readback_resolve`, `vulkan_pipeline_creation_threads`) will return `ApplyResult::kRejected` because `SetFlagByName` does not defer unregistered keys!
   - Plugin-owned flags configured in `<app_name>.toml` DO apply properly because of the pending storage mechanism.
3. **Plugin Loading (`LoadGpuPlugin`)**: Dynamically loads `librexgpu-xenos.so` via `dlopen`. Static initializers register the plugin's CVars and flush pending values from `GetPendingValuesStorage()`.
4. **`OnPostSetup()` / `Initialize()`**: At this point, the GPU plugin is loaded. Programmatic `SetFlagByName()` calls for plugin CVars will now succeed.

Always place GPU plugin CVars directly in `<app_name>.toml` or defer programmatic overrides to `OnPostSetup()`.

