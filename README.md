# Midnight Club: Los Angeles Recomp

Early static-recompilation project for the Xbox 360 release of *Midnight Club:
Los Angeles*, built with ReXGlue, SDL3 and Vulkan. The host targets are Windows
x86-64 and Linux x86-64.

This repository does not include the game or any other proprietary files. Use
only a dump that you own; local game data belongs in `game/` and is ignored by
Git.

## Current status

- ReXGlue SDK pinned to `v0.10.0` (`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`),
  with reproducible POSIX shared-memory, Vulkan shader-dump, and Vulkan
  performance/stability patches in `patches/`.
- `default.xex` loads and passes ReXGlue analysis with reviewed function-entry
  hints in `config/default.toml`.
- Codegen emits 245 files and is deterministic on a second pass.
- Linux RelWithDebInfo compiles and links the host plus the Vulkan Xenos plugin.
- A host smoke test selects the AMD Radeon RX 7600 through RADV and creates both
  the initial and 1920x1080 Vulkan swapchains.
- The stock presentation path is stable at 30 FPS. A 25-second Linux Release
  smoke test produced 701 presents at 29.66 FPS, with a 33 ms median and 36 ms
  p95 frame interval; no empty-resolve/backend failure was logged.
- The complete XDVDFS tree has been extracted locally with the gitignored
  full-game extractor.
- Runtime registers 30,028 recompiled functions, presents 1280x720 frames and
  starts SDL audio at 48 kHz/6 channels.
- The runtime-reached indirect entries `0x822C9DD8` and `0x82554080`, their
  adjacent dispatch thunks at `0x822C9DC8` and `0x82554060`, and the tail-call
  target `0x822C9828` are now reviewed function hints in `config/default.toml`.
- Game data path resolution in `src/midnight_club_la_app.h` automatically discovers
  the owned `game/` root relative to current working directory or upward from the
  executable directory, supporting direct execution from the build tree or packages.
- A 90-second Linux smoke test presented frames continuously across multiple swapchain
  transitions with active shader compilation and 6-channel SDL audio, with no fatal
  function-dispatch or memory error.
- A `SIGSEGV` observed in `sub_8217BC28` under GDB was a normal GPU write-watch
  fault intercepted before ReXGlue's handler. Forced debugger exits had left
  `xenia_memory_*` arenas in `/dev/shm`; removing the confirmed orphaned arenas
  resolved the unrelated startup `SIGBUS` in `Memory::InitializeFunctionTable`.
- Experimental intro-skip, shadow-skip, 60 FPS, and delta-time hooks were
  removed after controlled tests showed severe regressions. Only the reviewed
  presenter hook at `0x8241A0E4` remains, providing telemetry and host pacing
  without changing guest simulation.
- Linux gameplay no longer scans `/proc/self/maps` on every GPU write-watch
  fault. The focused SDK patch raised the tested race path from roughly
  4–14 FPS to 18–30 FPS and GPU occupancy from about 36% to 58%. Gameplay is
  substantially faster but is not yet a constant 30 FPS; see the current
  investigation report for the remaining mixed guest/GPU-command bottleneck.
- A causal negative control now confirms CPU-side Xenos-to-Vulkan draw
  translation as the limiting boundary in the tested sequence: bypassing draw
  translation reduced `GPU Commands` CPU from 84.1% to 25.4% and restored an
  exact 30.00 FPS presentation rate. The bypass intentionally produces invalid
  output and is diagnostic only; see the
  [focused investigation report](docs/investigations/xenos-draw-translation-bottleneck-2026-09-13.md).

ReXGlue currently reports 20 `Unexpected float16_4 pack instruction` warnings
during code generation. Treat them as a known correctness risk until those PPC
instructions are identified and tested.

Analyze comparable presentation logs without ad-hoc parsing:

```sh
python scripts/analyze_present_log.py /path/to/run.log --warmup-seconds 5
```

The tool reports exact interval percentiles when per-present events exist and
falls back to the project's five-second NativeRenderer FPS windows otherwise.
The current controlled baseline and its limitations are recorded in
`docs/investigations/performance-baseline-2026-09-07.md`.

For CPU/GPU correlation on Linux, capture and summarize procfs/sysfs counters:

```sh
python scripts/profile_linux_runtime.py --duration 120 \
  --output /tmp/mcla-host.csv -- ./out/build/linux-amd64-release/midnight_club_la
python scripts/analyze_runtime_profile.py /tmp/mcla-host.csv \
  --warmup-seconds 25
```

The CSV includes process, hottest-thread, and tracked `GPU Commands` CPU,
page-fault rates, AMD GPU occupancy, VRAM, RSS, and thread identity. The current gameplay bottleneck
investigation and GDB guest-thread sampling procedure are documented in
`docs/investigations/gameplay-cpu-bottleneck-2026-09-12.md`.

For focused static analysis, install the pinned local Ghidra 12.0.4,
XEXLoaderWV 13.0.0, and portable JDK 21 toolchain, then import the owned XEX
and export only the functions under investigation:

```sh
python scripts/ghidra/bootstrap.py
python scripts/ghidra/analyze_xex.py \
  --address 0x82415DC8 --address 0x82415EE8 --address 0x8241A630
```

The downloads are SHA-256 verified. Tool binaries, Ghidra projects, and
XEX-derived exports stay in ignored `.tools/` and `.ghidra/` directories.
See `docs/reverse-engineering/ghidra.md` for Windows usage and the evidence
handling rules.

To build the diagnostic guest-hotspot wrappers described in that report:

```sh
cmake --preset linux-amd64-release -DMCLA_ENABLE_HOTSPOT_PROBE=ON
cmake --build --preset linux-amd64-release --parallel
```

The option defaults to `OFF`; do not use an instrumented binary for FPS
comparisons.

## Prerequisites

- Git
- CMake 3.25 or newer
- Ninja
- Clang 20 or newer
- A Vulkan-capable driver and GPU

## Repeated tasks with just

Optionally install [just](https://github.com/casey/just#installation). The root
`justfile` uses the host's Release preset and keeps CMake as the build system:

```sh
just --list
just configure
just build
just run
just profile /tmp/mcla-host.csv 60
just analyze-profile /tmp/mcla-host.csv 25
just analyze-present /path/to/run.log 25
just analyze-queue /path/to/run.log
just analyze-memory /path/to/run.log
```

`profile` is Linux-only; the build, extraction and analysis recipes also support
Windows. Override tools or presets with, for example,
`just python=python3 preset=linux-amd64-relwithdebinfo build`.
`build` refreshes the exact GPU plugin identified by the selected Ninja build,
including when an SDK-only change does not relink the executable. Configure
before the first build. `config-reset` restores the checked-in runtime settings
beside the executable after an experiment. Run it only after recording any
local settings you want to keep.

The project selects 16 pages for `shared_memory_access_invalidation_pages`.
The SDK default remains 64; restore 64 first when investigating visual
corruption, missing GPU-written data, or a scene-specific regression.

For write-watch diagnostics, set `physical_access_profile = true` and
`log_level = "info"` in the executable-local TOML before launching. The probe
defaults to off and requires a restart. It logs cumulative counters every
65,536 enable calls per alias; `analyze-memory` needs two snapshots per alias
and uses last minus first. These are callback counters, not exclusively CPU
faults. Diagnostic captures do not establish an uninstrumented FPS gain.

## SDK setup

Clone the pinned SDK with its submodules:

```sh
git clone --branch v0.10.0 --depth 1 --recurse-submodules --shallow-submodules \
  https://github.com/rexglue/rexglue-sdk.git thirdparty/rexglue-sdk
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-posix-shm-unlink.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-vulkan-shader-dump.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-vulkan-performance-stability.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-texture-cache-profiling.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-linux-write-watch-fastpath.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-gpu-register-logging-fastpath.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-vulkan-submission-diagnostics.patch
git -C thirdparty/rexglue-sdk apply --unidiff-zero \
  ../../patches/rexglue-vulkan-shared-memory-profiling.patch
git -C thirdparty/rexglue-sdk apply ../../patches/rexglue-physical-access-profiling.patch
git -C thirdparty/rexglue-sdk apply \
  ../../patches/rexglue-shared-memory-invalidation-granularity.patch
git -C thirdparty/rexglue-sdk apply \
  ../../patches/rexglue-vulkan-draw-bypass-diagnostic.patch
```

## Extract the game

From the repository root:

```sh
python scripts/extract_xex.py "/path/to/your/game.iso"
```

The dedicated command writes `game/default.xex`. Use `--list-xex` to inspect
other XEX files and `--help` for its XEX-only options.

Runtime requires the complete XDVDFS tree. If `default.xex` already exists,
extract the remaining files without replacing it:

```sh
python scripts/extract_game.py "/path/to/your/game.iso" --skip-existing
```

Extraction is confined to `game/`, preflights free space, writes files
atomically, and does not commit or redistribute the proprietary game data.
Both frontends share the dependency-free XDVDFS reader in `scripts/xdvdfs.py`.

## Configure, generate and build

Linux:

```sh
cmake --preset linux-amd64-relwithdebinfo
cmake --build --preset linux-amd64-relwithdebinfo \
  --target midnight_club_la_codegen --parallel
cmake --build --preset linux-amd64-relwithdebinfo \
  --target midnight_club_la --parallel
```

Windows:

```powershell
cmake --preset win-amd64-relwithdebinfo
cmake --build --preset win-amd64-relwithdebinfo `
  --target midnight_club_la_codegen --parallel
cmake --build --preset win-amd64-relwithdebinfo `
  --target midnight_club_la --parallel
```

The Linux executable and its runtime libraries are placed in
`out/build/linux-amd64-relwithdebinfo/`. Do not use ReXGlue's `--force` option
to bypass analysis failures; add reviewed hints to `config/default.toml`.
The checked-in runtime TOML is copied beside the executable on every link, so
both development and packaged builds use the same defaults.

On Linux, an unpatched ReXGlue hard exit or debugger kill may leave
`xenia_memory_*` arenas in `/dev/shm`. The project patch unlinks each POSIX
shared-memory object immediately after creation while retaining its open file
descriptor, so the kernel reclaims it on every process exit. If upgrading or
running an unpatched SDK produces `SIGBUS` while zeroing the function table,
stop all ReXGlue processes, inspect `df -h /dev/shm` and the exact matching
files, then remove only confirmed orphaned arenas.
