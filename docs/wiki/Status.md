# Status

**Last refreshed:** 2026-11-18 (UTC), main `3e6626f`.
**Canonical source:** [`STATE.md`](https://github.com/noetl/quantum/blob/main/STATE.md) in the repo. This page is a copy of its headline numbers. If they disagree, `STATE.md` wins.
**Refresh cadence:** every Kaggle run, every merged optimizer PR, and every retraction.

> **Kaggle** = the official verifier's JSON `score` measured in a private Kaggle
> notebook run. **local** = the same official verifier run on a developer machine
> against the reference circuits. Only Kaggle numbers can justify keeping or
> submitting a candidate.

## Scores (lower is better)

| Task | Reference (Kaggle) | Best measured on Kaggle | v14 (Kaggle) | Latest local | Where it stands |
| :-- | :-- | :-- | :-- | :-- | :-- |
| invsqrt | 2076774.233715282 | **2068786.6405086848** (v9, PASS, Q 259) | PASS 2068786.6405086848 | PASS 2068786.6405086848 | −0.385% vs reference; tied since v9 |
| dqi | 24439466758900.453 | reference | candidate **FAIL** (phase errors 50948/102400) | PASS 0/102400, 24439469791639.395 | the correct candidate is **worse** than reference, not kept |
| dfthcsos | 3355599588.3155375 | reference | PASS on reference, no candidate | — | at reference |

## Submittable: nothing yet

- **No submission has ever been made.** The notebook stays private.
- The owner's bar for the first submission was dqi PASS below reference and invsqrt at or below 2068786.64, in one run where all three tasks PASS. v14 did not meet it.
- The only measured gain is invsqrt (v9, tied by v14). Whether an invsqrt-only first submission is worth it is an open owner decision. See [Current Problems](Current-Problems).
- Packaging ([#7](https://github.com/noetl/quantum/issues/7)) is fixed (PR #28) and builds the official file layout.

## Run history

| Version | main | Result (Kaggle) |
| :-- | :-- | :-- |
| 6–8 | PRs #15, #16, #18 | every task at reference |
| **9** | `da8490e` (PR #20) | **invsqrt PASS 2068786.64** (Q 260→259); others at reference |
| 10 | `5e22448` (PR #23) | no change |
| 11, 12 | PRs #24, #25 | killed at Kaggle's 12 h limit, no optimizer output |
| 13 | `38c11d2` (PR #26) | deadline held; invsqrt and dqi timed out (a throughput regression); all at reference |
| **14** | `9208fa2` (PR #27) | first full pass on every task; invsqrt tie; **dqi candidate FAIL**; dfthcsos at reference |

There has been no Kaggle run since v14. The next one starts only when a local candidate passes the official verifier with a strictly lower score. The full table is in [Tutorial 6: Optimization history](Tutorial-06-History).

## Merged since v14

| PR | What | Effect on scores |
| :-- | :-- | :-- |
| [#29](https://github.com/noetl/quantum/pull/29) | Docs: names the exact NoETL 5.3.2 distribution (PyPI wheel `noetl==5.3.2`) | none |
| [#30](https://github.com/noetl/quantum/pull/30) | Fixes four AND-tracker soundness bugs behind the v14 dqi FAIL | dqi now PASSes locally, worse than reference |
| [#31](https://github.com/noetl/quantum/pull/31) | Renames the profiler label `control_mutated` to `same_wire_reaccumulate` | none (label only) |

## Live threads

- [#19](https://github.com/noetl/quantum/issues/19): structural optimization, root causes and retractions
- [#9](https://github.com/noetl/quantum/issues/9): per-task loop, per-run evidence
- [#7](https://github.com/noetl/quantum/issues/7): submission packaging and the submit gate

See also [Current Problems](Current-Problems), [Decisions Log](Decisions-Log) and [Architecture](Architecture).
