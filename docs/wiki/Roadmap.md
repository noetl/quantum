# Roadmap

The baseline is the playbook, the adapters, measured invsqrt arithmetic, and
the packaging gate. It is not an optimizer.

## Done in the baseline

- NoETL 5.3.2 local playbook with eleven shell steps and provenance. The literal CLI command is `tests/test_playbook_cli.py` and CI job `cli-default`.
- Import of an on-disk baseline by path and SHA-256, without copying it into git.
- Structural kickmix fixtures that cannot be marked verified.
- Invsqrt cost from kickmix counts, source labeled, leaderboard left null.
- Zip layout checks. Playbook refuses to package unverified tasks.
- Fetch script that does not download unless a person passes `--download`.
- CI workflow that installs `requirements-baseline.txt` and runs unittest.

## Next, in issue order

1. [Issue 8](https://github.com/noetl/quantum/issues/8). A person accepts the
   Kaggle rules and downloads `data/` on a machine that will not commit it.
   Record the real verifier entry point and the sample zip names.
2. [Issue 4](https://github.com/noetl/quantum/issues/4). Call that entry point.
   Set `competition_verified` only from it. Keep salt notes: a local salt is
   not the leaderboard salt.
3. [Issue 5](https://github.com/noetl/quantum/issues/5). A PASS JSON `score`
   from the official script is now the authoritative task cost (FR-004).
   Diff `verifiers/` metric code against FR-006, FR-007, and FR-008 before
   closing those markers. Until then dqi `R(ε)` and dfthcsos `λ_eff` stay
   unapplied, and the hub geometric mean is not `leaderboard_score`.
4. [Issue 7](https://github.com/noetl/quantum/issues/7). After verification
   can pass, let the package step call `vqcc.packaging` on the accepted files.
5. [Issue 3](https://github.com/noetl/quantum/issues/3) and
   [issue 9](https://github.com/noetl/quantum/issues/9). Replace
   `tasks/*/generate.py` refusals with generators that emit kickmix circuits,
   keep the previous accepted artifact when the verifier rejects a proposal,
   and log only measured costs.

## Explicitly out of scope until someone asks

- Accepting competition rules, joining, or uploading a submission.
- Spending money or publishing a Kaggle notebook.
- Committing the dataset, `kickmix.so` from the Kaggle image, or a submission zip.
- Treating the paper's published reference counts (for example invsqrt
  `Q = 260`) as a result from this repository.
