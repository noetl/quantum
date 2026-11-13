# 0. Overview and goals

[Index](README.md) · Next: [Environment](01-environment.md)

## The competition

The entry is the Kaggle competition
[Google Quantum AI — Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).
The job is three circuits, each cheaper than Google's reference, that still
pass that task's verifier. Cheaper means a lower task cost. `Q`, the qubit
count, multiplies every cost, and on dqi it is squared.

The three tasks, from [the brief](../brief.md) and user story 1 through user
story 3 in `specs/001-noetl-pipeline/spec.md`:

| Task | What it is | File the verifier scores |
| --- | --- | --- |
| `invsqrt` | Reversible `1/√x`, the Coulomb phase | `invsqrt.kmb` or `.kmx` |
| `dqi` | Coherent Reed–Solomon decode over `GF(2^12)` | `dqi.kmb` or `.kmx` |
| `dfthcsos` | Block encoding of a DF/THC chemistry Hamiltonian | `dfthcsos/` angle circuits plus `submission.npz` |

US1 (User Story 1) is the check: a missing verifier blocks the run, and a
failed candidate is not packageable. US2 (User Story 2) is the improvement
loop: one task can get cheaper while the other two stay put. US3 (User Story
3) is the zip, and only after each task has been accepted. US4 (User Story 4)
is the experiment log. US5 (User Story 5) is the NoETL playbook that walks
those stages and returns a null leaderboard score when Kaggle has not
returned one.

FR-001 requires the three tasks to stay separate artifacts with separate
verifier runs.

## The team hub

The team hub is <https://dg-create.com/kaggle/quantum>. It is the brief this
repository was written from: task statements, the cost write-ups, the
submission layout, and the rules summary. Claims that page marks
**unconfirmed** stay marked that way. When the hub and the companion paper
[arXiv:2610.23832](https://arxiv.org/abs/2610.23832) disagree, both readings
stay on the page. The spec records the three disagreements that still block
a default formula as FR-006, FR-007, and FR-008. See
[Open questions](09-open-questions.md).

Bot activity is on <https://dg-create.com/tower/>. What that page shows is
[docs/tower.md](../tower.md).

## Why NoETL

NoETL is how this repository runs the loop. Constitution principle V: a
playbook sequences the work, and each task stays its own artifact. A step
that cannot run because the data or a tool is missing stops with a reason
and records no score.

That shows up as two playbooks:

- `playbooks/vqcc_pipeline.yaml` checks data, imports each baseline, verifies,
  costs, and refuses to package. US5, FR-016.
- `playbooks/vqcc_optimize.yaml` does that and then rewrites one task at a
  time. US2, FR-003, FR-004, FR-011.

The playbook is the thing a person or an agent can rerun. It does not contain
a circuit or a leaderboard score. `tasks/*/generate.py` still exits without
writing a file: building a new circuit is not the same job as rewriting a
verified baseline (US2, acceptance scenario 3, FR-003).

The precedent is the NoETL CUDA-Q fixture at tag `v2.10.15`. That file is a
MaxCut demonstration. It is not a competition result, and it is not on
current NoETL `main`.

## What "done" means for a circuit

A candidate replaces the retained artifact only when that task's official
verifier returns JSON `status` `PASS` and a finite `score` that is strictly
lower than the retained score. Lower is better on each task cost. A shorter
file that only deletes Cliffords does not qualify, because those gates are
not what the cost charges. The rule is spelled out in
[Scoring](04-scoring.md).

Nothing in this repository submits to Kaggle. Packaging stays disarmed on
the optimize playbook. Publishing or sharing the private notebook needs an
explicit approval. See [Running on Kaggle](05-kaggle.md).
