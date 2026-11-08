# Developer Guide

## Layout

| Path | Role |
| --- | --- |
| `playbooks/vqcc_pipeline.yaml` | NoETL 5.3.2 playbook. |
| `vqcc/pipeline.py` | CLI the shell steps call. |
| `vqcc/orchestrator.py` | Run state, import, structural fixtures, verify, cost, package gate. |
| `vqcc/formulas.py` | Hub and paper formulas. Callers choose the source. |
| `vqcc/packaging.py` | Zip layout checks. |
| `vqcc/kickmix` usage | Inside the orchestrator, not a second service. |
| `tests/` | Unit tests plus `tests/test_playbook_e2e.py`, which calls `noetl.run`. |
| `requirements-baseline.txt` | `noetl==5.3.2`, `kickmix==1.0.0`, `PyYAML==6.0.2`. |
| `.github/workflows/ci.yml` | Installs that file and runs unittest. |

## Tests

```bash
python3 -m pip install -r requirements-baseline.txt
python3 -m unittest discover -s tests -t .
```

27 tests ran in the implementation environment (Python 3.12). One test skips
when kickmix is installed, because it only covers the missing-module path.
`tests/test_playbook_e2e.py` skips if `noetl` 5.3.x cannot be imported.

The end-to-end tests call `noetl.run(...)`, which is the local engine, not a
reimplementation. They use a temporary `runs_root` and `data_dir`.

Distinguish the checks:

| Check | What it proves |
| --- | --- |
| Formula unit tests | Arithmetic of the hub rendering and paper equation 43 examples. Not a submission. |
| Packaging unit tests | Zip layout on empty stand-in bytes. Not a verifier pass. |
| Orchestrator tests | Absent data writes no circuit. An imported file is hashed. A hook that exits 0 does not set `competition_verified`. |
| `noetl.run` tests | The playbook's nine steps execute and the record step matches the provenance file. |
| kickmix measurement | `operation_statistics` on a circuit this process built or loaded. Not the Kaggle verifier. |

## Adding a real verifier

Do this in [issue 4](https://github.com/noetl/quantum/issues/4), after the
dataset is local:

1. Record the official command from `verifiers/` in the issue, with the file
   path inside the dataset.
2. Call that command from `vqcc.orchestrator._verify_one`.
3. Set `competition_verified` true only from that command's success.
4. Keep structural fixtures unable to set the flag.
5. Add a test that a fake exit-0 script still cannot set the flag unless it
   is the confirmed entry point. The current hook test already requires this.

## Formula changes

FR-006, FR-007, and FR-008 stay open until `verifiers/` confirms them.
[Issue 5](https://github.com/noetl/quantum/issues/5). Do not make paper
equation 43 or the square-root `λ_eff` the silent default. The invsqrt
product is the one expression both public write-ups share, and the cost step
says the extra Z_POW pricing is not applied.

## Provenance

`runs/` is git-ignored. `docs/experiments.md` is the human table and starts
empty. `scripts/log_experiment.py` refuses the words `guess`, `sample`, and
`auto` in the Local and LB cells.
