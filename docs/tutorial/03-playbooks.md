# 3. The pipeline playbooks

[Datasets](02-datasets.md) · [Index](README.md) · Next: [Scoring](04-scoring.md)

Two playbooks. Both are `apiVersion: noetl.io/v2` and both start with a step
named `start`. Neither file embeds a circuit or a numeric score (US5,
acceptance scenario 2). Workload keys are `mode`, `data_dir`, `runs_root`,
`repo_root`, and `seed` (default `20261108`). Override with
`noetl run ... --set key=value`.

The diagram on the [index](README.md) is this flow. The optimize steps exist
only in the second playbook.

## `playbooks/vqcc_pipeline.yaml`

The baseline orchestrator. Issue [#2](https://github.com/noetl/quantum/issues/2),
US5, FR-016. Eleven shell steps:

| Step | What it does |
| --- | --- |
| `start` | `python3 -m vqcc.pipeline prepare`. Creates `runs/<id>/` and points `runs/active.json` at it. |
| `check_data` | Reports whether `data/verifiers` is on disk. Absence is a block, not a pass (FR-002). |
| `adapt_invsqrt` | Imports an on-disk invsqrt baseline by path and SHA-256, or writes nothing. |
| `adapt_dqi` | Same for dqi. |
| `adapt_dfthcsos` | Same for the dfthcsos directory. |
| `verify_invsqrt` | Official invsqrt script with `--seed`. Missing script blocks. |
| `verify_dqi` | Official dqi script, after invsqrt. The sample is large and is passed by path. |
| `verify_dfthcsos` | Official dfthcsos script. No flag that weakens the check. |
| `cost` | Copies an authoritative verifier JSON `score` when one was stored (FR-004). Otherwise prices invsqrt from kickmix counts. `leaderboard_score` stays null (FR-008, FR-009, FR-016). |
| `package` | Refuses a zip while any task is unverified (US3, FR-011). |
| `record` | Writes `runs/<id>/provenance.json`. Does not append an invented experiments row (US4, FR-015). |

Default `mode` is `competition`. With no baseline file, adapt writes nothing
(FR-003). `mode=structural` writes kickmix fixtures labeled
`structural_fixture`. Those cannot set `competition_verified`.

```bash
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

## `playbooks/vqcc_optimize.yaml`

The per-task loop. Issue [#9](https://github.com/noetl/quantum/issues/9),
US2. It runs the same prepare, check, adapt, and verify steps, then:

| Step | What it does |
| --- | --- |
| `optimize_invsqrt` | Profiles invsqrt and rewrites that file only. |
| `optimize_dqi` | Profiles dqi and rewrites that file only. The `.kmb` is streamed. |
| `optimize_dfthcsos` | Profiles the angle circuits. `submission.npz` is copied, not recomputed. |
| `cost` | Copies an authoritative JSON score. `leaderboard_score` stays null. |
| `package` | Does not write a zip unless packaging was explicitly armed. The playbook does not arm it. |
| `record` | Writes `provenance.json`. |

One optimize step never writes another task's files (US2, scenario 1,
FR-001). A rejected proposal leaves the previous artifact in place (US2,
scenario 2, FR-011).

Defaults on the optimize playbook, from the workload block:

| Key | Value | Meaning |
| --- | --- | --- |
| `time_budget_s` | 14400 | Cap for one optimize step. Not a target runtime. |
| `memory_budget_bytes` | 2147483648 | Files above 2 GiB are left untouched. dqi's sample is about 886 MB and is mapped, not loaded as a circuit. |
| `window` | 4096 | Cancellation horizon. The search walks gates that share a qubit or a bit. Z-rotation merging ignores this horizon. |
| `max_candidates` | 1 | At most one candidate per task. The code refuses a value above 3. |

The notebook entrypoint that calls the same steps without requiring the
`noetl` binary is `kaggle/vqcc_optimize.py`. It does not submit.

## What the optimize step will and will not write

The rewriter is `vqcc/optimize.py`. Passes are semantics-preserving on the
kickmix instruction set. The same passes run for every task. The task changes
which static weight can veto a write.

A file is written when the charged weight drops or the qubit count drops
(FR-003). It is kept only after the verifier, which is the next section.

- Cancel a self-inverse gate (X, CX, CCX, Z, CZ, CCZ, SWAP, CSWAP, NEG,
  BIT_INVERT, including conditional forms) when everything between the two
  copies commutes.
- Merge Z and `Z_POW` on the same qubit by adding the exact turn fraction.
- Drop a later bit-store that overwrites an earlier one, and drop an empty
  push/pop condition pair.
- Measurement uncompute: a clean Toffoli whose target was used in between is
  replaced by kickmix `HMR` plus a classically controlled `CZ` (`del_and`).
  The compute Toffoli stays. Issue
  [#17](https://github.com/noetl/quantum/issues/17).
- Shared-control factoring: while a clean AND is still on its target, a
  later `CCX` of the same control values and a different target becomes
  `CX`. A restored control (`X`·`X`, `CX`·`CX`, `CCX`·`CCX`, `CSWAP`·`CSWAP`,
  `SWAP`·`SWAP`) and an unconditional `SWAP` that moves the control are
  included. A reset, a measurement, or any unproven write is not. Issue
  [#19](https://github.com/noetl/quantum/issues/19).
- Scratch reuse: scratch ids move onto a real gap, or onto an id freed by an
  unconditional `R` or `HMR`, and only when a named register tells system ids
  from scratch.

`structure` in the step JSON is the profile from `vqcc/profile.py`: opcodes,
lifetimes, peak live qubits, repeated blocks. It is logged even when no file
is written. It is not a score.

A shrink that only removes free Cliffords, and does not free a qubit id, is
not sent to the verifier. A rewrite that adds Toffolis is not written.

Charged weight used as that veto, from `docs/wiki/Architecture.md`:

- invsqrt: `4*Toffoli + T + 16*fine`. The 16 is kickmix's stand-in for a fine
  rotation, not the shot-mean score.
- dqi and dfthcsos: `4*Toffoli` only. FR-006 and FR-007 stay open on the
  factors in front of that count.

`Q` is one past the highest id that a register still names or an emitted
gate still uses. A scratch id the rewrite no longer touches is not padded
back with a pair of `Z` gates.
