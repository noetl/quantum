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
- `toffoli.match`: for each profiled shared-control candidate and each
  matching uncompute pair, one label. `eligible` is a strict match.
  `control_mutated` and `condition_bit_written` mean the profile still
  counted an AND after its bit stopped being that AND.
  `condition_mismatch` is a live AND whose firing condition does not match
  the later `CCX`. The four labels sum to the candidate count. The attempt
  `stats` also carry `and_replays`, `left_for_cancellation`, and
  `reject_condition_mismatch`
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

## Version 9: the counts were not strict matches

Kaggle version 9 (notebook scriptVersionId 368976547, main `da8490e`, run
`20261113T015716Z-fea5b448`) logged the profile of the input circuits.
Evidence is the comment on
[issue 19](https://github.com/noetl/quantum/issues/19#issuecomment-6844754721).
This environment still does not have the sample files, so the split of
those 832 and 222 rows is not measured here. The match rules below are
what the code did on that commit, checked on small circuits.

| Task | shared_control_candidates | matching_uncompute_pairs | shared_control_factors | and_uncomputes | Toffoli |
| --- | --- | --- | --- | --- | --- |
| invsqrt | 11 | 0 | 0 | 0 | unchanged (the retained gain was one qubit, 260 → 259) |
| dqi | 832 | 222 | 0 | 0 | 5725461 before and after |
| dfthcsos | 0 in every angle file | 0 | 0 | 0 | unchanged |

dqi's cost is `R × Q² × Toffoli`. `Q` is 1893 and
`reuse_headroom_vs_header` is 0, so a dqi gain has to be a lower Toffoli
count. Version 9 did not write a dqi candidate. The official score stayed
24439466758900.453. That number is the version 9 verifier result, not a
new measurement from this tree.

The profile and the transform did not use the same match.

The profile counts a later `CCX` as a shared-control candidate, or as a
matching uncompute when the target is the same, while any earlier clean
AND of those controls is still in its map. It drops that AND when the
**target** is value-written or reset. It does not drop it when a
**control** is value-written (`X`, `CX`, `SWAP`, `CSWAP`), when a
condition bit is overwritten (`BIT_INVERT`, `BIT_STORE0`, `BIT_STORE1`,
`HMR` into that bit), or when the explicit `if` bit or the
`PUSH_CONDITION` stack differs.

The transform drops the AND on a control write or a condition-bit write,
because the target no longer holds the AND of the current control bits.
Rewriting those `CCX`s would change the circuit. A same-target pair is an
uncompute only when the firing conditions are the same set of bits. A
different condition is not an inverse: the second `CCX` does not clear the
AND on every shot the first one set it. Version 9 also required the stack
tuple and the explicit bit to be identical, so a narrower later condition
was refused even when the stored bit was still the AND. And it refused to
record a 65th live AND on a qubit that already had 64 open ANDs. dqi's
`peak_open_ands` was 857, above that cap. A later `CCX` could still copy
from one of the 64 that remained valid. The miss was an AND the cap never
stored, which is the case this pass now records.

`longest_same_control_run` was 1 on dqi. The repeated control pair
`(888, 1803)` × 65520 is not an adjacent run of live ANDs. Kickmix's own
`init_gf2_mul`, lookup, and unary iteration separate a repeated control
pair with an `X` on a control or with `HMR`. Those idioms profile as 0
shared-control candidates. The 832 are the pairs that survive the
profile's weaker check and fail the transform's check.

`clean_and_opens` was 454645 on dqi, and `and_uncomputes` was 0. Most of
those opens are already closed by measurement (`HMR` plus a conditional
`CZ`, kickmix `del_and`), not by a second `CCX`. The profile drops the
record on that `HMR`, so those closes are not part of the 222. There is
no second Toffoli to delete until the same controls are computed again.

A pair the horizon can still cancel is left for that cancellation, which
removes two Toffolis and does not increment `and_uncomputes`. dqi's
Toffoli count did not move, so none of the 222 took that path. They were
not strict matches. `cancelled_pairs` on dqi was 598091 and the charged
weight did not change: those deletions were Cliffords.

## What this pass changes, and what it does not

Two strict misses are now rewrites. Both are checked by kickmix simulation
on small circuits, including the shot phase.

- A later `CCX` of a live AND may sit under a narrower condition. It
  becomes `CX` from the AND target, under that narrower condition. A
  same-target `CCX` whose condition is not the same set of bits is still
  left alone.
- `POP_CONDITION` no longer forgets an AND. The firing condition is the
  set of bits, so a later gate under that same set can still match.
- The per-control cap of 64 live ANDs is gone. The total open-AND cap
  stays 100000.
- Measurement replay. When `del_and` is `HMR` immediately followed by `CZ`
  on the two controls, and a later `CCX` uses those controls on a
  **different** target before any write of a control, any use of the
  measured bit, or any use of the AND qubit, the `HMR`/`CZ` pair is
  delayed and that `CCX` becomes `CX`. A recompute onto the same qubit
  emits the delayed pair first and keeps the `CCX`: dropping it would
  clear the bit on the next use. An `X` on a control in between is not
  replayed. That is the shape of kickmix unary iteration and lookup, so
  those idioms still do not lose a Toffoli.

`stats.and_replays` counts recomputes replaced that way.
`stats.shared_control_factors` counts a copy taken while the AND was never
uncomputed. `stats.reject_condition_mismatch` counts a live AND the later
`CCX` did not imply. `structure.toffoli.match` is the profile-side split
of the candidate counts. `structure.toffoli.measurement_and_closes` counts
open ANDs closed by `R` or `HMR`.

No Toffoli construction for a mutated control is sound. A ripple-like link
or an AND-cascade link is a shape count of adjacent `CCX`s. Kickmix
`iadd` and `init_gf2_mul` already copy with `CX` and uncompute with
`del_and`. This pass does not replace those blocks with a different adder.

Nothing here is a new official score. A candidate is written only when the
static Toffoli weight or the qubit count drops, and it is kept only on
verifier `PASS` and a strictly lower JSON `score` (user story 2, FR-001,
FR-003, FR-004, FR-010, FR-011). dqi's version 9 score is the baseline
until a later Kaggle run measures a candidate.
