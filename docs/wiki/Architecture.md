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
engine. The tests use it.

## Steps

`playbooks/vqcc_pipeline.yaml`:

1. `prepare` — create `runs/<id>/` and point `runs/active.json` at it.
2. `check_data` — report whether `data/verifiers` exists.
3. `adapt_invsqrt`, `adapt_dqi`, `adapt_dfthcsos` — import a baseline file if
   it is already on disk, or write a structural fixture when `mode=structural`.
4. `verify` — search for verifiers. Do not invent a pass.
5. `cost` — copy an authoritative verifier JSON `score` when the verify step stored one. Otherwise price a kickmix measurement when that formula's inputs exist. `leaderboard_score` stays null.
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

`ROOT` on Kaggle is `/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation`. A generic `verifiers/<task>/verify` hook is not these scripts. A tree marked `.vqcc-fixture` cannot set `competition_verified`. Exit 0 of the official script is a task pass, not an aggregate leaderboard score. No `--max-x` or other weakening flag is added.

## Score parsing

The official task scripts write one JSON object on stdout. The invsqrt script is the document redirected to `result.json`: `status` is `PASS` or `FAIL`, and `score` is that task's cost (lower is better). A full dqi run uses the same two fields. dfthcsos is read with the same rule. This repository does not have a dfthcsos stdout sample beyond that shared pair, so no extra chemistry keys are assumed.

`parse_verifier_stdout` accepts that object when it is the whole stdout or when log lines precede it. Nested maps (for example dqi `shot_operation_counts`) are dropped. Scalar fields are kept as the cost inputs. Two top-level objects that both contain `score` are `cost_parse: ambiguous` and are not a cost. A bare `cost:` or `score:` line is still stored as `one_line` and is not authoritative.

`cost_authoritative` is true only when all of these hold:

- the process is the official script, exit code 0, and not a timeout
- the dataset root is not marked `.vqcc-fixture`
- stdout has one JSON object with `status` `PASS` and a finite `score` greater than 0

A JSON `status` other than `PASS` sets the task to fail even if the process exited 0, so that candidate is not packageable. Spec FR-004: that JSON `score` overrides the hub and paper formulas for the task cost. The cost step copies it and names the source `official verifier JSON field score`.

`leaderboard_score` stays null. Spec FR-008 still marks the hub geometric mean of `refcost/cost` unconfirmed, and the paper states no aggregate. FR-009 allows that mean only on an explicit request (`vqcc.pipeline cost --aggregate` plus caller-supplied `--ref-*` values), labels it unconfirmed, and forbids the LB column. FR-016 keeps `leaderboard_score` null when no Kaggle leaderboard return was supplied. The spec defines no numeric refcosts, so they are not hardcoded from the private notebook.

cwd defaults to the dataset root. That was not recorded in the notebook evidence. `verifier_launch.json` in the dataset root can set `cwd` and `pythonpath` when the scripts' own notes require it. `PYTHONPATH` is prefixed with the dataset root, `verifiers/`, and the script directory.

This cloud workspace did not run those scripts on the competition data. The private notebook Version 3 did, with exit codes 0 and raw task costs 2076774.233715282, 24439466758900.453, and 3355599588.3155375. Those numbers are external evidence, not a result of this repository.

A structural circuit loading in kickmix is `measurement.status: measured`.
That is not competition verification.

## Costs

| Task | What the cost step computes |
| --- | --- |
| any task with `cost_authoritative` | The verifier JSON `score`. Hub and paper formulas are not re-derived (FR-004). FR-006 and FR-007 stay open as formula questions. |
| invsqrt, no authoritative score | `Q * (toffoli_like + t_like/4)` from kickmix counts. Paper Z_POW pricing beyond `num_t_like` is not applied. Hub and paper agree on this product. |
| dqi, no authoritative score | Counts only. `R(ε)` is not applied. FR-006 is open. |
| dfthcsos, no authoritative score | Qubit-cap note from the measured file. `λ_eff` is not applied. FR-007 is open. |
| aggregate | Hub geometric mean only with `--aggregate` and caller-supplied refcosts for all three tasks, and only from three authoritative scores. `unconfirmed: true`. `leaderboard_score` stays null (FR-008, FR-009, FR-016). |

## Packaging

`vqcc.packaging` checks the hub zip layout on files the caller already has.
The playbook does not call it until every task is `competition_verified`.
Unit tests cover gaps, extra files, and missing npz keys with labeled fixtures.
