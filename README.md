# NoETL quantum

Home for the NoETL entry in the Kaggle competition
[Google Quantum AI — Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).

NoETL playbooks orchestrate the work. The baseline playbook
`playbooks/vqcc_pipeline.yaml` runs on the NoETL 5.3.2 local runtime. With no
competition data it blocks verification, writes no circuit, and records
`leaderboard_score: null`. It does not contain the Kaggle dataset or a
leaderboard score.

The team hub is <https://dg-create.com/kaggle/quantum>. Bot activity is on
<https://dg-create.com/tower/> (see [docs/tower.md](docs/tower.md) for what that
page shows). The companion paper is
[arXiv:2610.23832](https://arxiv.org/abs/2610.23832). NoETL itself is
<https://github.com/noetl/noetl>.

## Three tasks

`Q` multiplies every cost. Details, constraints, and source labels are in
[docs/brief.md](docs/brief.md).

| Task | Job | Deliverable | Cost |
| --- | --- | --- | --- |
| `invsqrt` | Reversible `1/√x` for a Coulomb phase | `invsqrt.kmb` or `.kmx` | `Q × (Toffoli + T/4)` |
| `dqi` | Coherent Reed–Solomon decode over `GF(2^12)` | `dqi.kmb` or `.kmx` | `R(ε⁺) × Q² × T` |
| `dfthcsos` | Block encoding of a DF/THC chemistry Hamiltonian | `dfthcsos/angle_k_0..N` and `submission.npz` | `λ_eff × T × Q` |

**invsqrt** agrees across the hub and the paper:

$$
Q \times \left(\#\mathrm{Toffoli} + \frac{\#T}{4}\right)
$$

**dqi.** The product is shared. `R` is **unconfirmed (hub)**:

$$
R(\varepsilon) = \ln 2 - \ln\left(\tfrac12 + 2\varepsilon\right)
$$

The paper's equation 43 is different:
`ln 2 / (−ln(1/2 + 2√ε))`, with `T` a Toffoli count.

**dfthcsos.** **Conflict** (the hub does not mark its formula unconfirmed; the
paper disagrees):

$$
\lambda_{\mathrm{eff}} = E_{\mathrm{gap}}(2\Lambda - E_{\mathrm{gap}})
\quad\text{(hub)}
$$

$$
\lambda_{\mathrm{eff}} = \sqrt{E_{\mathrm{gap}}(2\Lambda - E_{\mathrm{gap}})}
\quad\text{(paper, eq. 44)}
$$

Rejected if any angle circuit uses more than 128 qubits, or the encoded
Hamiltonian is more than 20 mHa off. The hub lists `Λ / E_gap` as
`49.0 / 3.914898` Ha. The paper states those as strict floors.

## Scoring

**Unconfirmed (hub).** Check `verifiers/` before trusting this. The reference
scores 1.0 and higher is better:

$$
\mathrm{Score}
  = \left(
      \prod_{b \in \{\mathrm{invsqrt},\,\mathrm{dqi},\,\mathrm{dfthcsos}\}}
      \frac{\mathrm{refcost}_b}{\mathrm{cost}_b}
    \right)^{1/3}
$$

The paper defines each task score and does not state this product.
`scripts/score.py` evaluates a chosen source on numbers you pass in. It never
fills in a leaderboard score.

## Submission zip

```text
invsqrt.kmb or invsqrt.kmx
dqi.kmb or dqi.kmx
dfthcsos/angle_k_0 .. angle_k_N    # no gaps
dfthcsos/submission.npz            # U, W, H2_I, H1_I, Hsym_lower, tree_edges
```

`scripts/package_submission.py` checks that layout and will not invent missing
files. The Kaggle data page that would show the sample zip was rate-limited.

## Rules and limits

Stated on the hub. The Kaggle rules page was rate-limited on 2026-11-05, so
this list is not an independent copy of that page.

- 5 submissions per day, 2 final selections, team size at most 5.
- Public tools, data, and LLMs are allowed. No private sharing outside the team.
- Winners ship reproducible Apache-2.0 code. This repository is Apache-2.0.
  The Google announcement confirms Apache-2.0 for the reference circuits and
  verifiers. The winners' sentence is from the hub.
- About 45 minutes of scoring per submission (hub).
- Prize pool **$150,000** (paper). Hub split: $50k / $25k / $10k / $5k / $5k /
  $5k, plus $10k milestone, $10k longest leader, and 3 × $10k per task.

## Timeline

Hub instants, displayed on that page in `America/New_York`. Not re-read from
Kaggle.

| Event | When (UTC) |
| --- | --- |
| Blog and paper | 2026-10-21 |
| Start (hub) | 2026-10-22 |
| Milestone prize | 2026-11-20 23:59 |
| Longest Leader cutoff | 2027-01-04 23:59 |
| Entry and merger deadline | 2027-01-13 23:59 |
| Final submission | 2027-01-20 23:59 |

## Run the baseline

Tested with Python 3.12, `noetl==5.3.2`, and `kickmix==1.0.0` (public
Apache-2.0 Qualtran package, not the Kaggle image binary).

```bash
python3 -m pip install -r requirements-baseline.txt
python3 -m unittest discover -s tests -t .
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

Run that from the repository root. The local runtime executes `kind: shell`
commands. It does not execute `kind: python`. The default mode is
`competition`: missing `data/verifiers` blocks verification and the package
step writes no zip. `noetl run ... --set mode=structural` writes labeled
kickmix fixtures under git-ignored `runs/` and still sets
`competition_verified` to false.

Provenance for each run is `runs/<id>/provenance.json`. The committed
experiments table stays empty until a real measurement exists. Details are in
the wiki mirror under `docs/wiki/`.

## How this repo uses NoETL

`playbooks/vqcc_pipeline.yaml` is the baseline orchestrator: prepare, check
data, adapt each task, verify, cost, package, record.
`playbooks/vqcc_optimize.yaml` adds a per-task peephole after that
verification and keeps a circuit only when the official verifier accepts a
strictly lower score. Per-task `tasks/*/generate.py` scripts still exit
without writing a circuit. The playbooks are the paths that actually run.

The pattern comes from the NoETL CUDA-Q fixture at tag `v2.10.15`,
[`tests/fixtures/playbooks/quantum_cudaq/`](https://github.com/noetl/noetl/tree/v2.10.15/tests/fixtures/playbooks/quantum_cudaq)
(catalog path `tests/quantum/cudaq_ai_pipeline`). That file is not on current
NoETL `main`. It is a MaxCut demonstration, not a competition result.

Planning lives in Spec Kit, initialized for Cursor:

- Constitution: `.specify/memory/constitution.md`
- First feature: `specs/001-noetl-pipeline/spec.md`
- Open scoring questions stay marked `[NEEDS CLARIFICATION]`

## Layout

```text
docs/            brief, primers, glossary, experiment log, data fetch
tasks/           invsqrt, dqi, dfthcsos stubs
playbooks/       NoETL pipeline
scripts/         score, package, fetch, experiment log
vqcc/            formula and packaging helpers
specs/001-noetl-pipeline/
```

## Data

Do not commit the dataset. From a machine where you have accepted the rules:

```bash
scripts/fetch_data.sh              # print the steps
scripts/fetch_data.sh --download   # Kaggle CLI into data/
```

See [docs/data.md](docs/data.md).

## What we could not verify

On 2026-11-05 the Kaggle overview, rules, and data URLs all returned
"Too many requests". The data page also requires a login. Formulas that the
hub marks unconfirmed, and the `λ_eff` conflict with the paper, are listed in
[docs/open-questions.md](docs/open-questions.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
