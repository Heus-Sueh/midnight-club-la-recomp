# Debugging evidence and ownership

## Establish the failing layer

Use the last completed milestone rather than the user's description of the
symptom:

- no SDL video driver: host/window setup;
- Vulkan instance but no physical device: loader, ICD or device selection;
- physical/logical device but no surface or swapchain: SDL/Vulkan presentation;
- swapchain created, then invalid guest PC/LR: guest function discovery or PPC
  control flow, not GPU initialization;
- PM4/backend errors after valid presents: Xenos translation, resolve, texture,
  shader or synchronization path;
- stable presents with wrong speed: guest timing or hook semantics;
- abrupt `SIGBUS` during arena initialization: inspect `/dev/shm` capacity and
  orphaned `xenia_memory_*` objects before blaming codegen.

## Debugger signals

ReXGlue uses memory protection and signal/exception handlers for guest memory
behavior. Under GDB or LLDB, first-chance `SIGSEGV`/access violations may be
expected. Continue once to see whether the runtime handles the signal. Treat it
as a crash only if the process terminates, repeats without progress, or reaches
an unhandled host stack.

Capture both host and guest context when available:

- host thread and symbolic backtrace;
- guest PC, LR, CTR, relevant GPRs and callsite;
- generated C++ file/function corresponding to the guest address;
- recent GPU packets, shader/pipeline cache event and last successful present.

On Linux hosts where ptrace policy rejects attachment, the profiler can remain
the parent while GDB follows the launched game child:

```console
gdb --args python scripts/profile_linux_runtime.py --output /tmp/host.csv \
  -- ./path/to/game [arguments]
(gdb) set follow-fork-mode child
(gdb) set detach-on-fork on
(gdb) run
```

Only after confirming that first-chance write-watch signals are expected, use
`handle SIGSEGV nostop noprint pass` so the ReXGlue handler receives them. Read
the profiler CSV before interrupting to select the actual hottest Linux TIDs;
capture focused stacks rather than dumping every mostly idle guest thread.

## Remedy ownership

- Guest-specific address or behavior: revision-bound manifest hint or reviewed
  mid-assembly hook.
- Incorrect PPC semantics shared by titles: SDK fix with a focused instruction
  test.
- Host lifecycle, pipeline synchronization or backend policy: SDK fix with a
  focused unit/integration test and reproducible patch.
- SDL/Vulkan loader or packaging issue: portable host/CMake fix, verified on
  both platform configurations.

In static recompilation, writing new bytes to the loaded XEX after codegen does
not replace already-emitted host instructions. Express executable changes in
the codegen configuration and regenerate.

An entirely clipped resolve may be a valid no-op, but return success with a zero
extent only after verifying every caller handles that representation. Otherwise
the change can hide malformed PM4 state.
