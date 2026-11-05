# NoETL quantum

Home for the NoETL entry in the Kaggle competition
[Google Quantum AI — Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).

NoETL playbooks orchestrate the work: agents and tools propose circuits, kickmix
and the competition verifiers check them, a labeled formula explains the cost,
and a packager builds the submission zip. This repository is the brief, the
pipeline spec, and the skeleton. It does not contain the competition data, a
circuit, or a score.

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

## How this repo uses NoETL

`playbooks/vqcc_pipeline.yaml` is the orchestrator. Each step returns a status
and leaves `leaderboard_score` null. Per-task generators in `tasks/` exit
without writing a circuit until kickmix and the verifiers exist under `data/`.

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
