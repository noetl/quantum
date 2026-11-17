# Handover: noetl/quantum VQCC optimization loop

Written 2026-11-17 (UTC) for the next agent session that continues this work.
Read this whole file first, then `specs/001-noetl-pipeline/spec.md`, then
issues [#19](https://github.com/noetl/quantum/issues/19) and
[#9](https://github.com/noetl/quantum/issues/9).

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
- **Kaggle:** keep the notebook private. Never submit to the competition,
  publish, make public, share, invite anyone, or accept rules or terms without
  the owner's explicit OK. The final submission also needs the owner's OK.
- A candidate is kept only if the official verifier returns `PASS` and the JSON
  `score` is strictly lower. Never claim a score that a Kaggle run did not
  measure.

## Scoring (lower is better)

| Task | Formula | Current best | Source |
| --- | --- | --- | --- |
| invsqrt | Q × (Toffoli + T/4) | **2068786.6405086848** (Q 259, Toffoli 7735, T 1) | Version 9 |
| dqi | R × Q² × Toffoli | **24439466758900.453** (Q 1893, Toffoli about 5.7M) | Baseline |
| dfthcsos | λ × Toffoli × Q | **3355599588.3155375** (Q 730, Toffoli 93237) | Baseline |

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
| 13 | **370491848** | `38c11d2` (PR #26) | **Running at handover.** Started 2026-11-17 02:05 UTC (6:05 PM PT, Nov 16). |

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

1. **Set up a watch routine for version 13.** Check
   <https://www.kaggle.com/code/kadyapam/noetl-quantum-competition-pipeline-vqcc?scriptVersionId=370491848>
   read-only, never cancelling anything. Progress lines should appear live.
   It should finish about 8 to 9 hours after it started, around 10–11 UTC on
   Nov 17. Kaggle's hard limit is about 14:05 UTC.
2. **When it finishes,** download the outputs: `opt.log`, `runs/**/state.json`,
   the per-task logs and profiles, the official verifier outputs, and the cost.
   Then:
   - Compare each task's score with the bests above.
   - Confirm the deadline held: the end of the optimize step should be at or
     before `deadline_epoch`.
   - Report `structure.toffoli.match` (eligible versus control_mutated, split
     into undone, relabelled and open by opcode), `stats.and_replays`,
     `stats.shared_control_factors`, and any CCX rewrites.
   - Post the evidence on #19 and #9, and add the result to the version 13 row
     in `docs/tutorial/06-history.md` and its wiki mirror.
3. **Next optimizer lever, if dqi is still unchanged:** cut dqi's Toffoli count.
   The profile found 832 shared-control candidates and 222 matching uncompute
   pairs. Version 13 is the first run that can measure whether the
   restored-control matching (PR #24) turns them into rewrites. If most are
   still `open`, consider:
   - widening how far restored-control matching looks, within the time budget;
   - cheaper Toffoli constructions (temporary-AND ladders, measurement-based
     uncompute) for the blocks the profile finds (see #19).
4. **invsqrt:** further gains need a Toffoli cut. There are 11 shared-control
   candidates, and reuse headroom is already used.
5. **dfthcsos:** Q is 730 against a per-file width of 119, so look at whether a
   cross-file qubit reduction is valid under the verifier.
6. Repeat the loop until scores plateau. Then ask the owner before any Kaggle
   submission.

## Other open items

- PR #22 (the version 9 tutorial results and the validator pin) was folded into
  `main` by this handover commit. Its conflicting sections kept the newer text
  from `main`. You can close PR #22.
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
