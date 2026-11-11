# User Guide

Commands below were run with Python 3.12, NoETL 5.3.2, and kickmix 1.0.0.
Run them from the repository root.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-baseline.txt
python -m unittest discover -s tests -t .
```

`.venv/` is git-ignored. The install does not download the Kaggle dataset and
does not accept competition rules.

Confirm the CLI:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

Expect `status: ok`, eleven executed steps, and `leaderboard_score: null` in
`final_result`.

`tests/test_playbook_cli.py` runs this command from the repo root with no
`--set` and no competition data. It skips only when the `noetl` CLI is absent.
Verification is `blocked`, and no submission zip is written.

## Data acquisition

The dataset is about 1 GB and license-restricted. It is not in git.

`scripts/fetch_data.sh` prints the steps and does not download:

```bash
scripts/fetch_data.sh
```

A download happens only when a person who has already accepted the rules
passes `--download`. That requires:

1. `pip install kaggle` (separate from `requirements-baseline.txt`).
2. Rules accepted in the browser while logged in:
   <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/rules>
3. `~/.kaggle/kaggle.json` mode `600`.

```bash
scripts/fetch_data.sh --download
```

This repository's automation does not accept the rules, join the competition,
or upload a submission. The blocker is tracked in
[issue 8](https://github.com/noetl/quantum/issues/8).

After a human download, leave the files in `data/`. The playbook looks for:

- `data/verifiers/`
- `data/verifiers/<task>/SCORING_README.md`
- `data/verifiers/<task>/verify` (optional executable hook; a zero exit is
  recorded and is **not** treated as official verification)
- `data/sample_submission/invsqrt.kmb` or `.kmx` (and the same for `dqi`)
- `data/sample_submission/dfthcsos/` or `data/dfthcsos/`

Those relative paths are the ones the adapter searches. They are not a claim
that the official zip uses exactly those names. A miss is reported as absent.

## Register

Nothing is registered with a NoETL server for the local baseline. Registration
is for the distributed runtime, which this baseline does not require.

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

is the whole register-and-run step for local use. The playbook file is the
catalog entry.

## Run

Competition mode:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

Structural fixtures (real kickmix files, not a submission):

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json --set mode=structural
```

Point at another data directory without moving the repo:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json \
  --set data_dir=/absolute/path/to/data \
  --set runs_root=/absolute/path/to/runs \
  --set repo_root="$PWD"
```

## Verify

Official reference run, only when the dataset is mounted or extracted locally:

```bash
python3 kaggle/vqcc_reference_verify.py --seed 20261108
```

Or the playbook, which calls the same three scripts one after another:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json \
  --set data_dir=/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation \
  --set seed=20261108
```

Do not add flags that shorten the official check. Timeouts default to 7200s, 7200s, and 3600s. The dqi sample is about 886 MB and is passed by path, not loaded into the playbook.

A blocked run with no dataset looks like:

- `verification_status`: `blocked`
- `package_status`: `not_ready`
- `zip_written`: false
- `leaderboard_score`: null
- each task `competition_verified`: false

That is the expected result until the official verifier is available. It is
not a pass.

## Optimize

After the dataset is mounted, the NoETL playbook runs baseline verification
and then one peephole pass per task. It does not submit and it does not pass
`--package-when-verified`.

```bash
noetl run playbooks/vqcc_optimize.yaml --runtime local --json \
  --set data_dir=/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation \
  --set runs_root=/kaggle/working/runs \
  --set repo_root="$PWD" \
  --set seed=20261108
```

The same steps without the `noetl` binary, including a single task:

```bash
python3 kaggle/vqcc_optimize.py --task invsqrt --seed 20261108
```

`--time-budget-s` defaults to 14400 for one optimize step. `--memory-budget-bytes`
defaults to 2147483648. `--window` defaults to 4096 (the cancellation horizon;
Z-rotation merging is not limited by it). `--max-candidates` defaults
to 1 and cannot be set above 3.

What to check in `runs/<id>/provenance.json`:

- `leaderboard_score` is null and `package.zip_written` is false.
- `optimization.status` is `accepted` only when `retained_cost` is strictly
  less than `baseline_cost` and that task's verifier JSON `status` is `PASS`.
- `rejected` and `unchanged` leave `paths` on the previous artifact. A
  rejected file under `runs/<id>/proposals/` is not the retained path.
- With `--task invsqrt`, the dqi and dfthcsos sha256 values are unchanged.
- The dataset mount is not modified. New bytes are under `runs/`.

The reference costs from the private seed-20261108 run (lower is better) are
external evidence in `vqcc/official_verifier.py`, not a result of this
repository. An `unchanged` status means the rewrite did not lower the charged weight
or the qubit count, so no candidate was scored.
A `rejected` status means a candidate was scored and the verifier did not
return a strictly lower PASS score. The 2026-11-11 run
`20261111T000307Z-0d076b2d` was `unchanged` on every task because Clifford
cancellations did not move the old lexicographic gate key.

## Package

The playbook refuses to write a zip while verification is false.

Layout checks on files you already have:

```bash
python3 scripts/package_submission.py \
  --invsqrt path/invsqrt.kmb \
  --dqi path/dqi.kmb \
  --dfthcsos path/dfthcsos \
  --output submissions/submission.zip
```

`submissions/` is git-ignored. A zip produced this way is a layout check. The
playbook will still not call it submission-ready unless `competition_verified`
is true, which this baseline does not set.

## Scores

An official verifier that prints one JSON object with `status` `PASS` and a
positive `score` stores that number as the task cost (`cost_authoritative:
true`). The cost step names the source `official verifier JSON field score`.
`leaderboard_score` stays null: the hub geometric mean is still unconfirmed
(spec FR-008), is not written to the LB column (FR-009), and is not a Kaggle
leaderboard return (FR-016). The spec does not define numeric reference costs.

To evaluate the hub mean on numbers you supply, after three authoritative
scores exist in the active run:

```bash
python3 -m vqcc.pipeline cost --aggregate \
  --ref-invsqrt REF_INVSQRT \
  --ref-dqi REF_DQI \
  --ref-dfthcsos REF_DFTHCSOS
```

The result has `aggregate.unconfirmed: true` and `leaderboard_score: null`.
Without `--aggregate`, or without those three refcosts, the mean is not
computed and the gap text cites FR-008.

```bash
python3 scripts/score.py invsqrt --qubits 3 --toffoli 1 --t-gates 1 --json
```

prints a formula evaluation and `leaderboard_score: null`. dqi and dfthcsos
require `--source hub` or `--source paper` because those write-ups disagree.
Do not paste those numbers into the experiments table as a run.
