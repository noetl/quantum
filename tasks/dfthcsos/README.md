# dfthcsos

Block encoding of a double-factorized / tensor-hypercontraction chemistry
Hamiltonian (FeMoCo). The kickmix piece is the angle lookup; the rest of the
block encoding is priced with the published cost formula.

**Deliverable:** `dfthcsos/angle_k_0` through `dfthcsos/angle_k_N` with no gaps,
plus `dfthcsos/submission.npz` holding `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`,
and `tree_edges`.

**Cost.** The product `λ_eff × T × Q` is in both write-ups. The definition of
`λ_eff` conflicts:

- Hub, not marked unconfirmed there: `λ_eff = E_gap (2Λ − E_gap)`.
- Paper equation 44: `λ_eff = sqrt(E_gap (2Λ − E_gap))`, with `T_tot` and
  `Q_tot` expanded to include Outer, Inner, Givens rotations, and the angle
  circuits.

`scripts/score.py dfthcsos` requires `--source hub` or `--source paper`.

**Constraints, shared unless noted:**

- Rejected if any angle circuit uses more than 128 qubits (hub and paper).
- Rejected if the encoded Hamiltonian is off by more than 20 mHa (hub). The
  paper states a Frobenius error tolerance of 20 mHa and says the checks do
  not certify a 20 mHa many-electron energy error.
- Paper strict floors, which the hub lists as the values 49.0 and 3.914898 Ha:
  `Λ > 49.0` Ha and `E_gap > 3.914898` Ha. The paper says `λ_eff` itself has
  no separate floor. Confirm the inequality direction in
  `verifiers/dfthcsos/SCORING_README.md` once the data is local.

**Strategy ideas from the hub, not yet tried here:**

- Lower `λ` with a better factorization.
- Cheaper PREPARE / SELECT.
- Start from the Starter Kit dataset.

`generate.py` writes nothing. Do not commit `submission.npz` or angle files.
