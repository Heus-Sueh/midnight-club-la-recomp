# Validation and investigation journal

## Validation ladder

Report the highest level actually demonstrated:

1. static validation;
2. configure;
3. compile;
4. link;
5. unit or regression tests;
6. smoke execution;
7. deterministic trace comparison;
8. render or state comparison;
9. repeatable benchmark;
10. extended gameplay.

A lower level is not evidence for a higher one. A successful build does not
prove that the game runs, reaching a menu does not prove gameplay, and visible
output does not prove renderer correctness.

## Negative controls

Whenever practical, prove that an important validator can fail. Apply a small,
known temporary mutation, confirm that the trace/comparison/test reports a
difference, then remove the mutation and confirm the baseline passes again.
Never leave the intentional defect in the working tree.

For performance, use the same scene, duration, cache state, instrumentation,
configuration, and input sequence before and after a one-variable change.
Report median, p95, p99, maximum, CPU/GPU time or utilization, pipeline/shader
activity, memory, and stalls when available. Do not call differences within run
variance an improvement.

## Investigation note

For a significant investigation, record:

- target and reason for choosing it;
- executable/module revision and host configuration;
- falsifiable hypothesis;
- raw observations and their source;
- inferred conclusion, confidence, and competing explanations;
- instrumentation and exact reproducible commands;
- implementation or configuration change;
- validation level reached and negative control used;
- what worked, what failed, and which assumptions were rejected;
- remaining uncertainty and highest-value next target.

Store focused notes in `docs/investigations/` (or the established project
knowledge path). Link structured function/global/type entries back to the note.
A rejected hypothesis is reusable knowledge when its conditions and evidence
are recorded precisely.

## Completion test

Do not call an RE task complete unless another investigator can identify the
target and revision, reproduce the evidence, understand what changed, see the
validation boundary, distinguish facts from uncertainty, and select the next
investigation without reconstructing the entire session.
