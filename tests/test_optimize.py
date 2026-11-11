"""Per-task peephole and the verifier retention gate.

Spec: specs/001-noetl-pipeline/spec.md
User story 2 acceptance scenarios 1 and 2, FR-003, FR-011.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.kickmix_file import (  # noqa: E402
    Op,
    clifford_level,
    parse_half_turns,
    transcribe_kmb,
)
from vqcc.optimize import PassStats, peephole  # noqa: E402
from vqcc.pipeline import main as pipeline_main  # noqa: E402

OFFICIAL = {
    "invsqrt": "verifiers/invsqrt/verify_submission_invsqrt.py",
    "dqi": "verifiers/dqi/verify_submission_dqi.py",
    "dfthcsos": "verifiers/dfthcsos/verify.py",
}


def _kickmix():
    import kickmix

    return kickmix


class CodecTests(unittest.TestCase):
    def test_kmb_roundtrip_is_byte_identical(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                'APPEND_TO_REGISTER q0 r0',
                'REGISTER r1 "name"',
                'INFO_TAG "tag"',
                "X q0 if b0",
                "CX q1 q2",
                "CCX q0 q1 q2 if b1",
                "Z_POW q3 0.25",
                "Z_POW q3 -0.125 if b2",
                "HMR q4 b3",
                "SWAP q5 q6",
                "CSWAP q0 q1 q2",
                "PUSH_CONDITION if b0",
                "NEG if b4",
                "POP_CONDITION",
                "BIT_STORE1 b5",
                "DEBUG_PRINT q0",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            kickmix.Circuit(text).to_file(str(src), format="kmb")
            transcribe_kmb(str(src), str(dst), 8_000_000)
            self.assertEqual(src.read_bytes(), dst.read_bytes())
            reloaded = kickmix.Circuit.from_file(str(dst))
            self.assertGreater(reloaded.operation_statistics().num_toffoli_like, 0)

    def test_exponent_parser_matches_kickmix_angles(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "z.kmb"
            for exponent in ("0.25", "-0.25", "0.5", "1.0", "0.125", "0.1", "2.00"):
                kickmix.Circuit(f"Z_POW q0 {exponent}\n").to_file(str(path), format="kmb")
                from vqcc.kickmix_file import _parse_kmb, iter_kmb_ops, open_kmb

                mapped, handle = open_kmb(str(path), 1_000_000)
                try:
                    view = _parse_kmb(mapped)
                    angle = next(iter_kmb_ops(view)).angle
                    view.release()
                finally:
                    mapped.close()
                    handle.close()
                self.assertEqual(angle, parse_half_turns(exponent))
                if exponent == "0.25":
                    self.assertEqual(clifford_level(angle), 3)
                if exponent == "0.125":
                    self.assertEqual(clifford_level(angle), 4)
                if exponent == "2.00":
                    self.assertIsNone(clifford_level(angle))


class PeepholeTests(unittest.TestCase):
    def test_store_overwrite_and_empty_condition_and_push_barrier(self) -> None:
        stats = PassStats()
        stores = peephole(
            [
                Op(name="BIT_STORE0", bits=(1,)),
                Op(name="BIT_STORE1", bits=(1,)),
            ],
            window=8,
            stats=stats,
        )
        self.assertEqual(stores, [Op(name="BIT_STORE1", bits=(1,))])
        self.assertEqual(stats.store_overwrites, 1)
        empty = peephole(
            [
                Op(name="PUSH_CONDITION", condition=0),
                Op(name="POP_CONDITION"),
            ],
            window=4,
        )
        self.assertEqual(empty, [])
        blocked = [
            Op(name="X", qubits=(0,)),
            Op(name="PUSH_CONDITION", condition=0),
            Op(name="X", qubits=(0,)),
            Op(name="POP_CONDITION"),
        ]
        self.assertEqual(peephole(blocked, window=8), blocked)

    def test_rewritten_kmb_matches_kickmix_simulation(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "CCX q0 q1 q2",
                "X q3",
                "CCX q1 q0 q2",
                "Z_POW q4 0.25",
                "CZ q5 q6",
                "Z_POW q4 0.25",
                "SWAP q0 q1",
                "SWAP q1 q0",
                "X q2 if b0",
                "X q2 if b0",
                "BIT_INVERT b0",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            original = kickmix.Circuit(text)
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=16, memory_budget_bytes=2_000_000)
            self.assertTrue(result.wrote)
            self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
            self.assertLess(result.after["t_like"], result.before["t_like"])
            optimized = kickmix.Circuit.from_file(str(dst))
            self.assertEqual(int(optimized.operation_statistics().num_toffoli_like), 0)
            self.assertEqual(int(optimized.operation_statistics().num_t_like), 0)
            for sample in range(16):
                qubits = [(sample >> index) & 1 for index in range(7)]
                bit = sample & 1
                self.assertEqual(
                    _snapshot(kickmix, original, qubits, bit),
                    _snapshot(kickmix, optimized, qubits, bit),
                )

    def test_control_qubit_blocks_toffoli_cancellation(self) -> None:
        kickmix = _kickmix()
        text = "CCX q0 q1 q2\nX q0\nCCX q0 q1 q2\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            kickmix.Circuit(text).to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertFalse(result.wrote)
            self.assertFalse(dst.exists())

    def test_level4_pair_merges_when_the_sum_is_a_cheaper_t(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            cancel = Path(tmp) / "cancel.kmb"
            dst = Path(tmp) / "out.kmb"
            kickmix.Circuit("Z_POW q0 0.125\nZ_POW q0 -0.125\n").to_file(str(cancel), format="kmb")
            from vqcc.optimize import optimize_artifact

            cancelled = optimize_artifact(str(cancel), str(dst), window=4, memory_budget_bytes=2_000_000)
            self.assertTrue(cancelled.wrote)
            self.assertEqual(cancelled.after["high_rotations"], 0)
            kept = Path(tmp) / "kept.kmb"
            merged = Path(tmp) / "merged.kmb"
            original = kickmix.Circuit("Z_POW q0 0.125\nZ_POW q0 0.125\n")
            original.to_file(str(kept), format="kmb")
            merged_result = optimize_artifact(
                str(kept), str(merged), window=4, memory_budget_bytes=2_000_000
            )
            self.assertTrue(merged_result.wrote)
            self.assertEqual(merged_result.after["high_rotations"], 0)
            self.assertEqual(merged_result.after["t_like"], 1)
            self.assertLess(merged_result.after["cost_units"], merged_result.before["cost_units"])
            optimized = kickmix.Circuit.from_file(str(merged))
            self.assertEqual(
                _snapshot(kickmix, original, [0], 0),
                _snapshot(kickmix, optimized, [0], 0),
            )
            self.assertEqual(
                _snapshot(kickmix, original, [1], 0),
                _snapshot(kickmix, optimized, [1], 0),
            )

    def test_clifford_shrink_that_keeps_q_is_not_written(self) -> None:
        kickmix = _kickmix()
        text = "X q0\nX q1\nX q0\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            kickmix.Circuit(text).to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertFalse(result.wrote)
            self.assertFalse(dst.exists())
            self.assertEqual(result.after["cost_units"], result.before["cost_units"])
            self.assertEqual(result.after["qubits"], result.before["qubits"])

    def test_freeing_the_highest_qubit_is_written_and_matches(self) -> None:
        kickmix = _kickmix()
        text = "X q0\nX q5\nX q5\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            original = kickmix.Circuit(text)
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertTrue(result.wrote)
            self.assertLess(result.after["qubits"], result.before["qubits"])
            self.assertEqual(result.after["cost_units"], result.before["cost_units"])
            optimized = kickmix.Circuit.from_file(str(dst))
            self.assertEqual(optimized.num_qubits, 1)
            for value in (0, 1):
                original_shot = _snapshot(kickmix, original, [value, 0, 0, 0, 0, 0], 0)
                optimized_shot = _snapshot(kickmix, optimized, [value], 0)
                self.assertEqual(original_shot[0][:1], optimized_shot[0])
                self.assertEqual(original_shot[2], optimized_shot[2])

    def test_toffoli_cancels_across_x_on_the_target_and_keeps_qubit_width(self) -> None:
        kickmix = _kickmix()
        text = "CCX q0 q1 q2\nX q2\nCCX q0 q1 q2\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            original = kickmix.Circuit(text)
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertTrue(result.wrote)
            self.assertEqual(result.after["toffoli_like"], 0)
            self.assertLess(result.after["cost_units"], result.before["cost_units"])
            optimized = kickmix.Circuit.from_file(str(dst))
            self.assertEqual(optimized.num_qubits, original.num_qubits)
            self.assertEqual(int(optimized.operation_statistics().num_toffoli_like), 0)
            for sample in range(8):
                qubits = [(sample >> index) & 1 for index in range(3)]
                self.assertEqual(
                    _snapshot(kickmix, original, qubits, 0),
                    _snapshot(kickmix, optimized, qubits, 0),
                )

    def test_rotation_merge_is_not_limited_by_a_tiny_window(self) -> None:
        kickmix = _kickmix()
        text = "Z_POW q0 0.125\n" + ("X q1\n" * 8) + "Z_POW q0 0.125\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            original = kickmix.Circuit(text)
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=1, memory_budget_bytes=2_000_000)
            self.assertTrue(result.wrote)
            self.assertEqual(result.after["high_rotations"], 0)
            self.assertEqual(result.after["t_like"], 1)
            optimized = kickmix.Circuit.from_file(str(dst))
            self.assertEqual(optimized.num_qubits, 1)
            self.assertLess(result.after["qubits"], result.before["qubits"])
            for sample in range(4):
                values = [(sample >> index) & 1 for index in range(2)]
                original_shot = _snapshot(kickmix, original, values, 0)
                optimized_shot = _snapshot(kickmix, optimized, values[:1], 0)
                self.assertEqual(original_shot[0][:1], optimized_shot[0])
                self.assertEqual(original_shot[0][1], bool(values[1]))
                self.assertEqual(original_shot[2], optimized_shot[2])

    def test_rotation_does_not_merge_across_a_toffoli_target(self) -> None:
        kickmix = _kickmix()
        text = "Z_POW q2 0.125\nCCX q0 q1 q2\nZ_POW q2 0.125\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            kickmix.Circuit(text).to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertFalse(result.wrote)
            self.assertFalse(dst.exists())
            self.assertEqual(result.after["instructions"], result.before["instructions"])
            self.assertEqual(result.after["high_rotations"], 2)

    def test_cx_pair_cancels_across_a_same_control_partner(self) -> None:
        kickmix = _kickmix()
        text = "CX q0 q1\nCX q0 q2\nCX q0 q1\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            original = kickmix.Circuit(text)
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertFalse(result.wrote)
            self.assertEqual(result.stats["cancelled_pairs"], 1)
            self.assertEqual(result.after["cost_units"], result.before["cost_units"])
            self.assertEqual(result.after["qubits"], result.before["qubits"])
            optimized = kickmix.Circuit("CX q0 q2\n")
            for sample in range(8):
                qubits = [(sample >> index) & 1 for index in range(3)]
                self.assertEqual(
                    _snapshot(kickmix, original, qubits, 0),
                    _snapshot(kickmix, optimized, qubits, 0),
                )

    def test_wide_window_cancels_a_toffoli_pair_a_narrow_window_keeps(self) -> None:
        kickmix = _kickmix()
        text = "CCX q0 q1 q2\n" + "".join(f"X q{3 + index}\n" for index in range(40)) + "CCX q1 q0 q2\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            narrow = Path(tmp) / "narrow.kmb"
            wide = Path(tmp) / "wide.kmb"
            original = kickmix.Circuit(text)
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            missed = optimize_artifact(str(src), str(narrow), window=4, memory_budget_bytes=2_000_000)
            self.assertFalse(missed.wrote)
            caught = optimize_artifact(str(src), str(wide), window=64, memory_budget_bytes=2_000_000)
            self.assertTrue(caught.wrote)
            self.assertEqual(caught.after["toffoli_like"], 0)
            optimized = kickmix.Circuit.from_file(str(wide))
            for sample in range(16):
                qubits = [(sample >> index) & 1 for index in range(4)]
                self.assertEqual(
                    _snapshot(kickmix, original, qubits, 0),
                    _snapshot(kickmix, optimized, qubits, 0),
                )

    def test_measurement_uncompute_matches_kickmix_simulation(self) -> None:
        kickmix = _kickmix()
        for label in ("use", "phase", "nested", "cz"):
            with self.subTest(label=label):
                _assert_and_uncompute(self, kickmix, label)

    def test_named_target_is_not_measurement_uncomputed(self) -> None:
        kickmix = _kickmix()
        builder = kickmix.CircuitBuilder()
        controls = builder.create_quantum_register(2, "x")
        target = builder.create_quantum_register(1, "kept")
        out = builder.alloc_qubits(1)[0]
        builder.ccx(controls[0], controls[1], target[0])
        builder.cx(target[0], out)
        builder.ccx(controls[0], controls[1], target[0])
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            builder.finish_circuit().to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertFalse(result.wrote)
            self.assertEqual(result.stats["and_uncomputes"], 0)
            self.assertFalse(dst.exists())

    def test_reset_then_and_uncompute_on_a_named_qubit(self) -> None:
        kickmix = _kickmix()
        builder = kickmix.CircuitBuilder()
        controls = builder.create_quantum_register(2, "x")
        target = builder.create_quantum_register(1, "work")
        out = builder.alloc_qubits(1)[0]
        builder.reset(target[0])
        builder.ccx(controls[0], controls[1], target[0])
        builder.cx(target[0], out)
        builder.ccx(controls[0], controls[1], target[0])
        original = builder.finish_circuit()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.kmb"
            dst = Path(tmp) / "out.kmb"
            original.to_file(str(src), format="kmb")
            from vqcc.optimize import optimize_artifact

            result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
            self.assertTrue(result.wrote)
            self.assertEqual(result.stats["and_uncomputes"], 1)
            self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
            optimized = kickmix.Circuit.from_file(str(dst))
            _assert_same_shots(self, kickmix, original, optimized, inputs=2)

    def test_conditional_and_push_uncompute_matches(self) -> None:
        kickmix = _kickmix()
        explicit = kickmix.Circuit(
            "\n".join(
                [
                    "APPEND_TO_REGISTER q0 r0",
                    "APPEND_TO_REGISTER q1 r0",
                    'REGISTER r0 "x"',
                    "APPEND_TO_REGISTER b0 r1",
                    'REGISTER r1 "flag"',
                    "CCX q0 q1 q2 if b0",
                    "CX q2 q3 if b0",
                    "CCX q0 q1 q2 if b0",
                    "",
                ]
            )
        )
        pushed_builder = kickmix.CircuitBuilder()
        controls = pushed_builder.create_quantum_register(2, "x")
        flag = pushed_builder.create_classical_register(1, "flag")
        anc = pushed_builder.alloc_qubits(1)[0]
        out = pushed_builder.alloc_qubits(1)[0]
        pushed_builder.push_condition(flag[0])
        pushed_builder.ccx(controls[0], controls[1], anc)
        pushed_builder.cx(anc, out)
        pushed_builder.ccx(controls[0], controls[1], anc)
        pushed_builder.pop_condition()
        pushed = pushed_builder.finish_circuit()
        for label, original in (("explicit", explicit), ("push", pushed)):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    src = Path(tmp) / "in.kmb"
                    dst = Path(tmp) / "out.kmb"
                    original.to_file(str(src), format="kmb")
                    from vqcc.optimize import optimize_artifact

                    result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
                    self.assertTrue(result.wrote, result.reason)
                    self.assertGreaterEqual(result.stats["and_uncomputes"], 1)
                    optimized = kickmix.Circuit.from_file(str(dst))
                    _assert_same_shots(self, kickmix, original, optimized, inputs=2, flag=True)

    def test_modules_do_not_import_kickmix(self) -> None:
        for name in ("optimize.py", "kickmix_file.py"):
            text = (ROOT / "vqcc" / name).read_text(encoding="utf-8")
            self.assertNotIn("import kickmix", text)


class GatingTests(unittest.TestCase):
    def test_instruction_drop_is_materialized_and_a_cost_increase_is_not(self) -> None:
        from vqcc.kickmix_file import GateCounts
        from vqcc.optimize import should_materialize

        clifford = GateCounts(instructions=4)
        smaller = GateCounts(instructions=2)
        self.assertFalse(should_materialize(clifford, smaller, "dqi"))
        self.assertFalse(should_materialize(clifford, smaller, "invsqrt"))
        self.assertTrue(
            should_materialize(clifford, smaller, "dqi", qubits_before=8, qubits_after=7)
        )
        raised = GateCounts(toffoli_like=2, instructions=1)
        baseline = GateCounts(toffoli_like=1, instructions=3)
        self.assertFalse(should_materialize(baseline, raised, "dqi"))
        self.assertFalse(should_materialize(baseline, raised, "dfthcsos"))
        t_added = GateCounts(t_like=1, instructions=1)
        t_base = GateCounts(t_like=0, instructions=2)
        self.assertFalse(should_materialize(t_base, t_added, "invsqrt"))
        self.assertFalse(should_materialize(t_base, t_added, "dqi"))
        self.assertFalse(should_materialize(clifford, clifford))

    def test_instruction_drop_is_sent_to_the_verifier(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(proposal_score=40))
            source = data / "sample_submission" / "invsqrt.kmb"
            kickmix.Circuit("X q0\nX q5\nX q5\n").to_file(str(source), format="kmb")
            source_hash = _sha(source)
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "invsqrt"], runs)
            outcome = _pipeline(
                ["optimize", "--task", "invsqrt", "--time-budget-s", "30", "--verify-timeout", "10"],
                runs,
            )
            self.assertEqual(outcome["status"], "accepted")
            self.assertGreater(outcome["candidates_written"], 0)
            self.assertEqual(outcome["candidates_retained"], 1)
            self.assertLess(outcome["retained_cost"], outcome["baseline_cost"])
            attempt = outcome["attempts"][0]
            self.assertEqual(attempt["verifier_status"], "pass")
            self.assertGreater(attempt["before"]["qubits"], attempt["after"]["qubits"])
            self.assertEqual(attempt["before"]["cost_units"], attempt["after"]["cost_units"])
            self.assertEqual(_sha(source), source_hash)
            self.assertIsNone(outcome["leaderboard_score"])


class RetentionTests(unittest.TestCase):
    def test_rejected_proposal_and_other_tasks_stay_put(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(reject_proposals=True))
            _write_pair(kickmix, data / "sample_submission" / "invsqrt.kmb")
            dqi = data / "sample_submission" / "dqi.kmb"
            kickmix.Circuit("X q0\n").to_file(str(dqi), format="kmb")
            df = data / "sample_submission" / "dfthcsos"
            df.mkdir()
            (df / "submission.npz").write_bytes(b"npz-bytes")
            dqi_hash = _sha(dqi)
            npz_hash = _sha(df / "submission.npz")
            inv_hash = _sha(data / "sample_submission" / "invsqrt.kmb")
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "invsqrt"], runs)
            _pipeline(["adapt", "--task", "dqi"], runs)
            before_dqi = _task_state(runs, "dqi")
            outcome = _pipeline(
                ["optimize", "--task", "invsqrt", "--time-budget-s", "30", "--verify-timeout", "10"],
                runs,
            )
            self.assertEqual(outcome["status"], "rejected")
            self.assertFalse(outcome["circuit_written"])
            self.assertEqual(outcome["candidates_retained"], 0)
            self.assertGreater(outcome["candidates_written"], 0)
            self.assertIsNone(outcome["leaderboard_score"])
            self.assertTrue(outcome["lower_is_better"])
            state = _state(runs)
            self.assertEqual(state["tasks"]["invsqrt"]["role"], "imported_baseline")
            self.assertEqual(
                state["tasks"]["invsqrt"]["paths"]["file"],
                str(data / "sample_submission" / "invsqrt.kmb"),
            )
            self.assertEqual(state["tasks"]["invsqrt"]["verification"]["parsed_cost"], 100)
            self.assertTrue(state["tasks"]["invsqrt"]["competition_verified"])
            self.assertEqual(_task_state(runs, "dqi"), before_dqi)
            self.assertEqual(_sha(dqi), dqi_hash)
            self.assertEqual(_sha(df / "submission.npz"), npz_hash)
            self.assertEqual(_sha(data / "sample_submission" / "invsqrt.kmb"), inv_hash)
            packaged = _pipeline(["package"], runs)
            self.assertFalse(packaged["zip_written"])

    def test_higher_score_does_not_replace_the_baseline(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(proposal_score=150))
            source = data / "sample_submission" / "invsqrt.kmb"
            _write_pair(kickmix, source)
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "invsqrt"], runs)
            outcome = _pipeline(
                ["optimize", "--task", "invsqrt", "--time-budget-s", "30", "--verify-timeout", "10"],
                runs,
            )
            self.assertEqual(outcome["status"], "rejected")
            self.assertEqual(_state(runs)["tasks"]["invsqrt"]["paths"]["file"], str(source))
            self.assertEqual(_state(runs)["tasks"]["invsqrt"]["verification"]["parsed_cost"], 100)

    def test_accepted_candidate_is_isolated_and_not_packaged(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(proposal_score=40))
            source = data / "sample_submission" / "invsqrt.kmb"
            _write_pair(kickmix, source)
            dqi = data / "sample_submission" / "dqi.kmb"
            kickmix.Circuit("Z q0\n").to_file(str(dqi), format="kmb")
            dqi_hash = _sha(dqi)
            source_hash = _sha(source)
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "invsqrt"], runs)
            _pipeline(["adapt", "--task", "dqi"], runs)
            before_dqi = _task_state(runs, "dqi")
            outcome = _pipeline(
                ["optimize", "--task", "invsqrt", "--time-budget-s", "30", "--verify-timeout", "10"],
                runs,
            )
            self.assertEqual(outcome["status"], "accepted")
            self.assertEqual(outcome["baseline_cost"], 100)
            self.assertEqual(outcome["retained_cost"], 40)
            self.assertLess(outcome["retained_cost"], outcome["baseline_cost"])
            self.assertTrue(outcome["circuit_written"])
            state = _state(runs)
            retained = Path(state["tasks"]["invsqrt"]["paths"]["file"])
            self.assertEqual(state["tasks"]["invsqrt"]["role"], "retained_candidate")
            self.assertTrue(state["tasks"]["invsqrt"]["competition_verified"])
            self.assertEqual(state["tasks"]["invsqrt"]["verification"]["parsed_cost"], 40)
            self.assertNotEqual(retained, source)
            self.assertTrue(retained.is_file())
            self.assertEqual(_sha(source), source_hash)
            self.assertEqual(_sha(dqi), dqi_hash)
            self.assertEqual(_task_state(runs, "dqi"), before_dqi)
            self.assertFalse(any((ROOT / "tasks").rglob("*.kmb")))
            packaged = _pipeline(["package"], runs)
            self.assertFalse(packaged["zip_written"])
            self.assertIsNone(packaged["leaderboard_score"])

    def test_unchanged_circuit_writes_no_file(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(proposal_score=1))
            source = data / "sample_submission" / "invsqrt.kmb"
            kickmix.Circuit("X q0\nZ q1\n").to_file(str(source), format="kmb")
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "invsqrt"], runs)
            outcome = _pipeline(
                ["optimize", "--task", "invsqrt", "--time-budget-s", "30", "--verify-timeout", "10"],
                runs,
            )
            self.assertEqual(outcome["status"], "unchanged")
            self.assertEqual(outcome["candidates_written"], 0)
            proposals = _run_dir(runs) / "proposals"
            self.assertFalse(proposals.exists())
            self.assertFalse(any(_run_dir(runs).rglob("*.kmb")))

    def test_memory_budget_writes_nothing(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(proposal_score=1))
            source = data / "sample_submission" / "invsqrt.kmb"
            _write_pair(kickmix, source)
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "invsqrt"], runs)
            outcome = _pipeline(
                [
                    "optimize",
                    "--task",
                    "invsqrt",
                    "--time-budget-s",
                    "30",
                    "--verify-timeout",
                    "10",
                    "--memory-budget-bytes",
                    "32",
                ],
                runs,
            )
            self.assertEqual(outcome["status"], "not_rewritten")
            self.assertFalse(outcome["circuit_written"])
            self.assertEqual(
                _state(runs)["tasks"]["invsqrt"]["paths"]["file"],
                str(source),
            )
            self.assertFalse(any(_run_dir(runs).rglob("candidate-*")))

    def test_dfthcsos_directory_keeps_npz_bytes(self) -> None:
        kickmix = _kickmix()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, runs = _dataset(root, _script(proposal_score=10))
            folder = data / "sample_submission" / "dfthcsos"
            folder.mkdir(parents=True)
            angle = folder / "angle_k_0"
            _write_pair(kickmix, angle)
            idle = folder / "angle_k_1"
            kickmix.Circuit("X q0\n").to_file(str(idle), format="kmb")
            idle_bytes = idle.read_bytes()
            npz = folder / "submission.npz"
            npz.write_bytes(b"\x93NUMPYnot-really")
            npz_bytes = npz.read_bytes()
            _prepare(runs, data)
            _pipeline(["adapt", "--task", "dfthcsos"], runs)
            outcome = _pipeline(
                [
                    "optimize",
                    "--task",
                    "dfthcsos",
                    "--time-budget-s",
                    "30",
                    "--verify-timeout",
                    "10",
                ],
                runs,
            )
            self.assertEqual(outcome["status"], "accepted")
            retained = Path(_state(runs)["tasks"]["dfthcsos"]["paths"]["directory"])
            self.assertEqual((retained / "submission.npz").read_bytes(), npz_bytes)
            self.assertEqual((retained / "angle_k_1").read_bytes(), idle_bytes)
            self.assertEqual(npz.read_bytes(), npz_bytes)
            self.assertNotEqual((retained / "angle_k_0").read_bytes(), angle.read_bytes())
            loaded = kickmix.Circuit.from_file(str(retained / "angle_k_0"))
            self.assertEqual(int(loaded.operation_statistics().num_toffoli_like), 0)


class PlaybookTests(unittest.TestCase):
    def test_optimize_playbook_shape(self) -> None:
        import yaml

        document = yaml.safe_load((ROOT / "playbooks" / "vqcc_optimize.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["apiVersion"], "noetl.io/v2")
        steps = document["workflow"]
        names = [step["step"] for step in steps]
        self.assertEqual(names[0], "start")
        self.assertIn("optimize_invsqrt", names)
        self.assertIn("optimize_dqi", names)
        self.assertIn("optimize_dfthcsos", names)
        text = (ROOT / "playbooks" / "vqcc_optimize.yaml").read_text(encoding="utf-8")
        self.assertNotIn("package-when-verified", text)
        self.assertNotIn("leaderboard_score: 1", text)
        self.assertNotIn("\n      kind: python\n", text)
        for step in steps:
            self.assertEqual(step["tool"]["kind"], "shell")
        baseline = yaml.safe_load((ROOT / "playbooks" / "vqcc_pipeline.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            [step["step"] for step in baseline["workflow"]],
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

    def test_empty_optimize_playbook_writes_no_circuit(self) -> None:
        try:
            import noetl
        except ImportError:
            self.skipTest("noetl==5.3.2 is not installed")
        if not str(getattr(noetl, "__version__", "")).startswith("5.3."):
            self.skipTest("expected noetl 5.3.x")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            outcome = noetl.run(
                str(ROOT / "playbooks" / "vqcc_optimize.yaml"),
                variables={
                    "repo_root": str(ROOT),
                    "data_dir": str(data),
                    "runs_root": str(root / "runs"),
                    "mode": "competition",
                },
                quiet=True,
            )
            final = json.loads(outcome["final_result"])
            self.assertEqual(outcome["status"], "ok")
            self.assertIsNone(final["leaderboard_score"])
            self.assertIn("optimize_invsqrt", outcome["executed_steps"])
            self.assertFalse(final["zip_written"])
            for task in final["tasks"].values():
                self.assertFalse(task["circuit_written"])
                self.assertFalse(task["competition_verified"])
            run_dir = Path(final["run_dir"])
            self.assertEqual(list(run_dir.rglob("*.kmb")), [])
            self.assertEqual(list(run_dir.rglob("*.kmx")), [])


def _assert_and_uncompute(test: unittest.TestCase, kickmix, label: str) -> None:
    builder = kickmix.CircuitBuilder()
    controls = builder.create_quantum_register(2, "x")
    anc = builder.alloc_qubits(1)[0]
    out = builder.alloc_qubits(1)[0]
    extra = builder.alloc_qubits(1)[0]
    builder.ccx(controls[0], controls[1], anc)
    if label == "use":
        builder.cx(anc, out)
    elif label == "phase":
        builder.z(anc)
        builder.cx(anc, out)
    elif label == "cz":
        builder.cz(anc, out)
    elif label == "nested":
        builder.ccx(anc, controls[0], extra)
        builder.cx(extra, out)
        builder.ccx(anc, controls[0], extra)
    else:
        raise AssertionError(label)
    builder.ccx(controls[0], controls[1], anc)
    original = builder.finish_circuit()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.kmb"
        dst = Path(tmp) / "out.kmb"
        original.to_file(str(src), format="kmb")
        from vqcc.optimize import optimize_artifact

        result = optimize_artifact(str(src), str(dst), window=8, memory_budget_bytes=2_000_000)
        test.assertTrue(result.wrote, result.reason)
        test.assertGreaterEqual(result.stats["and_uncomputes"], 1)
        test.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
        optimized = kickmix.Circuit.from_file(str(dst))
        _assert_same_shots(test, kickmix, original, optimized, inputs=2)


def _assert_same_shots(test, kickmix, original, optimized, inputs: int, flag: bool = False) -> None:
    width = 1 << inputs
    if flag:
        width <<= 1
    for mask in range(width):
        values = [(mask >> index) & 1 for index in range(inputs)]
        bit = (mask >> inputs) & 1 if flag else 0
        left = _shots(kickmix, original, values, bit, shots=12)
        right = _shots(kickmix, optimized, values, bit, shots=12)
        test.assertEqual(len(left), 1, left)
        test.assertEqual(left, right, (values, bit, left, right))


def _shots(kickmix, circuit, values: list[int], bit: int, shots: int):
    sim = kickmix.Simulator(batch_size=shots)
    for index, value in enumerate(values):
        for shot in range(shots):
            sim.write_within_shot(kickmix.q(index), shot, bool(value))
    if circuit.num_bits:
        for shot in range(shots):
            sim.write_within_shot(kickmix.b(0), shot, bool(bit))
    sim.do(circuit)
    seen = set()
    for shot in range(shots):
        qubits = tuple(
            bool(sim.read_within_shot(kickmix.q(index), shot, out=int))
            for index in range(circuit.num_qubits)
        )
        seen.add((qubits, str(sim.read_shot_phase(shot))))
    return seen


def _snapshot(kickmix, circuit, qubits: list[int], bit: int):
    sim = kickmix.Simulator(batch_size=1)
    for index, value in enumerate(qubits):
        if index < circuit.num_qubits:
            sim.write_within_shot(kickmix.q(index), 0, bool(value))
    if circuit.num_bits:
        sim.write_within_shot(kickmix.b(0), 0, bool(bit))
    sim.do(circuit)
    qvals = [
        bool(sim.read_within_shot(kickmix.q(index), 0, out=int))
        for index in range(circuit.num_qubits)
    ]
    bvals = [
        bool(sim.read_within_shot(kickmix.b(index), 0, out=int))
        for index in range(circuit.num_bits)
    ]
    return qvals, bvals, str(sim.read_shot_phase(0))


def _write_pair(kickmix, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kickmix.Circuit("CCX q0 q1 q2\nX q3\nCCX q0 q1 q2\n").to_file(str(path), format="kmb")


def _script(*, reject_proposals: bool = False, proposal_score: int = 40) -> str:
    if reject_proposals:
        body = """
import json, sys
path = sys.argv[1]
if "proposals" in path:
    print(json.dumps({"status": "FAIL", "score": 1}))
    raise SystemExit(1)
print(json.dumps({"status": "PASS", "score": 100}))
"""
    else:
        body = f"""
import json, sys
path = sys.argv[1]
score = {int(proposal_score)} if "proposals" in path else 100
print(json.dumps({{"status": "PASS", "score": score}}))
"""
    return body


def _dataset(root: Path, script: str) -> tuple[Path, Path]:
    data = root / "data"
    for relative in OFFICIAL.values():
        path = data / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script, encoding="utf-8")
    (data / "sample_submission").mkdir(parents=True, exist_ok=True)
    return data, root / "runs"


def _prepare(runs: Path, data: Path) -> None:
    _pipeline(
        [
            "prepare",
            "--mode",
            "competition",
            "--data-dir",
            str(data),
            "--seed",
            "20261108",
        ],
        runs,
    )


def _pipeline(argv: list[str], runs: Path) -> dict:
    bucket: list[str] = []

    def capture(text: str) -> None:
        bucket.append(text)

    real_stdout = sys.stdout
    class _Buf:
        def write(self, text: str) -> int:
            capture(text)
            return len(text)

        def flush(self) -> None:
            return None

    sys.stdout = _Buf()
    try:
        code = pipeline_main(
            [*argv, "--repo-root", str(ROOT), "--runs-root", str(runs)]
        )
    finally:
        sys.stdout = real_stdout
    if code != 0:
        raise AssertionError(f"{argv} exited {code}: {''.join(bucket)}")
    return json.loads("".join(bucket))


def _run_dir(runs: Path) -> Path:
    pointer = json.loads((runs / "active.json").read_text(encoding="utf-8"))
    return Path(pointer["run_dir"])


def _state(runs: Path) -> dict:
    return json.loads((_run_dir(runs) / "state.json").read_text(encoding="utf-8"))


def _task_state(runs: Path, task: str):
    return _state(runs)["tasks"][task]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
