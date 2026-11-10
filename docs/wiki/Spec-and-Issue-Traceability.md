# Spec and issue traceability

Spec file: `specs/001-noetl-pipeline/spec.md`

Pinned main SHA for this change: `d47053659fed3b110eb057f58d048ac50bf9ba7d`
(merge of PR #10). The spec text is still the file introduced at
`0b3915b38fb2de7897b735995b7be33fde617c63`.

Constitution: `.specify/memory/constitution.md` at that same commit.
Principles that bind the baseline: no fabricated results, unconfirmed stays
unconfirmed, competition data stays out of git, verifiers decide correctness,
playbooks orchestrate.

| Issue | Spec | Baseline status |
| --- | --- | --- |
| [#2](https://github.com/noetl/quantum/issues/2) playbook runtime | User story 5, FR-016, SC-001, SC-005 | Literal CLI `noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` from the repo root, default variables, no competition data: eleven steps, `leaderboard_score` null, verification `blocked`, no zip. Covered by `tests/test_playbook_cli.py` and CI job `cli-default`. Distributed server execution is not claimed. |
| [#3](https://github.com/noetl/quantum/issues/3) task adapters | User stories 1–2, FR-001, FR-002, FR-003 | Import and structural fixtures work. Competition-quality generation does not. `tasks/*/generate.py` still refuses to write a file. |
| [#4](https://github.com/noetl/quantum/issues/4) verifier | FR-010, FR-011, user story 1 | Adapter calls the three official scripts with `--seed`. A generic hook does not pass. Full dataset execution is the Kaggle notebook, not this cloud VM. |
| [#5](https://github.com/noetl/quantum/issues/5) cost | FR-004–FR-009, FR-018, SC-002 | Invsqrt product is computed from measured counts and labeled. dqi `R`, dfthcsos `λ_eff`, and the aggregate stay unresolved. |
| [#6](https://github.com/noetl/quantum/issues/6) provenance | User story 4, FR-015, FR-020, SC-004 | `runs/<id>/provenance.json` is written. The committed experiments table is not filled with numbers. |
| [#7](https://github.com/noetl/quantum/issues/7) packaging | User story 3, FR-011–FR-014, SC-003 | Layout unit tests pass. The playbook does not write a zip while verification is false. |
| [#8](https://github.com/noetl/quantum/issues/8) data fetch | FR-019 | `scripts/fetch_data.sh` documents the Kaggle CLI and does not download unless asked. Rules are not accepted here. |
| [#9](https://github.com/noetl/quantum/issues/9) optimization | User story 2 | Not started. |

FR-006, FR-007, and FR-008 remain `[NEEDS CLARIFICATION]` in the spec. This
implementation does not edit those markers.
