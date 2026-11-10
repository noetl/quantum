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
