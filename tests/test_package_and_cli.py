"""Packaging, CLI, and log behavior. Fixture bytes are empty stand-ins."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.generate import refuse_unimplemented
from vqcc.packaging import REQUIRED_NPZ_KEYS, PackageError, build_submission_zip, inspect_dfthcsos_dir


def _npz(path: Path, keys: tuple[str, ...] = REQUIRED_NPZ_KEYS) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for key in keys:
            archive.writestr(f"{key}.npy", b"not-a-real-array")


def _task_dir(root: Path, angles: list[int], extra: str | None = None) -> Path:
    directory = root / "dfthcsos"
    directory.mkdir()
    _npz(directory / "submission.npz")
    for index in angles:
        (directory / f"angle_k_{index}").write_bytes(b"angle")
    if extra:
        (directory / extra).write_text("scratch", encoding="utf-8")
    return directory


class PackageTests(unittest.TestCase):
    def test_writes_hub_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inv = root / "mine.kmb"
            dqi = root / "other.kmx"
            inv.write_bytes(b"inv")
            dqi.write_bytes(b"dqi")
            directory = _task_dir(root, [0, 1, 2])
            output = root / "out" / "submission.zip"
            payload = build_submission_zip(
                invsqrt=inv,
                dqi=dqi,
                dfthcsos_dir=directory,
                output=output,
            )
            self.assertEqual(
                payload["entries"],
                [
                    "invsqrt.kmb",
                    "dqi.kmx",
                    "dfthcsos/submission.npz",
                    "dfthcsos/angle_k_0",
                    "dfthcsos/angle_k_1",
                    "dfthcsos/angle_k_2",
                ],
            )
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), payload["entries"])

    def test_rejects_gap_and_extra_and_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gapped = _task_dir(root, [0, 2])
            with self.assertRaises(PackageError):
                inspect_dfthcsos_dir(gapped)
            extra_root = root / "extra"
            extra_root.mkdir()
            extra = _task_dir(extra_root, [0], extra="notes.txt")
            with self.assertRaises(PackageError):
                inspect_dfthcsos_dir(extra)
            bad = root / "bad"
            bad.mkdir()
            _npz(bad / "submission.npz", keys=("U",))
            (bad / "angle_k_0").write_bytes(b"a")
            with self.assertRaises(PackageError):
                inspect_dfthcsos_dir(bad)


class CliTests(unittest.TestCase):
    def test_score_json_has_no_leaderboard_value(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "score.py"),
                "invsqrt",
                "--qubits",
                "2",
                "--toffoli",
                "4",
                "--t-gates",
                "4",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)
        self.assertIsNone(payload["leaderboard_score"])
        self.assertEqual(payload["cost"], 10.0)
        self.assertIn("Not a leaderboard score", payload["disclaimer"])

    def test_dqi_requires_source(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "score.py"),
                "dqi",
                "--qubits",
                "1",
                "--toffoli",
                "1",
                "--epsilon-plus",
                "0.0001",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_aggregate_is_marked_unconfirmed(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "score.py"),
                "aggregate",
                "--ref-invsqrt",
                "1",
                "--ref-dqi",
                "1",
                "--ref-dfthcsos",
                "1",
                "--cost-invsqrt",
                "1",
                "--cost-dqi",
                "1",
                "--cost-dfthcsos",
                "1",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["unconfirmed"])
        self.assertIsNone(payload["leaderboard_score"])
        self.assertAlmostEqual(payload["value"], 1.0)

    def test_log_rejects_guess_and_appends_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "experiments.md"
            log.write_text(
                textwrap.dedent(
                    """\
                    | Date | Run | Description | Local | LB | Notes |
                    | --- | --- | --- | --- | --- | --- |
                    """
                ),
                encoding="utf-8",
            )
            refused = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "log_experiment.py"),
                    "--date",
                    "2026-11-05",
                    "--run",
                    "x",
                    "--description",
                    "nope",
                    "--local",
                    "guess",
                    "--file",
                    str(log),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(refused.returncode, 0)
            added = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "log_experiment.py"),
                    "--date",
                    "2026-11-05",
                    "--run",
                    "local-only",
                    "--description",
                    "layout check",
                    "--file",
                    str(log),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("appended", added.stdout)
            text = log.read_text(encoding="utf-8")
            self.assertIn("| 2026-11-05 | local-only | layout check | — | — |  |", text)
            self.assertNotIn("| 0 |", text)

    def test_generators_write_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = list(root.rglob("*"))
            status = refuse_unimplemented("invsqrt", root)
            self.assertEqual(status, 2)
            self.assertEqual(list(root.rglob("*")), before)

    def test_fetch_script_does_not_download_by_default(self) -> None:
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts" / "fetch_data.sh")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Not downloading", proc.stdout)
        self.assertFalse((ROOT / "data").exists())

    def test_playbook_parses(self) -> None:
        import yaml

        document = yaml.safe_load((ROOT / "playbooks" / "vqcc_pipeline.yaml").read_text())
        self.assertEqual(document["apiVersion"], "noetl.io/v2")
        steps = [step["step"] for step in document["workflow"]]
        self.assertEqual(
            steps,
            ["check_data", "task_status", "score_tool", "package_tool", "end"],
        )


if __name__ == "__main__":
    unittest.main()
