# Experiments

No leaderboard submission has been made. No Local or LB number is recorded
in `docs/experiments.md`.

| Date | Run | Description | Local | LB | Notes |
| --- | --- | --- | --- | --- | --- |

Playbook runs write a git-ignored provenance file instead of a table row.
That file includes `leaderboard_score: null`.

## What a local run showed

On 2026-11-08 the implementation environment ran:

```bash
python3 -m unittest discover -s tests -t .
```

with `noetl==5.3.2`, `kickmix==1.0.0`, and Python 3.12. 27 tests passed and
1 skipped. The skip is the "kickmix missing" guard, which does not run when
kickmix is installed.

`tests/test_playbook_e2e.py` executed `playbooks/vqcc_pipeline.yaml` through
`noetl.run` (the 5.3.2 local engine):

- Competition mode, empty data directory: eleven steps, verification blocked,
  no circuit files, no zip, `leaderboard_score` null.
- Structural mode: kickmix wrote `fixture.kmb` files, reloaded them, priced
  the invsqrt fixture from measured `toffoli_like` and `t_like`, and left
  `competition_verified` false.

Those structural counts are properties of the fixture text in
`vqcc/orchestrator.py`. They are not reference-circuit scores from the paper
and they are not leaderboard scores.

## Literal CLI, 2026-11-10

From the repository root, NoETL **5.3.2**, no `data/` directory, and no
`--set`:

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

Exit 0. stderr: `runtime: local (--runtime flag)`. Run id
`20261110T155907Z-97652c24`. Nothing was submitted to Kaggle. No zip was
written. Trimmed JSON:

| Field | Value |
| --- | --- |
| `status` | `ok` |
| `executed_steps` | `start`, `check_data`, `adapt_invsqrt`, `adapt_dqi`, `adapt_dfthcsos`, `verify_invsqrt`, `verify_dqi`, `verify_dfthcsos`, `cost`, `package`, `record` |
| `final_result.mode` | `competition` |
| `final_result.leaderboard_score` | null |
| `final_result.verification_status` | `blocked` |
| `final_result.package_status` | `not_ready` |
| `final_result.zip_written` | false |
| `final_result.experiment_log_written` | false |
| each task `competition_verified` / `circuit_written` | false / false |
| each `verify_*` step `status` | `blocked` |
| provenance `runtime.noetl_tested_version` | `5.3.2` |
| provenance `seed` | `20261108` (playbook default) |

`docs/experiments.md` gained no Local or LB cell.

## Optimization loop, 2026-11-10

`playbooks/vqcc_optimize.yaml` and `kaggle/vqcc_optimize.py` were added from
main `d45b477d`. No competition data was mounted. No official verifier was
run on a reference circuit. No Local or LB cell was written.

`python3 -m unittest discover -s tests -t .` with `noetl==5.3.2` and
`kickmix==1.0.0`: 62 tests passed, 1 skipped. The skip is the kickmix-missing
guard. `tests/test_playbook_cli.py` still passes. The new tests cover a
byte-identical kmb round trip, kickmix simulation of the peephole, a rejected
proposal, a higher verifier score, task isolation, a dfthcsos directory whose
`submission.npz` bytes are copied, and the optimize playbook with an empty
data directory.

`POST https://noetl.ai/api/dsl/validate` on 2026-11-10, server 3.156.1:
`vqcc_pipeline.yaml` and `vqcc_optimize.yaml` both returned HTTP 200,
`valid: true`, findings empty. Schema digest
`sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6`.

## Verifier gate, 2026-11-11

Issue #9 run `20261111T000307Z-0d076b2d` cancelled Clifford pairs (dqi lost
about 1.1e6 instructions) and wrote no candidate, because the gate required
the lexicographic key `(toffoli_like, t_like, high_rotations)` to fall. Those
Cliffords are not in the published costs. That gate wrote the shorter
circuit. Kaggle version 7 then showed the JSON score does not move, so a
later pass stops writing a Clifford-only shrink. Retention is still a PASS
and a strictly lower JSON `score` (FR-004, FR-011).

No competition data was mounted for this change. No official verifier score
was produced. Fixture circuits checked with kickmix 1.0.0 simulation:

- `CCX; X` on the Toffoli target; `CCX` becomes the `X`. Toffoli count 2 → 0.
- Two `Z_POW 0.125` on one qubit become one T (`Z_POW 0.25`). Static weight
  32 → 1. The phase matches.
- `X q0; X q1; X q0` drops an instruction and leaves the static weight and
  the qubit count unchanged. That file is no longer sent to the verifier.
  See the cost-targeted section below.

`POST https://noetl.ai/api/dsl/validate` on 2026-11-11, server 3.156.2:
both playbooks returned HTTP 200, `valid: true`, `execute_verdict: accept`,
findings empty. Schema digest
`sha256:29b2831fdd2444fab0bbc8915283a22ac86532393111f3a3cdad782bf6b1c4be`.
On 2026-11-13 the public validator's digest moved to
`sha256:25071111774314cbf0c83ee9925b53701c2228232574bda3b13b1e27d58b372c`
(`GET /api/dsl/version` reported server 3.161.2). The playbook steps were
not rewritten for that pin.

## Cost-targeted passes, 2026-11-11

Issue #17. The numbers below are the external Kaggle version-7 run
(`20261111T052032Z-e1a4aedc`, main `cd0168a`), not a measurement made in
this environment. `vqcc.cost_breakdown` checks that the verifier JSON
fields multiply to the printed score. FR-006 and FR-007 are not resolved
here: `R` and `lambda_eff` are the verifier's printed values.

| Task | Score | What dominates | Marginal cost |
| --- | --- | --- | --- |
| invsqrt | 2076774.233715282 | `Q=260` times `C=7987.593`. Toffolis are 7735/C (96.8%). The 37 fine rotations are the residual 252.343 Toffoli-equivalents (3.2%), matching `0.56 log2(1/eps)+5.3` T per rotation at the printed `rotation_eps`. `T/4` is 0.25. | One Toffoli is 260. One qubit is 7987.6. |
| dqi | 24439466758900.453 | `R=1.19126` times `Q^2` times shot-mean Toffoli `5725109.13`. `t_like` and fine rotations are 0. The max Toffoli count is 5725461; the gap of about 352 is conditional Toffolis that do not fire on every shot. | One Toffoli is about 4.27e6. One qubit is about 2.58e10. |
| dfthcsos | 3355599588.3155375 | `lambda_eff=49.30137` times Toffoli `93237` times `Q=730`. Each of the 10 angle files has kickmix width 119, 3974 Toffolis, 0 T, 0 fine rotations, and 1 bit. `2 * 39740 = 79480`. The other 13757 Toffolis are the part of `T_tot` not explained by counting each file forward and reverse (paper eq. A14). `Q=730` is not the per-file width. | One verifier Toffoli is about 35990. One file Toffoli, if both directions count it, is about 71980. One qubit is about 4.60e6. |

Version 7's rewrite cancelled Cliffords only (invsqrt 2223 pairs, dqi
598091 pairs, dfthcsos 0). Toffoli, T, fine-rotation, and qubit counts
did not change, so the JSON scores did not change. dfthcsos wrote no
candidate because nothing in the horizon moved: the angle files have no
T or fine `Z_POW` for the rotation merge, and no self-inverse pair commutes
into a 4096-gate horizon. A compute/use/uncompute Toffoli does not commute,
so that horizon cannot see it.

The new pass replaces that uncompute with `HMR` and a conditional `CZ` when
the target is known clean. Kickmix 1.0.0 simulation (qubits and shot phase,
several measurement shots) matches on use, phase, nested AND, conditional,
and `PUSH_CONDITION` fixtures. A named register qubit is not treated as
clean unless `R` or `HMR` resets it first. A scratch id that the rewrite
stops using is dropped from `Q` instead of being padded with two `Z` gates.
A Clifford-only shrink that keeps the charged weight and `Q` is not written.

No competition data was mounted. No official verifier score was produced.
If a dfthcsos angle file has no clean AND uncompute, the run still writes
no candidate; `and_uncomputes` in the attempt stats is the count.

## Structural passes, 2026-11-12

Issue 19. No competition data was mounted. No official verifier was run on
a reference circuit. No Local or LB cell was written.

Version 8 (external notebook `20261112T030658Z-9813e023`, main `53304c8`)
left every official score at the baseline. The measurement-uncompute pass
recorded `and_uncomputes: 0` for invsqrt, dqi, and dfthcsos. Clifford
cancellation changed the instruction count and not the charged weight, so
no candidate was sent. Details and the kickmix-idiom profiles are in
[Circuit structure](Circuit-Structure).

What this environment did run, kickmix 1.0.0, on circuits it built:

- A clean AND computed twice, second target different: one `CCX` becomes
  `CX`. Toffoli count 2 → 1. Kickmix simulation of the wires matches.
- The same factor with a `Z` on the AND target. Wires match.
- An `X` on the AND target: the factor does not fire, and no file is written.
- Scratch ids 8 and 12, with named qubits 0..2 and an unconditional `R`
  between the two lifetimes: header width 13 → 4. On 16 shots per input,
  the named bits match the classical function and every other qubit is
  `|0>`. `R` still kicks a random phase; that phase is not a score.
- 4-control `multi_controlled_x`, 4-bit `iadd`, and 3-bit `init_gf2_mul`:
  the profile's peak live count equals the header, shared-control
  candidates are 0, and the optimize step writes no file. `iadd` stays at
  3 Toffolis and `Q` 10. `init_gf2_mul` stays at 7 Toffolis and `Q` 9.

`python3 -m unittest discover -s tests -t .` with `noetl==5.3.2` and
`kickmix==1.0.0`: 87 tests, 1 skipped. The skip is the kickmix-missing
guard, which does not run when kickmix is installed.

No effect on the version 8 scores is claimed. The sample files are not
here. The next Kaggle optimize run logs `structure` so those files can be
read the same way. A lower score is not expected unless that report shows
shared-control candidates or reuse headroom. dqi squares `Q`, which is why
headroom would matter, and why a circuit whose peak live count already
equals its header will not move.

## How to log a real attempt later

```bash
python3 scripts/log_experiment.py \
  --date YYYY-MM-DD \
  --run <id> \
  --description "what changed" \
  --notes "formula source, inputs, verifier command"
```

Omit `--local` and `--lb` until a verifier or Kaggle returns them. The script
rejects placeholder words such as `guess` and `sample`.
