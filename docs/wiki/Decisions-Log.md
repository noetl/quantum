# Decisions and Retractions Log

Append-only, newest first. Each entry was correct on its date. Where an entry
disagrees with [`STATE.md`](https://github.com/noetl/quantum/blob/main/STATE.md),
`STATE.md` is current.

## 2026-11-20: Reframed. Two tracks, and the submission record corrected

- **Withdrawn:** "a GF(2^12) multiplier redesign is the real remaining headroom" (STATE.md, 2026-11-18). It held only relative to the reference decoder. Public circuits already replace the whole decoder (5.7M → 366k Toffolis, 1,893 → 890 qubits).
- **Clarified:** our rewrite pass is a tidy pass worth about 1× (≈ 1.0013 overall). Real gains come from per-task algorithm redesigns.
- **Added (PR #34):** a portfolio pipeline that wraps other authors' public circuits, hash-pinned and credited, verified at several salts. It is worth ≈ 28× and counts for **leaderboard ranking only**: it is not original work and is not prize-eligible.
- **Corrected:** "no submission has ever been made" was true only of this repository. Account `kadyapam` has 8 submissions from 2026-10-23 to 27 (best 21.37712, Kaggle), made by Dimitri outside this repo, and their messages credit public circuits by other teams.

## 2026-11-18: Profiler label renamed (PR #31)

- `structure.toffoli.match.*.control_mutated` is now `same_wire_reaccumulate`. The old name read as "an uncompute blocked by a control write", which is what produced retraction R2 below.
- No behaviour change. History rows for v10–v14 keep the old name, because that is what those logs print.

## 2026-11-18: RETRACTED (R2): the "CX-blocked uncompute" lever

- **Claim (withdrawn):** 36,849 dqi uncompute pairs were blocked by a `CX` on a control. A measure-then-Clifford-correct uncompute (`CZ(a,b)` then `CZ(c,b)`) would unlock them, with a ceiling of about 0.64%.
- **What the pairs really are:** a later `CCX` on the same control wires and the same target after a control changed. With `a' = a⊕c` it leaves `t = ab ⊕ a'b'`. That is a GF(2^b) multiply-accumulate, not an uncompute. Example from dqi:
  ```
  CCX q828 q1833 q1851 ; CX q1834 q1833 ; CX q829 q828 ; CX q830 q828 ; CX q1835 q1833 ; CCX q828 q1833 q1851
  ```
- **Full dqi scan** (same-wire `CCX` pairs, target untouched in between):

  | Controls changed between the two `CCX` | Pairs |
  | :-- | --: |
  | both, by `CX` only | 523,899 |
  | both, mixed with `CCX`/`HMR`/`R`/`X` | 6,312 |
  | **exactly one, by `CX`** | **1** |

- The exact identity `CCX a b t; CX c a; CCX a b t ≡ CX c a; CCX c b t` needs exactly one changed control. With both changed, `ab ⊕ (a⊕x)(b⊕y) = ay ⊕ xb ⊕ xy` has bilinear rank 2, so two Toffolis are needed either way.
- **Decision:** not built. It is worth at most 1 Toffoli in ~5.7M. No Kaggle run.
- **Lesson:** check what the circuit actually does before sizing a lever from a profiler label.

## 2026-11-18: Correctness fix, dqi PASSes but is worse than reference (PR #30)

- PR #30 fixes four AND-tracker soundness bugs (below). Each has a regression test that fails on the old code. 10,800 fuzzed circuits (windows 1, 2, 4, 16) show 0 mismatches.
- **local** dqi: PASS, 0/102,400 value and phase errors, 24439469791639.395, which is above the reference 24439466758900.453. Only 1 sound uncompute remains. It lowers the static Toffoli count by 1 and raises the measured per-shot mean by 0.7.
- **Decision:** not kept (the rule is strictly lower). No Kaggle run, nothing submitted.
- The flaky test `test_recompute_after_del_and_replays_when_controls_stay` was **not** this bug. It compared outcome sets over 8 unseeded shots. It is now seeded and uses 256 shots.

## 2026-11-17: RETRACTED (R1): the dqi "−762 Toffoli" gain

- **Claim (withdrawn):** the v14 dqi candidate cut Toffoli 5,725,461 → 5,724,699.
- **Kaggle v14 measured it:** official verifier **FAIL**, phase errors 50,948/102,400, value errors 0.
- **Root cause:** dqi uncomputes AND chains in reverse on one measurement bit:
  ```
  HMR q1815 b ; CZ q1814 q839 if b
  HMR q1814 b ; CZ q1813 q838 if b    <- resets q1814 and rewrites b
  ```
  `_AndTracker.feed()` held an `HMR` and deferred its `CZ` without `_flush_conflicts`. So pair k ran after pair k+1, on a reset control and an overwritten bit.
- **Also found:** a fuzzer found a conditional `R`/`HMR` taken as a `|0>` proof, and a `SWAP` with a named qubit taken as a `|0>` proof. Code review found delayed pairs crossing `PUSH/POP_CONDITION` (this one did not occur in dqi). 761 of the 762 "saved" Toffolis relied on these false proofs.
- **How it was localized:** every component except the AND tracker gives 0 errors on its own. Allowing only the first deferral gives 0 errors, and every larger range fails.

## 2026-11-17: Slowdown fixed (PR #27)

- v13 timed out on invsqrt (3780 s) and dqi (7200 s cap). `vqcc/qubit_values.py` nested both controls' full frozen values in each `CCX` token, which doubled along AND chains (one invsqrt value reached 4,149,057 characters).
- **Fix:** tokens are interned to integer ids. v14 then completed every task (invsqrt 4.6 s, dqi 6271 s for 86M gates).

## 2026-11-17: Hard deadline (PR #26)

- v11 and v12 were killed at Kaggle's 12 h limit with no optimizer output. Each transform now runs in a child process killed at one absolute deadline. v13 confirmed the deadline holds.

## 2026-11-13: invsqrt Q 260→259 (PR #20, Kaggle v9)

- Scratch-qubit reuse freed one qubit. Kaggle PASS 2068786.6405086848, −0.385% vs reference. It is still the only measured gain.

## 2026-11-11/12: Clifford shrinking is not a cost reduction (v7, v8)

- The verifier accepted shorter invsqrt and dqi files with identical scores. Clifford-only shrinks are no longer sent to the verifier.
