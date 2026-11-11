# Playbooks

`vqcc_pipeline.yaml` is the baseline entry point. `vqcc_optimize.yaml` is the
per-task optimization loop. Both were checked on the NoETL **5.3.2** local
runtime (`noetl run --runtime local`).

That runtime runs `kind: shell` steps whose `cmds` are shell strings, and it
follows `next: [{step: ...}]`. `kind: python` is rejected by the local
runtime, so Python and kickmix are started from the shell commands.

Default workload:

| Key | Value | Meaning |
| --- | --- | --- |
| `mode` | `competition` | Import a baseline file if one is on disk. Otherwise write no circuit. |
| `data_dir` | `data` | Git-ignored competition data. Not downloaded by the playbook. |
| `runs_root` | `runs` | Git-ignored provenance directory. |
| `repo_root` | `.` | Directory that contains `vqcc/`. Run from the repository root. |

```bash
python3 -m pip install -r requirements-baseline.txt
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json --set mode=structural
```

`--json` prints the run outcome. `final_result` is the record step.
`leaderboard_score` is null. Structural mode writes real kickmix files under
`runs/` and labels them `structural_fixture`. Those files are not submission
candidates.

Optimization, only when a verified baseline is already the point of the run:

```bash
noetl run playbooks/vqcc_optimize.yaml --runtime local --json \
  --set data_dir=/absolute/path/to/data \
  --set runs_root=/absolute/path/to/runs \
  --set repo_root="$PWD" \
  --set seed=20261108
```

That playbook does not arm packaging. The cancellation horizon defaults to
4096. A shorter circuit is scored by the official verifier even when the
removed gates are free Cliffords. The candidate is kept only when that
verifier accepts it and the JSON score is strictly lower. The notebook
entrypoint that calls the same steps is `kaggle/vqcc_optimize.py`.

The CUDA-Q example that motivated quantum playbooks in NoETL is
[`tests/fixtures/playbooks/quantum_cudaq/`](https://github.com/noetl/noetl/tree/v2.10.15/tests/fixtures/playbooks/quantum_cudaq)
at tag `v2.10.15`. It is not on current NoETL `main`. This playbook does not
copy that demo's results. Current NoETL 5.3.2 still uses
`apiVersion: noetl.io/v2`.

Spec: `specs/001-noetl-pipeline/spec.md` at main
`0b3915b38fb2de7897b735995b7be33fde617c63`.
Issues: <https://github.com/noetl/quantum/issues/2> through
<https://github.com/noetl/quantum/issues/9>.
