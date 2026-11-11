# NoETL DSL provenance

Live API inspected 2026-11-08. Nothing here was hand-copied from an old CLI.

| Item | Value |
| --- | --- |
| Version endpoint | `GET https://noetl.ai/api/dsl/version` |
| Schema endpoint | `GET https://noetl.ai/schema/v2/playbook.schema.json` and `GET https://noetl.ai/api/dsl/schema` |
| Validate endpoint | `POST https://noetl.ai/api/dsl/validate` with `Content-Type: application/yaml` and the playbook body |
| Manifest | `GET https://noetl.ai/dsl/manifest.json` |
| Source | `GET https://noetl.ai/dsl/source.json` |
| `schema_digest` | `sha256:29b2831fdd2444fab0bbc8915283a22ac86532393111f3a3cdad782bf6b1c4be` (live validate response, 2026-11-11, server 3.156.2). The 2026-11-08 through 2026-11-10 pin was `sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6`. |
| `server_version` | `3.156.2` on the 2026-11-11 validate call. The 2026-11-08 note recorded `3.153.0`. |
| `server_commit` | `5cf0712da626a28af9f73f833d48d7c6e5c13140` (`noetl/server`) |
| ai-meta HEAD | `28353ae54dac7307443830283783441d066b314b` |
| Component gitlinks at that ai-meta commit | server `5cf0712`, docs `2d044a4`, noetl.ai `4d5aee1`, worker `ddc9eb93`, tools `4687bcab`, cli `3d8c5013` |

The committed `playbook.schema.json` is the document those GET endpoints returned. `scripts/validate_playbooks.py` posts `playbooks/*.yaml` and writes `last-validation.json`. A transport failure is not recorded as a pass.

The published local executor used by the tests is PyPI `noetl==5.3.2`. It runs `kind: shell` with `cmds`. The live server grammar also accepts `kind: python` and requires a step named `start`. This repository's playbook uses shell `cmds` and a `start` step so both the API and that CLI accept it.

Repeat:

```bash
python3 scripts/validate_playbooks.py
```
