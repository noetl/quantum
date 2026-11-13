"""Baseline orchestration without claiming a competition result."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.orchestrator import STRUCTURAL_KMX
from vqcc.pipeline import main as pipeline_main


def _run(argv: list[str]) -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "vqcc.pipeline", *argv],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


class CompetitionModeTests(unittest.TestCase):
    def test_absent_data_writes_no_circuit_and_blocks_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            data = root / "data"
            data.mkdir()
            prepared = _run(
                [
                    "prepare",
                    "--mode",
                    "competition",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                    "--data-dir",
                    str(data),
                ]
            )
            self.assertIsNone(prepared["leaderboard_score"])
            for task in ("invsqrt", "dqi", "dfthcsos"):
                adapted = _run(
                    ["adapt", "--task", task, "--repo-root", str(ROOT), "--runs-root", str(runs)]
                )
                self.assertEqual(adapted["artifact"]["role"], "absent")
                self.assertFalse(adapted["artifact"]["circuit_written"])
                self.assertFalse(adapted["artifact"]["competition_verified"])
            verified = _run(["verify", "--repo-root", str(ROOT), "--runs-root", str(runs)])
            self.assertEqual(verified["status"], "blocked")
            self.assertFalse(verified["competition_verified"])
            self.assertFalse(verified["mock"])
            packaged = _run(["package", "--repo-root", str(ROOT), "--runs-root", str(runs)])
            self.assertEqual(packaged["status"], "not_ready")
            self.assertFalse(packaged["zip_written"])
            recorded = _run(["record", "--repo-root", str(ROOT), "--runs-root", str(runs)])
            self.assertIsNone(recorded["leaderboard_score"])
            self.assertFalse(recorded["experiment_log_written"])
            provenance = json.loads(Path(recorded["provenance"]).read_text(encoding="utf-8"))
            self.assertIsNone(provenance["leaderboard_score"])
            self.assertEqual(
                provenance["spec"]["main_sha"],
                "d47053659fed3b110eb057f58d048ac50bf9ba7d",
            )
            self.assertFalse(any((ROOT / "tasks").rglob("*.kmb")))
            self.assertFalse(any((ROOT / "tasks").rglob("*.kmx")))

    def test_import_records_hash_without_copying_into_the_repo(self) -> None:
        kickmix = _kickmix_or_skip(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data" / "sample_submission"
            data.mkdir(parents=True)
            circuit = kickmix.Circuit(STRUCTURAL_KMX["invsqrt"])
            source = data / "invsqrt.kmx"
            circuit.to_file(str(source), format="kmx")
            runs = root / "runs"
            _run(
                [
                    "prepare",
                    "--mode",
                    "competition",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                    "--data-dir",
                    str(root / "data"),
                ]
            )
            adapted = _run(
                ["adapt", "--task", "invsqrt", "--repo-root", str(ROOT), "--runs-root", str(runs)]
            )
            artifact = adapted["artifact"]
            self.assertEqual(artifact["role"], "imported_baseline")
            self.assertFalse(artifact["circuit_written"])
            self.assertFalse(artifact["copied"])
            self.assertEqual(artifact["measurement"]["status"], "measured")
            self.assertGreater(artifact["measurement"]["toffoli_like"], 0)
            self.assertFalse((ROOT / "tasks" / "invsqrt" / "invsqrt.kmx").exists())

    def test_generic_hook_does_not_count_as_the_official_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            hook = data / "verifiers" / "invsqrt" / "verify"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
            runs = root / "runs"
            _run(
                [
                    "prepare",
                    "--mode",
                    "competition",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                    "--data-dir",
                    str(data),
                ]
            )
            verified = _run(
                [
                    "verify-official",
                    "--task",
                    "invsqrt",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                    "--timeout",
                    "5",
                ]
            )
            self.assertEqual(verified["status"], "blocked")
            self.assertFalse(verified["competition_verified"])
            self.assertIn("verify_submission_invsqrt.py", verified["reason"])


class StructuralModeTests(unittest.TestCase):
    def test_fixtures_are_real_kickmix_circuits_and_not_submission_ready(self) -> None:
        kickmix = _kickmix_or_skip(self)
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            data = Path(tmp) / "data"
            data.mkdir()
            _run(
                [
                    "prepare",
                    "--mode",
                    "structural",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                    "--data-dir",
                    str(data),
                ]
            )
            for task, text in STRUCTURAL_KMX.items():
                adapted = _run(
                    ["adapt", "--task", task, "--repo-root", str(ROOT), "--runs-root", str(runs)]
                )
                artifact = adapted["artifact"]
                self.assertEqual(artifact["role"], "structural_fixture")
                self.assertTrue(artifact["circuit_written"])
                self.assertFalse(artifact["competition_verified"])
                loaded = kickmix.Circuit.from_file(artifact["paths"]["kmb"])
                expected = kickmix.Circuit(text).operation_statistics()
                self.assertEqual(loaded.operation_statistics().num_toffoli_like, expected.num_toffoli_like)
                self.assertEqual(artifact["measurement"]["toffoli_like"], int(expected.num_toffoli_like))
            cost = _run(["cost", "--repo-root", str(ROOT), "--runs-root", str(runs)])
            inv = cost["tasks"]["invsqrt"]
            self.assertEqual(inv["status"], "computed")
            self.assertIsNone(inv["leaderboard_score"])
            self.assertFalse(inv["competition_cost"])
            measured = inv["inputs"]
            self.assertEqual(
                inv["value"],
                measured["qubits"] * (measured["toffoli_like"] + measured["t_like"] / 4),
            )
            self.assertEqual(cost["tasks"]["dqi"]["status"], "not_computed")
            self.assertEqual(cost["tasks"]["dfthcsos"]["status"], "not_computed")
            self.assertFalse(cost["aggregate"]["computed"])
            self.assertTrue(cost["aggregate"]["unconfirmed"])
            recorded = _run(["record", "--repo-root", str(ROOT), "--runs-root", str(runs)])
            self.assertIsNone(recorded["leaderboard_score"])

    def test_structural_mode_fails_closed_without_kickmix(self) -> None:
        if _kickmix_or_none() is not None:
            self.skipTest("kickmix is installed; the missing-module path is covered by the import guard")
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            code = pipeline_main(
                [
                    "prepare",
                    "--mode",
                    "structural",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                    "--data-dir",
                    str(Path(tmp) / "data"),
                ]
            )
            self.assertEqual(code, 0)
            code = pipeline_main(
                ["adapt", "--task", "invsqrt", "--repo-root", str(ROOT), "--runs-root", str(runs)]
            )
            self.assertEqual(code, 2)


class PlaybookShapeTests(unittest.TestCase):
    def test_playbook_uses_local_shell_steps(self) -> None:
        import yaml

        document = yaml.safe_load((ROOT / "playbooks" / "vqcc_pipeline.yaml").read_text())
        self.assertEqual(document["apiVersion"], "noetl.io/v2")
        self.assertEqual(document["workload"]["mode"], "competition")
        steps = document["workflow"]
        self.assertEqual(
            [step["step"] for step in steps],
            [
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
            ],
        )
        for step in steps:
            self.assertEqual(step["tool"]["kind"], "shell")
            self.assertIn("PYTHONUNBUFFERED=1 python3 -u -m vqcc.pipeline", step["tool"]["cmds"][0])
        text = (ROOT / "playbooks" / "vqcc_pipeline.yaml").read_text()
        self.assertNotIn("leaderboard_score: 1", text)
        self.assertNotIn("\n      kind: python\n", text)


def _kickmix_or_none():
    try:
        import kickmix
    except ImportError:
        return None
    return kickmix


def _kickmix_or_skip(test: unittest.TestCase):
    module = _kickmix_or_none()
    if module is None:
        test.skipTest("kickmix==1.0.0 is not installed")
    return module


if __name__ == "__main__":
    unittest.main()
