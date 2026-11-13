# 5. Running on Kaggle

[Scoring](04-scoring.md) · [Index](README.md) · Next: [Optimization history](06-history.md)

Official scores are produced on one private notebook. This page is the
procedure those runs used. It is not permission to submit.

Notebook (private):

<https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc>

The repository cannot see a private notebook's source. The steps below are
the ones the version 8 log and the issue comments actually show, plus the
rules this repo already enforces. Where the log is silent, the step is marked.

## Do this

1. Keep the notebook private.
2. Turn Internet on. The version 8 log shows `pip` downloading
   `noetl==5.3.2` and `kickmix==1.0.0` from `requirements-baseline.txt`.
   That download fails if Internet is off. The log does not print Kaggle's
   setting name; the downloads are the evidence the network was available.
3. Use **Save & Run All (Commit)** so Kaggle runs a background version.
   An interactive session is not a result. On 10 Nov 2026 the interactive
   optimize session died on Kaggle's idle timeout and left no `runs/`
   directory ([issue #9 comment](https://github.com/noetl/quantum/issues/9#issuecomment-6781973477)).
   Versions 2–5 of that notebook each finished in 8–10 seconds. Version 5
   was a Quick Version and was not the optimize run. A version that finishes
   in seconds did not verify dqi.
4. Let the notebook clone `main` of <https://github.com/noetl/quantum> into
   `/kaggle/working/quantum`, then fetch `origin/main`. The version 8 log
   shows `Cloning into '/kaggle/working/quantum'...` and
   `HEAD is now at 53304c8`.
5. Require the ancestor check before any verifier runs. The version 8 log
   prints: `Required merge commit ecb0f601c4301163ce67d00762cd2dfce0b75d81 is ancestor of HEAD: yes`.
   That commit is the merge of [PR #12](https://github.com/noetl/quantum/pull/12)
   (verifier JSON scores). The check refuses a checkout that does not contain
   the score-parsing code. The exact commit the version 9 notebook requires
   is **unverified**: this repository does not contain the notebook source.
6. Install `requirements-baseline.txt` from that clone. Confirm
   `git rev-parse HEAD` is the commit you meant to measure. Version 8's
   optimize HEAD was `53304c8e5f80c382320697b9bed28331cbbfab3b`.
7. Run the optimize entrypoint. Either the playbook, if `noetl` is on
   `PATH`:

   ```bash
   noetl run playbooks/vqcc_optimize.yaml --runtime local --json \
     --set data_dir=/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation \
     --set runs_root=/kaggle/working/runs \
     --set repo_root="$PWD" \
     --set seed=20261108
   ```

   or the same steps without the CLI:

   ```bash
   python3 kaggle/vqcc_optimize.py --seed 20261108
   ```

8. Read `runs/<id>/provenance.json` before you tell anyone a score moved.
   `leaderboard_score` is null. `package.zip_written` is false.
   `optimization.status` is `accepted` only when `retained_cost` is strictly
   lower than `baseline_cost` and the verifier JSON `status` is `PASS`.
   `structure` is a profile, not a score.

## Do not do this

Do not submit, publish, or share the notebook, its output, or a zip without
an explicit approval.

The playbook does not arm packaging. `kaggle/vqcc_optimize.py` does not call
the Kaggle submit API. Constitution principle IV: a local verifier pass is
not a leaderboard submission. Issue [#7](https://github.com/noetl/quantum/issues/7)
stays open until a real packaging run is exercised, and even then a zip is
not an upload.

Sharing privately outside the team is outside the rules the hub states and
outside constitution principle on competition boundaries. The Kaggle rules
page itself was rate-limited when the brief was written, so the daily
submission cap in [the brief](../brief.md) remains a hub statement.

## What to paste back

When a version finishes, comment on
[issue #9](https://github.com/noetl/quantum/issues/9) with:

- scriptVersionId and the notebook version number
- `git rev-parse HEAD` and whether the ancestor check passed
- run id, exit code, elapsed seconds
- per task: status (`unchanged`, `rejected`, or `accepted`), baseline score,
  retained score, instruction counts, Toffoli, T, `Q`, and `and_uncomputes`
  if the log has them
- `leaderboard_score` (expect null) and `zip_written` (expect false)

Leave a cell blank when the log does not contain it. Do not convert an
`unchanged` run into a Local score. `docs/experiments.md` stays empty until
someone logs a real measurement with `scripts/log_experiment.py`, and that
script rejects placeholder words.
