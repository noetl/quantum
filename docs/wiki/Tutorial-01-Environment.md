# 1. Environment

This is the wiki copy of `docs/tutorial/01-environment.md`. Wording matches that page. Links on this copy use wiki page names.


[Overview](Tutorial-00-Overview) · [Index](Tutorial) · Next: [Datasets](Tutorial-02-Datasets)

Local runs and CI use one pinned stack. The Kaggle notebook installs the
same file. Versions below are the ones `requirements-baseline.txt` and the
wiki record, not a newer release.

| Piece | Version | Role |
| --- | --- | --- |
| Python | 3.12 in CI (`.github/workflows/ci.yml`) | Adapters, formulas, packaging. The version 8 notebook log shows the Kaggle image on Python 3.13, installing the same requirements file. |
| NoETL CLI | 5.3.2 | Local playbook runtime. `apiVersion: noetl.io/v2`. |
| kickmix | 1.0.0 | Public Apache-2.0 Qualtran package. Builds and measures `.kmx` / `.kmb`. This is not `kickmix.so` from the Kaggle image. |
| PyYAML | `>=6.0.3` | Playbook parsing. The Kaggle image already has it. |

## Install and run the baseline

From the repository root:

```bash
python3 -m pip install -r requirements-baseline.txt
python3 -m unittest discover -s tests -t .
noetl run playbooks/vqcc_pipeline.yaml --runtime local --json
```

US5 and issue [#2](https://github.com/noetl/quantum/issues/2) are this
command. With no `data/` directory the run finishes `status: ok`, lists
eleven steps, sets `leaderboard_score` to null, sets verification to
`blocked`, and writes no zip. That blocked result is the correct local
outcome. It is not a pass. The CI job `cli-default` runs
`tests/test_playbook_cli.py`, which shells that command.

`noetl run ... --set mode=structural` writes labeled kickmix fixtures under
git-ignored `runs/`. `competition_verified` stays false. Those files are not
a submission.

## What the 5.3.2 local runtime actually executes

The local CLI runs `tool.kind: shell` steps whose `cmds` are shell strings,
and it follows `next`. It does not execute `kind: python`. Every Python call
in these playbooks is a `python3 -m vqcc.pipeline ...` line inside a shell
step. A workflow must contain a step named `start`. Both playbooks do.

The first step in the file is named `start`. The shell command it runs is
`python3 -m vqcc.pipeline prepare`.

## DSL validation

Before a playbook is trusted, it is posted to the public validator:

`POST https://noetl.ai/api/dsl/validate`

with `Content-Type: application/yaml`. The check this tree records, and that
CI repeats through `scripts/validate_playbooks.py`:

| Item | Value |
| --- | --- |
| Server | `GET /api/dsl/version` reported 3.161.2 on 2026-11-13. The validate body omitted `server_version`. The 2026-11-11 and 2026-11-12 checks recorded server 3.156.2. |
| Result | HTTP 200, `valid: true`, `execute_verdict: accept`, findings empty, on both playbooks. |
| Schema digest | `sha256:25071111774314cbf0c83ee9925b53701c2228232574bda3b13b1e27d58b372c` |
| Previous digest | `sha256:29b2831fdd2444fab0bbc8915283a22ac86532393111f3a3cdad782bf6b1c4be` on server 3.156.2 (2026-11-11). Before that, `sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6` on server 3.156.1 (2026-11-10) and server 3.156.0 / 3.153.0 earlier. |

The digest and the server version are copied from
[docs/dsl/README.md](../dsl/README.md) and from the comments at the top of
each playbook. The 2026-11-13 row is a live recheck. The playbook steps
were not rewritten.

A transport failure is not a pass. `scripts/validate_playbooks.py` is the
CI step that performs the POST.

## What is not part of the local stack

The competition dataset, `kickmix.so`, and any submission zip stay out of
this environment unless a person has accepted the rules and downloaded them
into git-ignored `data/`. Issue [#8](https://github.com/noetl/quantum/issues/8)
is that fetch path. The local runtime does not accept the rules and does not
call the Kaggle submit API.
