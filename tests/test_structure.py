"""Structure profile, shared-control Toffoli factor, and qubit reuse.

Spec: specs/001-noetl-pipeline/spec.md
User story 2, FR-003, FR-004, FR-010, FR-011.
Each rewrite is checked by kickmix simulation on a small circuit.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.kickmix_file import Op  # noqa: E402
from vqcc.profile import profile_ops  # noqa: E402


def _kickmix():
    import kickmix

    return kickmix


class ProfileTests(unittest.TestCase):
    def test_repeated_window_and_toffoli_shape_and_lifetimes(self) -> None:
        ops = [Op(name="X", qubits=(5,)) for _ in range(64)]
        ops.extend(
            [
                Op(name="R", qubits=(2,)),
                Op(name="CCX", qubits=(0, 1, 2)),
                Op(name="CCX", qubits=(0, 1, 4)),
                Op(name="CCX", qubits=(1, 0, 2)),
                Op(name="X", qubits=(3,)),
            ]
        )
        report = profile_ops(ops, has_registers=False, header_qubits=8)
        self.assertGreaterEqual(report["repeated_blocks"]["top"][0]["count"], 2)
        toffoli = report["toffoli"]
        self.assertEqual(toffoli["clean_and_opens"], 1)
        self.assertEqual(toffoli["matching_uncompute_pairs"], 1)
        self.assertEqual(toffoli["shared_control_candidates"], 1)
        self.assertGreater(report["qubits"]["peak_live_reset_only"], report["qubits"]["peak_live_with_uncompute"])
        self.assertEqual(report["resets"]["unconditional_r"], 1)
        self.assertTrue(report["not_a_score"])
        self.assertEqual(report["qubits"]["reuse_blocked"], "no_registers")

    def test_register_scratch_starts_clean_and_named_stays_in_the_peak(self) -> None:
        ops = [
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="CCX", qubits=(0, 1, 3)),
        ]
        report = profile_ops(ops, named={0, 1}, has_registers=True, header_qubits=4)
        self.assertEqual(report["toffoli"]["clean_and_opens"], 2)
        self.assertEqual(report["toffoli"]["shared_control_candidates"], 1)
        self.assertGreaterEqual(report["qubits"]["peak_live_reset_only"], 2)
        self.assertIsNone(report["qubits"]["reuse_blocked"])
        self.assertGreaterEqual(report["qubits"]["reuse_headroom_vs_header"], 0)


class RewriteSimulationTests(unittest.TestCase):
    def test_shared_control_factor_matches_and_drops_a_toffoli(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                'REGISTER r0 "x"',
                "CCX q0 q1 q2",
                "CCX q1 q0 q3",
                "CX q3 q4",
                "",
            ]
        )
        original, optimized, result = _optimize_text(kickmix, text)
        self.assertTrue(result.wrote, result.reason)
        self.assertEqual(result.stats["shared_control_factors"], 1)
        self.assertEqual(result.after["toffoli_like"], 1)
        self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
        _assert_same_wires(self, kickmix, original, optimized, inputs=2)

    def test_phase_on_the_and_target_still_factors(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                'REGISTER r0 "x"',
                "CCX q0 q1 q2",
                "Z q2",
                "CCX q0 q1 q3",
                "",
            ]
        )
        original, optimized, result = _optimize_text(kickmix, text)
        self.assertTrue(result.wrote, result.reason)
        self.assertGreaterEqual(result.stats["shared_control_factors"], 1)
        _assert_same_wires(self, kickmix, original, optimized, inputs=2)

    def test_flipped_and_target_is_not_factored(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                'REGISTER r0 "x"',
                "CCX q0 q1 q2",
                "X q2",
                "CCX q0 q1 q3",
                "",
            ]
        )
        _original, _optimized, result = _optimize_text(kickmix, text)
        self.assertEqual(result.stats["shared_control_factors"], 0)
        self.assertFalse(result.wrote)

    def test_reuse_after_reset_lowers_q_and_matches(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                "APPEND_TO_REGISTER q2 r0",
                'REGISTER r0 "x"',
                "R q8",
                "CCX q0 q1 q8",
                "CX q8 q2",
                "R q8",
                "R q12",
                "X q12",
                "CX q12 q2",
                "R q12",
                "",
            ]
        )
        original, optimized, result = _optimize_text(kickmix, text)
        self.assertTrue(result.wrote, result.reason)
        self.assertLess(result.after["qubits"], result.before["qubits"])
        self.assertGreater(result.stats["qubit_relabels"] + result.stats["qubit_reuses"], 0)
        self.assertLessEqual(result.after["toffoli_like"], result.before["toffoli_like"])
        _assert_expected(
            self,
            kickmix,
            optimized,
            inputs=2,
            named=3,
            expect=lambda values: [bool(values[0]), bool(values[1]), bool(values[0] and values[1]) ^ True],
        )

    def test_overlapping_ancillas_are_not_forced_onto_one_wire(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                "APPEND_TO_REGISTER q2 r0",
                'REGISTER r0 "x"',
                "R q8",
                "R q9",
                "CCX q0 q1 q8",
                "CCX q8 q0 q9",
                "CX q9 q2",
                "HMR q9 b0",
                "CZ q8 q0 if b0",
                "HMR q8 b0",
                "CZ q1 q0 if b0",
                "",
            ]
        )
        original, optimized, result = _optimize_text(kickmix, text)
        self.assertTrue(result.wrote, result.reason)
        self.assertLess(result.after["qubits"], result.before["qubits"])
        # Two scratch wires are live together, so the header cannot collapse
        # to the three named qubits.
        self.assertGreater(result.after["qubits"], 3)
        self.assertLessEqual(result.after["toffoli_like"], result.before["toffoli_like"])
        _assert_expected(
            self,
            kickmix,
            optimized,
            inputs=2,
            named=3,
            expect=lambda values: [bool(values[0]), bool(values[1]), bool(values[0] and values[1])],
        )
        _assert_expected(
            self,
            kickmix,
            original,
            inputs=2,
            named=3,
            expect=lambda values: [bool(values[0]), bool(values[1]), bool(values[0] and values[1])],
        )

    def test_no_register_does_not_remap_a_high_qubit(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(["R q6", "X q6", "R q6", ""])
        _original, _optimized, result = _optimize_text(kickmix, text)
        self.assertFalse(result.wrote)
        self.assertEqual(result.stats["qubit_relabels"], 0)
        self.assertEqual(result.stats["qubit_reuses"], 0)
        self.assertEqual(result.profile["qubits"]["reuse_blocked"], "no_registers")

    def test_kickmix_idioms_stay_equivalent(self) -> None:
        kickmix = _kickmix()
        cases = []

        builder = kickmix.CircuitBuilder()
        controls = builder.alloc_qubits(4)
        target = builder.alloc_qubits(1)[0]
        builder.multi_controlled_x(controls, target)
        cases.append(("multi", builder.finish_circuit(), 4))

        builder = kickmix.CircuitBuilder()
        left = builder.create_quantum_register(3, "a")
        right = builder.create_quantum_register(3, "b")
        builder.iadd(right, target=left)
        cases.append(("iadd", builder.finish_circuit(), 6))

        builder = kickmix.CircuitBuilder()
        lhs = builder.create_quantum_register(3, "x")
        rhs = builder.create_quantum_register(3, "y")
        builder.init_gf2_mul(lhs, rhs)
        cases.append(("gf_mul", builder.finish_circuit(), 6))

        for label, original, inputs in cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    src = Path(tmp) / "in.kmb"
                    dst = Path(tmp) / "out.kmb"
                    original.to_file(str(src), format="kmb")
                    from vqcc.optimize import optimize_artifact

                    result = optimize_artifact(
                        str(src), str(dst), window=64, memory_budget_bytes=4_000_000, task="dqi"
                    )
                    self.assertLessEqual(
                        result.after.get("toffoli_like", 0),
                        result.before["toffoli_like"],
                    )
                    self.assertIn("opcodes", result.profile)
                    self.assertIn("CCX", result.profile["opcodes"])
                    if result.wrote:
                        optimized = kickmix.Circuit.from_file(str(dst))
                        self.assertLessEqual(optimized.num_qubits, original.num_qubits)
                        _assert_same_wires(self, kickmix, original, optimized, inputs=inputs)


def _optimize_text(kickmix, text: str):
    from vqcc.optimize import optimize_artifact

    tmp = tempfile.mkdtemp()
    src = Path(tmp) / "in.kmb"
    dst = Path(tmp) / "out.kmb"
    original = kickmix.Circuit(text)
    original.to_file(str(src), format="kmb")
    result = optimize_artifact(str(src), str(dst), window=32, memory_budget_bytes=4_000_000, task="dqi")
    optimized = kickmix.Circuit.from_file(str(dst)) if result.wrote else original
    return original, optimized, result


def _assert_same_wires(test: unittest.TestCase, kickmix, original, optimized, inputs: int) -> None:
    test.assertEqual(original.num_qubits, optimized.num_qubits)
    for mask in range(1 << inputs):
        values = [(mask >> index) & 1 for index in range(inputs)]
        left = _final(kickmix, original, values)
        right = _final(kickmix, optimized, values)
        test.assertEqual(left, right, values)


def _assert_expected(test, kickmix, circuit, *, inputs: int, named: int, expect, shots: int = 16) -> None:
    """Named wires match the classical function on every shot. Scratch stays |0>.

    ``R`` and ``HMR`` kick a random phase. The kick is reseeded from the
    circuit bytes, so two equivalent files need not share one phase sample.
    The bit values are the equivalence the tasks actually check, together
    with scratch returning to |0>.
    """

    for mask in range(1 << inputs):
        values = [(mask >> index) & 1 for index in range(inputs)]
        wanted = [bool(bit) for bit in expect(values)]
        sim = kickmix.Simulator(batch_size=shots)
        for index, value in enumerate(values):
            for shot in range(shots):
                sim.write_within_shot(kickmix.q(index), shot, bool(value))
        sim.do(circuit)
        for shot in range(shots):
            qubits = [
                bool(sim.read_within_shot(kickmix.q(index), shot, out=int))
                for index in range(circuit.num_qubits)
            ]
            test.assertEqual(qubits[:named], wanted, (values, shot, qubits))
            test.assertTrue(all(bit is False for bit in qubits[named:]), (values, shot, qubits))


def _final(kickmix, circuit, values: list[int]):
    sim = kickmix.Simulator(batch_size=1)
    for index, value in enumerate(values):
        if index < circuit.num_qubits:
            sim.write_within_shot(kickmix.q(index), 0, bool(value))
    sim.do(circuit)
    qubits = [
        bool(sim.read_within_shot(kickmix.q(index), 0, out=int))
        for index in range(circuit.num_qubits)
    ]
    bits = [
        bool(sim.read_within_shot(kickmix.b(index), 0, out=int))
        for index in range(circuit.num_bits)
    ]
    return qubits, bits, str(sim.read_shot_phase(0))


if __name__ == "__main__":
    unittest.main()
