---
name: agentic-reverse-engineering
description: Plan and conduct incremental, evidence-driven reverse engineering for a static recompilation, including investigation scoping, Ghidra queries, structured knowledge capture, target prioritization, validation, and native subsystem replacement. Use for multi-stage subsystem discovery or building reusable RE knowledge; use the narrower Xbox 360, performance, or portability skills for isolated implementation tasks.
---

# Agentic reverse engineering

Turn each investigation into verified, revision-bound knowledge that makes the
next investigation cheaper. Do not optimize for pseudocode volume or attempt a
whole subsystem rewrite from weak evidence.

## Core loop

1. Define one observable target: a function, structure, call path, subsystem
   boundary, GPU operation, runtime behavior, or regression.
2. State a falsifiable hypothesis and the exact executable/module revision.
3. Collect the smallest relevant static and runtime context.
4. Instrument before replacing behavior. Preserve an existing fallback for
   operations that are not yet understood.
5. Implement the smallest change that can answer the question.
6. Validate at the level actually reached, then attempt to invalidate the
   conclusion with a negative control or competing explanation.
7. Record evidence, rejected hypotheses, uncertainty, and the next target.

Read [knowledge-system.md](references/knowledge-system.md) when exporting from
Ghidra, designing `re/` data, querying context, or building analysis tools.
Read [target-selection-and-migration.md](references/target-selection-and-migration.md)
when choosing what to investigate next or replacing emulated behavior with a
native implementation. Read [validation-and-journal.md](references/validation-and-journal.md)
when reporting results or writing an investigation note.

## Route specialized work

- Use `$xbox360-recomp-re` for PowerPC control flow, XEX revisions, function
  hints, switch tables, hooks, guest ABI, and deciding between a game fix and
  a ReXGlue SDK fix.
- Use `$recomp-performance-debugging` for benchmarks, frame pacing, profiling,
  crashes, stalls, and separating simulation rate from presentation rate.
- Use `$sdl-vulkan-portability` for host boundaries, SDL3, Vulkan, packaging,
  and Windows/Linux verification.

## Invariants

- An address, name, type, decompiler guess, or score is not a fact without
  evidence and revision identity.
- Ghidra databases and proprietary-derived bulk output remain local. Commit
  focused metadata, project-authored tools, original implementations, and
  reproducible conclusions only.
- Preserve guest field widths, packing, endianness, and pointer representation;
  translate explicitly at guest/host boundaries.
- Convert repeated deterministic analysis into a small tool rather than asking
  future agents to reproduce it manually.
- Never claim runtime correctness from configuration or compilation alone.
