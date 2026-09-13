# Reverse-engineering knowledge system

## Ghidra's role

Treat Ghidra as an analysis engine, not the project's canonical database.
Keep `.gpr`, `.rep`, memory dumps, bulk disassembly, bulk pseudocode, and other
proprietary-derived working data outside version control.

Prefer narrow headless exports and query tools such as:

- function inventory and exact function context;
- callers, callees, references, imports, strings, and globals;
- switch-table and indirect-target candidates;
- structures with evidence and confidence;
- runtime hit counts and trace correlation;
- shader, PM4, render-target, or draw context.

An agent should request additional context only when the current evidence cannot
answer the hypothesis. Avoid loading thousands of unrelated assembly lines.

For this repository, use `scripts/ghidra/bootstrap.py` to obtain the pinned
Ghidra/JDK/XEXLoaderWV combination and `scripts/ghidra/analyze_xex.py` for
hash-keyed projects and focused exports. Keep both `.tools/` and `.ghidra/`
ignored. Pin the loader and Ghidra as a compatible pair: extension metadata may
allow a nearby version while its compiled APIs do not. Verify every downloaded
archive before extraction and reject archive path traversal.

The XEX loader's PowerPC model and decompiler output are hypotheses, especially
around Xenon VMX128 instructions. Correlate each optimization target with
ReXGlue's generated C++, runtime hit/timing evidence, and—when correctness is
uncertain—focused PPC semantic tests. A visually plausible decompilation is not
sufficient proof for a native replacement.

XEXLoaderWV may print derived retail file/session keys during import. Always run
it through the repository wrapper, which redacts console output, and treat its
ignored application log as sensitive. Never paste or commit raw loader logs.
Python ZIP extraction also drops Unix executable bits; the bootstrap verifier
repairs Ghidra launch scripts and ELF analyzer helpers before headless use.

XEXLoaderWV's `.pdata` pass may leave an Xbox 360 function at an 8-byte body
when its `mflr`/`bl __savegprlr_*` prologue is modeled as non-returning. For a
focused function, use the next same-revision `.pdata` function entry as an
exclusive upper bound, disassemble from `entry + 8`, and record that the local
body was repaired. Never infer such a range from a different executable hash.

## Versioned knowledge layer

Create `re/` data only as real evidence becomes available. A useful shape is:

```text
re/
├── revisions/
├── knowledge/
│   ├── functions.csv
│   ├── globals.csv
│   ├── subsystems.toml
│   └── structures/
└── investigations/
```

Do not add empty scaffolding merely to match this layout. Choose CSV, TOML, or
another diffable format with a documented schema. Every address-bearing record
must identify at least:

- executable/module SHA-256 and size;
- base-game/title-update state and module name;
- address and evidence source;
- proposed semantic name or classification;
- confidence (`low`, `medium`, or `high`);
- related investigation note.

Record relationships such as calls, references, and structure use separately
from conclusions. Marketing region or title ID alone does not establish address
compatibility.

## Context-on-demand contract

A query should return a compact, reproducible bundle: revision, address, known
name, classification, subsystem, confidence, callers/callees, imports, runtime
frequency, evidence links, and unresolved questions. It must distinguish raw
observations from inference.

If agents repeatedly perform the same parse, address lookup, graph traversal,
trace correlation, shader inspection, or PM4 decode manually, add a deterministic
tool under an appropriate `scripts/` subdirectory. The tool should accept explicit
inputs, produce diffable output, expose the revision it used, and fail clearly on
schema or revision mismatch.

Domain-specific tooling may gradually understand Xbox 360, PowerPC, Xenos, PM4,
RAGE graphics types, shaders, render targets, textures, materials, meshes, and
draw calls. Add those concepts only when supported by project evidence.
