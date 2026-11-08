"""Contract tests for the official verifier adapter. Not a Kaggle dataset run."""

from __future__ import annotations

import json
import stat
import sys
import textwrap
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.official_verifier import (
    FIXTURE_MARKER,
    OFFICIAL_SCRIPTS,
    VerifierError,
    discover_dataset_root,
    run_official_task,
)
from vqcc.packaging import REQUIRED_NPZ_KEYS
from vqcc.pipeline import main as pipeline_main


def _script(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _official_tree(root: Path, body: str, fixture: bool) -> None:
    for relative in OFFICIAL_SCRIPTS.values():
        _script(root / relative, body)
    (root / "sample_submission").mkdir(parents=True)
    (root / "sample_submission" / "invsqrt.kmb").write_bytes(b"inv")
    (root / "sample_submission" / "dqi.kmb").write_bytes(b"dqi")
    df = root / "sample_submission" / "dfthcsos"
    df.mkdir()
    (df / "angle_k_0").write_bytes(b"angle")
    with zipfile.ZipFile(df / "submission.npz", "w") as archive:
        for key in REQUIRED_NPZ_KEYS:
            archive.writestr(f"{key}.npy", b"not-a-real-array")
    if fixture:
        (root / FIXTURE_MARKER).write_text("fixture\n", encoding="utf-8")


class DiscoveryTests(unittest.TestCase):
    def test_nested_mount_and_explicit_miss(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            nested = (
                base
                / "kaggle"
                / "input"
                / "competitions"
                / "google-verifiable-quantum-circuit-compilation"
            )
            _official_tree(nested, "#!/bin/sh\nexit 0\n", fixture=True)
            found = discover_dataset_root(explicit=base / "kaggle", require=True)
            self.assertEqual(Path(found["root"]), nested.resolve())
            self.assertEqual(found["evidence_class"], "fixture")
            empty = base / "empty"
            empty.mkdir()
            with self.assertRaises(VerifierError) as caught:
                discover_dataset_root(explicit=empty, require=True)
            self.assertIn("verify_submission_invsqrt.py", str(caught.exception))

    def test_wrong_script_name_is_not_a_root(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            hook = root / "verifiers" / "invsqrt" / "verify"
            _script(hook, "#!/bin/sh\nexit 0\n")
            found = discover_dataset_root(explicit=root, require=False)
            self.assertFalse(found["found"])
            self.assertIn("verifiers/dqi/verify_submission_dqi.py", found["missing"])


class InvocationTests(unittest.TestCase):
    def test_fixture_exit_zero_is_not_competition_verified(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _official_tree(
                root,
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    echo "cost: 1.25"
                    echo "$@"
                    """
                ),
                fixture=True,
            )
            log = root / "logs"
            report = run_official_task(
                root=root,
                task="invsqrt",
                seed="20261108",
                timeout_s=10,
                log_dir=log,
                python="sh",
            )
            # python="sh" would try to execute the python path wrongly.
            # The script is a shell script. Use the script's shebang via python
            # only when the command is the interpreter. Re-run with python3 -c no.
            self.assertEqual(report["command"][0], "sh")
            self.assertTrue(report["command"][1].endswith("verify_submission_invsqrt.py"))
            self.assertTrue(report["command"][2].endswith("invsqrt.kmb"))
            self.assertEqual(report["command"][3:], ["--seed", "20261108"])
            self.assertEqual(report["official_exit_pass"], True)
            self.assertFalse(report["competition_verified"])
            self.assertEqual(report["parsed_cost"], 1.25)
            self.assertFalse(report["cost_authoritative"])
            self.assertIsNone(report["leaderboard_score"])
            self.assertEqual(report["bundle_role"], "reference")

    def test_local_tree_exit_zero_sets_the_flag_and_is_not_a_leaderboard_score(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _official_tree(root, "#!/bin/sh\necho 'score: 3'\n", fixture=False)
            report = run_official_task(
                root=root,
                task="dfthcsos",
                seed="20261108",
                timeout_s=10,
                python="sh",
            )
            self.assertTrue(report["competition_verified"])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["parsed_cost"], 3.0)
            self.assertFalse(report["cost_authoritative"])
            self.assertIsNone(report["aggregate_score"])
            self.assertFalse(report["executed_by_this_repository_on_the_kaggle_dataset"])

    def test_timeout_does_not_verify(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _official_tree(root, "#!/bin/sh\nsleep 30\n", fixture=False)
            report = run_official_task(
                root=root,
                task="dqi",
                timeout_s=1,
                python="sh",
            )
            self.assertEqual(report["status"], "timeout")
            self.assertFalse(report["competition_verified"])

    def test_pipeline_packages_only_after_three_non_fixture_passes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            runs = Path(tmp) / "runs"
            _official_tree(
                root,
                textwrap.dedent(
                    """\
                    import sys
                    print("cost: 2")
                    sys.exit(0)
                    """
                ),
                fixture=False,
            )
            self.assertEqual(
                pipeline_main(
                    [
                        "prepare",
                        "--mode",
                        "competition",
                        "--repo-root",
                        str(ROOT),
                        "--runs-root",
                        str(runs),
                        "--data-dir",
                        str(root),
                        "--package-when-verified",
                        "--seed",
                        "20261108",
                    ]
                ),
                0,
            )
            for task in ("invsqrt", "dqi", "dfthcsos"):
                payload = _cli(
                    [
                        "verify-official",
                        "--task",
                        task,
                        "--timeout",
                        "10",
                        "--repo-root",
                        str(ROOT),
                        "--runs-root",
                        str(runs),
                    ]
                )
                self.assertTrue(payload["competition_verified"], payload)
                self.assertEqual(payload["command"][3:], ["--seed", "20261108"])
            packaged = _cli(
                ["package", "--repo-root", str(ROOT), "--runs-root", str(runs)]
            )
            self.assertTrue(packaged["zip_written"], packaged)
            self.assertIsNone(packaged["leaderboard_score"])
            self.assertEqual(packaged["bundle_role"], "reference")


def _cli(argv: list[str]) -> dict:
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = pipeline_main(argv)
    if code != 0:
        raise AssertionError(buffer.getvalue())
    return json.loads(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
