# VQCC on NoETL

Home for the NoETL entry in
[Google Quantum AI — Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).

This wiki matches the implementation on branch `cursor/vqcc-noetl-baseline-5071`.
The spec contract is `specs/001-noetl-pipeline/spec.md` at main
`0b3915b38fb2de7897b735995b7be33fde617c63`.
Issues: [2](https://github.com/noetl/quantum/issues/2) through
[9](https://github.com/noetl/quantum/issues/9).

## What runs today

`noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` on **NoETL 5.3.2**.

With no competition data the playbook:

- checks `data/verifiers` and reports it absent
- writes no circuit bytes
- does not call a stand-in verifier
- computes no leaderboard score (`leaderboard_score` is null)
- writes no submission zip
- writes `runs/<id>/provenance.json`

`noetl run ... --set mode=structural` also writes three real kickmix circuits
under `runs/` using **kickmix 1.0.0**. They are labeled `structural_fixture`.
`competition_verified` stays false. The invsqrt fixture is priced with
`Q * (Toffoli + T/4)` from `kickmix` operation statistics. That number is a
formula evaluation of that file, not a leaderboard score. dqi and dfthcsos
costs stay uncomputed because `ε⁺` and the chemistry inputs are not invented.

## What is not done

- No competition-quality optimizer.
- No official verifier pass. The Kaggle dataset needs an account that has
  accepted the rules. This repo does not accept those rules or submit.
- FR-006, FR-007, and FR-008 in the spec stay `[NEEDS CLARIFICATION]`.
- The committed experiments table has no Local or LB numbers.

## Pages

- [Architecture](Architecture)
- [User Guide](User-Guide)
- [Developer Guide](Developer-Guide)
- [Spec and issue traceability](Spec-and-Issue-Traceability)
- [Experiments](Experiments)
- [Roadmap](Roadmap)

A copy of these pages is versioned in the repository at `docs/wiki/`.
