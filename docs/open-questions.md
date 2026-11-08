# Open questions

The three scoring questions are also `[NEEDS CLARIFICATION]` markers in
`specs/001-noetl-pipeline/spec.md` (FR-006, FR-007, FR-008) at main
`0b3915b38fb2de7897b735995b7be33fde617c63`. They stay open. The baseline
playbook can evaluate the shared invsqrt expression from kickmix counts and
names that source. It does not apply a dqi `R(ε)` or a dfthcsos `λ_eff`, and
it does not treat the hub geometric mean as the official score. The Kaggle
`verifiers/` tree is still the authority, and it is not in this repository.
Tracked as <https://github.com/noetl/quantum/issues/5>.

## Scoring

1. **Aggregate metric, unconfirmed on the hub.** The hub prints the geometric
   mean of `refcost/cost` over the three tasks and says the Kaggle rendering
   was garbled. The paper never states an aggregate. Until `verifiers/` is
   local, the pipeline computes that mean only on an explicit request and
   will not store it as LB. Should that stay the rule, or should the command
   refuse the aggregate entirely?
2. **dqi `R(ε)`, unconfirmed on the hub.** Hub rendering:
   `ln 2 − ln(1/2 + 2ε)`. Paper equation 43:
   `ln 2 / (−ln(1/2 + 2√ε))`, undefined as a finite score at `ε ≥ 1/16`.
   The paper also defines `T` as the Toffoli count. The hub just writes `T`.
   Which pair is the default?
3. **dfthcsos `λ_eff`, a conflict.** The hub does not mark
   `E_gap(2Λ − E_gap)` unconfirmed. Paper equation 44 takes the square root
   and uses expanded `T_tot` and `Q_tot`. Which one does
   `verifiers/dfthcsos/SCORING_README.md` implement? Are the paper's floors
   strict (`Λ > 49.0` Ha, `E_gap > 3.914898` Ha)?

## Submission and rules

4. Does the official sample zip use any filenames beyond the hub's list
   (`invsqrt.kmb|.kmx`, `dqi.kmb|.kmx`, `dfthcsos/angle_k_*`,
   `dfthcsos/submission.npz`)? Do angle files have an extension?
5. Are the npz keys exactly `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`, and
   `tree_edges`, or does the verifier require more?
6. The hub states 5 submissions per day, 2 final selections, team size at
   most 5, about 45 minutes of scoring, and Apache-2.0 for winners' code.
   The rules page was not readable here. The announcement confirms Apache-2.0
   for the reference circuits and verifiers only.
7. The hub's prize split and the UTC deadlines in [brief.md](brief.md) need
   a pass against the Kaggle overview once it loads. The $150,000 total is
   in the paper. The 2026-10-22 start is the hub's date; the blog is dated
   2026-10-21.

## Repository

8. kickmix's PyPI release was "pending" on the hub. Is the local binary only
   the `.so` from the Kaggle image?
9. The CUDA-Q fixture used as a precedent is at NoETL tag `v2.10.15` and is
   not on current `main`. Should new playbooks stay on the `v2` YAML used by
   current `main`, and should that fixture be revived upstream?
10. How should a local salt be recorded so a passing local run is not mistaken
    for a leaderboard run under the secret salt?
