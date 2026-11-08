"""Live check of playbooks/vqcc_pipeline.yaml against https://noetl.ai ."""

from __future__ import annotations

import unittest
from pathlib import Path

from vqcc.dsl_validate import EXPECTED_SCHEMA_DIGEST, validate_playbook_file

ROOT = Path(__file__).resolve().parents[1]


class DslApiTests(unittest.TestCase):
    def test_reference_playbook_is_accepted(self) -> None:
        report = validate_playbook_file(ROOT / "playbooks" / "vqcc_pipeline.yaml")
        remote = report["remote"]
        self.assertTrue(remote.get("_remote"), remote.get("error"))
        self.assertEqual(remote.get("_http_status"), 200)
        self.assertTrue(remote.get("valid"), remote.get("findings"))
        self.assertEqual(remote.get("execute_verdict"), "accept")
        self.assertEqual(remote.get("schema_digest"), EXPECTED_SCHEMA_DIGEST)
        self.assertTrue(report["local_semantic"]["valid"], report["local_semantic"])


if __name__ == "__main__":
    unittest.main()
