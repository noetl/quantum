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

`competition_verified` is set to false in this baseline, including when an
optional executable `data/verifiers/<task>/verify` exits 0. That hook is
recorded as `hook_exit_code` only. The official verifier command line is not
in the public Qualtran tree we inspected, and the Kaggle data page was not
readable without login. Issue
[4](https://github.com/noetl/quantum/issues/4).

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
