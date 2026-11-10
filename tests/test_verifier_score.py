"""Fixtures of official-verifier stdout. Not a Kaggle dataset run."""

from __future__ import annotations

import json
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_official_verifier import _official_tree  # noqa: E402
from vqcc.formulas import HUB_AGGREGATE_GAP, geometric_mean_ratio  # noqa: E402
from vqcc.official_verifier import parse_verifier_stdout, run_official_task  # noqa: E402
from vqcc.pipeline import main as pipeline_main  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "verifier_stdout"
REFERENCE_COSTS = {
    "invsqrt": 2076774.233715282,
    "dqi": 24439466758900.453,
    "dfthcsos": 3355599588.3155375,
}


class ParseFixtureTests(unittest.TestCase):
    def test_three_pass_documents_expose_the_score_field(self) -> None:
        for task, name in (
            ("invsqrt", "invsqrt_pass.json"),
            ("dqi", "dqi_pass.json"),
            ("dfthcsos", "dfthcsos_pass.json"),
        ):
            parsed = parse_verifier_stdout((FIXTURES / name).read_text(encoding="utf-8"))
            self.assertEqual(parsed["cost_parse"], "json_score", name)
            self.assertEqual(parsed["verifier_status"], "PASS")
            self.assertEqual(parsed["score_source"], "json.score")
            self.assertEqual(parsed["parsed_cost"], REFERENCE_COSTS[task])
            self.assertNotIn("shot_operation_counts", parsed["score_inputs"])

    def test_invsqrt_inputs_are_the_json_scalars(self) -> None:
        parsed = parse_verifier_stdout(
            (FIXTURES / "invsqrt_pass.json").read_text(encoding="utf-8")
        )
        self.assertEqual(parsed["score_inputs"]["num_qubits"], 260)
        self.assertEqual(parsed["score_inputs"]["toffoli_equivalent"], 7987.593206597238)
        self.assertEqual(parsed["score_inputs"]["score"], REFERENCE_COSTS["invsqrt"])

    def test_preamble_before_json_still_parses_one_object(self) -> None:
        parsed = parse_verifier_stdout(
            (FIXTURES / "invsqrt_preamble.txt").read_text(encoding="utf-8")
        )
        self.assertEqual(parsed["cost_parse"], "json_score")
        self.assertEqual(parsed["parsed_cost"], REFERENCE_COSTS["invsqrt"])

    def test_fail_status_keeps_the_number_and_is_not_a_pass_score(self) -> None:
        parsed = parse_verifier_stdout(
            (FIXTURES / "invsqrt_fail.json").read_text(encoding="utf-8")
        )
        self.assertEqual(parsed["cost_parse"], "json_not_pass")
        self.assertEqual(parsed["verifier_status"], "FAIL")
        self.assertEqual(parsed["parsed_cost"], REFERENCE_COSTS["invsqrt"])

    def test_two_json_scores_are_ambiguous(self) -> None:
        parsed = parse_verifier_stdout(
            (FIXTURES / "two_scores.txt").read_text(encoding="utf-8")
        )
        self.assertEqual(parsed["cost_parse"], "ambiguous")
        self.assertIsNone(parsed["parsed_cost"])

    def test_non_positive_score_is_not_a_json_score(self) -> None:
        parsed = parse_verifier_stdout('{"status": "PASS", "score": 0}\n')
        self.assertEqual(parsed["cost_parse"], "json_invalid_score")
        self.assertEqual(parsed["parsed_cost"], 0.0)

    def test_bare_line_stays_a_non_json_fallback(self) -> None:
        parsed = parse_verifier_stdout("cost: 1.25\n")
        self.assertEqual(parsed["cost_parse"], "one_line")
        self.assertEqual(parsed["parsed_cost"], 1.25)
        self.assertIsNone(parsed["verifier_status"])


class AuthorityTests(unittest.TestCase):
    def test_non_fixture_pass_json_is_authoritative_and_not_a_leaderboard_score(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _official_tree(root, _printer(FIXTURES / "dfthcsos_pass.json"), fixture=False)
            report = run_official_task(
                root=root,
                task="dfthcsos",
                seed="20261108",
                timeout_s=10,
            )
            self.assertTrue(report["competition_verified"])
            self.assertTrue(report["cost_authoritative"])
            self.assertEqual(report["cost_parse"], "json_score")
            self.assertEqual(report["parsed_cost"], REFERENCE_COSTS["dfthcsos"])
            self.assertIsNone(report["leaderboard_score"])

    def test_fixture_json_parses_and_stays_non_authoritative(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _official_tree(root, _printer(FIXTURES / "invsqrt_pass.json"), fixture=True)
            report = run_official_task(
                root=root,
                task="invsqrt",
                seed="20261108",
                timeout_s=10,
            )
            self.assertFalse(report["competition_verified"])
            self.assertFalse(report["cost_authoritative"])
            self.assertEqual(report["parsed_cost"], REFERENCE_COSTS["invsqrt"])

    def test_fail_json_is_not_authoritative(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _official_tree(root, _printer(FIXTURES / "invsqrt_fail.json"), fixture=False)
            report = run_official_task(
                root=root,
                task="invsqrt",
                seed="20261108",
                timeout_s=10,
            )
            self.assertEqual(report["status"], "fail")
            self.assertTrue(report["official_exit_pass"])
            self.assertFalse(report["competition_verified"])
            self.assertFalse(report["cost_authoritative"])
            self.assertEqual(report["cost_parse"], "json_not_pass")


class PipelineScoreTests(unittest.TestCase):
    def test_cost_step_uses_json_scores_and_leaves_leaderboard_score_null(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            runs = Path(tmp) / "runs"
            bodies = {
                "invsqrt": FIXTURES / "invsqrt_pass.json",
                "dqi": FIXTURES / "dqi_pass.json",
                "dfthcsos": FIXTURES / "dfthcsos_pass.json",
            }
            _official_tree(root, _printer(bodies["invsqrt"]), fixture=False)
            # The shared stub prints one file. Swap the script body per task.
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
                        "--seed",
                        "20261108",
                    ]
                ),
                0,
            )
            for task, path in bodies.items():
                script = root / {
                    "invsqrt": "verifiers/invsqrt/verify_submission_invsqrt.py",
                    "dqi": "verifiers/dqi/verify_submission_dqi.py",
                    "dfthcsos": "verifiers/dfthcsos/verify.py",
                }[task]
                script.write_text(_printer(path), encoding="utf-8")
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
                self.assertTrue(payload["cost_authoritative"], payload)
                self.assertEqual(payload["parsed_cost"], REFERENCE_COSTS[task])
                self.assertIsNone(payload["leaderboard_score"])
            priced = _cli(
                ["cost", "--repo-root", str(ROOT), "--runs-root", str(runs)]
            )
            self.assertIsNone(priced["leaderboard_score"])
            self.assertFalse(priced["aggregate"]["computed"])
            self.assertTrue(priced["aggregate"]["unconfirmed"])
            self.assertIn("FR-008", priced["aggregate"]["gap"])
            self.assertIn(HUB_AGGREGATE_GAP, priced["aggregate"]["gap"])
            for task, expected in REFERENCE_COSTS.items():
                report = priced["tasks"][task]
                self.assertEqual(report["status"], "computed")
                self.assertTrue(report["cost_authoritative"])
                self.assertEqual(report["source"], "official verifier JSON field score")
                self.assertEqual(report["value"], expected)
                self.assertIsNone(report["leaderboard_score"])
                self.assertIn("score", report["inputs"])
            recorded = _cli(
                ["record", "--repo-root", str(ROOT), "--runs-root", str(runs)]
            )
            self.assertIsNone(recorded["leaderboard_score"])
            for task in REFERENCE_COSTS:
                self.assertTrue(recorded["tasks"][task]["cost_authoritative"])
                self.assertTrue(recorded["tasks"][task]["competition_verified"])

    def test_explicit_aggregate_uses_caller_refcosts_and_not_the_lb_field(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            runs = Path(tmp) / "runs"
            _official_tree(root, _printer(FIXTURES / "invsqrt_pass.json"), fixture=False)
            for task, name in (
                ("invsqrt", "verifiers/invsqrt/verify_submission_invsqrt.py"),
                ("dqi", "verifiers/dqi/verify_submission_dqi.py"),
                ("dfthcsos", "verifiers/dfthcsos/verify.py"),
            ):
                fixture = {
                    "invsqrt": "invsqrt_pass.json",
                    "dqi": "dqi_pass.json",
                    "dfthcsos": "dfthcsos_pass.json",
                }[task]
                (root / name).write_text(_printer(FIXTURES / fixture), encoding="utf-8")
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
                    "--seed",
                    "20261108",
                ]
            )
            for task in REFERENCE_COSTS:
                _cli(
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
            without_refs = _cli(
                [
                    "cost",
                    "--aggregate",
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                ]
            )
            self.assertFalse(without_refs["aggregate"]["computed"])
            self.assertEqual(
                without_refs["aggregate"]["missing_refcosts"],
                ["invsqrt", "dqi", "dfthcsos"],
            )
            self.assertIsNone(without_refs["leaderboard_score"])
            halved = dict(REFERENCE_COSTS)
            halved["invsqrt"] = REFERENCE_COSTS["invsqrt"] / 8.0
            priced = _cli(
                [
                    "cost",
                    "--aggregate",
                    "--ref-invsqrt",
                    str(REFERENCE_COSTS["invsqrt"]),
                    "--ref-dqi",
                    str(REFERENCE_COSTS["dqi"]),
                    "--ref-dfthcsos",
                    str(REFERENCE_COSTS["dfthcsos"]),
                    "--repo-root",
                    str(ROOT),
                    "--runs-root",
                    str(runs),
                ]
            )
            # Costs equal the supplied refcosts, so the hub mean is 1.
            self.assertTrue(priced["aggregate"]["computed"])
            self.assertTrue(priced["aggregate"]["unconfirmed"])
            self.assertAlmostEqual(priced["aggregate"]["value"], 1.0)
            self.assertIsNone(priced["aggregate"]["leaderboard_score"])
            self.assertIsNone(priced["leaderboard_score"])
            self.assertAlmostEqual(
                geometric_mean_ratio(REFERENCE_COSTS, halved),
                2.0,
            )


def _printer(path: Path) -> str:
    body = path.read_text(encoding="utf-8")
    return textwrap.dedent(
        f"""\
        import sys
        sys.stdout.write({body!r})
        """
    )


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
