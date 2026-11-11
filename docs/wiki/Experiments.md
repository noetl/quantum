# Experiments

No leaderboard submission has been made. No Local or LB number is recorded
in `docs/experiments.md`.

| Date | Run | Description | Local | LB | Notes |
| --- | --- | --- | --- | --- | --- |

Playbook runs write a git-ignored provenance file instead of a table row.
That file includes `leaderboard_score: null`.

## What a local run showed

On 2026-11-08 the implementation environment ran:

```bash
python3 -m unittest discover -s tests -t .
```

with `noetl==5.3.2`, `kickmix==1.0.0`, and Python 3.12. 27 tests passed and
1 skipped. The skip is the "kickmix missing" guard, which does not run when
kickmix is installed.

`tests/test_playbook_e2e.py` executed `playbooks/vqcc_pipeline.yaml` through
`noetl.run` (the 5.3.2 local engine):

- Competition mode, empty data directory: eleven steps, verification blocked,
  no circuit files, no zip, `leaderboard_score` null.
- Structural mode: kickmix wrote `fixture.kmb` files, reloaded them, priced
  the invsqrt fixture from measured `toffoli_like` and `t_like`, and left
  `competition_verified` false.

Those structural counts are properties of the fixture text in
`vqcc/orchestrator.py`. They are not reference-circuit scores from the paper
and they are not leaderboard scores.

## Literal CLI, 2026-11-10

From the repository root, NoETL **5.3.2**, no `data/` directory, and no
`--set`:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

Exit 0. stderr: `runtime: local (--runtime flag)`. Run id
`20261110T155907Z-97652c24`. Nothing was submitted to Kaggle. No zip was
written. Trimmed JSON:

| Field | Value |
| --- | --- |
| `status` | `ok` |
| `executed_steps` | `start`, `check_data`, `adapt_invsqrt`, `adapt_dqi`, `adapt_dfthcsos`, `verify_invsqrt`, `verify_dqi`, `verify_dfthcsos`, `cost`, `package`, `record` |
| `final_result.mode` | `competition` |
| `final_result.leaderboard_score` | null |
| `final_result.verification_status` | `blocked` |
| `final_result.package_status` | `not_ready` |
| `final_result.zip_written` | false |
| `final_result.experiment_log_written` | false |
| each task `competition_verified` / `circuit_written` | false / false |
| each `verify_*` step `status` | `blocked` |
| provenance `runtime.noetl_tested_version` | `5.3.2` |
| provenance `seed` | `20261108` (playbook default) |

`docs/experiments.md` gained no Local or LB cell.

## Optimization loop, 2026-11-10

`playbooks/vqcc_optimize.yaml` and `kaggle/vqcc_optimize.py` were added from
main `d45b477d`. No competition data was mounted. No official verifier was
run on a reference circuit. No Local or LB cell was written.

`python3 -m unittest discover -s tests -t .` with `noetl==5.3.2` and
`kickmix==1.0.0`: 62 tests passed, 1 skipped. The skip is the kickmix-missing
guard. `tests/test_playbook_cli.py` still passes. The new tests cover a
byte-identical kmb round trip, kickmix simulation of the peephole, a rejected
proposal, a higher verifier score, task isolation, a dfthcsos directory whose
`submission.npz` bytes are copied, and the optimize playbook with an empty
data directory.

`POST https://noetl.ai/api/dsl/validate` on 2026-11-10, server 3.156.1:
`vqcc_pipeline.yaml` and `vqcc_optimize.yaml` both returned HTTP 200,
`valid: true`, findings empty. Schema digest
`sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6`.

## Verifier gate, 2026-11-11

Issue #9 run `20261111T000307Z-0d076b2d` cancelled Clifford pairs (dqi lost
about 1.1e6 instructions) and wrote no candidate, because the gate required
the lexicographic key `(toffoli_like, t_like, high_rotations)` to fall. Those
Cliffords are not in the published costs. The gate now writes a shorter
circuit and sends it to the official verifier. Retention is still a PASS and
a strictly lower JSON `score` (FR-004, FR-011).

No competition data was mounted for this change. No official verifier score
was produced. Fixture circuits checked with kickmix 1.0.0 simulation:

- `CCX; X` on the Toffoli target; `CCX` becomes the `X`. Toffoli count 2 → 0.
- Two `Z_POW 0.125` on one qubit become one T (`Z_POW 0.25`). Static weight
  32 → 1. The phase matches.
- `X q0; X q1; X q0` drops an instruction and leaves the static weight at 0.
  The pipeline test sends that file to the stub verifier.

`POST https://noetl.ai/api/dsl/validate` on 2026-11-11, server 3.156.2:
both playbooks returned HTTP 200, `valid: true`, `execute_verdict: accept`,
findings empty. Schema digest
`sha256:29b2831fdd2444fab0bbc8915283a22ac86532393111f3a3cdad782bf6b1c4be`.

## How to log a real attempt later

```bash
python3 scripts/log_experiment.py \
  --date YYYY-MM-DD \
  --run <id> \
  --description "what changed" \
  --notes "formula source, inputs, verifier command"
```

Omit `--local` and `--lb` until a verifier or Kaggle returns them. The script
rejects placeholder words such as `guess` and `sample`.
