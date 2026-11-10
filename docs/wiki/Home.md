# VQCC on NoETL

Home for the NoETL entry in
[Google Quantum AI — Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).

This wiki matches this tree: verifier JSON score parsing, the default local CLI run (`tests/test_playbook_cli.py`, eleven steps), and the per-task optimization loop (`playbooks/vqcc_optimize.yaml`).
The spec contract is `specs/001-noetl-pipeline/spec.md` at main
`0b3915b38fb2de7897b735995b7be33fde617c63`.
Issues: [2](https://github.com/noetl/quantum/issues/2) through
[9](https://github.com/noetl/quantum/issues/9).

## What runs today

`noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` on the PyPI CLI **noetl 5.3.2**, after the document passes `POST https://noetl.ai/api/dsl/validate`. Rechecked 2026-11-10 on server **3.156.1** (`valid: true`, findings empty). Schema digest `sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6` is unchanged from the 3.156.0 and 3.153.0 / `noetl/server@5cf0712` snapshots. The workflow's first step is named `start`.

With no competition data the playbook:

- checks `data/verifiers` and reports it absent
- writes no circuit bytes
- does not call a stand-in verifier
- computes no leaderboard score (`leaderboard_score` is null). A later run that has the dataset can store each task's official JSON `score` as an authoritative cost. That number is still not the LB column (spec FR-008, FR-009, FR-016).
- writes no submission zip
- writes `runs/<id>/provenance.json`

`noetl run ... --set mode=structural` also writes three real kickmix circuits
under `runs/` using **kickmix 1.0.0**. They are labeled `structural_fixture`.
`competition_verified` stays false. The invsqrt fixture is priced with
`Q * (Toffoli + T/4)` from `kickmix` operation statistics. That number is a
formula evaluation of that file, not a leaderboard score. dqi and dfthcsos
costs stay uncomputed because `ε⁺` and the chemistry inputs are not invented.

## Optimization loop

`playbooks/vqcc_optimize.yaml` is a second playbook. It verifies each baseline,
then runs a kickmix peephole on that task only. A candidate replaces the
retained artifact only when the official verifier accepts it and the JSON
`score` is strictly lower (user story 2, FR-011). The other tasks' files are
not written. A pass that does not improve the local gate-count proxy writes
no circuit (FR-003). Packaging stays disarmed. The Kaggle entrypoint is
`python3 kaggle/vqcc_optimize.py`. It does not submit.

The passes are adjacent and windowed cancellation of self-inverse gates, and
fusion of Z rotations on the same qubit when that fusion does not add a
T-like gate or a level-4-or-finer rotation. They are semantics-preserving on
the kickmix gate set. They are not a new invsqrt, dqi, or dfthcsos algorithm.
If the reference circuits have no such pairs inside the window, the loop keeps
the baseline and writes no candidate.

## What is not done

- No measured improvement on the Kaggle reference circuits. This environment
  does not have the dataset, so the official verifiers were not run here.
- No official verifier pass recorded by this repository. The Kaggle dataset
  needs an account that has accepted the rules. This repo does not accept
  those rules or submit.
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
