# References

Checked on 2026-11-05 unless noted.

## Primary

- Competition home: <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation>
- Overview: <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/overview>
- Rules: <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/rules>
- Data: <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/data>

  All three Kaggle pages returned the site shell and "Error: Too many requests"
  from this environment. The data page also needs a Kaggle login. Dates, the
  submission cap, the prize split, the ~45 minute scoring note, and the file
  inventory were **not** confirmed from Kaggle. See [data.md](data.md) for how
  to fetch the dataset after accepting the rules. Do not commit it.

- Team hub (main brief): <https://dg-create.com/kaggle/quantum>

  Saved with the task. Facts on the page are dated 2026-10-23. Unconfirmed
  marks on that page are preserved in [brief.md](brief.md).

- Interactive course linked from the hub: <https://dg-create.com/kaggle/quantum/learn/>

- Bot Tower, the team's bot-activity dashboard: <https://dg-create.com/tower/>

  What the saved page actually shows is in [tower.md](tower.md).

## Official write-ups we could read

- Google Open Source Blog, 2026-10-21, Tanuj Khattar and Ryan Babbush,
  [Announcing the verifiable quantum circuit compilation competition on Kaggle](https://opensource.googleblog.com/2026/10/announcing-verifiable-quantum-circuit-compilation-competition-on-kaggle.html).

  Confirms the three applications (fusion inverse square root, Reed–Solomon
  decoding for DQI, FeMoCo factorization plus lookup), kickmix inside Qualtran,
  and Apache-2.0 for the reference circuits and standalone verifiers. It does
  not state the cost formulas, the geometric-mean metric, the calendar after
  the announcement, or the winners' licensing sentence.

- Companion paper, 2026-10-21,
  [arXiv:2610.23832](https://arxiv.org/abs/2610.23832),
  Khattar, Rubin, Gidney, Broughton, Low, and Babbush,
  *Leveraging verifiable structure in quantum circuits to find more efficient
  compilations with agentic AI*.

  Confirms the per-task scores quoted in the brief, including the dqi `R`
  formula and the square root in `λ_eff`, the 128-qubit cap, the 20 mHa
  Frobenius tolerance, the `Λ` and `E_gap` floors, salted SHA-256 fuzz tests,
  and a $150,000 prize pool. It publishes SHA-256 digests of Google's
  internal runs and says the circuits will be released after the competition.
  Those digests are Google's commitments, not files in this repository:

  - Benchmark I (`1/√x`): `4b98f38a52a01fc125da7fc2847f9698abe192519dccf894fd758eccc8f37cea`
  - Benchmark II (DQI): `0701f553a9ac4e8af100f66acfccf2fc82cf5a44c2e5aa765b1d4ace01cbaadb`
  - Benchmark III (FeMoCo): `9b8d070f41dd3b6e10a69dbbae9b047847646d1540de30c7b75799f15692f644`

  The paper does not state the geometric-mean leaderboard formula.

## NoETL

- Organization: <https://github.com/noetl>
- Repository: <https://github.com/noetl/noetl>
- CUDA-Q playbook fixture (tag `v2.10.15`, not on `main` or `v4.26.2` when
  checked 2026-11-05):
  <https://github.com/noetl/noetl/blob/v2.10.15/tests/fixtures/playbooks/quantum_cudaq/quantum_cudaq.yaml>

  Catalog path `tests/quantum/cudaq_ai_pipeline`. Playbook name
  `quantum_cudaq_ai_pipeline`. It orchestrates a CUDA-Q sweep, an analysis
  step, Postgres persistence, and an HTTP publish. Current `main` playbooks
  still use `apiVersion: noetl.io/v2`.

## Primer links

Collected on the hub and repeated in [primers.md](primers.md):

- <https://quantum.country/qcvc>
- <https://arxiv.org/abs/1212.5069>
- <https://arxiv.org/abs/1709.06648>
- <https://arxiv.org/abs/2408.08292>
- <https://arxiv.org/abs/1202.5822>
- <https://arxiv.org/abs/1806.01838>
- <https://arxiv.org/abs/2007.14460>
- <https://arxiv.org/abs/2011.03494>
- <https://arxiv.org/abs/1605.03590>
