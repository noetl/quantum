# Strategy ideas

These are the ideas listed on the team hub. None of them has been run in this
repository. There are no local scores and no leaderboard scores yet.

`Q` multiplies every cost, and on dqi it is squared, so ancilla reuse shows
up in all three tasks.

## invsqrt

- Fewer Newton iterations with a better initial guess.
- Measurement-based uncomputation (0-T AND uncompute).
- Aggressive ancilla reuse to shrink `Q`.

The hub's primer adds the usual knobs: lookup table versus bit tricks for the
initial guess, iteration count, fixed-point precision, and when garbage is
uncomputed. The Newton update on the hub is

$$
y_{k+1} = y_k \left(\tfrac{3}{2} - \tfrac{x}{2} y_k^2\right).
$$

The paper's baseline uses one Newton–Raphson step after a polynomial initial
guess, at 24 bits of relative error for `n_p = 10`. That is a reference
design, not a result we measured.

## dqi

- `Q` is squared, so qubits matter most here.
- Cheaper `GF(2^12)` multipliers.
- Trade a small failure rate `ε` for fewer gates.

The hub's decoding pipeline is syndromes, then Berlekamp–Massey or Euclid,
then Chien search, then Forney. Addition in `GF(2^12)` is XOR and has no T
cost. Multiplication needs Toffolis. The paper's baseline multiplier costs
63 Toffolis and is called out as improvable relative to a 51-Toffoli
hand-tuned circuit in earlier work. Whether a higher `ε⁺` is worth the
repetition factor depends on which `R` is official. See
[open-questions.md](open-questions.md).

## dfthcsos

- Lower `λ` with a better factorization.
- Cheaper PREPARE / SELECT.
- Start from the Starter Kit dataset in the competition data.

The hub's THC sketch is

$$
V_{pqrs} \approx \sum_{\mu\nu} \chi_p^\mu \chi_q^\mu Z_{\mu\nu} \chi_r^\nu \chi_s^\nu.
$$

Double factorization writes the two-electron tensor as a sum of squared
one-body operators diagonalized by orbital rotations (`U`). The fields in
`submission.npz` encode a factorization of that kind. Ranks and angle-circuit
width have to stay inside the 128-qubit cap and the 20 mHa tolerance. Because
`λ_eff` is inside the cost, a factorization that only shrinks the lookup is
not automatically a win if `λ_eff` or `Q` grows. The square-root disagreement
changes how large that trade is. Do not pick a ranking until the scoring
readme is local.

## What we will not do from these notes

- We will not log a strategy as an experiment until a verifier has run.
- We will not treat the paper's published baseline counts as our scores.
- We will not download or commit the Starter Kit. The fetch steps are in
  [data.md](data.md).
