# invsqrt

Reversible inverse square root, fixed-point arithmetic, used to phase by
`1/√x` for Coulomb interactions (fusion / warm dense matter).

**Deliverable:** `invsqrt.kmb` or `invsqrt.kmx`.

**Cost.** Hub and paper agree:

$$
Q \times \left(\#\mathrm{Toffoli} + \frac{\#T}{4}\right)
$$

The paper (section III.1.3) defines the benchmark score as `S = Q × C` with
`C = Toffolis + T/4`, the mean Toffoli-equivalent cost per shot. Clifford
`Z_POW` angles are free, a T angle costs one T, and each finer `Z_POW` is
priced analytically. `scripts/score.py invsqrt` evaluates the shared product
only. It does not price rotations.

The paper's reference circuit, which is Google's baseline and not a result
from this repository, is described in section III.1.2: `n_p = 10` (22-bit
`x`), `Q = 260`, 7,735 Toffolis, 1 T, 37 non-Clifford `Z_POW` rotations,
`C = 7,988`, space-time score `Q × C = 2.08 × 10^6`.

**Verification sketch from the paper.** One named register `x` of 22 qubits.
Scratch returns to `|0⟩`. Every `x` in range is simulated with the PRNG seeded
from the circuit hash plus the competition salt. Every shot must pass inside
the relative-error tolerance. The exact shot count and tolerance belong to
the verifier; do not re-implement them here.

**Strategy ideas from the hub, not yet tried here:**

- Fewer Newton iterations with a better initial guess.
- Measurement-based uncomputation (0-T AND uncompute).
- Aggressive ancilla reuse to shrink `Q`.

`generate.py` writes nothing.
