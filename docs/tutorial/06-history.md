# 6. Optimization history

[Running on Kaggle](05-kaggle.md) · [Index](README.md) · Next: [Current work](07-current-work.md)

Timeline of what landed on `main`, and what the private notebook measured.
Kaggle rows cite the issue comment or the attached log. A row with no Kaggle
version was not a scored optimize run. "No change" means no retained
candidate and no movement in the official JSON score.

The notebook is
<https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc>.

## Timeline

| When (UTC) | Change | Kaggle | Result |
| --- | --- | --- | --- |
| 2026-11-08 | [PR #1](https://github.com/noetl/quantum/pull/1) merged, `0b3915b`. Brief, spec, skeleton. Issues [#2](https://github.com/noetl/quantum/issues/2)–[#9](https://github.com/noetl/quantum/issues/9) opened. | — | No circuit and no score. |
| 2026-11-08 | [PR #10](https://github.com/noetl/quantum/pull/10) merged, `d470536`. Baseline playbook on NoETL 5.3.2. | — | No data: verification blocked, `leaderboard_score` null. |
| 2026-11-08 | [PR #11](https://github.com/noetl/quantum/pull/11) merged, `349a858`. Official verifier scripts, seed `20261108`. | Version 3 is named inside later logs as the source of the reference costs. scriptVersionId for version 3 is **unverified** here. | PR body reports exit 0 and the three raw costs below. Not an optimization. |
| 2026-11-10 | [Issue #13](https://github.com/noetl/quantum/issues/13) closed by [PR #12](https://github.com/noetl/quantum/pull/12), merge `ecb0f601`. JSON `score` becomes the task cost. | — | `leaderboard_score` stays null. This merge is the ancestor check's required commit on version 8. |
| 2026-11-10 | [PR #14](https://github.com/noetl/quantum/pull/14) merged, `d45b477`. Literal CLI run with no data. | — | Eleven steps, verification blocked. |
| 2026-11-10 | [PR #15](https://github.com/noetl/quantum/pull/15) merged, `10013fb`. Per-task optimize loop. Implements [#9](https://github.com/noetl/quantum/issues/9). | [Version 6](https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc?scriptVersionId=368231739), scriptVersionId `368231739`. Branch `cursor/per-task-optimize-loop-559e`, HEAD `3af81db`. Run `20261111T000307Z-0d076b2d`. | No change. Evidence: [issue #9 comment](https://github.com/noetl/quantum/issues/9#issuecomment-6785361226). |
| 2026-11-11 | [PR #16](https://github.com/noetl/quantum/pull/16) merged, `cd0168a`. Clifford shrinks are sent to the verifier. Wider horizon, rotation merge. | [Version 7](https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc?scriptVersionId=368303187), scriptVersionId `368303187`. HEAD `cd0168a`. Run `20261111T052032Z-e1a4aedc`. | Instructions dropped. Costs unchanged. Evidence: [issue #9 comment](https://github.com/noetl/quantum/issues/9#issuecomment-6800303863) and the version 7 log. |
| 2026-11-12 | [PR #18](https://github.com/noetl/quantum/pull/18) merged, `53304c8`. Measurement uncompute and the Clifford-only gate. Issue [#17](https://github.com/noetl/quantum/issues/17). | [Version 8](https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc?scriptVersionId=368640063), scriptVersionId `368640063`. HEAD `53304c8`. Run `20261112T030658Z-9813e023`. | 0 clean-AND uncomputes. All costs at baseline. Evidence: [issue #17 comment](https://github.com/noetl/quantum/issues/17#issuecomment-6820164452) and [issue #9 comment](https://github.com/noetl/quantum/issues/9#issuecomment-6820165973), matching the version 8 log. |
| 2026-11-13 | [PR #20](https://github.com/noetl/quantum/pull/20) merged, `da8490e`. Structure profile, shared-control factoring, scratch reuse. Issue [#19](https://github.com/noetl/quantum/issues/19). | **Version 9 — pending.** Running from `da8490e`. No scriptVersionId, run id, or scores are in the repo or in the issue comments read for this page. | **Pending.** Do not fill this row. |

## Version 6, in one paragraph

Optimize session on the PR #15 branch, window 32, elapsed 3001s inside a
notebook version that ran 8421.5s. Every task `unchanged`, `candidates_written`
0, verifier `PASS` on the baselines, `leaderboard_score` null. Peephole
instruction counts: invsqrt 62160 → 62096 (32 cancelled pairs), dqi
86051014 → 84954212 (548331 pairs), dfthcsos 2060743 → 2060743 (0 pairs).
The gate then was the local gate-count proxy, so those cancellations were
not written. Costs stayed at the baseline. The same kernel then ran
`vqcc_pipeline.yaml` at the merge commit `10013fb` (run
`20261111T015310Z-32706be9`): verification pass, zip not written,
`LEADERBOARD_SCORE` null.

## Version 7, in one paragraph

`vqcc_optimize.yaml`, status `ok`, duration 5941.10s, window 4096. From the
attached optimize log:

| Task | Status | Instructions | Charged counts | Score |
| --- | --- | --- | --- | --- |
| invsqrt | `rejected` (1 candidate sent, not retained) | 62160 → 57714, 2223 Clifford pairs | Toffoli 7735, T 1, fine rotations 37. Cost units 31533 before and after. | 2076774.233715282 unchanged. Verifier `PASS`. |
| dqi | `rejected` (1 candidate sent, not retained) | 86051014 → 84854692, 598091 pairs | Toffoli 5725461, T 0. Cost units 22901844 before and after. | 24439466758900.453 unchanged. Verifier `PASS`. |
| dfthcsos | `unchanged` (nothing written) | 2060743 → 2060743, 0 pairs | Toffoli 39740, T 0. | 3355599588.3155375 unchanged. |

The verifier accepted the shorter invsqrt and dqi files and returned the
same score. Fail-closed kept the baseline. dfthcsos had nothing inside the
horizon to cancel.

## Version 8, in one paragraph

Save & Run All, optimize elapsed 4525s, notebook log "Successfully ran in
9690.6s". Ancestor check passed. Every task `unchanged`,
`candidates_written` 0, reason "rewrite did not lower the charged gate
weight or the qubit count." `and_uncomputes` is 0 for invsqrt, dqi, and
dfthcsos (six occurrences in the log, all zero). Clifford pairs still
cancelled (invsqrt 2223, dqi 598091, dfthcsos 0) and were not sent. Qubits
in the attempt record: invsqrt 260, dqi 1893, dfthcsos 119. Official scores
unchanged. `zip_written` false. `leaderboard_score` null.

## Version 9

**Pending.** The run was started from main `da8490e` (merge of PR #20).
Results are not in. When they land, add a row here and on
[issue #9](https://github.com/noetl/quantum/issues/9). Until then this cell
stays empty on purpose.

## Baseline scores used in every row above

| Task | Official JSON score |
| --- | --- |
| invsqrt | 2076774.233715282 |
| dqi | 24439466758900.453 |
| dfthcsos | 3355599588.3155375 |

Counts that go with those scores are in [Scoring](04-scoring.md). No version
in this table has beaten them.
