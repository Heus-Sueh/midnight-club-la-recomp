---
name: rexglue-project
description: Scaffold, upgrade, configure, generate, diagnose, and maintain an Xbox 360 static recompilation built with the ReXGlue SDK. Use for project layout, manifests, SDK pinning, codegen, guest modules, missing indirect function entries, or ownership boundaries; do not use for broad binary reverse engineering or platform-specific SDL/Vulkan failures.
---

# ReXGlue project

Keep the project reproducible from a legally dumped Xbox 360 game tree without committing retail executables or assets.

## Workflow

1. Confirm the exact game, platform, executable revision, and title-update state. This repository assumes **Midnight Club: Los Angeles for Xbox 360**, not Midnight Club 3.
2. Pin an exact ReXGlue release or commit. Never silently float the SDK while investigating game behavior.
3. Inventory `default.xex`, DLLs, and update files before initialization. With v0.10.0, use `--scan-dll` when the game ships guest DLLs, then verify every generated module entry rather than trusting the scan blindly.
4. Run `rexglue init` only after the owned dump exists. Treat `--force` as an overwrite operation: inspect the diff immediately.
5. Keep codegen knowledge in the manifest and its included TOML files. Prefer named functions, switch-table hints, `rexcrt` mappings, and `[[midasm_hook]]` entries over edits to generated C++.
6. Bootstrap codegen, reconfigure CMake so `sources.cmake` is loaded, then build. Later incremental builds may invoke codegen automatically.
7. Record the exact XEX digest and title update used for every address-bearing change.
8. When runtime reaches an unregistered guest function, prove the callsite and source of the pointer before adding a function hint. Prefer recovering a complete callback or initializer table over discovering its entries one crash at a time.

Read [workflow.md](references/workflow.md) when initializing, migrating, generating, or building. Read [manifest-and-ownership.md](references/manifest-and-ownership.md) before changing a manifest, adding a module, running `init --force`, or touching generated files.

Read [runtime-function-discovery.md](references/runtime-function-discovery.md) when launch fails on `Call to invalid or unregistered function`, or when a suspected Vulkan failure occurs after the device and swapchain have already initialized.

## Invariants

- Never add game dumps, XEX/XEXP files, DLC, keys, extracted copyrighted assets, or generated recompilation output to commits or public CI artifacts.
- Do not bypass encryption, access controls, or ownership checks. Ask the user for their own lawful dump when inputs are absent.
- Do not edit `generated/rexglue.cmake`; regenerate it with the pinned CLI. Do not hand-edit codegen output. If an unavoidable generated-code workaround is proven, encode it as a deterministic, revision-checked patch and document why.
- Keep vanilla and title-update configurations distinct. Addresses and hashes from one revision are not evidence for another.
- Preserve project-owned files such as `src/*_app.h`; inspect before any migration or forced initialization.
- A successful compile is not proof of a correct recompilation. Require codegen diagnostics, launch logs, and the current phase's runtime check.
