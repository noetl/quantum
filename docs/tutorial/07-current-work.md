# 7. Current work and next steps

[History](06-history.md) · [Index](README.md) · Next: [Deliverables](08-deliverables.md)

Main is `da8490eed953875d6e7bb3a2f306554f41620905`, the merge of
[PR #20](https://github.com/noetl/quantum/pull/20). That PR is the structural
pass for [issue #19](https://github.com/noetl/quantum/issues/19), and it
references [#17](https://github.com/noetl/quantum/issues/17) and
[#9](https://github.com/noetl/quantum/issues/9).

## What main does now

`playbooks/vqcc_optimize.yaml` still verifies each baseline, then rewrites
one task. A candidate is written only when the charged weight or the qubit
count drops. It is kept only on official `PASS` and a strictly lower JSON
`score` (US2, FR-001, FR-003, FR-004, FR-010, FR-011). FR-006, FR-007, and
FR-008 are unchanged.

New on this commit, beyond PR #18:

- `vqcc/profile.py` records opcodes, repeated blocks, Toffoli shape, and
  qubit lifetimes. The optimize step logs that as `structure`, including
  when it writes no file. The write-up is
  [docs/wiki/Circuit-Structure.md](../wiki/Circuit-Structure.md).
- Shared-control factoring replaces a second clean `CCX` with `CX` while the
  AND is still on its target.
- Scratch ids are reused after an unconditional `R` or `HMR`, or folded into
  a real id gap, and only when a named register is present.

No improvement on the reference circuits is claimed from the machine that
merged PR #20. The sample files were not in that environment.

## What is running

**Version 9 is pending.** It is the Kaggle run of this commit
(`da8490e`) on the private notebook. There is no scriptVersionId, run id,
elapsed time, or score to report. Do not treat a missing number as zero, and
do not copy the version 8 scores forward as if they were version 9.

The useful output, when the log exists, is the `structure` object on each
optimize step: `shared_control_candidates`, `reuse_headroom_vs_header`,
clean-AND counts, and the opcode histogram. PR #20's own expectation, which
this page repeats and does not strengthen: a lower official score is not
expected unless that report shows shared-control candidates above 0 or reuse
headroom above 0. dqi would feel a real `Q` drop because `Q` is squared. A
circuit whose peak live count already equals its header will not move.
dfthcsos's official `Q` is 730 while each angle file is width 119, so a
narrower file is not assumed to change that score. The verifier still
decides.

## What to do next

1. Let version 9 finish. Paste the provenance summary onto
   [issue #9](https://github.com/noetl/quantum/issues/9) using the list in
   [Running on Kaggle](05-kaggle.md). Leave version 9 blank in
   [the history](06-history.md) until that comment exists.
2. Read `structure` before writing another pass. If shared-control
   candidates and reuse headroom are both 0, another Clifford or clean-AND
   pass will not move the score. Version 8 already showed the clean-AND
   uncompute count is 0.
3. Spend the next code change on something the cost formula charges:
   Toffoli count, T count, the invsqrt fine-rotation term, or `Q`. Issue
   [#19](https://github.com/noetl/quantum/issues/19) still lists cheaper
   Toffoli constructions (adders, temporary-AND ladders) for blocks the
   profile actually finds. Keep the fail-closed gate.
4. Do not edit FR-006, FR-007, or FR-008 in the spec until the clarification
   in [Open questions](09-open-questions.md) is accepted. The logs are
   evidence. They are not a spec change.
5. Do not submit, publish, or share.

## What is already settled, so it is not next

- The playbook runs on NoETL 5.3.2 with no data and blocks cleanly. Issue
  [#2](https://github.com/noetl/quantum/issues/2) is closed.
- Fetch-without-downloading works. Issue
  [#8](https://github.com/noetl/quantum/issues/8) is closed.
- A PASS JSON `score` is the task cost, and it is not the leaderboard
  column. Issue [#13](https://github.com/noetl/quantum/issues/13) is closed.
- Clifford cancellation is not a cost reduction. Versions 7 and 8 measured
  that. The optimize step no longer sends those files to the verifier.
