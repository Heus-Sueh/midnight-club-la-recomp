---
name: xbox360-recomp-re
description: Investigate Xbox 360 PowerPC/XEX behavior for a ReXGlue port and turn binary evidence into function hints, switch tables, hooks, CRT mappings, or focused SDK bug reports. Use for codegen gaps, crashes, hangs, bad guest state, and revision-specific patches; do not use for ordinary CMake or packaging work.
---

# Xbox 360 recompilation reverse engineering

Work from evidence tied to one exact executable revision. The goal is the smallest reproducible correction at the right layer.

For a multi-stage subsystem map, structured knowledge base, target-priority
queue, or investigation journal, use `$agentic-reverse-engineering` to
coordinate this specialized workflow.

## Investigation loop

1. Capture the failure boundary: phase, platform, build type, command line, last log lines, exception or signal, guest PC/LR, and whether the Vulkan device was created.
2. Hash the relevant XEX/XEXP and state whether codegen used vanilla or updated bytes.
3. Reproduce with RelWithDebInfo and trace logging. Change one variable at a time.
4. Map the guest address to generated code and compare the surrounding PPC control flow with the recompiled function. Check missing indirect targets, wrong function extents, jump tables, imports, and unsupported or mistranslated instructions before writing a hook.
5. Choose the narrowest durable remedy:
   - manifest hint for analysis discovery;
   - named function or complete `rexcrt` group for a recognized routine;
   - `[[midasm_hook]]` for a proven game-specific behavior;
   - SDK fix plus focused PPC regression test for a general instruction/codegen defect.
6. Regenerate from a clean codegen boundary, reconfigure, rebuild, and verify both Windows and Linux when the affected layer is shared.
7. Add an investigation note containing evidence, addresses, hashes, rejected hypotheses, and the validation result.

Read [investigation-playbook.md](references/investigation-playbook.md) for the evidence checklist and remedy hierarchy. Read [revision-and-hook-rules.md](references/revision-and-hook-rules.md) before adding any address, mid-assembly hook, generated patch, or title-update variant.

For FPS regressions, timing patches, profiler captures, debugger-only signals,
or ambiguity between guest and GPU/runtime behavior, use
`$recomp-performance-debugging` before deciding on an address-bearing remedy.

## Guardrails

- Never invent an address, function boundary, register contract, or struct layout.
- Do not convert a crash into a no-op merely to advance boot unless evidence shows the skipped behavior is optional; label temporary bypasses and keep them out of release builds by default.
- A hook must declare why that program point is stable, which registers or memory it reads/writes, and what original control flow continues.
- Guest memory is big-endian and generated code may rely on ReXGlue access helpers. Do not use unreviewed host pointer casts for guest data.
- If the defect is a PPC semantic error shared across games, fix the SDK and add a focused test instead of accumulating a game-specific hook.
