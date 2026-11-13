"""Matcher cost on a dqi-shaped circuit, and the optimize wall clock.

The shape is the one that stalled Kaggle version 11: many live ANDs on one
qubit, then a long run of CX and SWAP on those controls. Issues
https://github.com/noetl/quantum/issues/19 and
https://github.com/noetl/quantum/issues/9.

The equivalence cases for restored controls stay in tests/test_structure.py.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from vqcc.kickmix_file import Op, OptimizeBudgetError
from vqcc.optimize import (
    DEFAULT_OPTIMIZE_BUDGET_S,
    TASK_BUDGET_SHARE,
    optimize_artifact,
    task_budget_seconds,
)
from vqcc.profile import profile_ops
from vqcc.qubit_values import OPEN_WRITE_LIMIT


def _fanout_circuit(n_and: int, n_cx: int, n_swap: int, tail: int = 0) -> list[Op]:
    """Live ANDs on qubit 0, then CX and SWAP traffic on that control."""

    ops: list[Op] = []
    for index in range(n_and):
        target = 100 + index
        ops.append(Op(name="R", qubits=(target,)))
        ops.append(Op(name="CCX", qubits=(0, 1 + (index % 8), target)))
    for index in range(n_cx):
        source = 20 + (index % 40)
        # Paired CX so the value tracker can cancel them. The cost is the
        # fanout scan, not whether the pair restores.
        if index % 2 == 0:
            ops.append(Op(name="CX", qubits=(source, 0)))
        else:
            ops.append(Op(name="CX", qubits=(source, 0)))
    for index in range(n_swap):
        ops.append(Op(name="SWAP", qubits=(0, 30 + (index % 6))))
    for index in range(tail):
        ops.append(Op(name="CCX", qubits=(0, 1 + (index % 8), 20_000 + index)))
    return ops


class MatcherScaleTests(unittest.TestCase):
    def test_million_gate_matcher_finishes_within_a_minute(self) -> None:
        ops = _fanout_circuit(n_and=800, n_cx=500_000, n_swap=500_000, tail=64)
        self.assertGreaterEqual(len(ops), 1_000_000)
        started = time.perf_counter()
        report = profile_ops(ops, has_registers=False, header_qubits=30_000)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 60.0, f"matcher took {elapsed:.2f}s on {len(ops)} gates")
        self.assertGreaterEqual(report["toffoli"]["peak_open_ands"], 800)
        self.assertEqual(report["instructions"], len(ops))
        self.assertTrue(report["not_a_score"])

    def test_open_write_cap_does_not_restore(self) -> None:
        ops = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
        ]
        for index in range(OPEN_WRITE_LIMIT + 1):
            ops.append(Op(name="CX", qubits=(10 + index, 0)))
        ops.append(Op(name="CCX", qubits=(0, 1, 3)))
        report = profile_ops(ops, has_registers=False, header_qubits=40)
        shared = report["toffoli"]["match"]["shared_control"]
        self.assertEqual(shared["eligible"], 0)
        self.assertEqual(shared["control_mutated"], 1)

    def test_swap_routing_longer_than_the_cap_still_relabels(self) -> None:
        ops = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
        ]
        for _ in range(OPEN_WRITE_LIMIT + 4):
            ops.append(Op(name="SWAP", qubits=(0, 3)))
            ops.append(Op(name="SWAP", qubits=(0, 3)))
        ops.append(Op(name="SWAP", qubits=(0, 3)))
        ops.append(Op(name="CCX", qubits=(3, 1, 4)))
        report = profile_ops(ops, has_registers=False, header_qubits=8)
        shared = report["toffoli"]["match"]["shared_control"]
        mutation = report["toffoli"]["match"]["control_mutation"]["shared_control"]
        self.assertEqual(shared["eligible"], 1)
        self.assertEqual(shared["control_mutated"], 0)
        self.assertEqual(mutation["SWAP"]["relabelled"], 1)

    def test_task_shares_sum_to_the_nine_hour_budget(self) -> None:
        shares = [task_budget_seconds(task, DEFAULT_OPTIMIZE_BUDGET_S) for task in TASK_BUDGET_SHARE]
        self.assertEqual(sum(shares), DEFAULT_OPTIMIZE_BUDGET_S)
        self.assertEqual(task_budget_seconds("dqi", DEFAULT_OPTIMIZE_BUDGET_S), 22680)
        self.assertEqual(task_budget_seconds("invsqrt", DEFAULT_OPTIMIZE_BUDGET_S), 4860)
        self.assertEqual(task_budget_seconds("dfthcsos", DEFAULT_OPTIMIZE_BUDGET_S), 4860)

    def test_expired_budget_keeps_the_source(self) -> None:
        import kickmix

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmx"
            dst = Path(tmp) / "out.kmx"
            kickmix.Circuit("X q0\nX q0\n").to_file(str(src), format="kmx")
            with self.assertRaises(OptimizeBudgetError) as caught:
                optimize_artifact(
                    str(src),
                    str(dst),
                    window=8,
                    memory_budget_bytes=2_000_000,
                    deadline=time.monotonic() - 1,
                    transform_budget_s=0,
                    task="dqi",
                )
            self.assertIn("unmodified circuit", str(caught.exception))
            self.assertFalse(dst.exists())


if __name__ == "__main__":
    unittest.main()
