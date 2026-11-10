# Architecture

The baseline is one NoETL playbook. Quantum work is ordinary programs the
playbook starts. There is no second orchestrator.

## Runtime

Tested command:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

| Piece | Version | Role |
| --- | --- | --- |
| NoETL | 5.3.2 | Local playbook runtime. `apiVersion: noetl.io/v2`. |
| Python | 3.12 | Adapters, formulas, packaging. |
| kickmix | 1.0.0 | Public Qualtran package. Builds and measures `.kmx` / `.kmb`. Not the Kaggle `kickmix.so`. |

NoETL 5.3.2 local execution runs `tool.kind: shell` with a `cmds` list and
routes with `next: [{step: name}]`. `kind: python` prints "not supported" and
is not used. Shell commands call `python3 -m vqcc.pipeline`.

`import noetl` then `noetl.run(path, variables=...)` calls that same local
engine. `tests/test_playbook_e2e.py` uses it with explicit variables.
`tests/test_playbook_cli.py` shells the operator command with no `--set`.

## Steps

`playbooks/vqcc_pipeline.yaml`:

1. `prepare` — create `runs/<id>/` and point `runs/active.json` at it.
2. `check_data` — report whether `data/verifiers` exists.
3. `adapt_invsqrt`, `adapt_dqi`, `adapt_dfthcsos` — import a baseline file if
   it is already on disk, or write a structural fixture when `mode=structural`.
4. `verify_invsqrt`, `verify_dqi`, `verify_dfthcsos` — official scripts when they exist. Absence blocks. Do not invent a pass.
5. `cost` — price a kickmix measurement when the formula inputs exist.
6. `package` — refuse a zip while any task has `competition_verified: false`.
7. `record` — write `provenance.json`. Do not append a guessed experiments row.

Workload keys: `mode`, `data_dir`, `runs_root`, `repo_root`. Override with
`noetl run ... --set key=value`.

## Modes

**competition** (default). A task with no file under `data/` gets
`role: absent` and `circuit_written: false`. A file that is present is hashed
and, when kickmix can read it, measured. It is not copied into git and it is
not marked verified.

**structural**. kickmix writes `fixture.kmx` and `fixture.kmb` under the run
directory from a fixed text circuit. The text says it is not a submission.
If kickmix is not installed, the adapt step exits 2 and writes nothing.

## Verification boundary

Official commands, seed `20261108`, absolute paths, sequential:

```text
python3 ROOT/verifiers/invsqrt/verify_submission_invsqrt.py ROOT/sample_submission/invsqrt.kmb --seed 20261108
python3 ROOT/verifiers/dqi/verify_submission_dqi.py ROOT/sample_submission/dqi.kmb --seed 20261108
python3 ROOT/verifiers/dfthcsos/verify.py ROOT/sample_submission/dfthcsos --seed 20261108
```

`ROOT` on Kaggle is `/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation`. A generic `verifiers/<task>/verify` hook is not these scripts. A tree marked `.vqcc-fixture` cannot set `competition_verified`. Exit 0 of the official script is a task pass, not an aggregate leaderboard score. Parsed `cost:` / `score:` lines are stored with `cost_authoritative: false` because this repository has not read the scripts' print statements. No `--max-x` or other weakening flag is added.

cwd defaults to the dataset root. That was not recorded in the notebook evidence. `verifier_launch.json` in the dataset root can set `cwd` and `pythonpath` when the scripts' own notes require it. `PYTHONPATH` is prefixed with the dataset root, `verifiers/`, and the script directory.

This cloud workspace did not run those scripts on the competition data. The private notebook Version 3 did, with exit codes 0 and raw task costs 2076774.233715282, 24439466758900.453, and 3355599588.3155375. Those numbers are external evidence, not a result of this repository.

A structural circuit loading in kickmix is `measurement.status: measured`.
That is not competition verification.

## Costs

| Task | What the baseline computes |
| --- | --- |
| invsqrt | `Q * (toffoli_like + t_like/4)` from kickmix counts. Paper Z_POW pricing beyond `num_t_like` is not applied. Hub and paper agree on this product. |
| dqi | Counts only. `R(ε)` is not applied. FR-006 is open. |
| dfthcsos | Qubit-cap note from the measured file. `λ_eff` is not applied. FR-007 is open. |
| aggregate | Not computed. The hub geometric mean stays unconfirmed (FR-008). |

## Packaging

`vqcc.packaging` checks the hub zip layout on files the caller already has.
The playbook does not call it until every task is `competition_verified`.
Unit tests cover gaps, extra files, and missing npz keys with labeled fixtures.
