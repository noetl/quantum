# Experiments

Log of runs for this repository. The columns match the Experiments table on
the team hub: Date, Run, Description, Local, LB, Notes. The hub's
`progress.json` uses the field names `date`, `run_id`, `description`,
`local_score`, `lb_score`, and `notes` for the same cells.

No submissions yet. Leaderboard position unknown. Do not invent a Local or LB
value. Leave the cell as `—` until a verifier run or the Kaggle leaderboard
returns a number.

Playbook runs write `runs/<id>/provenance.json` instead of appending a row
here. That file is git-ignored. `leaderboard_score` in those records is null
until a real leaderboard return exists.

Append a row with:

```bash
python3 scripts/log_experiment.py \
  --date 2026-11-05 \
  --run run-id \
  --description "what changed" \
  --notes "formula source, inputs, salt note"
```

Omit `--local` and `--lb` when you do not have those measurements.

| Date | Run | Description | Local | LB | Notes |
| --- | --- | --- | --- | --- | --- |
