# Handover: noetl/quantum VQCC optimization loop

Refreshed 2026-11-18 (UTC), main `3e6626f`. **Current scores, what has been
ruled out and the real remaining headroom are in [STATE.md](STATE.md), the
single source of truth.** This file is the operating manual: rules, the Kaggle
notebook, and how to run a round. Read `STATE.md` first, then this file, then
`specs/001-noetl-pipeline/spec.md`, then issues
[#19](https://github.com/noetl/quantum/issues/19) and
[#9](https://github.com/noetl/quantum/issues/9). The wiki dashboard is
<https://github.com/noetl/quantum/wiki/Status>.

## Goal

This repo is the team entry for the Kaggle competition "Google Quantum AI -
Verifiable Quantum Circuit Compilation" (VQCC). The owner's standing ask is:
keep iterating until there is a final, winning, ready-to-submit solution.
Each round:

1. Write an optimizer change on a new branch from current `main`, then open a PR.
2. When CI is green and the tests pass, merge it (squash, pinned to the head SHA).
3. Start a **private** Kaggle Save & Run All from `main`.
4. Watch the run and collect its outputs. Compare the scores with the bests,
   post the evidence on #19 and #9, then plan the next fix.

## Rules from the owner (do not break)

- The main-branch specs are the authority (`specs/001-noetl-pipeline/spec.md`).
  Track work in GitHub issues that cite spec FRs, and keep the wiki and the
  `docs/wiki/` mirror up to date.
- The pipeline must run entirely on NoETL: `noetl run playbooks/vqcc_optimize.yaml --runtime local`.
  Validate any playbook change with `POST https://noetl.ai/api/dsl/validate`,
  and record the server version and schema digest in the playbook header.
  The current pin is server 3.161.2,
  `sha256:25071111774314cbf0c83ee9925b53701c2228232574bda3b13b1e27d58b372c`.
- Start each new piece of work from `main`, in a new PR.
- **Standing permission:** merge optimizer PRs yourself when CI is green and
  the tests pass, then start the private Kaggle run from `main`. Docs-only PRs
  are for the owner to merge unless the owner says otherwise.
- **Kaggle:** keep the notebook private. Never publish, make public, share,
  invite anyone, or accept rules or terms without the owner's explicit OK.
  Submissions follow the owner's standing approval (2026-11-17), which has
  conditions:
  - submit only a package from **one** Kaggle run in which all three tasks
    PASS the official verifier, with a strictly lower score;
  - use the fixed packager (PR #28);
  - respect the daily limit;
  - submit from `main`;
  - before the **first-ever** submission, show the owner the package contents
    and the measured scores in one message.

  No submission has been made yet.
- A candidate is kept only if the official verifier returns `PASS` and the JSON
  `score` is strictly lower. Never claim a score that a Kaggle run did not
  measure.

- NoETL "5.3.2" means the PyPI wheel `noetl==5.3.2` (Rust CLI, noetl/cli tag
  `v5.3.2`). The noetl/noetl tag `pypi-v5.3.2` is only its build recipe; that
  tag's root `pyproject.toml` is not a distribution. Never `pip install` from a
  noetl/noetl checkout. Details in `docs/tutorial/01-environment.md`.

## Scoring (lower is better)

Current numbers, with Kaggle-measured and local results marked, are in
[STATE.md](STATE.md). In short:

| Task | Formula | Best measured on Kaggle | Source |
| --- | --- | --- | --- |
| invsqrt | Q × (Toffoli + T/4) | **2068786.6405086848** (Q 259, Toffoli 7735, T 1) | Version 9, tied by version 14 |
| dqi | R × Q² × T_mean (per-shot mean Toffoli) | **24439466758900.453** (Q 1893, Toffoli about 5.7M) | Reference |
| dfthcsos | λ × Toffoli × Q | **3355599588.3155375** (Q 730, Toffoli 93237) | Reference |

dqi profile: about 86M instructions, 3.13M SWAP, 53.9M CX, up to 857 live
ANDs on one qubit, and peak live qubits equal to the header (1893). It has no
spare qubits, so any dqi gain has to come from cutting Toffolis.

## Kaggle notebook

- Edit page: <https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc/edit>
  (account `kadyapam`). Settings: Internet ON, accelerator None, no persistence.
- Run with **Save Version → Save & Run All (Commit)**. The version name must be
  under 50 characters. Kaggle kills a run at 12 hours.
- Cell 1 clones `main` and checks that `ecb0f601` is an ancestor. Cell 5 is the
  optimizer launch. Since version 13 it tails the progress file so progress
  shows up live in the Kaggle log:

```bash
%%bash
cd /kaggle/working
rm -rf quantum
git clone https://github.com/noetl/quantum.git
cd quantum
git checkout main
echo "HEAD: $(git rev-parse HEAD)"
pip install -q noetl==5.3.2 kickmix==1.0.0 2>&1 | tail -3
date +%s > /kaggle/working/t0
mkdir -p /kaggle/working/runs
touch /kaggle/working/runs/optimize-progress.log
tail -n +1 -F /kaggle/working/runs/optimize-progress.log &
TAIL_PID=$!
set +e
noetl run playbooks/vqcc_optimize.yaml --runtime local --json --set data_dir=/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation --set runs_root=/kaggle/working/runs --set repo_root="$PWD" --set seed=20261108 > /kaggle/working/opt.log 2>&1
RC=$?
kill "$TAIL_PID" 2>/dev/null || true
wait "$TAIL_PID" 2>/dev/null || true
tail -c 20000 /kaggle/working/opt.log
echo "EXIT: $RC"
echo "ELAPSED: $(( $(date +%s) - $(cat /kaggle/working/t0) ))s"
```

The other cells rerun `vqcc_pipeline.yaml` and the reference verifiers, which
takes about 28 minutes. Leave them in place unless time runs short.

## History (see docs/tutorial/06-history.md for the full table)

| Version | scriptVersionId | main | Outcome |
| --- | --- | --- | --- |
| 9 | 368976547 | `da8490e` (PR #20) | invsqrt improved to 2068786.64 (`PASS`, Q 260→259). Others unchanged. |
| 10 | 369071305 | `5e22448` (PR #23) | No change. Every Toffoli match was rejected as `control_mutated`. |
| 11 | 369141743 | `b9bb74d` (PR #24) | Killed at 12 h. SWAP relabel was superlinear on dqi. |
| 12 | 369303709 | `513ad76` (PR #25) | Killed at 12 h. The 9 h budget did not hold, and no optimizer output survived. |
| 13 | 370491848 | `38c11d2` (PR #26) | The deadline held. invsqrt and dqi timed out from a throughput regression (fixed in PR #27). All tasks at reference. |
| 14 | not recorded (run `20261117T153014Z-33b3a27c`) | `9208fa2` (PR #27) | First full pass on every task. invsqrt PASS tie. The dqi candidate FAILED (phase errors; the cause was fixed in PR #30). dfthcsos at reference. |

## What PR #26 changed (now on main)

- Each streaming transform runs in a child process. The child is killed at one
  absolute deadline (`optimize_clock.deadline_epoch` in `state.json`): SIGTERM,
  then SIGKILL 60 s later. Each shell step is also wrapped in
  `timeout --signal=TERM --kill-after=60`.
- When a task times out, it keeps its previous artifact, and cost, package and
  record still run.
- The default optimize budget is now 25200 s (7 h): invsqrt 3780 s, dqi 17640 s,
  dfthcsos 3780 s. The env overrides are `VQCC_OPTIMIZE_BUDGET_S`,
  `VQCC_TASK_BUDGET_S` and `VQCC_TRANSFORM_BUDGET_S`.
- Correction after version 13: under PR #26, each transform was also capped by
  `transform_budget_s` (7200 s), so dqi got 2 h, not 17640 s. The cap is now
  16200 s, and each task's share still bounds it.
- Root cause of the overrun: the cancellation window scanned the whole
  cancellation window even when a gate had no inverse partner, and the
  deadline check was only cooperative.
- Progress lines are written to `runs/optimize-progress.log` and
  `runs/<run_id>/optimize/<task>.log`. A partial profile is saved atomically to
  `runs/<run_id>/optimize/<task>.profile.json`.

## Next steps for the new session

There has been no Kaggle run since version 14, and nothing is submittable.
See [STATE.md](STATE.md) for the reasons.

1. **Do not start a Kaggle run** until a local candidate passes the official
   verifier with a strictly lower score. The dqi verifier runs locally in
   about 4 s at 256 shots, and in about 85 s at the full 102,400 shots on 4
   workers. Use it before spending a 4–6 h Kaggle run.
2. **dqi:** the only material lever left is a lower-multiplicative-complexity
   GF(2^12) multiplier. That is a separate, larger project (see STATE.md,
   "Real remaining headroom"). Peephole uncompute rewriting is exhausted:
   1 sound rewrite remains after PR #30, and it does not lower the measured
   `T_mean`.
3. **Ruled out, so do not re-propose:**
   - the dqi "−762 Toffoli" candidate (an optimizer bug, FAIL on Kaggle);
   - the "CX-blocked uncompute pairs" lever (multiply-accumulates, not
     uncomputes: 1 applicable pair in all of dqi).

   The profiler label behind the second one is now `same_wire_reaccumulate`
   (PR #31). It is not headroom. Details:
   <https://github.com/noetl/quantum/wiki/Decisions-Log>.
4. **invsqrt** is stuck at the v9 tie, and **dfthcsos** at reference. The
   only unexplored idea is a cross-file qubit reduction for dfthcsos, and
   whether the verifier allows it is unknown.
5. **Owner decision pending:** whether an invsqrt-only package is worth a
   first submission. The milestone cutoff is 2026-11-20.
6. Any optimizer change needs regression tests plus differential fuzzing, as
   in PR #30, so a false gain cannot reach Kaggle again.

## Other open items

- There are stale `cursor/*` branches, all already merged by squash. They are
  safe to delete with the owner's OK.
- Unrelated repos in the same workspace: ehgraph (Rust, `noetl/ehgraph`) and
  qnetmon (`shastaranch/qnetmon`). Do not touch the qnetmon IonQ document
  ("stop, don't touch it"). Spec step 2 (FR-006/FR-007/FR-008) is blocked
  until the owner clarifies it.

## Team links

- Team hub: <https://dg-create.com/kaggle/quantum>
- Bot dashboard: <https://dg-create.com/tower/>
- GitHub user: `kadyapam`
