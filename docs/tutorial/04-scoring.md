# 4. Scoring

[Playbooks](03-playbooks.md) · [Index](README.md) · Next: [Running on Kaggle](05-kaggle.md)

Each task has its own cost. Lower is better. The official number is the
verifier's JSON `score` when that object says `PASS` (FR-004). The formulas
below are how that score is built. Two of the factors are still
`[NEEDS CLARIFICATION]` in the spec. The arithmetic that the baseline JSON
actually printed is in the tables. It is evidence from the notebook, not a
spec edit.

## Per-task costs

**invsqrt** (FR-005). Hub and paper agree on

`Q * (Toffoli + T/4)`.

The official baseline score is higher than that product because the verifier
also prices fine rotations. FR-005 says the pipeline does not apply the
paper's rotation-to-T pricing unless those inputs are supplied. The JSON
score already includes them, and the cost step copies the JSON score instead
of recomputing it.

**dqi** (FR-006, still open). The working shape, and the one the printed
fields multiply to, is

`R(ε) * Q² * mean Toffoli`.

`mean Toffoli` is the shot mean (`toffoli_count` in the JSON). The max count
is a different field. Which algebraic `R` is the default is the open
question. The number the verifier printed is in the table.

**dfthcsos** (FR-007, still open). The working shape is

`lambda_eff * Toffoli * Q`.

On this task those three factors are the verifier's `lambda_eff`,
`toffoli_count`, and `num_qubits`. They are not the sum of per-file Toffolis
and not the per-file width. The version 8 log captured
`verifiers/dfthcsos/SCORING_README.md`, which writes

`score = lambda_eff * T_total * Q_total`

and

`lambda_eff = sqrt(E_gap * (2 * Lambda - E_gap))`.

That is the paper's square root, not the hub product without the root. The
spec marker is still open. See [Open questions](09-open-questions.md).

## Baseline official scores

These are the reference-sample scores. Same three numbers on version 7
(`20261111T052032Z-e1a4aedc`) and version 8 (`20261112T030658Z-9813e023`).
Source: the verifier JSON `score_inputs` in those logs. Lower is better.

| Task | JSON `score` | Fields that multiply to that score |
| --- | --- | --- |
| invsqrt | 2076774.233715282 | `Q = 260`, Toffoli `7735`, `T = 1`, `toffoli_equivalent = 7987.593206597238` (includes 37 fine rotations). `260 * 7987.593206597238` equals the score. `260 * (7735 + 1/4)` is 2011165.0 and does not. |
| dqi | 24439466758900.453 | `repetition_factor = 1.1912604648115832`, `Q = 1893`, shot-mean Toffoli `5725109.125927734`. Max Toffoli is `5725461`. `R * Q² * mean` equals the score. `T` and fine rotations on the optimizer's static count are 0. |
| dfthcsos | 3355599588.3155375 | `lambda_eff = 49.301369250574396`, verifier Toffoli `93237`, verifier `Q = 730`. That product equals the score. |

Optimizer counts on the angle files, from the version 8 record, are a
different triple: Toffoli-like `39740`, `T = 0`, per-file qubits `119`. Ten
files, 3974 Toffolis each. The README in the log says the forward and reverse
passes are `2 * 39740 = 79480`, the heuristic part adds 13757, and
`T_total = 93237`. `Q = 730` is the verifier's total, not the per-file width
of 119. Multiplying `lambda_eff` by 39740 and 119 does not produce the score.

The README's worked example prints `3355599588.3155365`. The run's JSON
field is `3355599588.3155375`. Use the JSON field. The difference is only in
the last digit of the printed example.

## Verifier JSON

Each official script writes one JSON object. The fields the pipeline treats
as the contract, from `docs/wiki/Architecture.md` and the version 7 and 8
logs:

| Field | Meaning |
| --- | --- |
| `status` | `PASS` or `FAIL`. |
| `score` | That task's cost. Lower is better. Finite and greater than 0. |

`cost_authoritative` is true only when the process is the official script,
exit code 0, not a timeout, the dataset root is not marked `.vqcc-fixture`,
and stdout has one such object. A JSON `status` other than `PASS` fails the
task even if the process exited 0, so the candidate is not packageable
(FR-011).

The cost step names the source `official verifier JSON field score` and
copies the number. It does not re-derive `R` or `lambda_eff` (FR-006,
FR-007). `leaderboard_score` stays null.

## Fail-closed rule

Keep a candidate only on `PASS` with a strictly lower score.

From US2, FR-003, FR-004, and FR-011, and from the optimize step on versions
7 and 8:

1. If the rewrite does not lower the charged weight and does not lower `Q`,
   write no file and do not call the verifier. Version 8 did this on every
   task: instruction counts moved, Toffoli and `Q` did not, `candidates_written`
   was 0.
2. If a file is written, run that task's official verifier.
3. Retain it only when `competition_verified` is true, `cost_authoritative`
   is true, and the new `score` is strictly less than the retained score.
4. Otherwise the previous artifact stays. Version 7 sent invsqrt and dqi to
   the verifier, both returned `PASS` with the same score, and both were
   `rejected`.

Equal is not good enough. A pass with the same score is a rejection.

## The aggregate is not the task score

FR-008 marks the hub's geometric mean of `refcost/cost` unconfirmed. The
paper states no three-task aggregate. FR-009 allows that mean only on an
explicit request, labeled unconfirmed, and forbids the LB column. FR-016
keeps `leaderboard_score` null when no leaderboard return was supplied.

The version 8 cost step records `aggregate.computed: false` and
`leaderboard_score: null`. Per-task costs are lower-is-better. The hub mean,
if it is ever confirmed, is higher-is-better, because it is a ratio of
reference cost over our cost.

## The lesson from versions 6, 7, and 8

Clifford-only shrinking does not move the cost. The cost moves when the
Toffoli count, the T count, the fine-rotation term, or `Q` moves. Version 7
dropped invsqrt from 62160 instructions to 57714 and dqi from 86051014 to
84854692. Toffoli, T, and `Q` stayed put, and both JSON scores stayed put.
Version 8 cancelled the same Clifford pairs (invsqrt 2223, dqi 598091,
dfthcsos 0) and, with the new gate, did not send those files at all.
