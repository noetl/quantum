# 2. Datasets

[Environment](01-environment.md) · [Index](README.md) · Next: [Playbooks](03-playbooks.md)

Each task is scored against files from the Kaggle competition dataset. Those
files are not in this repository. FR-017 forbids copying competition data and
kickmix binaries into the playbook or the task directories. FR-019 says an
operator fetches them with the Kaggle CLI into a git-ignored directory, and
that the repository must not contain them. Constitution principle III is the
same rule.

## Where they sit on Kaggle

The private notebook mounts the competition at:

`/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation`

The version 8 log lists that mount and the scripts the playbook calls. Paths
below are from that log and from `docs/wiki/Architecture.md`.

| Task | Input the adapt step imports | Official verifier |
| --- | --- | --- |
| `invsqrt` | `sample_submission/invsqrt.kmb` | `verifiers/invsqrt/verify_submission_invsqrt.py` |
| `dqi` | `sample_submission/dqi.kmb` (about 886 MB; passed by path, not loaded as a `kickmix.Circuit`) | `verifiers/dqi/verify_submission_dqi.py` |
| `dfthcsos` | `sample_submission/dfthcsos/` | `verifiers/dfthcsos/verify.py` |

The version 8 log's directory listing shows `sample_submission/invsqrt.kmb`,
`sample_submission/dqi.kmb`, and ten angle files
`sample_submission/dfthcsos/angle_k_0.kmb` through `angle_k_9.kmb`, plus
`submission.npz` as described by `verifiers/dfthcsos/SCORING_README.md` in
that same log. The image also has `kickmix/kickmix.so` and
`verifiable_circuit_compilation.pdf`. The early listing in the log is
shallow (`verifiers` shows one entry at that instant); the later lines name
the three scripts and the ten angle files, so those paths are the ones to
trust.

Seed on these runs is `20261108`, passed as `--seed`. A local seed is not
the leaderboard salt. FR-010: verification uses the competition verifiers,
including their salted inputs, and does not substitute a hand-picked example.

## What each task is made of

**invsqrt.** One kickmix circuit. The paper's reference description (not a
measurement from this repo) is `Q = 260`, 7,735 Toffolis, 1 T, 37
non-Clifford rotations. The verifier JSON on the sample matches those counts.
See [Scoring](04-scoring.md).

**dqi.** One kickmix circuit, the coherent decoder. The sample header is
1,893 qubits and 5,725,461 Toffolis at the max count. The file is large
enough that the rewriter memory-maps `.kmb` instead of building a
`kickmix.Circuit`.

**dfthcsos.** A directory. The sample has `angle_k_0.kmb` … `angle_k_9.kmb`
and `submission.npz`. The verifier README captured in the version 8 log says
the npz holds `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`, and `tree_edges`, and
that submitted `H1_I` and `Hsym_lower` are ignored in favor of a fixed
baseline shift. It also says other files in the directory are ignored by
that verifier. This repo's packager is stricter: `vqcc/packaging.py` still
expects the hub names `angle_k_0` … `angle_k_N` with no extension and no
extra files (FR-012, FR-014). That mismatch is an open packaging question,
not a silent change to the packager. See [Open questions](09-open-questions.md).

## Why the samples are not in git

The dataset is about 1 GB and license-restricted. `.gitignore` excludes
`/data/`, `/submissions/`, `/runs/`, `**/*.so`, `*.kmb`, `*.kmx`, `*.npz`,
and Kaggle credentials. Committing a sample would publish competition inputs
this repo is not licensed to redistribute, and it would mix reference
circuits into the history of the code.

Fetch, only after a person has accepted the rules in the browser:

```bash
scripts/fetch_data.sh              # print the steps, contact nothing
scripts/fetch_data.sh --download   # Kaggle CLI into data/
```

`scripts/fetch_data.sh` without `--download` does not contact Kaggle. Issue
[#8](https://github.com/noetl/quantum/issues/8) is closed on that behavior.
The download itself is a human step. This repository's automation does not
accept the rules.

Leave the files untracked. `git status` should not list `data/`.

## What a machine without the dataset can still prove

US1, scenario 1, and FR-002: if `data/verifiers` is absent, every task check
finishes blocked, no circuit is written, and no Local or LB number is
recorded. That is the CI default. Official PASS/FAIL on the reference
circuits happens on the Kaggle notebook, not in this cloud workspace.
