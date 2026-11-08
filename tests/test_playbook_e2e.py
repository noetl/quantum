"""Execute the VQCC playbook on the installed NoETL local runtime."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NoETLPlaybookTests(unittest.TestCase):
    def test_competition_playbook_blocks_without_a_score(self) -> None:
        noetl = _noetl_or_skip(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            runs = root / "runs"
            outcome = noetl.run(
                str(ROOT / "playbooks" / "vqcc_pipeline.yaml"),
                variables={
                    "repo_root": str(ROOT),
                    "data_dir": str(data),
                    "runs_root": str(runs),
                    "mode": "competition",
                },
                quiet=True,
            )
            self.assertEqual(outcome["status"], "ok")
            final = json.loads(outcome["final_result"])
            provenance = json.loads(Path(final["provenance"]).read_text(encoding="utf-8"))
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(
            outcome["executed_steps"],
            [
                "prepare",
                "check_data",
                "adapt_invsqrt",
                "adapt_dqi",
                "adapt_dfthcsos",
                "verify",
                "cost",
                "package",
                "record",
            ],
        )
        self.assertIsNone(final["leaderboard_score"])
        self.assertEqual(final["verification_status"], "blocked")
        self.assertEqual(final["package_status"], "not_ready")
        self.assertFalse(final["zip_written"])
        self.assertFalse(final["experiment_log_written"])
        for task in final["tasks"].values():
            self.assertFalse(task["competition_verified"])
            self.assertFalse(task["circuit_written"])
        self.assertIsNone(provenance["leaderboard_score"])
        self.assertEqual(provenance["runtime"]["noetl_tested_version"], "5.3.2")
        self.assertEqual(outcome.get("error"), None)

    def test_structural_playbook_measures_a_real_circuit(self) -> None:
        noetl = _noetl_or_skip(self)
        try:
            import kickmix  # noqa: F401
        except ImportError:
            self.skipTest("kickmix==1.0.0 is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            outcome = noetl.run(
                str(ROOT / "playbooks" / "vqcc_pipeline.yaml"),
                variables={
                    "repo_root": str(ROOT),
                    "data_dir": str(root / "data"),
                    "runs_root": str(root / "runs"),
                    "mode": "structural",
                },
                quiet=True,
            )
            final = json.loads(outcome["final_result"])
            provenance = json.loads(Path(final["provenance"]).read_text(encoding="utf-8"))
            kmb = Path(provenance["tasks"]["invsqrt"]["paths"]["kmb"])
            kmb_size = kmb.stat().st_size
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(final["mode"], "structural")
        self.assertIsNone(final["leaderboard_score"])
        self.assertTrue(final["tasks"]["invsqrt"]["circuit_written"])
        self.assertFalse(final["tasks"]["invsqrt"]["competition_verified"])
        inv = provenance["costs"]["tasks"]["invsqrt"]
        self.assertEqual(inv["status"], "computed")
        self.assertFalse(inv["competition_cost"])
        self.assertIsNone(inv["leaderboard_score"])
        self.assertGreater(kmb_size, 0)


def _noetl_or_skip(test: unittest.TestCase):
    try:
        import noetl
    except ImportError:
        test.skipTest("noetl==5.3.2 is not installed")
    version = getattr(noetl, "__version__", "")
    if not str(version).startswith("5.3."):
        test.skipTest(f"expected noetl 5.3.x, found {version}")
    return noetl


if __name__ == "__main__":
    unittest.main()
