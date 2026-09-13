// Exports narrow, gitignored function context for evidence-driven investigation.
// @category MCLA

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.FlowOverride;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class ExportFunctionContext extends GhidraScript {
    private static String safeName(String value) {
        return value.replaceAll("[^A-Za-z0-9_.-]", "_");
    }

    @Override
    protected void run() throws Exception {
        String[] arguments = getScriptArgs();
        if (arguments.length < 2) {
            throw new IllegalArgumentException(
                "usage: ExportFunctionContext.java OUTPUT_DIR ADDRESS [ADDRESS ...]"
            );
        }

        Path outputDirectory = Path.of(arguments[0]);
        Files.createDirectories(outputDirectory);
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        StringBuilder index = new StringBuilder();
        index.append("program=").append(currentProgram.getName()).append('\n');
        index.append("language=").append(currentProgram.getLanguageID()).append('\n');
        index.append("compiler=").append(currentProgram.getCompilerSpec().getCompilerSpecID()).append('\n');

        for (int position = 1; position < arguments.length; position++) {
            monitor.checkCancelled();
            long rawAddress = Long.decode(arguments[position]);
            Address address = currentProgram.getAddressFactory()
                .getDefaultAddressSpace().getAddress(rawAddress);
            Function function = currentProgram.getFunctionManager().getFunctionAt(address);
            if (function == null) {
                function = currentProgram.getFunctionManager().getFunctionContaining(address);
            }

            FunctionIterator followingFunctions = currentProgram.getFunctionManager()
                .getFunctions(function.getEntryPoint().add(1), true);
            Function nextFunction = followingFunctions.hasNext() ? followingFunctions.next() : null;
            boolean repairedPdataBody = false;
            if (nextFunction != null) {
                long span = nextFunction.getEntryPoint().subtract(function.getEntryPoint());
                if (function.getBody().getNumAddresses() < span && span > 8 && span <= 0x4000) {
                    Address end = nextFunction.getEntryPoint().subtract(1);
                    AddressSet repairedBody = new AddressSet(function.getEntryPoint(), end);
                    DisassembleCommand disassemble = new DisassembleCommand(
                        function.getEntryPoint().add(8), repairedBody, true
                    );
                    disassemble.enableCodeAnalysis(false);
                    disassemble.applyTo(currentProgram, monitor);
                    function.setBody(repairedBody);
                    repairedPdataBody = true;
                }
            }
            boolean repairedSharedPrologue = false;
            boolean repairedPrologueFallthrough = false;
            Instruction prologueCall = currentProgram.getListing()
                .getInstructionAt(function.getEntryPoint().add(4));
            if (prologueCall != null && "bl".equals(prologueCall.getMnemonicString())) {
                if (prologueCall.getFlowOverride() != FlowOverride.CALL) {
                    prologueCall.setFlowOverride(FlowOverride.CALL);
                    repairedPrologueFallthrough = true;
                }
                for (Address destination : prologueCall.getFlows()) {
                    Function callee = currentProgram.getFunctionManager().getFunctionAt(destination);
                    if (callee != null && callee.hasNoReturn()) {
                        callee.setNoReturn(false);
                        repairedSharedPrologue = true;
                    }
                }
                Address expectedFallthrough = function.getEntryPoint().add(8);
                if (!expectedFallthrough.equals(prologueCall.getFallThrough())) {
                    prologueCall.setFallThrough(expectedFallthrough);
                    repairedPrologueFallthrough = true;
                }
            }
            if (function == null) {
                index.append(arguments[position]).append(" not-found\n");
                continue;
            }

            String stem = String.format("%08X_%s", rawAddress, safeName(function.getName()));
            StringBuilder assembly = new StringBuilder();
            assembly.append("name=").append(function.getName()).append('\n');
            assembly.append("entry=").append(function.getEntryPoint()).append('\n');
            assembly.append("body=").append(function.getBody()).append('\n');
            assembly.append("calling_convention=").append(function.getCallingConventionName()).append('\n');
            assembly.append("parameters=").append(function.getParameterCount()).append("\n\n");
            assembly.append("next_function=")
                .append(nextFunction == null ? "none" : nextFunction.getEntryPoint())
                .append("\n\n");
            assembly.append("pdata_body_repaired=").append(repairedPdataBody).append("\n\n");
            assembly.append("shared_prologue_return_repaired=")
                .append(repairedSharedPrologue).append("\n\n");
            assembly.append("prologue_fallthrough_repaired=")
                .append(repairedPrologueFallthrough).append("\n\n");
            assembly.append("callers:\n");
            for (Reference reference : currentProgram.getReferenceManager()
                    .getReferencesTo(function.getEntryPoint())) {
                if (reference.getReferenceType().isCall()) {
                    assembly.append("  ").append(reference.getFromAddress()).append('\n');
                }
            }
            assembly.append("\ninstructions:\n");
            for (Instruction instruction : currentProgram.getListing()
                    .getInstructions(function.getBody(), true)) {
                assembly.append(instruction.getAddress()).append("  ")
                    .append(instruction).append('\n');
            }
            Files.writeString(
                outputDirectory.resolve(stem + ".asm.txt"), assembly,
                StandardCharsets.UTF_8
            );

            decompiler.flushCache();
            DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
            String decompiled = result.decompileCompleted()
                ? result.getDecompiledFunction().getC()
                : "Decompiler failed: " + result.getErrorMessage() + "\n";
            Files.writeString(
                outputDirectory.resolve(stem + ".c.txt"), decompiled,
                StandardCharsets.UTF_8
            );
            index.append(arguments[position]).append(' ')
                .append(function.getEntryPoint()).append(' ')
                .append(function.getName()).append(' ')
                .append(function.getBody().getNumAddresses()).append("-bytes next=")
                .append(nextFunction == null ? "none" : nextFunction.getEntryPoint())
                .append(" pdata_body_repaired=").append(repairedPdataBody)
                .append(" shared_prologue_return_repaired=").append(repairedSharedPrologue)
                .append(" prologue_fallthrough_repaired=").append(repairedPrologueFallthrough)
                .append('\n');
        }
        decompiler.dispose();
        Files.writeString(outputDirectory.resolve("index.txt"), index, StandardCharsets.UTF_8);
        println("Focused function context written to " + outputDirectory);
    }
}
