# Tasks

One directory per competition task. Generators are not implemented. Running
`generate.py` prints a blocked or not-implemented message and writes no circuit.

| Directory | Deliverable | Cost, as far as the sources agree |
| --- | --- | --- |
| `invsqrt/` | `invsqrt.kmb` or `invsqrt.kmx` | `Q × (Toffoli + T/4)` |
| `dqi/` | `dqi.kmb` or `dqi.kmx` | `R(ε⁺) × Q² × T`, and `R` is disputed |
| `dfthcsos/` | `dfthcsos/angle_k_0..N` and `submission.npz` | `λ_eff × T × Q`, and `λ_eff` is disputed |

Full formulas, constraints, and the unconfirmed marks are in
[docs/brief.md](../docs/brief.md).
