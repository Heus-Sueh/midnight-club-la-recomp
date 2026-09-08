# ReXGlue project workflow

This project starts from ReXGlue v0.10.0's manifest-first flow. Re-check the pinned SDK's CLI help before adopting commands from another port because the API is still evolving.

## Input inventory

Before scaffolding, record without committing proprietary data:

- game title and Xbox 360 edition;
- SHA-256 and size of `default.xex`;
- media/release identity and region;
- title update identity, or explicitly `vanilla`;
- every guest DLL/XEX loaded by the game;
- a shallow directory inventory sufficient to reproduce the manifest.

Store the owned dump under gitignored `game/`. Keep public CI free of retail data. A private artifact store is not automatically authorized; ask before uploading anything.

For a standard Xbox 360 XDVDFS ISO, extract only the entrypoint with the repository's dependency-free helper:

```text
python scripts/extract_xex.py /path/to/owned-game.iso
```

It writes `game/default.xex`, reports its SHA-256, and refuses to overwrite an existing file unless `--force` is explicit. Use `--list-xex` to inspect XEX paths or `--member path/to/other.xex -o game/other.xex` for another executable. This is enough for initial XEX inventory and codegen, but runtime testing will eventually need the rest of the legally dumped game tree.

Extract the complete tree with the separate full-game frontend:

```text
python scripts/extract_game.py /path/to/owned-game.iso --skip-existing
```

Both commands share the dependency-free `scripts/xdvdfs.py` parser. Keep the frontends separate so XEX inventory never accidentally expands into a multi-gigabyte full extraction.

## Initialize

With the pinned `rexglue` CLI and `game/default.xex` present:

```text
rexglue init --project-name midnight_club_la --project-root . --xex-path game/default.xex --game-root game --scan-dll
```

Inspect the manifest's scanned modules and guest paths. Remove false positives; add dynamically loaded modules when runtime evidence identifies them.

`rexglue init --force` can overwrite the root `CMakeLists.txt`, `CMakePresets.json`, and manifest. Use it only when deliberately refreshing SDK-managed scaffolding, after preserving project-owned changes and with a clean, reviewable diff.

## Configure and generate

The intended local SDK path is `thirdparty/rexglue-sdk`; alternatively consume an installed, exactly pinned SDK package. Presets must carry the Vulkan-only settings described by `$sdl-vulkan-portability`.

Initial bootstrap is two-stage because the first configure cannot include a `generated/.../sources.cmake` that does not exist yet:

```text
cmake --preset linux-amd64-relwithdebinfo
cmake --build --preset linux-amd64-relwithdebinfo --target midnight_club_la_codegen --parallel
cmake --preset linux-amd64-relwithdebinfo
cmake --build --preset linux-amd64-relwithdebinfo --parallel
```

Use the analogous Windows preset on Windows. Confirm the exact generated target name from the pinned SDK's `generated/rexglue.cmake` rather than guessing after a migration.

For direct diagnosis, the CLI shape is:

```text
rexglue codegen midnight_club_la_manifest.toml --log-level=debug --log-file=codegen.log
```

Use `--ignore-stamp` only when intentionally invalidating the codegen stamp. The global `--force` flag permits output despite analysis errors; it is not a routine regeneration flag and requires documented justification.

## Migrate

Read the pinned release notes and template diff first. ReXGlue v0.10.0 has no `migrate` subcommand; refresh generated glue through its supported codegen/init flow, and use forced init only on a clean branch after preserving project-owned files. Then review:

- manifest schema and SDK version stamp;
- generated CMake integration;
- app hooks and entry point compatibility;
- backend options and runtime plugin staging;
- codegen output changes and diagnostics.

Do not combine an SDK migration with gameplay hooks or unrelated refactors.

## Phase gates

Advance in observable increments:

1. deterministic codegen with no unexplained unresolved targets;
2. linkable host and staged runtime/plugin;
3. runtime and VFS initialization;
4. entrypoint reached;
5. SDL window plus Vulkan device and swapchain;
6. first stable presented frame;
7. input, audio, saves, and asset streaming;
8. menus and one repeatable gameplay path;
9. packaging and clean-machine smoke tests.

Native rendering, enhancements, installers, and mod support come after a stable baseline unless they directly unblock one of these gates.
