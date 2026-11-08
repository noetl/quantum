"""Validate playbook YAML against the public NoETL DSL API.

GET https://noetl.ai/api/dsl/version
POST https://noetl.ai/api/dsl/validate with Content-Type: application/yaml

The body is the playbook text. No credentials and no dataset bytes are sent.
If the API cannot be reached, the result says so and a local check against
the committed schema plus the start-step rule from noetl/server@5cf0712 is
used instead. That local check is not reported as a remote validation.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

API_VERSION_URL = "https://noetl.ai/api/dsl/version"
API_VALIDATE_URL = "https://noetl.ai/api/dsl/validate"
USER_AGENT = "noetl-quantum-dsl-client/1.0"

# Inspected 2026-11-08 from GET /api/dsl/version and /dsl/source.json.
EXPECTED_SCHEMA_DIGEST = (
    "sha256:de6519f1f025dcb0e4743e321cff30e8ac4800d38acaaecf8249c00a13ab9ad6"
)
SERVER_COMMIT = "5cf0712da626a28af9f73f833d48d7c6e5c13140"
SERVER_VERSION = "3.153.0"
AI_META_HEAD = "28353ae54dac7307443830283783441d066b314b"


def fetch_version(timeout: float = 30) -> dict:
    request = urllib.request.Request(API_VERSION_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
        payload["_http_status"] = response.status
    return payload


def validate_yaml(text: str, timeout: float = 60) -> dict:
    request = urllib.request.Request(
        API_VALIDATE_URL,
        data=text.encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/yaml",
            "Accept": "application/json",
            "x-noetl-schema-digest": EXPECTED_SCHEMA_DIGEST,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            payload["_http_status"] = response.status
            payload["_remote"] = True
            return payload
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "_remote": False,
            "_http_status": exc.code,
            "error": body[:2000],
            "valid": None,
        }
    except urllib.error.URLError as exc:
        return {"_remote": False, "_http_status": None, "error": str(exc.reason), "valid": None}


def local_semantic_check(text: str) -> dict:
    """Rules stated by the live server that the JSON Schema does not enforce."""

    import yaml

    findings = []
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {"valid": False, "remote": False, "findings": [{"rule": "yaml", "message": str(exc)}]}
    if not isinstance(document, dict):
        findings.append({"rule": "metadata", "message": "document is not a mapping"})
        return {"valid": False, "remote": False, "findings": findings}
    workflow = document.get("workflow") or []
    names = []
    for step in workflow:
        if isinstance(step, dict) and step.get("step"):
            names.append(step["step"])
    if "start" not in names:
        findings.append(
            {
                "rule": "playbook_rule",
                "message": "Workflow must have a step named 'start'",
            }
        )
    if len(names) != len(set(names)):
        findings.append({"rule": "playbook_rule", "message": "duplicate step name"})
    known = set(names)
    for step in workflow:
        if not isinstance(step, dict):
            continue
        for target in _next_targets(step.get("next")):
            if target not in known:
                findings.append(
                    {
                        "rule": "playbook_rule",
                        "message": f"next target {target} does not exist",
                        "step": step.get("step"),
                    }
                )
    return {
        "valid": not findings,
        "remote": False,
        "source": f"local semantic checks from noetl/server@{SERVER_COMMIT}",
        "findings": findings,
    }


def _next_targets(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        targets = []
        for item in value:
            if isinstance(item, str):
                targets.append(item)
            elif isinstance(item, dict) and item.get("step"):
                targets.append(item["step"])
        return targets
    if isinstance(value, dict):
        arcs = value.get("arcs") or []
        return [arc["step"] for arc in arcs if isinstance(arc, dict) and arc.get("step")]
    return []


def validate_playbook_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    remote = validate_yaml(text)
    local = local_semantic_check(text)
    return {
        "path": str(path),
        "remote": remote,
        "local_semantic": local,
        "accepted": remote.get("valid") is True,
    }
