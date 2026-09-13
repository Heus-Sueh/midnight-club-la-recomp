# Focused Ghidra workflow

The repository pins a local Ghidra toolchain for repeatable Xbox 360 analysis:

- Ghidra 12.0.4;
- XEXLoaderWV 13.0.0, built for Ghidra 12.0.4;
- Eclipse Temurin JDK 21.0.12.1+1 for Linux or Windows x86-64.

The bootstrap downloads official release archives and rejects any file whose
SHA-256 does not match the recorded release digest. It does not need an
administrator install:

```sh
python scripts/ghidra/bootstrap.py
python scripts/ghidra/bootstrap.py --verify-only
```

PowerShell uses the same Python commands. The portable toolchain is stored in
`.tools/ghidra/`.

## Import and focused export

Place the XEX from a legally owned copy in `game/default.xex`, then run:

```sh
python scripts/ghidra/analyze_xex.py \
  --address 0x82415DC8 \
  --address 0x82415EE8 \
  --address 0x8241A630
```

The importer names the project with the first 12 characters of the XEX hash,
which prevents accidental reuse across revisions. It prints the complete hash
at the start of every run. Projects live in `.ghidra/projects/`; focused
assembly and decompiler exports live in `.ghidra/exports/<xex-sha256>/`.

The community XEX loader logs derived file/session keys while importing retail
executables. The project wrapper redacts those lines from console output. Its
private application log remains under ignored `.ghidra/config/`; never attach
or publish that directory without reviewing and sanitizing it.

Use `--no-analysis` only after the same hashed project has already completed
analysis. Increase `--analysis-timeout` for a slow host. The Java post-script is
ordinary repository code and can be extended with narrowly scoped queries when
an investigation needs callers, callees, data references, or type evidence.

XEXLoaderWV can initially define some functions as an 8-byte body when their
first two instructions call a shared `__savegprlr_*` prologue. For a focused
target with this exact shape, the export script uses the next `.pdata` function
entry as an exclusive upper bound, disassembles from `entry + 8`, and repairs
the function body in the local database before decompiling. It also clears an
incorrect `no-return` inference on the direct shared-prologue callee. The export
records whether either repair occurred. Do not generalize the inferred boundary
to an address that is not backed by the same revision's `.pdata` ordering.

## Evidence boundary

Never commit the Ghidra project, decompiler output, disassembly, memory dumps,
or retail bytes. Commit only concise conclusions that identify the XEX hash,
address, observation method, confidence, and validation status. Compare static
results with runtime traces before assigning semantic names or replacing guest
code.

XEXLoaderWV supplies a PowerPC language suitable for Xbox 360 executables, but
VMX128 coverage can still be incomplete. When an instruction disagrees with
ReXGlue output or runtime behavior, preserve the bytes locally, treat the
decompilation as untrusted evidence, and validate the instruction semantics
against the code generator and a focused runtime test.
