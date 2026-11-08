#!/usr/bin/env python3
"""Validate repository playbooks against https://noetl.ai/api/dsl/validate.

Sends only the YAML in playbooks/. Prints the API provenance and exits 1
when the live API rejects a document. A transport failure is reported as
remote=false and is not described as a successful validation; the local
semantic check still runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.dsl_validate import (  # noqa: E402
    AI_META_HEAD,
    EXPECTED_SCHEMA_DIGEST,
    SERVER_COMMIT,
    SERVER_VERSION,
    fetch_version,
    validate_playbook_file,
)


def main() -> int:
    try:
        version = fetch_version()
    except Exception as exc:  # noqa: BLE001 — the CLI must show the transport error
        version = {"error": str(exc), "_remote": False}
    print(
        json.dumps(
            {
                "endpoint": "https://noetl.ai/api/dsl/version",
                "expected_schema_digest": EXPECTED_SCHEMA_DIGEST,
                "expected_server_version": SERVER_VERSION,
                "expected_server_commit": SERVER_COMMIT,
                "ai_meta_head": AI_META_HEAD,
                "live_version": version,
            },
            indent=2,
        )
    )
    failed = False
    remote_failed = version.get("_remote") is False or "error" in version and "api_version" not in version
    reports = []
    for path in sorted((ROOT / "playbooks").glob("*.yaml")):
        report = validate_playbook_file(path)
        reports.append(
            {
                "path": path.name,
                "remote_valid": report["remote"].get("valid"),
                "remote_http": report["remote"].get("_http_status"),
                "findings": report["remote"].get("findings"),
                "error": report["remote"].get("error"),
                "local_valid": report["local_semantic"]["valid"],
            }
        )
        if report["remote"].get("valid") is not True:
            failed = True
        if not report["local_semantic"]["valid"]:
            failed = True
    print(json.dumps({"playbooks": reports}, indent=2))
    out = ROOT / "docs" / "dsl" / "last-validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"version": version, "playbooks": reports}, indent=2) + "\n",
        encoding="utf-8",
    )
    if remote_failed:
        print("remote DSL API was not validated", file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
