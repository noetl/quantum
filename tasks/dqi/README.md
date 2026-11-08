# dqi

Decoded Quantum Interferometry step: a coherent Reed–Solomon decoder over
`GF(2^12)`.

**Deliverable:** `dqi.kmb` or `dqi.kmx`.

**Cost.** Both write-ups use

$$
R(\varepsilon^+) \times Q^2 \times T
$$

`R` is **unconfirmed (hub)**. The hub renders

$$
R(\varepsilon) = \ln 2 - \ln\left(\tfrac{1}{2} + 2\varepsilon\right)
$$

and says the exact form is uncertain. The paper's equation 43 instead gives

$$
R(\varepsilon) = \frac{\ln 2}{-\ln\left(\tfrac{1}{2} + 2\sqrt{\varepsilon}\right)}
$$

with `T` the single-run Toffoli count (including cleanup) and `Q` the total
qubit count. The paper assigns no finite score when `ε⁺ ≥ 1/16`. Pass
`--source hub` or `--source paper` to `scripts/score.py dqi`. There is no
silent default.

**Strategy ideas from the hub, not yet tried here:**

- `Q` is squared, so qubits matter most here.
- Cheaper `GF(2^12)` multipliers.
- Trade a small failure rate `ε` for fewer gates.

The paper's reference circuit (not a result from this repository) uses 1,893
qubits and 5,725,461 Toffolis after cleanup. Field addition is XOR. The paper's
baseline multiplier is a 63-Toffoli Karatsuba circuit.

`generate.py` writes nothing.
