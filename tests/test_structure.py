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
from vqcc.optimize import PassStats, peephole  # noqa: E402
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
        self.assertEqual(toffoli["match"]["shared_control"]["eligible"], 1)
        self.assertEqual(toffoli["match"]["uncompute"]["eligible"], 1)
        self.assertEqual(sum(toffoli["match"]["shared_control"].values()), toffoli["shared_control_candidates"])
        self.assertEqual(sum(toffoli["match"]["uncompute"].values()), toffoli["matching_uncompute_pairs"])

    def test_control_flip_is_counted_and_not_a_strict_match(self) -> None:
        ops = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="X", qubits=(0,)),
            Op(name="CCX", qubits=(0, 1, 3)),
            Op(name="CCX", qubits=(1, 0, 2)),
        ]
        report = profile_ops(ops, has_registers=False, header_qubits=4)
        toffoli = report["toffoli"]
        self.assertEqual(toffoli["shared_control_candidates"], 1)
        self.assertEqual(toffoli["match"]["shared_control"]["control_mutated"], 1)
        self.assertEqual(toffoli["match"]["shared_control"]["eligible"], 0)
        self.assertEqual(toffoli["match"]["control_mutation"]["shared_control"]["X"]["open"], 1)
        self.assertEqual(toffoli["matching_uncompute_pairs"], 1)
        self.assertEqual(toffoli["match"]["uncompute"]["control_mutated"], 1)
        self.assertEqual(toffoli["match"]["control_mutation"]["uncompute"]["X"]["open"], 1)
        _assert_mutation_totals(self, toffoli)
        stats = PassStats()
        peephole(ops, 32, stats)
        self.assertEqual(stats.shared_control_factors, 0)
        self.assertEqual(stats.and_replays, 0)
        self.assertEqual(stats.and_uncomputes, 0)

    def test_condition_mismatch_and_condition_bit_write(self) -> None:
        mismatched = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2), condition=0),
            Op(name="CCX", qubits=(0, 1, 3)),
        ]
        report = profile_ops(mismatched, has_registers=False, header_qubits=4)
        self.assertEqual(report["toffoli"]["match"]["shared_control"]["condition_mismatch"], 1)
        self.assertEqual(report["toffoli"]["match"]["shared_control"]["eligible"], 0)
        written = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2), condition=0),
            Op(name="BIT_INVERT", bits=(0,)),
            Op(name="CCX", qubits=(0, 1, 3), condition=0),
        ]
        report = profile_ops(written, has_registers=False, header_qubits=4)
        self.assertEqual(report["toffoli"]["match"]["shared_control"]["condition_bit_written"], 1)
        stats = PassStats()
        peephole(mismatched, 32, stats)
        self.assertEqual(stats.shared_control_factors, 0)
        self.assertGreaterEqual(stats.reject_condition_mismatch, 1)

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

    def test_narrower_condition_factors_and_matches(self) -> None:
        kickmix = _kickmix()
        builder = kickmix.CircuitBuilder()
        controls = builder.create_quantum_register(2, "x")
        flag = builder.create_classical_register(1, "flag")
        anc = builder.alloc_qubits(1)[0]
        out = builder.alloc_qubits(1)[0]
        builder.ccx(controls[0], controls[1], anc)
        builder.push_condition(flag[0])
        builder.ccx(controls[0], controls[1], out)
        builder.pop_condition()
        original = builder.finish_circuit()
        _original, optimized, result = _optimize_circuit(kickmix, original)
        self.assertTrue(result.wrote, result.reason)
        self.assertEqual(result.stats["shared_control_factors"], 1)
        self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
        _assert_same_shots(self, kickmix, original, optimized, inputs=2, flag=True)

    def test_recompute_after_del_and_replays_when_controls_stay(self) -> None:
        kickmix = _kickmix()
        builder = kickmix.CircuitBuilder()
        controls = builder.create_quantum_register(2, "x")
        first = builder.alloc_qubits(1)[0]
        copied = builder.alloc_qubits(1)[0]
        builder.init_and(controls[0], controls[1], first)
        builder.cx(first, copied)
        builder.del_and(controls[0], controls[1], first)
        second = builder.alloc_qubits(1)[0]
        again = builder.alloc_qubits(1)[0]
        builder.init_and(controls[0], controls[1], second)
        builder.cx(second, again)
        builder.del_and(controls[0], controls[1], second)
        original = builder.finish_circuit()
        _original, optimized, result = _optimize_circuit(kickmix, original)
        self.assertTrue(result.wrote, result.reason)
        self.assertGreaterEqual(result.stats["and_replays"], 1)
        self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
        _assert_same_shots(self, kickmix, original, optimized, inputs=2)

    def test_control_flip_between_del_and_and_recompute_is_not_replayed(self) -> None:
        kickmix = _kickmix()
        text = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                'REGISTER r0 "x"',
                "R q2",
                "CCX q0 q1 q2",
                "HMR q2 b0",
                "CZ q0 q1 if b0",
                "X q0",
                "R q3",
                "CCX q0 q1 q3",
                "",
            ]
        )
        _original, _optimized, result = _optimize_text(kickmix, text)
        self.assertEqual(result.stats["and_replays"], 0)
        self.assertEqual(result.stats["shared_control_factors"], 0)
        same_target = "\n".join(
            [
                "APPEND_TO_REGISTER q0 r0",
                "APPEND_TO_REGISTER q1 r0",
                'REGISTER r0 "x"',
                "R q2",
                "CCX q0 q1 q2",
                "HMR q2 b0",
                "CZ q0 q1 if b0",
                "CCX q0 q1 q2",
                "CX q2 q3",
                "",
            ]
        )
        _original_same, _optimized_same, same = _optimize_text(kickmix, same_target)
        self.assertFalse(same.wrote)
        self.assertEqual(same.stats["and_replays"], 0)
        self.assertEqual(same.after["toffoli_like"], same.before["toffoli_like"])
        self.assertEqual(result.after["toffoli_like"], result.before["toffoli_like"])
        self.assertEqual(result.profile["toffoli"]["match"]["shared_control"]["control_mutated"], 0)
        self.assertEqual(result.profile["toffoli"]["shared_control_candidates"], 0)

    def test_hot_control_past_the_old_fanout_cap_still_factors(self) -> None:
        kickmix = _kickmix()
        builder = kickmix.CircuitBuilder()
        regs = builder.create_quantum_register(2, "x")
        hub, hot = regs[0], regs[1]
        partners = builder.alloc_qubits(64)
        ancs = builder.alloc_qubits(64)
        for partner, anc in zip(partners, ancs):
            builder.ccx(hub, partner, anc)
        kept = builder.alloc_qubits(1)[0]
        builder.ccx(hub, hot, kept)
        extra = builder.alloc_qubits(1)[0]
        out = builder.alloc_qubits(1)[0]
        builder.ccx(hub, hot, extra)
        builder.cx(extra, out)
        original = builder.finish_circuit()
        _original, optimized, result = _optimize_circuit(kickmix, original)
        self.assertTrue(result.wrote, result.reason)
        self.assertGreaterEqual(result.stats["shared_control_factors"], 1)
        self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
        _assert_same_shots(self, kickmix, original, optimized, inputs=2)

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


class RestoredControlTests(unittest.TestCase):
    """Controls restored by tracking, or moved by SWAP, are real matches.

    Each accepted circuit is checked on every input assignment. The qubit
    vector and the shot phase are the exact simulator state. Patterns that
    must stay rejected keep their Toffoli count and the same state.
    """

    def test_profile_splits_restored_and_open_mutations(self) -> None:
        restored = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="X", qubits=(0,)),
            Op(name="X", qubits=(0,)),
            Op(name="CCX", qubits=(0, 1, 3)),
        ]
        report = profile_ops(restored, has_registers=False, header_qubits=4)
        shared = report["toffoli"]["match"]["shared_control"]
        self.assertEqual(shared["eligible"], 1)
        self.assertEqual(shared["control_mutated"], 0)
        self.assertEqual(report["toffoli"]["match"]["control_mutation"]["shared_control"]["X"]["undone"], 1)
        moved = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="SWAP", qubits=(0, 3)),
            Op(name="CCX", qubits=(3, 1, 4)),
        ]
        moved_report = profile_ops(moved, has_registers=False, header_qubits=5)
        mutation = moved_report["toffoli"]["match"]["control_mutation"]["shared_control"]
        self.assertEqual(moved_report["toffoli"]["match"]["shared_control"]["eligible"], 1)
        self.assertEqual(mutation["SWAP"]["relabelled"], 1)
        self.assertEqual(mutation["SWAP"]["open"], 0)
        stale = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="SWAP", qubits=(0, 3)),
            Op(name="CCX", qubits=(0, 1, 4)),
        ]
        stale_report = profile_ops(stale, has_registers=False, header_qubits=5)
        stale_match = stale_report["toffoli"]["match"]
        self.assertEqual(stale_match["shared_control"]["control_mutated"], 1)
        self.assertEqual(stale_match["control_mutation"]["shared_control"]["SWAP"]["open"], 1)
        reset = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="R", qubits=(0,)),
            Op(name="CCX", qubits=(0, 1, 3)),
        ]
        reset_report = profile_ops(reset, has_registers=False, header_qubits=4)
        self.assertEqual(reset_report["toffoli"]["match"]["shared_control"]["control_mutated"], 1)
        self.assertEqual(reset_report["toffoli"]["match"]["control_mutation"]["shared_control"]["R"]["open"], 1)
        self.assertEqual(reset_report["toffoli"]["match"]["control_mutation"]["shared_control"]["R"]["undone"], 0)
        measured = [
            Op(name="R", qubits=(2,)),
            Op(name="CCX", qubits=(0, 1, 2)),
            Op(name="HMR", qubits=(0,), bits=(0,)),
            Op(name="CCX", qubits=(0, 1, 3)),
        ]
        measured_report = profile_ops(measured, has_registers=False, header_qubits=4)
        self.assertEqual(measured_report["toffoli"]["match"]["control_mutation"]["shared_control"]["HMR"]["open"], 1)
        for item in (report, moved_report, stale_report, reset_report, measured_report):
            _assert_mutation_totals(self, item["toffoli"])

    def test_restored_and_relabelled_patterns_match_exactly(self) -> None:
        kickmix = _kickmix()
        named = _named_prefix(2)
        three = _named_prefix(3)
        four = _named_prefix(4)
        accepted = [
            ("x-x-factor", named + "CCX q0 q1 q2\nX q0\nX q0\nCCX q0 q1 q3\n", 2, 0, "shared_control_factors"),
            ("x-x-uncompute", named + "CCX q0 q1 q2\nX q0\nX q0\nCCX q0 q1 q2\n", 2, 0, "and_uncomputes"),
            ("cx-cx", three + "CCX q0 q1 q3\nCX q2 q0\nCX q2 q0\nCCX q0 q1 q4\n", 3, 0, "shared_control_factors"),
            (
                "cx-control-restored",
                three + "CCX q0 q1 q3\nCX q2 q0\nX q2\nX q2\nCX q2 q0\nCCX q0 q1 q4\n",
                3,
                0,
                "shared_control_factors",
            ),
            ("swap-swap", three + "CCX q0 q1 q3\nSWAP q0 q2\nSWAP q0 q2\nCCX q0 q1 q4\n", 3, 0, "shared_control_factors"),
            ("swap-relabel", three + "CCX q0 q1 q3\nSWAP q0 q2\nCCX q2 q1 q4\n", 3, 0, "shared_control_factors"),
            ("swap-uncompute", three + "CCX q0 q1 q3\nSWAP q0 q2\nCCX q2 q1 q3\n", 3, 0, "and_uncomputes"),
            (
                "ccx-ccx",
                four + "CCX q0 q1 q4\nCCX q2 q3 q0\nCCX q2 q3 q0\nCCX q0 q1 q5\n",
                4,
                0,
                "shared_control_factors",
            ),
            (
                "cswap-cswap",
                four + "CCX q0 q1 q4\nCSWAP q2 q0 q3\nCSWAP q2 q0 q3\nCCX q0 q1 q5\n",
                4,
                0,
                "shared_control_factors",
            ),
            ("conditional-x-x", named + "CCX q0 q1 q2\nX q0 if b0\nX q0 if b0\nCCX q0 q1 q3\n", 2, 1, "shared_control_factors"),
            ("target-x-x", named + "CCX q0 q1 q2\nX q2\nX q2\nCCX q0 q1 q3\n", 2, 0, "shared_control_factors"),
        ]
        for label, text, inputs, bits, stat in accepted:
            with self.subTest(label=label):
                original, optimized, result = _optimize_text(kickmix, text)
                self.assertTrue(result.wrote, result.reason)
                self.assertGreaterEqual(result.stats[stat], 1)
                self.assertLess(result.after["toffoli_like"], result.before["toffoli_like"])
                phase = stat != "and_uncomputes"
                _assert_permutation(self, kickmix, original, optimized, inputs, bits, phase=phase)

    def test_open_mutations_are_not_rewritten(self) -> None:
        kickmix = _kickmix()
        named = _named_prefix(2)
        three = _named_prefix(3)
        four = _named_prefix(4)
        rejected = [
            ("single-x", named + "CCX q0 q1 q2\nX q0\nCCX q0 q1 q3\n", 2, 0),
            ("cx-control-changed", three + "CCX q0 q1 q3\nCX q2 q0\nX q2\nCX q2 q0\nCCX q0 q1 q4\n", 3, 0),
            ("swap-then-old-ids", three + "CCX q0 q1 q3\nSWAP q0 q2\nCCX q0 q1 q4\n", 3, 0),
            ("single-cswap", four + "CCX q0 q1 q4\nCSWAP q2 q0 q3\nCCX q0 q1 q5\n", 4, 0),
            ("conditional-x-once", named + "CCX q0 q1 q2\nX q0 if b0\nCCX q0 q1 q3\n", 2, 1),
            ("reset-control", named + "CCX q0 q1 q2\nR q0\nCCX q0 q1 q3\n", 2, 0),
            ("measure-control", named + "CCX q0 q1 q2\nHMR q0 b1\nCCX q0 q1 q3\n", 2, 0),
            ("single-target-x", named + "CCX q0 q1 q2\nX q2\nCCX q0 q1 q3\n", 2, 0),
        ]
        for label, text, inputs, bits in rejected:
            with self.subTest(label=label):
                original, optimized, result = _optimize_text(kickmix, text)
                self.assertEqual(result.stats["shared_control_factors"], 0)
                self.assertEqual(result.stats["and_uncomputes"], 0)
                self.assertEqual(result.stats["and_replays"], 0)
                self.assertEqual(result.after["toffoli_like"], result.before["toffoli_like"])
                # R and HMR reseed a phase kick per simulator call. The qubit
                # permutation is the exact check for those two circuits.
                _assert_permutation(
                    self,
                    kickmix,
                    original,
                    optimized,
                    inputs,
                    bits,
                    phase=label not in {"measure-control", "reset-control"},
                )


def _named_prefix(count: int) -> str:
    lines = [f"APPEND_TO_REGISTER q{index} r0" for index in range(count)]
    lines.append('REGISTER r0 "x"')
    return "\n".join(lines) + "\n"


def _assert_mutation_totals(test: unittest.TestCase, toffoli: dict) -> None:
    match = toffoli["match"]
    expected = {
        "shared_control": toffoli["shared_control_candidates"],
        "uncompute": toffoli["matching_uncompute_pairs"],
    }
    for kind, count in expected.items():
        test.assertEqual(sum(match[kind].values()), count)
        opened = sum(row["open"] for row in match["control_mutation"][kind].values())
        test.assertEqual(opened, match[kind]["control_mutated"])


def _assert_permutation(test, kickmix, original, optimized, inputs: int, bits: int, phase: bool) -> None:
    """Exact computational image of every input.

    ``inputs`` named qubits and ``bits`` classical bits are enumerated.
    Unnamed scratch stays at the simulator's |0>, which is the clean-AND
    assumption. When ``phase`` is set, the shot phase is compared too.
    Measurement uncompute reseeds that kick from the file bytes, so those
    circuits compare the qubit permutation only.
    """

    for mask in range(1 << inputs):
        for bit in range(1 << bits):
            values = [(mask >> index) & 1 for index in range(inputs)]
            left = _permutation_row(kickmix, original, values, bit)
            right = _permutation_row(kickmix, optimized, values, bit)
            width = min(len(left[0]), len(right[0]))
            test.assertEqual(left[0][:width], right[0][:width], (values, bit))
            test.assertFalse(any(left[0][width:]), (values, bit, left[0]))
            test.assertFalse(any(right[0][width:]), (values, bit, right[0]))
            if phase:
                test.assertEqual(left[2], right[2], (values, bit))


def _permutation_row(kickmix, circuit, values: list[int], bit: int):
    sim = kickmix.Simulator(batch_size=1)
    for index, value in enumerate(values):
        if index < circuit.num_qubits:
            sim.write_within_shot(kickmix.q(index), 0, bool(value))
    if circuit.num_bits:
        sim.write_within_shot(kickmix.b(0), 0, bool(bit))
    sim.do(circuit)
    qubits = tuple(
        int(sim.read_within_shot(kickmix.q(index), 0, out=int)) for index in range(circuit.num_qubits)
    )
    classical = tuple(
        int(sim.read_within_shot(kickmix.b(index), 0, out=int)) for index in range(circuit.num_bits)
    )
    return qubits, classical, str(sim.read_shot_phase(0))


def _optimize_text(kickmix, text: str):
    return _optimize_circuit(kickmix, kickmix.Circuit(text))


def _optimize_circuit(kickmix, original):
    from vqcc.optimize import optimize_artifact

    tmp = tempfile.mkdtemp()
    src = Path(tmp) / "in.kmb"
    dst = Path(tmp) / "out.kmb"
    original.to_file(str(src), format="kmb")
    result = optimize_artifact(str(src), str(dst), window=32, memory_budget_bytes=4_000_000, task="dqi")
    optimized = kickmix.Circuit.from_file(str(dst)) if result.wrote else original
    return original, optimized, result


def _assert_same_shots(test, kickmix, original, optimized, inputs: int, flag: bool = False) -> None:
    width = 1 << inputs
    if flag:
        width <<= 1
    for mask in range(width):
        values = [(mask >> index) & 1 for index in range(inputs)]
        bit = (mask >> inputs) & 1 if flag else 0
        left = _shot_set(kickmix, original, values, bit, shots=8)
        right = _shot_set(kickmix, optimized, values, bit, shots=8)
        test.assertEqual(left, right, (values, bit))


def _shot_set(kickmix, circuit, values: list[int], bit: int, shots: int):
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
            int(sim.read_within_shot(kickmix.q(index), shot, out=int))
            for index in range(circuit.num_qubits)
        )
        bits = tuple(
            int(sim.read_within_shot(kickmix.b(index), shot, out=int))
            for index in range(circuit.num_bits)
        )
        seen.add((qubits, bits, str(sim.read_shot_phase(shot))))
    return seen


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
