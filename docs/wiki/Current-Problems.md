# Current Problems / Open Questions

**Last refreshed:** 2026-11-18 (UTC). Canonical numbers: [`STATE.md`](https://github.com/noetl/quantum/blob/main/STATE.md) and [Status](Status).

## 1. dqi: the multiplier redesign is the only real lever left

- dqi charges `R × Q² × T_mean`, where `T_mean` is the per-shot mean Toffoli count the verifier measures. Q is already 1893 with zero reuse headroom (peak live qubits equal the header). So only Toffolis can move the score.
- The Toffolis sit in GF(2^b) multiply-accumulate blocks. Each `CCX` adds one bilinear product into an accumulator. Peephole rewriting has been exhausted:
  - Sound uncompute rewrites: **1** remains after the PR #30 correctness fix. It lowers the static count by 1 but raises the measured `T_mean` by 0.7, so it is not kept.
  - The "CX-blocked" pairs are not uncomputes. One Toffoli can be saved in all ~5.7M (see the [Decisions Log](Decisions-Log)).
- **What would move dqi:** a lower-multiplicative-complexity GF(2^12) multiplier, for example Karatsuba-style or other bilinear formulas of lower rank, or a different reduction. It would have to be generated, proven equivalent (verifier PASS at full shots), keep Q ≤ 1893, and lower `T_mean`, not only the static count.
- **Status:** not started. It is a separate project, larger than anything else in this repo.

## 2. invsqrt: stuck at the v9 tie

- Best is 2068786.6405086848 (Kaggle v9, tied by v14). Q 259, Toffoli 7735, T 1.
- All 11 shared-control candidates are same-wire re-accumulates (control written by `X`). The qubit-reuse headroom is already spent. No known lever.

## 3. dfthcsos: stuck at reference

- No candidate has ever been written. The profile finds 0 shared-control candidates and 0 uncompute pairs.
- **Open question:** Q is 730 against a per-file width of 119. Is a cross-file qubit reduction valid under the verifier? Not investigated.

## 4. Submission decision (owner)

- Nothing meets the first-submission bar set for v14 (dqi PASS below reference and invsqrt at or below 2068786.64, from one run where all three tasks PASS).
- **Open:** is an invsqrt-only package (invsqrt 2068786.64, dqi and dfthcsos at reference, all PASS in one run) worth a first submission? The first submission needs the owner's sanity check (package contents plus measured scores in one message). No submission has been made.

## 5. Deadline

- Milestone cutoff, per the owner: **2026-11-20**. No buildable lever lands before then. The choice at the cutoff is "no submission" or "owner-approved invsqrt-only package".

## 6. Spec clarifications still open

- FR-006 (dqi `R(ε)`), FR-007 (dfthcsos `λ_eff`) and FR-008 (leaderboard aggregate) stay `[NEEDS CLARIFICATION]`. See [Tutorial 9: Open questions](Tutorial-09-Open-Questions).
