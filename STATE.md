# VQCC state: the single source of truth

**As of 2026-11-20 (UTC).** This file is the canonical snapshot. The wiki
[Status](https://github.com/noetl/quantum/wiki/Status) page, issues
[#19](https://github.com/noetl/quantum/issues/19),
[#9](https://github.com/noetl/quantum/issues/9) and
[#7](https://github.com/noetl/quantum/issues/7), and `HANDOVER.md` point here.
When they disagree with this file, this file wins. Update it in the same PR
as any change to scores, levers or submission state.

Every score below says where it came from:

- **Kaggle**: measured on Kaggle, either by the official verifier inside a
  private notebook run or as a leaderboard score.
- **local**: the same official verifiers run on a developer machine against
  the competition data. Not a Kaggle measurement.

## How the leaderboard scores

`score = (ratio_invsqrt × ratio_dqi × ratio_dfthcsos)^(1/3)`, where each
`ratio = reference cost / submitted cost` is the per-task improvement factor
from the official verifier's JSON `score`. The reference circuits score
exactly **1.0**. If any task fails the verifier on the hidden private-board
salt, the whole submission scores 0 there.

Task costs: invsqrt `Q × (Toffoli + T/4)`; dqi `R(ε⁺) × Q² × T` (per-shot
mean Toffolis); dfthcsos `λ_eff × T × Q`.

## Two tracks. Keep them apart.

| | Track A: our optimizer | Track B: wrapped public circuits |
| --- | --- | --- |
| What it is | `playbooks/vqcc_optimize.yaml`: the NoETL rewrite pass over the reference circuits | `playbooks/vqcc_portfolio.yaml` (PR #34): hash-pinned public circuits by other authors, verified at several salts, packaged by NoETL |
| Whose circuits | ours (rewrites of the reference) | **other authors'**, credited in `portfolio/CREDITS.md` |
| Score | **≈ 1.0013** | **≈ 28.24** |
| Counts for | ranking and prizes (it is original) | **leaderboard ranking only. Not original work, not eligible for prizes.** |

### Track A: our optimizer gets about 1×

| Task | Reference (Kaggle) | Our best (Kaggle) | Ratio |
| --- | --- | --- | --- |
| invsqrt | 2076774.233715282 | 2068786.6405086848 (v9, tied by v14, PASS, Q 259) | **1.0039** |
| dqi | 24439466758900.453 | reference (the correct candidate, local 24439469791639.395, is worse) | **1.0** |
| dfthcsos | 3355599588.3155375 | reference (no candidate) | **1.0** |
| **Geometric mean** | | | **≈ 1.0013** (calculated from the Kaggle-measured task scores; this package was never submitted) |

The rewrite pass makes provably exact local rewrites: phase merging,
inverse-pair cancellation, measurement-based Toffoli uncompute, shared-control
factoring and scratch-qubit reuse. It keeps the reference algorithm. The
reference circuits are already well compiled, so it finds almost nothing.

### Track B: wrapped public circuits get about 28× (ranking only)

Run `portfolio-20261120T060028Z-1e4f688f` on the NoETL 5.3.2 local runtime,
main `bc4c10a` (PR #34). The official verifiers ran on this machine (**local**)
at 5 salts: the default plus `noetl-salt-1..4`. The verifier's `--salt` was
used, never `--seed`.

| Task | Kept circuit (author) | Default-salt score (local) | Ratio | Worst of 5 salts | All 5 salts |
| --- | --- | --- | --- | --- | --- |
| invsqrt | `acc7b9c8` (maoxin123) | 74,361.67, Q 44 | **27.93×** | 27.93× | PASS |
| dqi | `f6b555a6` (manwithacat, on goodpjw2008 / Koushik Rudra) | 345,118,737,157.6, Q 890, 0 errors | **70.81×** | 70.49× (1 phase error in 102,400 at 2 of 5 salts, still PASS) | PASS |
| dfthcsos | `e6233e86` (weights 6ef06081 on maoxin123's loaders) | 294,642,169.5, Q 427 | **11.39×** | 11.39× | PASS |
| **Geometric mean** | | | **28.2410** (local calculation) | 28.1978 | |

- The 28.2410 matches the public score Kaggle measured for alex chilton's
  identical zip (28.24094). This repository has not submitted it, so there is
  no Kaggle measurement of our own.
- The rewrite pass, run as a polish, found nothing on any of the three
  circuits.
- **Ranking only. Not original work, not prize-eligible.** Credits:
  `portfolio/CREDITS.md`.

## Submission status

- **Account `kadyapam` has 8 submissions (2026-10-23 to 2026-10-27), best
  public leaderboard score 21.37712 (Kaggle).** They were made by Dimitri
  with a separate approach, outside this repository. Their messages credit
  other teams' public circuits (mrmeows, SomeJoint, heliosli and others).
  Nothing in this repo produced them, and the repo cannot reproduce them.
- **Nothing produced by this repository's pipelines has been submitted.**
  - The Track A invsqrt-only package (≈ 1.0013) was staged and held. It
    would not change the account's leaderboard position.
  - The Track B package is staged for the owner's decision. It ranks only
    and is not prize-eligible.
- A public notebook is not needed to submit. It is only a condition of the
  Milestone (Nov 20) and Longest Leader prizes. The Milestone leader is at
  31.74, so it is out of reach.

## Kaggle run history

| Version | main | Outcome (Kaggle-measured) |
| --- | --- | --- |
| 6–8 | PRs #15, #16, #18 | Every score at reference. |
| 9 | `da8490e` (PR #20) | **invsqrt PASS 2068786.6405086848** (Q 260→259). dqi and dfthcsos at reference. |
| 10 | `5e22448` (PR #23) | No change. invsqrt tie. |
| 11, 12 | PRs #24, #25 | Killed at Kaggle's 12 h limit. No optimizer output. |
| 13 | `38c11d2` (PR #26), scriptVersionId 370491848 | The deadline held. invsqrt (3780 s) and dqi (7200 s cap) timed out from a throughput regression; every score at reference. |
| 14 | `9208fa2` (PR #27), run `20261117T153014Z-33b3a27c` | First full pass on every task (dqi 6271 s for 86M gates). invsqrt PASS tie. **dqi candidate FAIL** (phase errors). dfthcsos at reference. |

There has been no Kaggle run since v14. Rule: start one only when a local
candidate passes the official verifier with a strictly lower score.

## Tried and ruled out

Full write-ups: [Decisions log](https://github.com/noetl/quantum/wiki/Decisions-Log)
and [#19](https://github.com/noetl/quantum/issues/19).

1. **Slowdown, fixed (PR #27).** Value-tracking tokens nested the full frozen
   value of both controls, which doubled along AND chains (one invsqrt value
   reached 4,149,057 characters). This caused the v13 timeouts. Tokens are
   now interned ids, and v14 completed every task.
2. **The dqi "−762 Toffoli" gain, retracted.** It came from optimizer bugs,
   and the official verifier failed it on Kaggle (v14). The cause: dqi
   uncomputes AND chains in reverse on one measurement bit, and the AND
   tracker held or deferred an `HMR`/`CZ` pair past the next pair without a
   conflict check. Three more soundness bugs were found by differential
   fuzzing: a conditional reset taken as a `|0>` proof, a `SWAP` with a
   named qubit taken as a `|0>` proof, and a delayed pair crossing
   `PUSH/POP_CONDITION`.
3. **Correctness fix (PR #30).** All four bugs are fixed, each with a
   regression test that fails on the old code. 10,800 fuzzed circuits show 0
   mismatches. dqi now passes locally at full shots, and its score is worse
   than reference (only 1 sound uncompute rewrite remains).
4. **The CX-blocked uncompute lever, retracted.** The profiler's 36,849
   `control_mutated` pairs (now `same_wire_reaccumulate`, PR #31) are
   GF(2^b) multiply-accumulate steps (`t ^= ab`, then `t ^= a'b'`), not
   uncomputes. The only exact Toffoli-saving identity needs exactly one
   control changed, which applies to **1 pair** in all of dqi's ~5.7M
   Toffolis. 523,899 pairs have both controls changed by CX, and 6,312 have
   both changed by a mix of gates. These have bilinear rank 2, so both
   Toffolis are needed. Not built.

## Where real gains come from

The earlier claim here, that a GF(2^12) multiplier redesign was "the real
remaining headroom", is withdrawn. It was true only relative to the
reference decoder. The public field has already replaced the whole design.

- **Our rewrite pass is a tidy pass.** It gets about 1×, and at most about
  +0.01–0.1% as a polish on top of strong circuits.
- **Real gains are per-task algorithm redesigns.**
  - invsqrt: new fixed-point arithmetic, 260 → 44 qubits.
  - dqi: a different decoder family, 5.7M → 366k Toffolis and 1,893 → 890
    qubits. dqi has the largest leverage, because Q is squared in its cost.
  - dfthcsos: a refitted factorization and new lookup loaders.

  This is weeks to months of specialist work per task, with uncertain
  results. It is not an extension of the rewrite pass.
- **The wrapper path (Track B) imports strong external circuits.** It
  reaches the public plateau (≈ 28.24, shared by about 100 teams) for
  ranking only. Multi-salt verification protects the private board. Beating
  the 31.74 leader needs about 1.42× better combined than the public best,
  which only original redesigns can deliver.

## Deadline

The owner's target for 2026-11-20 is a submission done and scored by about
1:00 PM PT (21:00 UTC), ahead of the 3:59 PM PT cutoff. Any submission needs
the owner's explicit go.

## How to reproduce

- Track A (NoETL only): `noetl run playbooks/vqcc_optimize.yaml --runtime local`,
  using the PyPI wheel `noetl==5.3.2` and `kickmix==1.0.0`.
- Track B: `scripts/fetch_portfolio.sh`, then
  `noetl run playbooks/vqcc_portfolio.yaml --runtime local --json --set data_dir=<competition data> --set candidates_dir=candidates`.
- Validate playbook edits with `POST https://noetl.ai/api/dsl/validate`.
- Local verifier times on this machine: invsqrt (44 qubits) about 100 s,
  dqi (890 qubits) about 95 s, dfthcsos about 17 s. Kaggle runs are private
  Save & Run All from `main` (see `HANDOVER.md`).
