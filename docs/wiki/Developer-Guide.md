# Developer Guide

## Layout

| Path | Role |
| --- | --- |
| `playbooks/vqcc_pipeline.yaml` | NoETL 5.3.2 playbook. |
| `vqcc/pipeline.py` | CLI the shell steps call. `optimize` is the per-task loop. |
| `vqcc/orchestrator.py` | Run state, import, structural fixtures, verify, optimize, cost, package gate. |
| `vqcc/optimize.py` | Streaming rewrite. A structural shrink or a lower static cost weight is written and scored. The verifier JSON score decides retention. |
| `vqcc/kickmix_file.py` | Streaming `.kmb` / `.kmx` reader and writer. Does not import kickmix. |
| `playbooks/vqcc_optimize.yaml` | Verify, then optimize each task. Packaging stays disarmed. |
| `kaggle/vqcc_optimize.py` | Notebook entrypoint for the same steps. Does not submit. |
| `vqcc/formulas.py` | Hub and paper formulas. Callers choose the source. |
| `vqcc/packaging.py` | Zip layout checks. |
| `vqcc/kickmix` usage | Inside the orchestrator, not a second service. |
| `tests/` | Unit tests, `tests/test_playbook_e2e.py` (`noetl.run`), and `tests/test_playbook_cli.py` (the `noetl` CLI). |
| `requirements-baseline.txt` | `noetl==5.3.2`, `kickmix==1.0.0`, `PyYAML==6.0.2`. |
| `.github/workflows/ci.yml` | Installs that file, runs unittest, and runs the literal CLI in job `cli-default`. |

## Tests

```bash
python3 -m pip install -r requirements-baseline.txt
python3 -m unittest discover -s tests -t .
```

With `requirements-baseline.txt` installed (noetl 5.3.2 and kickmix 1.0.0),
one test skips:
`tests.test_orchestrator.StructuralModeTests.test_structural_mode_fails_closed_without_kickmix`.
It covers the missing-module path and does not run when kickmix is installed.
That was the single skip in the PR #11 CI run (34 tests, `OK (skipped=1)` on
workflow run 42521609515). The log did not name it; the installed baseline
deps make it the only skip. `tests/test_playbook_e2e.py` skips if `noetl`
5.3.x cannot be imported. `tests/test_playbook_cli.py` skips only when the
`noetl` executable is not on `PATH`.

`tests/test_playbook_e2e.py` calls `noetl.run(...)` with a temporary
`runs_root` and `data_dir`. `tests/test_playbook_cli.py` does not. It shells
`noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` from the
repository root and leaves the playbook defaults (`mode`, `data_dir`,
`runs_root`, `repo_root`, `seed`) unset on the command line.

Distinguish the checks:

| Check | What it proves |
| --- | --- |
| Formula unit tests | Arithmetic of the hub rendering and paper equation 43 examples. Not a submission. |
| Packaging unit tests | Zip layout on empty stand-in bytes. Not a verifier pass. |
| Orchestrator tests | Absent data writes no circuit. An imported file is hashed. A hook that exits 0 does not set `competition_verified`. |
| `noetl.run` tests | The playbook's eleven steps execute and the record step matches the provenance file. |
| `noetl` CLI test | The same eleven steps, from the literal CLI with default variables and no competition data. `leaderboard_score` is null, verification is `blocked`, and no zip is written. |
| Optimization tests | Synthetic kickmix fixtures. A rejected or higher-score proposal does not replace the retained path. One task's run does not change the other tasks' bytes. An unchanged circuit writes no file. An instruction-count drop with an unchanged Toffoli weight is sent to the verifier. |
| kickmix measurement | `operation_statistics` on a circuit this process built or loaded. Not the Kaggle verifier. |

## Adding a real verifier

Do this in [issue 4](https://github.com/noetl/quantum/issues/4), after the
dataset is local:

1. Record the official command from `verifiers/` in the issue, with the file
   path inside the dataset.
2. Call that command from `vqcc.official_verifier.run_official_task`. The current names are `verify_submission_invsqrt.py`, `verify_submission_dqi.py`, and `verifiers/dfthcsos/verify.py`.
3. Set `competition_verified` true only from that command's success.
4. Keep structural fixtures unable to set the flag.
5. Add a test that a fake exit-0 script still cannot set the flag unless it
   is the confirmed entry point. The current hook test already requires this.

## Formula changes

FR-006, FR-007, and FR-008 stay open. [Issue 5](https://github.com/noetl/quantum/issues/5).
Do not make paper equation 43 or the square-root `λ_eff` the silent default.
The invsqrt product is the one expression both public write-ups share, and the
kickmix cost path says the extra Z_POW pricing is not applied.

When `cost_authoritative` is true, the cost step uses the verifier JSON
`score` instead of those formulas (spec FR-004). Parsing is
`vqcc.official_verifier.parse_verifier_stdout`. Fixtures live in
`tests/fixtures/verifier_stdout/`. The hub geometric mean is
`vqcc.formulas.unconfirmed_hub_aggregate`. It does not set
`leaderboard_score`.

## Provenance

`runs/` is git-ignored. `docs/experiments.md` is the human table and starts
empty. `scripts/log_experiment.py` refuses the words `guess`, `sample`, and
`auto` in the Local and LB cells.
