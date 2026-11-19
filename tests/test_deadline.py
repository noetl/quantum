"""Hard optimize deadline and live progress, driven by the NoETL playbook.

Issue https://github.com/noetl/quantum/issues/19 and
https://github.com/noetl/quantum/issues/9. Kaggle version 12 ran past the
in-process deadline because the cancellation window scanned every commuting
gate and noetl 5.3.2 only emits a shell step's output when the step exits.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from tests.dqi_shape import write_dqi_shaped_kmb
from vqcc.kickmix_file import Op
from vqcc.optimize import PassStats, _Hold

ROOT = Path(__file__).resolve().parents[1]


def _noetl_or_skip(test: unittest.TestCase):
    try:
        import noetl
    except ImportError:
        test.skipTest("noetl==5.3.2 is not installed")
    version = getattr(noetl, "__version__", "")
    if not str(version).startswith("5.3."):
        test.skipTest(f"expected noetl 5.3.x, found {version}")
    return noetl


class CancellationWindowTests(unittest.TestCase):
    def test_commuting_cx_without_a_partner_stays_fast(self) -> None:
        # Before the cancel-key index, 20_000 of these took 81 s.
        hold = _Hold(4096)
        stats = PassStats()
        started = time.perf_counter()
        for index in range(100_000):
            hold.push(Op(name="CX", qubits=((index % 8192) + 1, 50)), stats)
            while hold.overflow():
                hold.pop_front()
        elapsed = time.perf_counter() - started
        self.assertEqual(stats.cancelled_pairs, 0)
        self.assertLess(elapsed, 2.0, f"cancellation window took {elapsed:.2f}s")


class PlaybookDeadlineTests(unittest.TestCase):
    def test_slow_transform_is_killed_and_later_steps_run(self) -> None:
        noetl = _noetl_or_skip(self)
        budget = 5.0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            runs = root / "runs"
            circuit = root / "spin.kmb"
            circuit.write_bytes(b"spin")
            env = _push_env(
                {
                    "VQCC_OPTIMIZE_BUDGET_S": str(budget),
                    "VQCC_KILL_AFTER_S": "1",
                    "VQCC_SPIN_UNTIL_KILLED": "1",
                    "VQCC_SYNTHETIC_CIRCUIT": str(circuit),
                }
            )
            started = time.perf_counter()
            try:
                outcome = noetl.run(
                    str(ROOT / "playbooks" / "vqcc_optimize.yaml"),
                    variables={
                        "repo_root": str(ROOT),
                        "data_dir": str(data),
                        "runs_root": str(runs),
                    },
                    quiet=True,
                )
            finally:
                _pop_env(env)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, budget + 15, f"playbook took {elapsed:.1f}s")
            self.assertEqual(outcome["status"], "ok", outcome.get("error"))
            for step in ("cost", "package", "record"):
                self.assertIn(step, outcome["executed_steps"])
            progress = (runs / "optimize-progress.log").read_text(encoding="utf-8")
            self.assertIn("phase=timeout", progress)
            state = _active_state(runs)
            for task in ("invsqrt", "dqi", "dfthcsos"):
                optimization = state["tasks"][task]["optimization"]
                self.assertEqual(optimization["status"], "timeout", task)
                self.assertFalse(optimization.get("circuit_written"))
            self.assertIsNone(state.get("leaderboard_score"))

    def test_dqi_shaped_playbook_respects_a_short_budget(self) -> None:
        noetl = _noetl_or_skip(self)
        budget = 30.0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            runs = root / "runs"
            circuit = root / "dqi-shaped.kmb"
            gates = write_dqi_shaped_kmb(str(circuit), n_gates=10_000_000, live_ands=857)
            self.assertGreaterEqual(gates, 10_000_000)
            env = _push_env(
                {
                    "VQCC_OPTIMIZE_BUDGET_S": str(budget),
                    "VQCC_KILL_AFTER_S": "5",
                    "VQCC_SYNTHETIC_CIRCUIT": str(circuit),
                }
            )
            started = time.perf_counter()
            try:
                outcome = noetl.run(
                    str(ROOT / "playbooks" / "vqcc_optimize.yaml"),
                    variables={
                        "repo_root": str(ROOT),
                        "data_dir": str(data),
                        "runs_root": str(runs),
                    },
                    quiet=True,
                )
            finally:
                _pop_env(env)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, budget + 20, f"playbook took {elapsed:.1f}s")
            self.assertEqual(outcome["status"], "ok", outcome.get("error"))
            for step in ("optimize_invsqrt", "optimize_dqi", "optimize_dfthcsos", "cost", "package", "record"):
                self.assertIn(step, outcome["executed_steps"])
            progress = (runs / "optimize-progress.log").read_text(encoding="utf-8")
            for phase in ("parse", "profile", "restore", "cancel", "reuse"):
                self.assertIn(f"phase={phase} ", progress)
            self.assertTrue("phase=timeout" in progress or "phase=materialize" in progress)
            state = _active_state(runs)
            self.assertIsNone(state.get("leaderboard_score"))
            for task in ("invsqrt", "dqi", "dfthcsos"):
                optimization = state["tasks"][task]["optimization"]
                self.assertIn(optimization["status"], {"timeout", "unchanged"})
                self.assertFalse(optimization.get("circuit_written"))
                task_log = Path(state["run_dir"]) / "optimize" / f"{task}.log"
                self.assertTrue(task_log.is_file(), task_log)
                text = task_log.read_text(encoding="utf-8")
                self.assertIn("remaining_s=", text)
                self.assertIn("eligible=", text)
                self.assertIn("same_wire_reaccumulate=", text)


def _active_state(runs: Path) -> dict:
    pointer = json.loads((runs / "active.json").read_text(encoding="utf-8"))
    return json.loads(Path(pointer["run_dir"], "state.json").read_text(encoding="utf-8"))


def _push_env(values: dict[str, str]) -> dict[str, str | None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    return previous


def _pop_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
