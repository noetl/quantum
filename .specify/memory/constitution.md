# NoETL Quantum Constitution

## Core Principles

### I. No fabricated results

Reports, experiment logs, and commits contain only measurements this repository
actually produced. A missing circuit, verifier outcome, local cost, or
leaderboard score stays blank. Sample numbers used to test formula code are
labeled as formula checks and are never written into the experiment log as runs.

### II. Unconfirmed stays unconfirmed

A claim the team hub marks unconfirmed stays marked unconfirmed until the
competition metric code confirms it. When the hub, the companion paper, and the
verifier sources disagree, the disagreement is recorded. It is not resolved by
picking the convenient reading.

### III. Competition data stays out of git

The Kaggle dataset, kickmix binaries, and built submission archives are local
files. They are git-ignored. Code published from this repository is Apache-2.0
so a winning entry can meet the reproducibility requirement stated on the hub.
Secrets, including Kaggle API tokens, are never committed.

### IV. Verifiers decide correctness

A circuit is eligible for packaging only after the competition verifiers accept
it. Local formula helpers explain a cost. They do not replace kickmix, and they
do not stand in for a leaderboard score. Randomized tests are seeded from the
submission, so a circuit has to be correct beyond a fixed example set.

### V. Playbooks orchestrate, tasks stay separate

NoETL playbooks sequence generation, verification, cost calculation, packaging,
and experiment logging. Circuit work for invsqrt, dqi, and dfthcsos lives in
its own task directory. A playbook step that cannot run because data or a tool
is missing stops with an explicit reason and records no score.

## Competition boundaries

The entry is the Kaggle competition "Google Quantum AI - Verifiable Quantum
Circuit Compilation". Three tasks are in scope: invsqrt, dqi, and dfthcsos.
Public tools, public data, and public models are allowed. Sharing privately
outside the team is not. dfthcsos submissions have to respect the qubit cap and
the Hamiltonian tolerance documented in the brief. This repository does not
vendor the competition dataset.

## Development workflow

Changes land through a pull request. A change that adds a numeric result names
the command, the formula source, and the inputs that produced it. Experiment
rows use the hub's columns: Date, Run, Description, Local, LB, Notes. Unknown
Local or LB cells stay unknown. Spec Kit specs under `specs/` are the planning
record for pipeline work. Open scoring questions stay marked
`[NEEDS CLARIFICATION]` until the verifier sources close them.

## Governance

This constitution supersedes informal practice for this repository. Amendments
are pull requests that update this file, bump the version below, and note what
changed. Versioning follows semantic versions: MAJOR for a principle removed or
redefined, MINOR for a new principle or a material expansion, PATCH for wording
that does not change a rule. Reviewers check that diffs do not add competition
data, kickmix binaries, submission archives, or unsupported scores.

**Version**: 1.0.0 | **Ratified**: 2026-11-05 | **Last Amended**: 2026-11-05
