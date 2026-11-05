# Competition brief

Google Quantum AI — Verifiable Quantum Circuit Compilation, as collected for
the NoETL entry. The team hub
([dg-create.com/kaggle/quantum](https://dg-create.com/kaggle/quantum), facts
read 2026-10-23, page saved 2026-11-04) is the main brief. This note adds what
the companion paper and the Google announcement confirm, and it says when a
Kaggle page could not be read.

**Unconfirmed (hub)** means the hub itself flags the claim. A conflict between
the hub and the paper is labeled **conflict** and is not silently "fixed".

## Goal

Make three quantum circuits cheaper than Google's reference versions: fewer
T / Toffoli gates, times fewer qubits. The circuits still have to pass
randomized verifier tests. The hub says the score is the geometric mean of the
improvement ratios, the reference scores 1.0, and higher is better. That
aggregate is **unconfirmed (hub)**. See [Scoring](#scoring).

`Q`, the qubit count, multiplies every task cost. Saving qubits pays off in
all three tasks. On dqi, `Q` is squared.

## The three tasks

### invsqrt

A reversible inverse-square-root circuit (fixed-point arithmetic). In the
application, given a squared distance `x`, the circuit applies a phase
proportional to `1/√x`. The Google announcement describes this as the Coulomb
bottleneck in inertial-confinement fusion stopping-power simulations. The
paper's benchmark phases by `exp(2πi β / √x)` with default `β = 1`.

**Cost** (hub and paper agree):

$$
Q \times \left(\#\mathrm{Toffoli} + \frac{\#T}{4}\right)
$$

Rotations are priced in T gates. The paper's score is `S = Q × C` with
`C = Toffolis + T/4` per shot. Clifford `Z_POW` angles are free. Finer
rotations are priced from the remaining phase-error margin. The local scorer
does not apply that rotation pricing.

**Deliverable:** `invsqrt.kmb` or `invsqrt.kmx`.

### dqi

Decoded Quantum Interferometry with a coherent Reed–Solomon decoder over
`GF(2^12)`. The announcement frames this as the arithmetic bottleneck in
Optimal Polynomial Intersection: decode a Reed–Solomon code in superposition.

**Cost:**

$$
R(\varepsilon^+) \times Q^2 \times T
$$

**Unconfirmed (hub):** the page renders

$$
R(\varepsilon) = \ln 2 - \ln\left(\tfrac{1}{2} + 2\varepsilon\right)
$$

and says the exact form is uncertain. `ε⁺` is an upper confidence bound on
the failure rate.

**Paper equation 43, which disagrees:**

$$
R(\varepsilon) = \frac{\ln 2}{-\ln\left(\tfrac{1}{2} + 2\sqrt{\varepsilon}\right)}
$$

The paper sets `T` to the single-run Toffoli count, including workspace
cleanup, and gives no finite score for `ε⁺ ≥ 1/16`. With zero failures in
`N = 102,400` shots it quotes `ε⁺ ≈ 8.7 × 10⁻⁴` and a floor
`R(ε⁺) ≈ 1.19` for an exact submission. Those figures describe the paper's
verifier, not a run from this repository.

**Deliverable:** `dqi.kmb` or `dqi.kmx`.

### dfthcsos

A block encoding of a double-factorized / THC chemistry Hamiltonian. The
announcement describes co-designing a factorization of the FeMoCo Hamiltonian
and the lookup circuits that load it. The paper restricts the kickmix piece
to the angle lookups and prices the rest with analytic formulas.

**Cost product** (both sources):

$$
\lambda_{\mathrm{eff}} \times T \times Q
$$

**Conflict.** The hub writes, and does not mark unconfirmed,

$$
\lambda_{\mathrm{eff}} = E_{\mathrm{gap}}(2\Lambda - E_{\mathrm{gap}})
$$

measured over the whole block encoding. Paper equation 44 writes the square
root,

$$
\lambda_{\mathrm{eff}} = \sqrt{E_{\mathrm{gap}}(2\Lambda - E_{\mathrm{gap}})}
$$

and expands `T` and `Q` into `T_tot` and `Q_tot` (angle circuits forward and
back, plus heuristic Outer, Inner, and Givens costs; persistent qubits plus
the largest temporary workspace). Until `verifiers/dfthcsos/SCORING_README.md`
is on disk, both expressions stay available and neither is treated as the
official one by default.

**Constraints:**

- Rejected if any angle circuit uses more than **128 qubits** (hub and paper).
- Rejected if the encoded Hamiltonian is more than **20 mHa** off (hub). The
  paper sets the Frobenius tolerance to 20 mHa and says this does not certify
  a 20 mHa many-electron energy error.
- `Λ` / `E_gap`: **49.0 / 3.914898 Ha** (hub, citing
  `verifiers/dfthcsos/SCORING_README.md`). The paper states strict floors
  `Λ > 49.0` Ha and `E_gap > 3.914898` Ha, and says `λ_eff` has no separate
  floor. The inequality direction was not re-read from the Kaggle file.

**Deliverable:** `dfthcsos/angle_k_0` … `angle_k_N` with no gaps, plus
`dfthcsos/submission.npz` with `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`, and
`tree_edges`.

## Verification

**Hub:** verifiers are kickmix fuzz tests seeded by the submission hash plus
a secret salt, so a circuit has to be correct beyond a fixed test set.

**Paper (section II.3):** the verifier hashes the circuit bytes with SHA-256
and mixes in a private salt so entrants cannot grind the seed. A shot checks
the output bitstring, clean scratch, and the phase. The failure-rate bound
uses a one-sided Clopper–Pearson interval at confidence `1 − 2⁻¹²⁸`.

**Hub, not re-checked on Kaggle:** `kickmix/kickmix.so` is built for the
Kaggle image, and a PyPI release was still pending when the hub was written.
The data bundle is described as 1.04 GB and 34 files, including the paper PDF,
`sample_submission/` (the hub says this scores 1.0), `verifiers/`, and the
kickmix binary. The Kaggle data page was rate-limited here, so that inventory
is hub-only.

**Blog:** kickmix is an open-source C++20 and Python library in Qualtran.
The reference circuits and standalone verifiers are Apache-2.0.

## Scoring

**Unconfirmed (hub).** The formula rendered badly on Kaggle, and the hub says
to check it against the metric code in `verifiers/`:

$$
\mathrm{Score} = \left( \prod_{b \in \{\mathrm{invsqrt},\,\mathrm{dqi},\,\mathrm{dfthcsos}\}} \frac{\mathrm{refcost}_b}{\mathrm{cost}_b} \right)^{1/3}
$$

The reference scores 1.0, and higher is better. The paper defines a separate
score `S` for each benchmark and does not state this product. The local
command `scripts/score.py aggregate` evaluates the expression only when every
input is passed on the command line, labels the value unconfirmed, and sets
`leaderboard_score` to null.

Per-task costs are lower-is-better. The geometric mean, if it is the real
metric, is higher-is-better.

## Submission format

One zip:

- `invsqrt.kmb` or `invsqrt.kmx`
- `dqi.kmb` or `dqi.kmx`
- `dfthcsos/angle_k_0` … `dfthcsos/angle_k_N` (no gaps)
- `dfthcsos/submission.npz`

This layout is from the hub. The Kaggle data page that would show the sample
zip was rate-limited. `scripts/package_submission.py` enforces this layout
and does not create missing files.

## Rules and limits

From the hub. The Kaggle rules page returned "Too many requests" on
2026-11-05, so these were not re-read from Kaggle:

- 5 submissions per day.
- 2 final selections.
- Team size at most 5.
- Public and free tools, data, and LLMs are allowed.
- No private sharing outside the team. One account per person.
- Winners deliver reproducible code under Apache-2.0.
- Scoring time about 45 minutes per submission (hub statement, not marked
  unconfirmed there, and not seen on the pages we could read).
- dfthcsos qubit cap 128, as above.

The Google announcement confirms that the reference circuits and verifiers
are Apache-2.0. The winners' licensing sentence is hub-only. This repository
is Apache-2.0 anyway, which matches that requirement.

The paper states a **$150,000** prize pool. The hub's breakdown, which sums
to that total and was not in the paper text we read, is $50k / $25k / $10k /
$5k / $5k / $5k, plus a $10k milestone, a $10k longest-leader prize, and
3 × $10k per-task prizes.

## Timeline

Times below are the instants in the hub page source (UTC). The page displays
them in `America/New_York`. The Kaggle overview was rate-limited, so the
official timestamps were not re-read.

| Event | When | Where it came from |
| --- | --- | --- |
| Announcement | 2026-10-21 | Google Open Source Blog; paper date |
| Start | 2026-10-22 | Hub. The blog is the day before and says the competition is launching. |
| Milestone prize | 2026-11-20 23:59 UTC | Hub countdown |
| Longest Leader cutoff | 2027-01-04 23:59 UTC | Hub prose |
| Entry and merger deadline | 2027-01-13 23:59 UTC | Hub countdown |
| Final submission | 2027-01-20 23:59 UTC | Hub countdown |

## What this repository does

NoETL playbooks orchestrate the work: agents, tools, and the steps from a
candidate circuit through kickmix verification, a labeled cost, a zip, and a
log row. The playbook is `playbooks/vqcc_pipeline.yaml`. The spec for that
pipeline is `specs/001-noetl-pipeline/spec.md`.

The NoETL repository already used this pattern for a CUDA-Q workload at tag
`v2.10.15` under `tests/fixtures/playbooks/quantum_cudaq/`. That fixture is a
demonstration (fetch a problem, run sweeps, summarize, store a row). It is
not on current NoETL `main`. This competition repo keeps the same idea and
does not import that demo's numbers.

Task code that would read the dataset is a stub. `tasks/<task>/generate.py`
exits without writing a file. Fetch the dataset with `scripts/fetch_data.sh`
into `data/` when you are ready. Do not commit it.
