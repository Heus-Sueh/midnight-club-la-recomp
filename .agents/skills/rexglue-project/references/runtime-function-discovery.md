# Runtime function discovery

Use this flow when static codegen succeeds but runtime reports `Call to invalid or unregistered function at guest address ...`. It recovers evidence for indirect entry points without editing generated C++ or blindly treating every nearby address as a function.

## Separate host graphics from guest execution

Do not diagnose a late guest abort as a Vulkan initialization failure. The host graphics path is established when the log shows all of the following:

- the intended ReXGlue GPU plugin loaded;
- a physical Vulkan device was selected;
- `vkCreateDevice` completed with the required features/extensions;
- a presenter swapchain was created;
- the runtime proceeded to guest memory, VFS, XEX loading, or function registration.

If those milestones are present, preserve their log lines and investigate the first later fatal message. A loader-layer informational message is not proof that device creation failed when the same log subsequently names the device and creates a swapchain.

## Capture guest control-flow state

Locate the fatal trap in the pinned SDK rather than assuming its source line:

```text
rg -n "Call to invalid or unregistered function" thirdparty/rexglue-sdk
```

If no system core was preserved, run the debuggable build under GDB and set a pending source breakpoint on that trap. At the breakpoint record:

- `ctx.last_indirect_target`: missing guest entry point;
- `ctx.lr`: guest return address, normally the instruction after `bctrl`;
- `ctx.ctr` and `ctx.r12`: registers commonly carrying the target;
- the host backtrace: identifies the generated C++ function containing the callsite.

Find the guest `LR` and generated caller in `generated/<module>/`. Confirm that the caller performs an indirect branch and determine where it loads the pointer. Stop if the target is outside the module code range or the callsite cannot be justified.

## Recognize secondary entries and shared tails

An indirect target may numerically fall inside the range between two already discovered functions without being an invalid mid-function jump. Inspect the guest instruction boundary around it:

- an address immediately after an unconditional `b`, `bctr`, or `blr` may begin an independent thunk omitted by direct-call discovery;
- consecutive short thunks often dispatch adjacent vtable slots;
- a later registered block may be a shared tail reached by multiple valid entry points.

Add only observed targets or entries justified by a bounded structural pattern. Let normal codegen split and decode them, then inspect the generated function: its instructions, terminal control transfer, and any shared tail must match the proposed boundary. Do not use `--force` to accept a bad split.

## Recover pointer tables in one pass

When the caller walks a bounded callback, constructor, or initializer table, recover the full table instead of adding one target per crash:

1. Derive the table's guest start/end from the generated load and loop bounds.
2. Confirm the runtime's guest virtual memory base from its log or debugger state.
3. In GDB, inspect a few bytes first, then dump only the proven table range to a temporary file. ReXGlue's mapped guest address is normally `virtual_membase + guest_address`, but verify this for the pinned SDK/build.
4. Decode Xbox 360 table entries as big-endian 32-bit values.
5. Keep only values inside the loaded module's logged code range.
6. Compare unique values against `SetFunction(...)` entries in the generated register source.

The difference is a candidate set, not automatic permission to add hints. Require the table provenance, code-range check, and revision identity. Record the XEX SHA-256 next to address-bearing config.

## Add and validate hints

Express proven targets in an included project-owned TOML file:

```toml
[functions."0x827A7FD0"]
name = "sub_827A7FD0"
```

Use names appropriate to current knowledge; rename them when reverse engineering establishes semantics. Regenerate with the exact pinned CLI without `--force`. Review validation output for `not a function entry point`, overlap/split warnings, analysis errors, and the number of files changed. Then rebuild and repeat the host smoke test.

A successful hint should increase the registered-function count and move execution beyond the prior target. If it instead creates validation warnings or fails at the same address, revisit the table range, endianness, executable revision, and code-range assumptions.

## Distinguish GDB write-watch stops from crashes

ReXGlue may deliberately make guest physical-memory pages read-only so a write raises `SIGSEGV`, invalidates GPU-cached data, restores write access, and resumes. GDB sees the signal before ReXGlue's exception handler, so a source location in a generated `REX_STORE_*` is not by itself evidence of a guest buffer overflow.

First reproduce outside GDB. At a debugger stop, verify all of the following before treating it as write-watch traffic:

- the faulting host address maps to a guest physical alias such as `0xA...`, `0xC...`, or `0xE...`;
- the guest allocation metadata and record count show that the store is in bounds;
- the page is protected rather than unmapped;
- continuing delivers the signal to ReXGlue and normal execution resumes.

For a targeted debugging session, start with GDB stopping and passing `SIGSEGV`, inspect one representative fault, then use `handle SIGSEGV nostop noprint pass` only after it is proven to be ReXGlue write-watch traffic. Restore normal handling when investigating a genuine crash. Do not patch generated stores or enlarge guest buffers merely to suppress an expected protection fault.

## Recover from orphaned Linux shared-memory arenas

On Linux, ReXGlue backs guest memory with a sparse `/dev/shm/xenia_memory_*` object. SDK destruction unlinks it, but paths that hard-exit the process, debugger kills, and crashes may bypass destruction and leave the object behind with hundreds of megabytes of resident tmpfs pages. Accumulated arenas can cause `SIGBUS` at varying addresses inside `Memory::Zero` or `Memory::InitializeFunctionTable`, before guest execution begins.

Diagnose this in the same host namespace as the runtime:

```text
df -h /dev/shm
find /dev/shm -maxdepth 1 -type f -name 'xenia_memory_*' -printf '%f\n'
pgrep -af 'rexglue|midnight_club_la'
```

Stop every live ReXGlue process, resolve the exact filenames and ownership, and remove only confirmed orphaned `xenia_memory_*` objects. Do not use a broad wildcard while a runtime is active. Recheck free space before launching again. This is a host-resource failure, not evidence for adding function hints or changing Vulkan device selection.

For a durable POSIX fix, unlink the `shm_open` name immediately after a successful `ftruncate` while retaining the open descriptor used to create all views. POSIX keeps the object alive until the final descriptor/mapping closes and reclaims it even after a hard process exit. Keep this as a focused SDK patch, leave Windows unchanged, and validate three states: no named object while the runtime is active, no object after forced termination, and successful guest startup/frame presentation.

## Observed project example

For the vanilla Midnight Club: Los Angeles executable recorded in this repository, GDB showed guest target `0x827A7FD0`, LR `0x821327F8`, and generated caller `sub_82132740`. The caller iterates a bounded initializer table with `bctrl`. Dumping that table and comparing its big-endian code pointers to the generated registry exposed the remaining missing entries in a single pass.

Later, runtime target `0x822C9DD8` was recovered by inspecting the bounded bytes between `sub_822C9DB8` and `sub_822C9DE8`. They contained complete consecutive dispatch thunks at `0x822C9DC8` and `0x822C9DD8`; validation then exposed the direct tail-call target `0x822C9828`. Codegen accepted all three without force. These addresses apply only to the recorded XEX digest and must not be reused for another region or title update.
