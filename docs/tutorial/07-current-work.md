# 7. Current work and next steps

[History](06-history.md) · [Index](README.md) · Next: [Deliverables](08-deliverables.md)

> **Current state, 2026-11-18 (main `3e6626f`):** scores, what has been ruled
> out and the remaining headroom are in [STATE.md](../../STATE.md) and on the wiki
> [Status](https://github.com/noetl/quantum/wiki/Status) page. Retractions are in the
> [Decisions Log](https://github.com/noetl/quantum/wiki/Decisions-Log). "What main does now" and "What version 9 measured"
> describe the version 9 tree and are kept as history.

At the time of version 9, main was `da8490eed953875d6e7bb3a2f306554f41620905`, the merge of
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

## What version 9 measured

Version 9 finished. Notebook scriptVersionId `368976547`, run
`20261113T015716Z-fea5b448`, from main `da8490e`. The evidence comment is
on [issue 19](https://github.com/noetl/quantum/issues/19#issuecomment-6844754721).
invsqrt's retained official score is `2068786.6405086848` (259 qubits; the
Toffoli count did not change). dqi stayed at `24439466758900.453` and
dfthcsos stayed at `3355599588.3155375`. `shared_control_factors` and
`and_uncomputes` were 0 on every task. dqi's profile still counted 832
shared-control candidates and 222 matching uncompute pairs, with
`reuse_headroom_vs_header` 0. Those counts are not strict matches. The
split is written up in
[docs/wiki/Circuit-Structure.md](../wiki/Circuit-Structure.md). A candidate
count above 0 did not move the official score.

dqi would feel a real `Q` drop because `Q` is squared, and it has no
headroom. dfthcsos's official `Q` is 730 while each angle file is width
119, so a narrower file is not assumed to change that score. The verifier
still decides. No score from a later pass is claimed here.

## What to do next

1. Do not start a Kaggle run until a local candidate passes the official
   verifier with a strictly lower score. The last run was version 14. Its
   dqi candidate failed on phase errors, and the cause was fixed in
   [PR #30](https://github.com/noetl/quantum/pull/30).
2. Our rewrite pass is a tidy pass that gets about 1×. Real gains are
   per-task algorithm redesigns (new decoder, arithmetic or factorization),
   a larger separate effort. The portfolio pipeline wraps strong external
   circuits for ranking only; see `STATE.md`.
3. Read `structure.toffoli.match` labels for what they mean.
   `same_wire_reaccumulate` (formerly `control_mutated`) is a second product
   XORed onto the same wires. It is not a blocked uncompute and not headroom.
4. Any optimizer change ships with regression tests and differential
   fuzzing, as in PR #30.
5. Do not edit FR-006, FR-007, or FR-008 in the spec until the clarification
   in [Open questions](09-open-questions.md) is accepted.
6. Submissions follow the owner's standing approval and its conditions (see
   `HANDOVER.md`). Submission status: the account's 8 October submissions (best 21.37712, Kaggle) were made by Dimitri outside this repo; nothing from this repo's pipelines has been submitted.

## What is already settled, so it is not next

- The playbook runs on NoETL 5.3.2 with no data and blocks cleanly. Issue
  [#2](https://github.com/noetl/quantum/issues/2) is closed.
- Fetch-without-downloading works. Issue
  [#8](https://github.com/noetl/quantum/issues/8) is closed.
- A PASS JSON `score` is the task cost, and it is not the leaderboard
  column. Issue [#13](https://github.com/noetl/quantum/issues/13) is closed.
- Clifford cancellation is not a cost reduction. Versions 7 and 8 measured
  that. The optimize step no longer sends those files to the verifier.
