# VQCC state: the single source of truth

**As of 2026-11-18 (UTC), main `3e6626f`.** This file is the
canonical snapshot. The wiki [Status](https://github.com/noetl/quantum/wiki/Status)
page, issues [#19](https://github.com/noetl/quantum/issues/19),
[#9](https://github.com/noetl/quantum/issues/9) and
[#7](https://github.com/noetl/quantum/issues/7), and `HANDOVER.md` point here.
When they disagree with this file, this file wins. Update it in the same PR
as any change to scores, levers or submission state.

Every score below is labelled with where it came from:

- **Kaggle**: the official verifier's JSON `score`, measured inside a private
  Kaggle notebook run. Only these numbers can justify keeping or submitting
  a candidate.
- **local**: the same official verifier run on this machine against the
  competition reference circuits. Useful for debugging, but not a
  measurement anyone should quote as a result.

## Scores (lower is better)

| Task | Reference (Kaggle, every run) | Best measured on Kaggle | Latest run (v14, Kaggle) | Latest local (main `1bd630c`, unchanged by #31) | Position |
| --- | --- | --- | --- | --- | --- |
| invsqrt | 2076774.233715282 | **2068786.6405086848**, v9, PASS (Q 260→259, Toffoli 7735, T 1) | PASS 2068786.6405086848 (ties v9) | PASS 2068786.6405086848 | −0.385% vs reference; stuck at the v9 tie |
| dqi | 24439466758900.453 | reference (no candidate has ever been kept) | candidate **FAIL**: phase errors 50948/102400, value errors 0 (the "−762 Toffoli" was false) | PASS, 0/102400 errors, **24439469791639.395** | the correct candidate is **worse** than reference, so it is not kept |
| dfthcsos | 3355599588.3155375 | reference (no candidate has ever been written) | PASS on reference, no candidate | not rerun | at reference |

Formulas: invsqrt `Q × (Toffoli + T/4)`; dqi `R × Q² × T_mean`, where
`T_mean` is the per-shot mean Toffoli count the verifier measures (not the
static count); dfthcsos `λ × Toffoli × Q`. FR-006/007/008 in the spec stay
`[NEEDS CLARIFICATION]`.

## Submittable: nothing yet

- No submission has ever been made. The notebook
  `kadyapam/noetl-quantum-competition-pipeline-vqcc` is private.
- Owner rule: a package must come from **one** Kaggle run in which all three
  tasks' outputs are present and the official verifier returns PASS, with a
  strictly lower score. Before the first-ever submit, the package contents
  and measured scores go to the owner in one message.
- The bar set for v14 was dqi PASS below 24439466758900.453 and invsqrt at or
  below 2068786.64. v14's dqi candidate failed, so that bar was not met.
- The only measured improvement over reference is invsqrt (v9, tied by v14).
  Whether an invsqrt-only package (dqi and dfthcsos at reference) is worth a
  first submission is an **open owner decision**. It is not a standing
  approval.
- Packaging ([#7](https://github.com/noetl/quantum/issues/7)) was fixed in
  PR #28 (dfthcsos angle files under their official `.kmb`/`.kmx` names).

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

## Real remaining headroom

- **dqi: a GF(2^12) multiplier redesign.** This is the only material lever
  left. The Toffolis sit in the multiplier's bilinear products. Cutting them
  means lowering the multiplicative complexity of each GF(2^12) product
  (Karatsuba-style or other low-rank multiplication formulas, or a different
  reduction), not peephole rewriting. It is a separate, larger project:
  generate a new multiplier, prove it equivalent, keep Q at 1893 or below,
  and measure `T_mean`, because dqi charges the per-shot mean, not the
  static count. Nothing has been built or measured.
- **invsqrt: stuck at the v9 tie.** The 11 shared-control candidates are all
  same-wire re-accumulates (by `X`), and the qubit-reuse headroom is spent.
- **dfthcsos: stuck at reference.** The pass finds nothing (0 shared-control
  candidates, 0 uncompute pairs). A cross-file qubit reduction (Q 730 against
  a per-file width of 119) is unexplored, and its validity under the verifier
  is unknown.

## Deadline

The owner gave the milestone cutoff as **2026-11-20**. With no lever that
can be built in time, the realistic outcome for that cutoff is either no
submission or an owner-approved invsqrt-only package.

## How to reproduce

- Pipeline (NoETL only): `noetl run playbooks/vqcc_optimize.yaml --runtime local`,
  using the PyPI wheel `noetl==5.3.2` and `kickmix==1.0.0`. Validate playbook
  edits with `POST https://noetl.ai/api/dsl/validate`.
- Official dqi verifier, locally: about 4 s at 256 shots and about 85 s at
  the full 102,400 shots on 4 workers. Kaggle runs are private Save & Run All
  from `main`. See `HANDOVER.md`.
