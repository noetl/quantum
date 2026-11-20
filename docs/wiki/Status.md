# Status

**Last refreshed:** 2026-11-20 (UTC).
**Canonical source:** [`STATE.md`](https://github.com/noetl/quantum/blob/main/STATE.md) in the repo. This page is a copy of its headline numbers. If they disagree, `STATE.md` wins.
**Refresh cadence:** every Kaggle run, every merged pipeline PR, every submission and every retraction.

> **Kaggle** = measured on Kaggle (an official verifier run in a private
> notebook, or a leaderboard score). **local** = the same official verifiers
> run on a developer machine. The leaderboard score is the geometric mean of
> the three per-task ratios `reference cost / submitted cost`; the reference
> scores 1.0.

## Two tracks. Keep them apart.

| | Our optimizer (Track A) | Wrapped public circuits (Track B) |
| :-- | :-- | :-- |
| Playbook | `vqcc_optimize.yaml` | `vqcc_portfolio.yaml` ([PR #34](https://github.com/noetl/quantum/pull/34)) |
| Whose circuits | ours (rewrites of the reference) | **other authors'** ([credits](https://github.com/noetl/quantum/blob/main/portfolio/CREDITS.md)) |
| invsqrt / dqi / dfthcsos | 1.0039× (Kaggle) / 1.0× / 1.0× | 27.93× / 70.81× / 11.39× (local, all 5 salts PASS) |
| Score | **≈ 1.0013** | **≈ 28.24 (local; worst salt 28.20)** |
| Counts for | ranking and prizes | **ranking only. Not original, not prize-eligible.** |

## Submission status

- **Account `kadyapam`: 8 submissions, 2026-10-23 to 27, best public score 21.37712 (Kaggle).** Made by Dimitri with a separate approach, outside this repository. Their messages credit other teams' public circuits.
- **Nothing from this repository's pipelines has been submitted.** The Track A package (≈ 1.0013) is held, because it would not change the account's position. The Track B package is staged for the owner's decision.
- A public notebook is needed only for the Milestone and Longest Leader prizes, not to submit.

## Track A details (our optimizer)

| Task | Reference (Kaggle) | Best measured on Kaggle | v14 (Kaggle) | Latest local |
| :-- | :-- | :-- | :-- | :-- |
| invsqrt | 2076774.233715282 | **2068786.6405086848** (v9, PASS, Q 259) | PASS 2068786.6405086848 | PASS 2068786.6405086848 |
| dqi | 24439466758900.453 | reference | candidate **FAIL** (phase errors 50948/102400) | PASS 0/102400, 24439469791639.395 (worse, not kept) |
| dfthcsos | 3355599588.3155375 | reference | PASS on reference, no candidate | — |

## Track A Kaggle run history

| Version | main | Result (Kaggle) |
| :-- | :-- | :-- |
| 6–8 | PRs #15, #16, #18 | every task at reference |
| **9** | `da8490e` (PR #20) | **invsqrt PASS 2068786.64** (Q 260→259); others at reference |
| 10 | `5e22448` (PR #23) | no change |
| 11, 12 | PRs #24, #25 | killed at Kaggle's 12 h limit, no optimizer output |
| 13 | `38c11d2` (PR #26) | deadline held; invsqrt and dqi timed out (a throughput regression); all at reference |
| **14** | `9208fa2` (PR #27) | first full pass on every task; invsqrt tie; **dqi candidate FAIL**; dfthcsos at reference |

There has been no Kaggle run since v14. The next one starts only when a local candidate passes the official verifier with a strictly lower score. The full table is in [Tutorial 6: Optimization history](Tutorial-06-History).

## Pipeline PRs since v14

| PR | What | Effect on scores |
| :-- | :-- | :-- |
| [#29](https://github.com/noetl/quantum/pull/29) | Docs: names the exact NoETL 5.3.2 distribution (PyPI wheel `noetl==5.3.2`) | none |
| [#30](https://github.com/noetl/quantum/pull/30) | Fixes four AND-tracker soundness bugs behind the v14 dqi FAIL | dqi now PASSes locally, worse than reference |
| [#31](https://github.com/noetl/quantum/pull/31) | Renames the profiler label `control_mutated` to `same_wire_reaccumulate` | none (label only) |
| [#34](https://github.com/noetl/quantum/pull/34) | Portfolio pipeline: hash-pinned external circuits, multi-salt verification | Track B (ranking only) |

## Live threads

- [#19](https://github.com/noetl/quantum/issues/19): structural optimization, root causes and retractions
- [#9](https://github.com/noetl/quantum/issues/9): per-task loop, per-run evidence
- [#7](https://github.com/noetl/quantum/issues/7): submission packaging and the submit gate

See also [Current Problems](Current-Problems), [Decisions Log](Decisions-Log) and [Architecture](Architecture).
