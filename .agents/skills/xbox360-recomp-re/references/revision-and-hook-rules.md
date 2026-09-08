# Revision and hook rules

## Revision identity

At minimum, bind an address map to SHA-256, file size, base game/update state, and module name. A marketing region or title ID alone is not sufficient; different pressings and title updates can relocate or replace code.

Title updates may arrive as packages or XEXP deltas. Preserve the owned original outside version control and document the deterministic step used to obtain the analyzed image. Never publish the resulting executable.

## Function and switch hints

Use a named function only when its entry is supported by call references, prologue/control-flow evidence, symbols, or a matching signature. Function sizes and ends must follow the pinned SDK schema. Switch-table labels must come from the table/control-flow evidence and must be valid aligned guest addresses.

## Mid-assembly hooks

In a static recompilation, changing executable bytes in the loaded guest image
after code generation does not change the already-emitted host instructions.
Instruction replacements must be expressed in the codegen configuration (for
example, a reviewed mid-assembly hook) and the generated sources rebuilt.

For every `[[midasm_hook]]`, document:

- module and compatible executable hash;
- hook address and surrounding guest function;
- why the address is reached and stable;
- live registers requested by the hook;
- guest memory read or written, including endian handling;
- whether the hook returns, conditionally returns, or redirects control flow;
- original instructions displaced or semantics preserved;
- a test or deterministic runtime observation.

Keep hook names semantic. Do not name them only after an address. Fail codegen or startup on an unsupported revision instead of applying the hook optimistically.

## SDK defects

Suspect an SDK defect when a minimal instruction sequence has wrong semantics independent of game state, especially vector/VMX, carry/condition-register, endian, or aliasing behavior. Reduce the case, compare against the PowerPC specification or trusted execution, add a PPC test, then patch the SDK. Keep a local SDK patch only while upstream is unavailable and pin it to an exact SDK preimage.

## Temporary bypasses

A bypass is acceptable only to expose the next diagnostic boundary. It must be disabled by default or clearly marked experimental, include a removal condition, and never be presented as a completed feature. Do not bypass save integrity, content ownership, cryptography, or security checks.
