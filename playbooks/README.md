# Playbooks

`vqcc_pipeline.yaml` is the NoETL entry point for this competition. It checks
that `data/verifiers` exists, reports that per-task generators are not
implemented, and confirms the score and packaging scripts are on disk. The
closing step sets `leaderboard_score` to null.

It follows the current NoETL playbook shape (`apiVersion: noetl.io/v2`, a
Python `main()` in each step), the same shape as
`tests/fixtures/playbooks/fanout_reduce/fanout_reduce_phase6.yaml` on NoETL
`main`.

The CUDA-Q example that motivated this layout is
[`tests/fixtures/playbooks/quantum_cudaq/`](https://github.com/noetl/noetl/tree/v2.10.15/tests/fixtures/playbooks/quantum_cudaq)
at NoETL tag `v2.10.15` (playbook `quantum_cudaq_ai_pipeline`, catalog path
`tests/quantum/cudaq_ai_pipeline`). That fixture is not on current NoETL
`main` or tag `v4.26.2`. It shows how a playbook can run a quantum workload,
hand the trace to an analysis step, and persist the record. It is a MaxCut
demo, not a VQCC submission, and this repository does not copy its outputs.

This playbook was not executed against a NoETL gateway in the change that
added it. Register and run it with the NoETL CLI when a gateway is available.
Until then, use the scripts in `scripts/` directly.
