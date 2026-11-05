# Primers

Short primers from the team hub, in the hub's order, plus the first-principles
chain on that page. The one-line summaries are the hub's. Open the linked
sources for the full arguments. There is also an interactive course,
[What is a quantum circuit?](https://dg-create.com/kaggle/quantum/learn/),
described on the hub as 10 lessons with a live simulator.

The goal in the hub's words: build three quantum circuits (an inverse square
root, a Reed–Solomon DQI step, and a chemistry Hamiltonian block encoding)
that provably do the same job as Google's reference circuits and use fewer
expensive gates and fewer qubits.

## Qubits and gates

Qubits are unit vectors. Gates are unitary matrices. `n` qubits give `2^n`
dimensions. A qubit is `α|0⟩ + β|1⟩` with `|α|² + |β|² = 1`. A circuit is a
sequence of gates.

$$
H = \tfrac{1}{\sqrt{2}}\begin{pmatrix}1&1\\1&-1\end{pmatrix},\quad
S = \begin{pmatrix}1&0\\0&i\end{pmatrix},\quad
T = \begin{pmatrix}1&0\\0&e^{i\pi/4}\end{pmatrix}
$$

- [Quantum computing for the very curious](https://quantum.country/qcvc)
- [Qubit](https://en.wikipedia.org/wiki/Qubit)
- [Quantum logic gate](https://en.wikipedia.org/wiki/Quantum_logic_gate)

## Clifford+T and T-count

Clifford gates (H, S, CNOT) are cheap on error-corrected hardware. Adding T
makes the set universal, and every T needs magic-state distillation. An
arbitrary rotation `R_z(θ)` costs roughly `3 log2(1/ε)` T gates, which is why
the tasks price rotations in T.

- [Clifford gates](https://en.wikipedia.org/wiki/Clifford_gates)

## Toffoli gate

The reversible AND, and the building block of quantum arithmetic. Exact
decomposition costs 7 T. A measurement-assisted temporary AND costs 4 T to
compute and 0 T to uncompute, which is the idea behind "T/4 ≈ Toffoli".

$$
\mathrm{CCX}:\ |a,b,c\rangle \mapsto |a,b,c \oplus ab\rangle
$$

- [Toffoli gate](https://en.wikipedia.org/wiki/Toffoli_gate)
- [Jones, fault-tolerant Toffoli](https://arxiv.org/abs/1212.5069)
- [Gidney, Halving the cost of addition](https://arxiv.org/abs/1709.06648)

## Ancillas and measurement-based uncomputation

Scratch qubits must return to `|0⟩`. Measuring them in the X basis, then
fixing the phase with a classically controlled CZ, uncomputes an AND with no
T gates. `Q` multiplies every cost, so reusing ancillas helps directly.

- [Gidney 2018, temporary logical-AND](https://arxiv.org/abs/1709.06648)

## Newton iteration for 1/√x

A division-free update that doubles the correct bits each step. Every multiply
costs Toffolis. Tradeoffs are the initial guess, the iteration count,
fixed-point precision, and when to uncompute garbage.

$$
y_{k+1} = y_k\left(\tfrac{3}{2} - \tfrac{x}{2} y_k^2\right)
$$

- [Fast inverse square root](https://en.wikipedia.org/wiki/Fast_inverse_square_root)
- [Newton's method](https://en.wikipedia.org/wiki/Newton%27s_method)
- [Methods of computing square roots](https://en.wikipedia.org/wiki/Methods_of_computing_square_roots)

## Reed–Solomon decoding over GF(2^12)

Field addition is XOR (CNOTs, no T cost). Multiplication costs Toffolis. DQI
runs the decoder coherently. The hub's pipeline is syndromes, then
Berlekamp–Massey or Euclid (the error locator), then Chien search, then
Forney.

- [Reed–Solomon error correction](https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction)
- [Finite field](https://en.wikipedia.org/wiki/Finite_field)
- [Decoded Quantum Interferometry](https://arxiv.org/abs/2408.08292)

## Block encodings, LCU, and λ

Put `H/λ` inside a unitary. The algorithm's cost scales with `λ`, so smaller
is better.

$$
H = \sum_j \alpha_j U_j, \qquad \lambda = \sum_j |\alpha_j|
$$

PREPARE loads `√(α_j / λ)` and SELECT applies `U_j`. Phase estimation and
QSVT need on the order of `λ/ε` calls, which is why `λ_eff` is in the
dfthcsos cost.

- [Childs and Wiebe, LCU](https://arxiv.org/abs/1202.5822)
- [Gilyén et al., QSVT](https://arxiv.org/abs/1806.01838)

## Double-factorized and THC Hamiltonians

Compress the `O(N^4)` two-electron tensor to lower `λ` and gate cost.

$$
V_{pqrs} \approx \sum_{\mu\nu} \chi_p^\mu \chi_q^\mu Z_{\mu\nu} \chi_r^\nu \chi_s^\nu
$$

Double factorization writes the tensor as a sum of squared one-body operators
diagonalized by orbital rotations (`U`). The `submission.npz` fields encode a
factorization of this kind.

- [von Burg et al., double factorization](https://arxiv.org/abs/2007.14460)
- [Lee et al., THC](https://arxiv.org/abs/2011.03494)

## FeMoCo

Nitrogenase's iron-molybdenum cofactor, a strongly correlated benchmark for
fault-tolerant quantum chemistry. It is the active site that fixes N₂ into
ammonia. The announcement notes that industrial nitrogen fixation uses about
1–2% of the world's energy supply.

- [FeMoco](https://en.wikipedia.org/wiki/FeMoco)
- [Reiher et al.](https://arxiv.org/abs/1605.03590)

## From first principles

The hub's chain, from the bottom of the page. Play it on the hub to see
prerequisites. The score node repeats the **unconfirmed (hub)** aggregate.

| Level | Node | Needs | What the hub says |
| --- | --- | --- | --- |
| 0 | Bits and reversibility | — | Classical bits are 0/1. A reversible gate is a bijection. Quantum gates must be reversible, so arithmetic is reversible too. |
| 1 | Qubits and superposition | bits | A qubit is a unit vector `α\|0⟩+β\|1⟩`. Measuring yields 0 or 1 with probabilities `\|α\|²`, `\|β\|²`. |
| 2 | Gates are unitaries | qubit | Gates satisfy `U†U = I`. A circuit is a product of gates. |
| 3 | Universal gate sets | gates | A finite set is universal if it can approximate any unitary. Clifford+T is the fault-tolerant standard. |
| 4 | Why T and Toffoli cost | universal sets | Cliffords are cheap. Each T needs a distilled magic state. Toffoli is about 7 T exact, or 4 T with a temporary AND. |
| 5 | Ancillas and uncomputation | Clifford+T | Scratch returns to `\|0⟩`. X-basis measurement plus a classical CZ fix-up uncomputes an AND with 0 T. |
| 6 | Reversible arithmetic | ancillas | Adders and multipliers from Toffolis and CNOTs. Multiplies leave garbage that must be uncomputed. |
| 6 | Hamiltonians | gates | `H` is the molecule's energy. The two-body tensor has `O(N^4)` terms. |
| 7 | Newton inverse square root | arithmetic | Division-free iteration. Cost depends on the guess, the iteration count, and the precision. `y ← y·(3/2 − x·y²/2)`. |
| 7 | Finite fields GF(2^12) | arithmetic | 12-bit polynomials. Addition is XOR. Multiplication needs Toffolis. |
| 7 | DF / THC factorization | Hamiltonians | Compression lowers `λ` and gate cost. `submission.npz` holds `U`, `W`, and the rest. |
| 8 | Reed–Solomon decoding (DQI) | finite fields | Syndromes, error locator, Chien search, Forney. Failure rate `ε` enters the dqi cost through `R(ε⁺)`. |
| 8 | Block encoding / LCU / λ | factorization, ancillas | `H/λ` in a block of a unitary. `λ_eff = E_gap(2Λ − E_gap)` on this node, which is the hub's form, not the paper's square root. |
| 9 | FeMoCo | block encoding | The nitrogenase benchmark molecule. |
| 10 | Cost model | the three tasks and Clifford+T | invsqrt `Q·(Tof + T/4)`. dqi `R(ε⁺)·Q²·T` with `R` uncertain. dfthcsos `λ_eff·T·Q`. |
| 11 | The score | cost model | Geometric mean of `refcost/cost`. Reference is 1.0. **Unconfirmed (hub):** "as read from the page, to be confirmed." |

## Why cheaper matters

On error-corrected hardware every T or Toffoli needs a distilled magic state,
and every logical qubit costs many physical qubits. Fewer of both brings
algorithms such as FeMoCo chemistry closer to something a machine can run.
The announcement's question is whether we get more from a quantum computer by
asking it to do less.
