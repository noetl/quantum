# VQCC on NoETL

Home for the NoETL entry in
[Google Quantum AI — Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).

This wiki matches this tree: verifier JSON score parsing, the default local CLI run (`tests/test_playbook_cli.py`, eleven steps), and the per-task optimization loop (`playbooks/vqcc_optimize.yaml`).
The spec contract is `specs/001-noetl-pipeline/spec.md` at main
`0b3915b38fb2de7897b735995b7be33fde617c63`.
Issues: [2](https://github.com/noetl/quantum/issues/2) through
[9](https://github.com/noetl/quantum/issues/9).

## What runs today

`noetl run playbooks/vqcc_pipeline.yaml --runtime local --json` on the PyPI CLI **noetl 5.3.2**, after the document passes `POST https://noetl.ai/api/dsl/validate`. Rechecked 2026-11-11 on server **3.156.2** (`valid: true`, `execute_verdict: accept`, findings empty). Schema digest `sha256:29b2831fdd2444fab0bbc8915283a22ac86532393111f3a3cdad782bf6b1c4be`. The 2026-11-10 digest on server 3.156.1 was `sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6`. The workflow's first step is named `start`.

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
then rewrites that task only. A candidate replaces the retained artifact only
when the official verifier accepts it and the JSON `score` is strictly lower
(user story 2, FR-004, FR-011). The other tasks' files are not written. A
pass that does not lower the charged weight or the qubit count
writes no circuit (FR-003). Packaging stays disarmed. The Kaggle entrypoint
is `python3 kaggle/vqcc_optimize.py`. It does not submit.

The passes are semantics-preserving on the kickmix gate set. They are not a
new invsqrt, dqi, or dfthcsos algorithm. Cancellation uses a configurable
horizon (playbook default 4096) and only walks gates that share a qubit or a
bit, plus condition barriers. Z rotations on one qubit merge at any distance
until a gate they do not commute with. Arithmetic commutation lets a Toffoli
slide past an X on its target, a phase on its controls, and other Toffolis
that share those controls. A clean Toffoli uncompute whose target is used in
between is replaced by kickmix `HMR` plus a classically controlled `CZ`
(`del_and`); the compute Toffoli stays. invsqrt's static weight charges
Toffolis, T gates, and fine rotations. dqi and dfthcsos charge Toffolis only
(FR-006 and FR-007 stay open on the factors in front of that count). A file
is written when that weight drops or when the qubit count drops. A shrink
that only removes free Cliffords, and does not free a qubit id, is not sent
to the verifier. A rewrite that adds Toffolis is not written.

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
