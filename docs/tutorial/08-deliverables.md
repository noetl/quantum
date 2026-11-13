# 8. Deliverables and acceptance criteria

[Current work](07-current-work.md) · [Index](README.md) · Next: [Open questions](09-open-questions.md)

Checklists for the workstreams that are still the team's contract. Each item
cites the spec. A checked box is something the repo or a posted Kaggle log
already shows. An open issue stays open even when some of its boxes are
checked. Partial means the remaining boxes are the work.

Spec file: `specs/001-noetl-pipeline/spec.md` on main `da8490e`.

## Playbook runtime — issue [#2](https://github.com/noetl/quantum/issues/2), closed

US5, FR-016, SC-001, SC-005.

- [x] `noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` from the
      repo root, no competition data, finishes on NoETL 5.3.2.
- [x] The JSON lists every step. `leaderboard_score` is null. Verification is
      `blocked`. No zip is written.
- [x] CI job `cli-default` runs that command.

## Data fetch — issue [#8](https://github.com/noetl/quantum/issues/8), closed

FR-019. Constitution principle III.

- [x] `scripts/fetch_data.sh` prints the Kaggle CLI steps and does not download
      unless `--download` is passed.
- [x] `data/`, submission archives, and `kickmix.so` stay git-ignored.
- [x] No automation accepts the rules, joins, or uploads.

## Task adapters — issue [#3](https://github.com/noetl/quantum/issues/3), open

US1, US2, FR-001, FR-002, FR-003.

- [x] Separate adapt steps for invsqrt, dqi, and dfthcsos.
- [x] Competition mode writes no circuit when `data/` has no baseline.
- [x] A file that is present is recorded by path and SHA-256 and is not marked
      verified by the import itself.
- [x] Structural mode writes a kickmix fixture labeled `structural_fixture`.
- [ ] Confirm path and SHA-256 recording on a fresh read of a real Kaggle
      provenance file. Version 9's evidence names invsqrt `candidate-0.kmb`
      with sha256 prefix `7e205ced…f9a7`. The full hash is not copied here.
      Version 8 imported the baselines (`role: imported_baseline`) but this
      checklist does not treat that as closing the issue.

## Verifier — issue [#4](https://github.com/noetl/quantum/issues/4), open

US1 scenarios 1 and 2, FR-010, FR-011.

- [x] Missing `data/verifiers` blocks, and `competition_verified` stays false.
- [x] The three official scripts are called with `--seed` and no weakening flag.
- [x] A generic `verify` hook cannot set `competition_verified`. A
      `.vqcc-fixture` tree cannot either.
- [x] Versions 7 and 8 recorded `verifier_status: PASS` and a JSON `score` on
      the reference sample.
- [ ] The issue stays open until the team accepts a playbook run on `main`
      against the real data as the close-out. Version 9 finished: optimize
      exit 0, run `20261113T015716Z-fea5b448`, verifier `PASS` on invsqrt's
      retained candidate and on the dqi and dfthcsos baselines. No submission
      was made. This page does not close the issue.

## Cost — issue [#5](https://github.com/noetl/quantum/issues/5), open

FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-018, SC-002.
Also issue [#13](https://github.com/noetl/quantum/issues/13), closed, for the
JSON parse itself.

- [x] A cost names its source. A PASS JSON `score` is that source (FR-004).
- [x] invsqrt's shared product is `Q * (Toffoli + T/4)`. The pipeline does not
      apply paper Z_POW pricing on its own (FR-005). The official score still
      includes the rotation term; the cost step copies the JSON number.
- [x] dqi and dfthcsos do not silently pick hub versus paper inside
      `scripts/score.py`. Callers pass `--source`.
- [x] The hub geometric mean is opt-in, labeled unconfirmed, and is not
      `leaderboard_score` (FR-009, FR-016).
- [ ] FR-006, FR-007, and FR-008 remain `[NEEDS CLARIFICATION]`. Do not check
      this box by editing the tutorial. See [Open questions](09-open-questions.md).
- [ ] dfthcsos constraint checks (128-qubit cap, 20 mHa, the paper floors) are
      documented. They are not a measured acceptance of a new factorization
      from this team (FR-018).

## Provenance and the experiment log — issue [#6](https://github.com/noetl/quantum/issues/6), open

US4, FR-015, FR-020, SC-004.

- [x] Each playbook run writes `runs/<id>/provenance.json`.
- [x] The committed experiments table has no invented Local or LB cell.
- [x] Version 7 and version 8 provenance records exist as notebook output.
      They are not committed.
- [ ] A local-salt note on an integrated run is still the remaining close-out
      in the issue. The runs above passed `--seed 20261108` and say a local
      pass is not a leaderboard pass. The issue is still open.

## Packaging — issue [#7](https://github.com/noetl/quantum/issues/7), open

US3, FR-011, FR-012, FR-013, FR-014, SC-003.

- [x] Layout checks reject a missing task file, an angle-index gap, an extra
      file, and a `submission.npz` missing a required key.
- [x] The playbook does not present a bundle as ready while verification is
      false. On versions 7 and 8, status was `verified_not_packaged` and
      `zip_written` was false because packaging was not armed.
- [ ] No submission zip has been produced from an accepted optimize candidate.
      Version 9 retained invsqrt and the notebook stayed private. No Kaggle
      submission was made.
- [ ] The sample's `angle_k_*.kmb` names use an extension. The packager still
      requires extensionless hub names. That is unresolved. Do not "fix" it
      inside a docs change.

## Optimization loop — issue [#9](https://github.com/noetl/quantum/issues/9), open

US2 scenarios 1 and 2, FR-001, FR-003, FR-004, FR-010, FR-011.
Shipped in [PR #15](https://github.com/noetl/quantum/pull/15), tightened in
[PR #16](https://github.com/noetl/quantum/pull/16).

- [x] One task's attempt does not write the other tasks' files.
- [x] A proposal the verifier rejects does not replace the retained artifact.
      Version 7 is the example: invsqrt and dqi `rejected`, scores unchanged.
- [x] `tasks/*/generate.py` still writes nothing.
- [x] A pass that does not lower charged weight or `Q` writes no file.
      Version 8 is the example.
- [x] Version 9 retained invsqrt at 2068786.6405086848, strictly below
      2076774.233715282, verifier `PASS`. dqi and dfthcsos wrote no
      candidate. Evidence: [issue #9 comment](https://github.com/noetl/quantum/issues/9#issuecomment-6844754839).
      Issue [#9](https://github.com/noetl/quantum/issues/9) stays open; this
      box records the invsqrt result.

## Cost-targeted passes — issue [#17](https://github.com/noetl/quantum/issues/17), open

US2, FR-001, FR-003, FR-004, FR-010, FR-011. FR-006 and FR-007 are not in
scope for the code. Shipped in [PR #18](https://github.com/noetl/quantum/pull/18).

- [x] Version 7 fields are broken out in `vqcc/cost_breakdown.py`. The products
      match the printed scores. See [Scoring](04-scoring.md).
- [x] Measurement uncompute is implemented and covered by kickmix simulation
      on small circuits built in this repo.
- [x] Version 8 reports `and_uncomputes: 0` on invsqrt, dqi, and dfthcsos.
      The pass ran. It found nothing to delete.
- [x] dfthcsos "no candidate" on version 7 is explained: nothing commuted into
      the horizon, and the files have no T or fine `Z_POW`. Version 8 then
      refused the Clifford-only shrink as well.
- [ ] A Kaggle run of the measurement-uncompute pass that lowers a charged
      count and keeps a strictly lower PASS score. Version 9 reports
      `and_uncomputes` 0 on invsqrt, dqi, and dfthcsos. The invsqrt score
      that moved is the scratch-reuse result under issue
      [#19](https://github.com/noetl/quantum/issues/19).

## Structural passes — issue [#19](https://github.com/noetl/quantum/issues/19), open

US2, FR-001, FR-003, FR-004, FR-010, FR-011. FR-006, FR-007, and FR-008 are
not edited. Shipped in [PR #20](https://github.com/noetl/quantum/pull/20).

- [x] The optimize step logs a structure profile.
- [x] Shared-control factoring and scratch reuse have unit tests with kickmix
      simulation on small circuits. PR #20 reports 87 tests and 1 skipped.
- [x] DSL validation of both playbooks was recorded on 2026-11-12, server
      3.156.2, digest `sha256:29b2831fdd2444fab0bbc8915283a22ac86532393111f3a3cdad782bf6b1c4be`.
      This tutorial does not re-validate them because it does not edit them.
- [x] The Kaggle `structure` report for the sample files is version 9,
      run `20261113T015716Z-fea5b448`. Input-circuit counts are in
      [History](06-history.md). Evidence: [issue #19 comment](https://github.com/noetl/quantum/issues/19#issuecomment-6844754721).
- [x] invsqrt's retained score 2068786.6405086848 is strictly lower.
      `reuse_headroom_vs_header` was 1 and Q went 260 → 259. Shared-control
      factoring applied 0 times. dqi (832 shared-control candidates, 222
      matching uncompute pairs, headroom 0) and dfthcsos (0 / 0 / headroom 0,
      per file) wrote no candidate.

## Explicitly not a deliverable until someone asks

- Accepting the rules, joining, or uploading a submission.
- Publishing the Kaggle notebook.
- Committing the dataset, `kickmix.so`, or a submission zip.
- Treating the paper's reference counts as a result this repository measured.
  The counts in [Scoring](04-scoring.md) are labeled as verifier JSON from the
  notebook.
