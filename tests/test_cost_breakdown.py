"""Arithmetic splits of verifier JSON fields. Not a leaderboard score.

The scalars are the version-7 Kaggle reference run
(``20261111T052032Z-e1a4aedc``, main ``cd0168a``). They are external
evidence attached to issue #17, not a measurement this repository made.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.cost_breakdown import (  # noqa: E402
    dfthcsos_breakdown,
    dqi_breakdown,
    invsqrt_breakdown,
)


class BreakdownTests(unittest.TestCase):
    def test_invsqrt_version7_fields_multiply_and_rotations_match_the_paper_price(self) -> None:
        parts = invsqrt_breakdown(
            qubits=260,
            toffoli_count=7735.0,
            t_count=1.0,
            toffoli_equivalent=7987.593206597238,
            rotation_count=37.0,
            rotation_eps=1.5289254939242122e-12,
            score=2076774.233715282,
        )
        self.assertAlmostEqual(parts["parts"]["toffoli"], 260 * 7735.0)
        self.assertAlmostEqual(parts["parts"]["t"], 65.0)
        self.assertGreater(parts["shares_of_gate_factor"]["toffoli"], 0.96)
        self.assertLess(parts["shares_of_gate_factor"]["rotation"], 0.04)
        self.assertAlmostEqual(parts["marginal"]["one_toffoli"], 260.0)
        self.assertAlmostEqual(parts["marginal"]["one_qubit"], 7987.593206597238)
        synthesis = parts["synthesis"]["toffoli_equivalent"]
        self.assertAlmostEqual(synthesis, parts["rotation_toffoli_equivalent"], places=9)

    def test_dqi_version7_is_only_toffoli_and_qubits(self) -> None:
        parts = dqi_breakdown(
            qubits=1893,
            toffoli_count=5725109.125927734,
            repetition_factor=1.1912604648115832,
            max_toffoli_count=5725461,
            score=24439466758900.453,
        )
        self.assertAlmostEqual(parts["marginal"]["one_toffoli"], 1.1912604648115832 * 1893**2)
        self.assertGreater(parts["marginal"]["one_qubit"], parts["marginal"]["one_toffoli"])
        self.assertAlmostEqual(parts["conditional_toffoli_gap"], 5725461 - 5725109.125927734)

    def test_dfthcsos_version7_doubles_the_file_toffolis_and_leaves_a_heuristic(self) -> None:
        parts = dfthcsos_breakdown(
            qubits=730,
            toffoli_count=93237.0,
            lambda_eff=49.301369250574396,
            file_toffoli_count=39740.0,
            score=3355599588.3155375,
        )
        self.assertAlmostEqual(parts["forward_and_reverse_file_toffolis"], 79480.0)
        self.assertAlmostEqual(parts["unexplained_toffolis"], 13757.0)
        self.assertAlmostEqual(parts["marginal"]["one_toffoli"], 49.301369250574396 * 730)
        self.assertAlmostEqual(
            parts["marginal"]["one_file_toffoli_if_counted_twice"],
            49.301369250574396 * 2 * 730,
        )


if __name__ == "__main__":
    unittest.main()
