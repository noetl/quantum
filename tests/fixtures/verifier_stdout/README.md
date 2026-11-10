# Verifier stdout fixtures

These files are shapes of official-verifier stdout, used by
`tests/test_verifier_score.py`. They are not measurements produced by this
repository and they are not a Kaggle submission.

`invsqrt_pass.json` uses the public full-run fields whose product matches the
task cost 2076774.233715282 (`num_qubits` 260 times `toffoli_equivalent`
7987.593206597238). `dqi_pass.json` and `dfthcsos_pass.json` carry the raw
task costs named in the pipeline report for seed 20261108. Only `status` and
`score` are treated as the shared document. Extra dfthcsos keys are not
invented here. Nested maps are present on the dqi fixture so the parser can
show that it keeps scalars only.
