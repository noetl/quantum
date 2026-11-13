# 7. Current work and next steps

This is the wiki copy of `docs/tutorial/07-current-work.md`. Wording matches that page. Links on this copy use wiki page names.


[History](Tutorial-06-History) · [Index](Tutorial) · Next: [Deliverables](Tutorial-08-Deliverables)

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
  [docs/wiki/Circuit-Structure.md](Circuit-Structure).
- Shared-control factoring replaces a second clean `CCX` with `CX` while the
  AND is still on its target.
- Scratch ids are reused after an unconditional `R` or `HMR`, or folded into
  a real id gap, and only when a named register is present.

No improvement on the reference circuits is claimed from the machine that
merged PR #20. The sample files were not in that environment. The measurement
is the private Kaggle notebook, recorded below.

## What version 9 measured

Version 9 is the Kaggle Save & Run All of commit `da8490e` on the private
notebook
[kadyapam/noetl-quantum-competition-pipeline-vqcc](https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc?scriptVersionId=368976547),
scriptVersionId `368976547`. Run `20261113T015716Z-fea5b448`. Total 8120.2 s.
Optimize step exit 0, 4644 s. No submission was made. The same record is in
[the history](Tutorial-06-History).

| Task | Candidate | Verifier | Official score |
| --- | --- | --- | --- |
| invsqrt | retained | `PASS` | 2068786.6405086848, from the version 8 baseline 2076774.233715282 (Δ −7987.593206597, −0.3846%). Q 260 → 259 by scratch-qubit reuse. Toffoli 7735, T 1. Instructions 62160 → 57714. |
| dqi | none written | `PASS` on the baseline | 24439466758900.453 unchanged. Instructions 86051014 → 84854692 (about 1.2M). Toffoli and Q unchanged. |
| dfthcsos | none written | `PASS` on the baseline | 3355599588.3155375 unchanged. |

PR #20's shared-control factoring and AND-uncompute applied 0 times on all
three tasks.

Input-circuit `structure` (not a score), invsqrt / dqi / dfthcsos:
`shared_control_candidates` 11 / 832 / 0, `matching_uncompute_pairs`
0 / 222 / 0, peak live qubits 259 / 1893 / 119, `reuse_headroom_vs_header`
1 / 0 / 0. dfthcsos figures are per angle file. invsqrt's headroom of 1 is
the qubit the retained candidate freed. dqi's peak live count equals its
header (1893), so a dqi gain has to come from the Toffoli count. dfthcsos's
official `Q` is 730; a per-file peak of 119 with headroom 0 left that score
where it was.

Evidence: [issue #19 comment](https://github.com/noetl/quantum/issues/19#issuecomment-6844754721)
and [issue #9 comment](https://github.com/noetl/quantum/issues/9#issuecomment-6844754839).

## What to do next

1. Next lever: dqi Toffoli reduction. The input profile has 832
   shared-control candidates and 222 matching uncompute pairs, and both new
   transforms applied 0 times. Issue
   [#19](https://github.com/noetl/quantum/issues/19) is where to find out why
   shared-control factoring and AND-uncompute do not fire. Qubits stay 1893
   with reuse headroom 0.
2. Keep the fail-closed gate. invsqrt cleared it: official `PASS` and a
   strictly lower JSON `score`. dqi's shorter instruction list did not,
   because Toffoli and Q were unchanged, so no candidate was written.
3. invsqrt's reuse headroom on the input is the one qubit already taken.
   Further invsqrt gains need a Toffoli cut. The profile lists 11
   shared-control candidates there, and that transform applied 0 times.
4. Do not edit FR-006, FR-007, or FR-008 in the spec until the clarification
   in [Open questions](Tutorial-09-Open-Questions) is accepted. The logs are
   evidence. They are not a spec change.
5. Do not submit, publish, or share. Version 9 did not.

## What is already settled, so it is not next

- The playbook runs on NoETL 5.3.2 with no data and blocks cleanly. Issue
  [#2](https://github.com/noetl/quantum/issues/2) is closed.
- Fetch-without-downloading works. Issue
  [#8](https://github.com/noetl/quantum/issues/8) is closed.
- A PASS JSON `score` is the task cost, and it is not the leaderboard
  column. Issue [#13](https://github.com/noetl/quantum/issues/13) is closed.
- Clifford cancellation is not a cost reduction. Versions 7 and 8 measured
  that. The optimize step no longer sends those files to the verifier.
- Scratch-qubit reuse on version 9 lowered invsqrt from `Q` 260 to 259 and
  kept the official score 2068786.6405086848. That qubit is the input
  profile's reuse headroom. It is not the next lever.
