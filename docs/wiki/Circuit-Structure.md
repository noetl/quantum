# Circuit structure

The Kaggle sample circuits are not in this repository. Competition data
stays out of git. This page is the structure report for issue 19: what the
version 8 run already showed, what kickmix's own blocks look like, and what
the optimize step will log on the next Kaggle run.

None of the numbers below is a new official score. Version 8's scores are
external evidence from that notebook. The kickmix figures are measurements
of circuits this environment built with kickmix 1.0.0. They are not the
reference files.

## What version 8 already measured

Run `20261112T030658Z-9813e023`, main `53304c8`. The rewrite found **0**
clean-AND uncomputes on every task. Clifford cancellation did not change
the charged weight, so no candidate was sent to the verifier. Official
scores stayed at the baseline.

| Task | Toffoli | T | Q | Instructions | Other |
| --- | --- | --- | --- | --- | --- |
| invsqrt | 7735 | 1 | 260 | 62160 | 37 fine rotations. 2223 Clifford pairs cancelled. |
| dqi | 5725461 | 0 | 1893 | 86051014 | 49154 bits. 598091 Clifford pairs and 70 empty conditions. Score uses `Q` squared. |
| dfthcsos | 39740 across 10 files | 0 | 119 per file | 2060743 | Official `Q` is 730 and `lambda_eff` is 49.301369250574396. Nothing in the horizon moved. |

The charged weight is the Toffoli count times `Q`, with `Q` squared for
dqi. invsqrt also prices one T and the 37 fine rotations. Deleting
Cliffords does not move those products.

## What kickmix's own blocks look like

Inspected here with kickmix 1.0.0. `python3 -m vqcc.profile` on the written
`.kmb`, then `optimize_artifact`. Not the sample submission.

`multi_controlled_x` on 4 controls, no register packet:

- Opcodes: `R` 2, `CCX` 3, `HMR` 2, `CZ` 2.
- Clean AND opens 2. Matching CCX uncompute pairs 0. Shared-control
  candidates 0. AND-cascade links 2.
- Header 7, touched 7, peak live 7, reuse headroom 0.
- Reuse is blocked: there is no quantum register, so system ids cannot be
  separated from scratch.
- The optimize step did not write a file.

That is the same shape as version 8's "0 clean-AND uncomputes". The
uncompute is already `HMR` plus a conditional `CZ`, which is kickmix
`del_and`. There is no second `CCX` to delete.

4-bit `iadd` of two named registers:

- Opcodes: `CCX` 3, `CX` 15, `R` 2, `HMR` 2, `CZ` 2.
- Clean AND opens 2. Shared-control candidates 0. The carry bit is copied
  with `CX`, not with a second `CCX`.
- Header 10, peak live 10, unused ids 0, reuse headroom 0.
- The optimize step did not write a file. Toffoli count stayed 3 and `Q`
  stayed 10.

`init_gf2_mul` of two 3-bit registers:

- `CCX` 7, `CX` 27, `SWAP` 7, `R` 3. No `HMR`.
- Control pair `(0, 3)` occurs 4 times and `(1, 4)` occurs twice.
  `clean_and_opens` is 0 and `shared_control_candidates` is 0: by the time
  the pair repeats, the target has been flipped, so it is not still holding
  that AND.
- Header 9, peak live 9, reuse headroom 0. No file was written.

A ripple-like link in that profile is a `CCX` whose three qubits are each
one more than the previous `CCX`. The multiplier has 2 such links. That is
a shape count, not an adder rewrite.

## What the next Kaggle run logs

`playbooks/vqcc_optimize.yaml` profiles the input inside the optimize step.
The step JSON field `structure` (and each attempt's `structure`) holds:

- opcode histogram
- reset counts (`R`, `HMR`, and conditional resets, which are not treated
  as freeing a qubit)
- Toffoli shape: clean AND opens, matching uncompute pairs, shared-control
  candidates, adjacent same-control run length, cascade links, ripple-like
  links, and the heaviest control pairs
- qubit lifetimes: header width, ids touched, unused ids below the header,
  peak live qubits if a qubit dies only on unconditional `R`/`HMR`, peak
  live if a matching clean-AND uncompute also kills the target, and
  `reuse_headroom_vs_header`
- repeated 32-gate windows, as lossy heavy hitters of a qubit-relative
  hash. Count-1 windows are dropped once the map is full. This is not an
  exhaustive catalog.

`reuse_headroom_vs_header` is an upper bound, not a promised saving. Named
register ids stay live for the whole circuit because the verifier reads
them. dqi's syndromes and invsqrt's `x` register pin those ids.

A dfthcsos directory report lists each angle file. The official `Q` of 730
is not the per-file width of 119, so a narrower file is sent to the
verifier only when the charged weight or a file width actually drops. The
verifier score decides whether it is kept.

## What would have to be true for a score to move

Shared-control factoring replaces one `CCX` with `CX` only while a clean
AND is still stored on its target. The kickmix adder and multiplier above
do not have that pattern. Version 8's uncompute pass, which uses the same
`|0>` proof, found nothing to delete. If the sample files are built the
same way, the Toffoli count will not move.

Qubit reuse lowers `Q` only when a scratch id sits above a real gap, or
above an id that an unconditional `R` or `HMR` has returned to `|0>`, and
the file has a named quantum register so system ids stay put. The kickmix
builder already hands freed ancillas back out, and the three idioms above
have peak live equal to the header. A reference built that way has no
headroom. dqi squares `Q`, so headroom would matter, but it is not visible
from here.

Until the logged `structure` for the sample files shows
`shared_control_candidates` above 0 or `reuse_headroom_vs_header` above 0,
the official scores should be expected to stay at the version 8 baselines.
A candidate is still kept only on verifier `PASS` and a strictly lower
JSON `score`.
