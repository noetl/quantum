"""Issue #2: the literal NoETL CLI command, default variables, no competition data.

This does not call ``noetl.run``. It shells the operator command from the
repository root and checks the JSON document that command prints.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The acceptance command. No --set, no extra flags, cwd is the repo root.
CLI = [
    "noetl",
    "run",
    "playbooks/vqcc_pipeline.yaml",
    "--runtime",
    "local",
    "--json",
]

PIPELINE_STEPS = [
    "start",
    "check_data",
    "adapt_invsqrt",
    "adapt_dqi",
    "adapt_dfthcsos",
    "verify_invsqrt",
    "verify_dqi",
    "verify_dfthcsos",
    "cost",
    "package",
    "record",
]

OFFICIAL_SCRIPTS = (
    Path("data/verifiers/invsqrt/verify_submission_invsqrt.py"),
    Path("data/verifiers/dqi/verify_submission_dqi.py"),
    Path("data/verifiers/dfthcsos/verify.py"),
)


class LiteralCliTests(unittest.TestCase):
    def test_default_cli_blocks_without_a_score_or_zip(self) -> None:
        if shutil.which("noetl") is None:
            self.skipTest("noetl CLI is not installed")

        present = [str(path) for path in OFFICIAL_SCRIPTS if (ROOT / path).exists()]
        self.assertEqual(
            present,
            [],
            "this acceptance run requires no competition data",
        )
        data_dir = ROOT / "data"
        if data_dir.exists():
            extras = sorted(p.relative_to(ROOT).as_posix() for p in data_dir.rglob("*") if p.is_file())
            self.assertEqual(extras, [], "this acceptance run requires no competition data")

        version = subprocess.run(
            ["noetl", "--version"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn("5.3.2", version.stdout)

        log_path = ROOT / "docs" / "experiments.md"
        log_before = log_path.read_bytes()
        zips_before = _zip_paths(ROOT)

        completed = subprocess.run(
            CLI,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertIn("runtime: local", completed.stderr)
        outcome = json.loads(completed.stdout)
        final = json.loads(outcome["final_result"])
        provenance = json.loads(Path(final["provenance"]).read_text(encoding="utf-8"))

        import yaml

        playbook = yaml.safe_load((ROOT / "playbooks" / "vqcc_pipeline.yaml").read_text(encoding="utf-8"))
        self.assertEqual([step["step"] for step in playbook["workflow"]], PIPELINE_STEPS)
        self.assertEqual(outcome["status"], "ok")
        self.assertIsNone(outcome.get("error"))
        self.assertEqual(outcome["executed_steps"], PIPELINE_STEPS)
        self.assertEqual(set(outcome["step_results"]), set(PIPELINE_STEPS))

        self.assertEqual(final["mode"], "competition")
        self.assertIsNone(final["leaderboard_score"])
        self.assertEqual(final["verification_status"], "blocked")
        self.assertNotEqual(final["verification_status"], "passed")
        self.assertEqual(final["package_status"], "not_ready")
        self.assertFalse(final["zip_written"])
        self.assertFalse(final["experiment_log_written"])
        for task in final["tasks"].values():
            self.assertFalse(task["competition_verified"])
            self.assertFalse(task["circuit_written"])

        for name in ("verify_invsqrt", "verify_dqi", "verify_dfthcsos"):
            step = json.loads(outcome["step_results"][name])
            self.assertEqual(step["status"], "blocked")
            self.assertNotEqual(step["status"], "passed")
            self.assertFalse(step["competition_verified"])
            self.assertIsNone(step["leaderboard_score"])
        package = json.loads(outcome["step_results"]["package"])
        self.assertFalse(package["zip_written"])
        self.assertIsNone(package["zip_path"])
        self.assertIsNone(package["leaderboard_score"])
        for raw in outcome["step_results"].values():
            _assert_leaderboard_scores_null(self, json.loads(raw))
        _assert_leaderboard_scores_null(self, final)
        _assert_leaderboard_scores_null(self, provenance)

        self.assertEqual(Path(provenance["repo_root"]).resolve(), ROOT.resolve())
        self.assertEqual(Path(provenance["data_dir"]).resolve(), (ROOT / "data").resolve())
        self.assertEqual(provenance["seed"], "20261108")
        self.assertEqual(provenance["mode"], "competition")
        self.assertEqual(provenance["runtime"]["noetl_tested_version"], "5.3.2")
        self.assertIsNone(provenance["leaderboard_score"])
        self.assertEqual(provenance["verification"]["status"], "blocked")
        self.assertFalse(provenance["package"]["zip_written"])

        run_dir = Path(final["run_dir"])
        self.assertTrue(run_dir.is_relative_to(ROOT / "runs"))
        self.assertEqual(list(run_dir.rglob("*.zip")), [])
        self.assertEqual(list(run_dir.rglob("*.kmb")), [])
        self.assertEqual(list(run_dir.rglob("*.kmx")), [])
        self.assertEqual(_zip_paths(ROOT), zips_before)
        self.assertFalse((ROOT / "submissions").exists() and any((ROOT / "submissions").rglob("*.zip")))
        self.assertEqual(log_path.read_bytes(), log_before)


def _zip_paths(root: Path) -> set[Path]:
    found: set[Path] = set()
    for path in root.rglob("*.zip"):
        if ".git" in path.parts:
            continue
        found.add(path)
    return found


def _assert_leaderboard_scores_null(test: unittest.TestCase, value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        if "leaderboard_score" in value:
            test.assertIsNone(value["leaderboard_score"], path)
        for key, item in value.items():
            _assert_leaderboard_scores_null(test, item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_leaderboard_scores_null(test, item, f"{path}[{index}]")


if __name__ == "__main__":
    unittest.main()
