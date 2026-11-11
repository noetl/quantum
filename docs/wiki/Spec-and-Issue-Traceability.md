# Spec and issue traceability

Spec file: `specs/001-noetl-pipeline/spec.md`

Pinned main SHA for the score-parsing change: `349a858e52e78474c5ebb0fde02987a67813715f`
(merge of PR #11). The optimization loop was added from main
`d45b477dc85ca8f3d0051937c44aea4e57ada90e` (merge of PR #14). The spec text
is still the file introduced at
`0b3915b38fb2de7897b735995b7be33fde617c63`. It was not edited.

Constitution: `.specify/memory/constitution.md` at that same commit.
Principles that bind the baseline: no fabricated results, unconfirmed stays
unconfirmed, competition data stays out of git, verifiers decide correctness,
playbooks orchestrate.

| Issue | Spec | Baseline status |
| --- | --- | --- |
| [#2](https://github.com/noetl/quantum/issues/2) playbook runtime | User story 5, FR-016, SC-001, SC-005 | Literal CLI `noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` from the repo root, default variables, no competition data: eleven steps, `leaderboard_score` null, verification `blocked`, no zip. Covered by `tests/test_playbook_cli.py` and CI job `cli-default`. Distributed server execution is not claimed. |
| [#3](https://github.com/noetl/quantum/issues/3) task adapters | User stories 1–2, FR-001, FR-002, FR-003 | Import and structural fixtures work. Competition-quality generation does not. `tasks/*/generate.py` still refuses to write a file. |
| [#4](https://github.com/noetl/quantum/issues/4) verifier | FR-010, FR-011, user story 1 | Adapter calls the three official scripts with `--seed`. A generic hook does not pass. Full dataset execution is the Kaggle notebook, not this cloud VM. |
| [#5](https://github.com/noetl/quantum/issues/5) cost | FR-004–FR-009, FR-018, SC-002 | A PASS JSON `score` from the official script is the authoritative task cost (FR-004) and names that source plus the JSON scalars. Kickmix invsqrt pricing remains the fallback. dqi `R`, dfthcsos `λ_eff`, and FR-008 stay unresolved. The hub mean is opt-in, unconfirmed, and is not `leaderboard_score` (FR-009, FR-016). |
| [#6](https://github.com/noetl/quantum/issues/6) provenance | User story 4, FR-015, FR-020, SC-004 | `runs/<id>/provenance.json` is written. The committed experiments table is not filled with numbers. |
| [#7](https://github.com/noetl/quantum/issues/7) packaging | User story 3, FR-011–FR-014, SC-003 | Layout unit tests pass. The playbook does not write a zip while verification is false. |
| [#8](https://github.com/noetl/quantum/issues/8) data fetch | FR-019 | `scripts/fetch_data.sh` documents the Kaggle CLI and does not download unless asked. Rules are not accepted here. |
| [#9](https://github.com/noetl/quantum/issues/9) optimization | User story 2 (acceptance scenarios 1 and 2), FR-001, FR-003, FR-004, FR-010, FR-011 | `playbooks/vqcc_optimize.yaml` plus `vqcc.optimize`. One task per step. A structural shrink is written and scored even when the removed gates are free Cliffords. A rewrite that raises the task's static Toffoli weight is not written. A proposal is retained only when that task's official verifier accepts it and the JSON `score` is strictly lower (FR-004, FR-011). A rejected proposal does not replace the previous artifact. `tasks/*/generate.py` still refuses. No Kaggle dataset was present for the gating fix, so no new reference-circuit score is claimed. |

FR-006, FR-007, and FR-008 remain `[NEEDS CLARIFICATION]` in the spec. This
implementation does not edit those markers.
