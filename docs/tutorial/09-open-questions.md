# 9. Open questions

[Deliverables](08-deliverables.md) · [Index](README.md) · [Glossary](glossary.md)

FR-006, FR-007, and FR-008 are still `[NEEDS CLARIFICATION]` in
`specs/001-noetl-pipeline/spec.md`. This briefing does not remove those
markers. Issue [#5](https://github.com/noetl/quantum/issues/5) tracks them.
The longer list, including submission-layout and rules questions, is
[docs/open-questions.md](../open-questions.md).

The notebook logs now contain evidence a clarification would have to accept
or reject. Evidence is not a closed marker.

## FR-006 — dqi `R(ε)`, pending

The spec asks which definition is the default until `verifiers/` is present:

- Hub, marked unconfirmed there: `R(ε) = ln 2 − ln(1/2 + 2ε)`.
- Paper equation 43: `R(ε) = ln 2 / (−ln(1/2 + 2√ε))`, with `T` the single-run
  Toffoli count. Undefined as a finite score at `ε ≥ 1/16`.

What the logs already print, from dqi `score_inputs` on version 7 and version
8 (the objects match):

| Field | Value |
| --- | --- |
| `effective_error_rate` | 0.0008660587301657926 |
| `repetition_factor` | 1.1912604648115832 |
| `toffoli_count` (shot mean) | 5725109.125927734 |
| `max_toffoli_count` | 5725461 |
| `num_qubits` | 1893 |
| `score` | 24439466758900.453 |

`repetition_factor * 1893² * 5725109.125927734` equals that score.

With `eps` set to that `effective_error_rate`:

- Paper equation 43, `ln 2 / (−ln(1/2 + 2√eps))`, equals `1.1912604648115832`.
- Hub, `ln 2 − ln(1/2 + 2 eps)`, equals `1.38283611283892`, which does not
  match the printed factor.

That arithmetic was checked while writing this page, from the printed fields.
It is not a change to the spec, and it does not by itself say the verifier
source implements equation 43. Closing FR-006 means reading `verifiers/dqi/`
and then editing the marker. The dqi verifier source was not in the attached
logs, so the formula match is necessary and not sufficient.

Until that edit, the pipeline copies the JSON `score` and does not apply an
`R` of its own.

## FR-007 — dfthcsos `lambda_eff`, pending

The spec asks which definition is the default until
`verifiers/dfthcsos/SCORING_README.md` is present:

- Hub, not marked unconfirmed there: `lambda_eff = E_gap * (2Λ − E_gap)`,
  no square root.
- Paper equation 44: the square root of that product, with `T` and `Q`
  expanded to `T_tot` and `Q_tot`.

The version 8 notebook log captured that README. The captured text says:

- `score = lambda_eff * T_total * Q_total` (lower is better).
- `lambda_eff = sqrt(E_gap * (2 * Lambda - E_gap))`.
- Strict floors `Lambda > 49.0` and `E_gap > 3.914898` Ha. Equality is
  rejected. The baseline table in the capture lists `Lambda`
  308.4559397330944 and `E_gap` 3.965477244291833.
- Any angle circuit over 128 qubits is rejected. `error_1` or `error_2`
  over 20 mHa is rejected.
- `T_total` counts angle Toffolis forward and reverse, plus heuristic
  outer, inner, and Givens costs. The worked example:
  `2 * 39740 = 79480`, plus `846 + 9461 + 3450 = 13757`, so `T_total = 93237`.
- `Q_total = 730`, not the per-file width 119.

The run's JSON matches the product:
`49.301369250574396 * 93237 * 730 = 3355599588.3155375`.

This is the file the spec said would settle FR-007, as copied into a
notebook log. It is still a log capture, not a commit of `verifiers/`, and
the spec marker has not been edited. Closing FR-007 is a spec change after
the team accepts the capture. This tutorial does not make that change.

The README's worked example prints score `3355599588.3155365`. The JSON
field on the run is `3355599588.3155375`. They differ in the last printed
digit. The authoritative stored cost is the JSON field (FR-004).

## FR-008 — leaderboard aggregate, pending

The spec asks whether the hub geometric mean

`(refcost_invsqrt / cost_invsqrt * refcost_dqi / cost_dqi * refcost_dfthcsos / cost_dfthcsos) ** (1/3)`

should be refused until metric code is local, or computed only on request
and labeled unconfirmed. The hub marks the metric unconfirmed. The paper
does not state an aggregate.

Nothing in the version 7 or version 8 logs shows a Kaggle metric script that
computes that mean. The cost step on version 8 records `aggregate.computed:
false`, `unconfirmed: true`, and `leaderboard_score: null`, and the gap text
cites FR-008, FR-009, and FR-016.

The current behavior, which is the safe default written into the spec's
assumptions, stays: the mean is opt-in, labeled unconfirmed, and never
stored as LB. Closing FR-008 still needs the metric code. That code was not
in the attached logs.

## Related, not one of the three markers

These came out of the same logs. They are not resolved either.

- Sample angle files are `angle_k_0.kmb` through `angle_k_9.kmb`. The hub
  layout and `vqcc/packaging.py` still use extensionless `angle_k_0` …
  `angle_k_N`. Open question 4 in [docs/open-questions.md](../open-questions.md).
- The captured dfthcsos README says the verifier ignores extra files. The
  packager rejects them (FR-014's neighborhood, and the edge case in the
  spec). Both statements can be true: the verifier is looser than our zip
  check. Do not weaken the packager from this page.
- Version 9's `structure` report is **pending**. It is not an open formula
  question. It is the measurement [issue #19](https://github.com/noetl/quantum/issues/19)
  asked for.
