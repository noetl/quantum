"""Formula checks on caller-supplied numbers. Not competition results."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.formulas import (
    FormulaError,
    FormulaSource,
    dfthcsos_constraint_notes,
    dfthcsos_cost,
    dqi_repetition,
    geometric_mean_ratio,
    invsqrt_cost,
    lambda_eff,
)


class InvsqrtTests(unittest.TestCase):
    def test_shared_product(self) -> None:
        self.assertEqual(invsqrt_cost(2, 4, 4), 2 * (4 + 1))

    def test_rejects_negative(self) -> None:
        with self.assertRaises(FormulaError):
            invsqrt_cost(-1, 0, 0)


class DqiTests(unittest.TestCase):
    def test_paper_examples_from_arxiv(self) -> None:
        # Paper section III.2.3 quotes these R(eps+) values. They check the
        # transcription of equation 43. They are not a team submission.
        quoted = {
            1e-5: 1.02,
            1e-4: 1.06,
            1e-3: 1.21,
            1e-2: 1.94,
        }
        for epsilon, expected in quoted.items():
            got = dqi_repetition(epsilon, FormulaSource.PAPER)
            self.assertAlmostEqual(got, expected, delta=0.01)

    def test_hub_rendering_disagrees(self) -> None:
        for epsilon in (1e-5, 1e-4, 1e-3, 1e-2):
            hub = dqi_repetition(epsilon, FormulaSource.HUB)
            paper = dqi_repetition(epsilon, FormulaSource.PAPER)
            self.assertNotAlmostEqual(hub, paper, places=2)

    def test_paper_rejects_one_sixteenth(self) -> None:
        with self.assertRaises(FormulaError):
            dqi_repetition(1.0 / 16.0, FormulaSource.PAPER)


class DfthcsosTests(unittest.TestCase):
    def test_square_root_conflict(self) -> None:
        e_gap = 4.0
        lam = 50.0
        hub = lambda_eff(e_gap, lam, FormulaSource.HUB)
        paper = lambda_eff(e_gap, lam, FormulaSource.PAPER)
        self.assertAlmostEqual(hub, e_gap * (2 * lam - e_gap))
        self.assertAlmostEqual(paper, math.sqrt(hub))
        self.assertNotAlmostEqual(hub, paper)

    def test_cost_scales(self) -> None:
        value = dfthcsos_cost(4.0, 50.0, 2.0, 3.0, FormulaSource.PAPER)
        self.assertAlmostEqual(value, lambda_eff(4.0, 50.0, FormulaSource.PAPER) * 6.0)

    def test_floors_are_notes_not_scores(self) -> None:
        notes = dfthcsos_constraint_notes(qubits=129, lambda_ha=49.0, e_gap_ha=3.9)
        self.assertEqual(len(notes), 3)
        self.assertEqual(
            dfthcsos_constraint_notes(qubits=128, lambda_ha=49.1, e_gap_ha=3.92),
            [],
        )


class AggregateTests(unittest.TestCase):
    def test_reference_ratio_is_one(self) -> None:
        costs = {"invsqrt": 2.0, "dqi": 3.0, "dfthcsos": 5.0}
        self.assertAlmostEqual(geometric_mean_ratio(costs, costs), 1.0)

    def test_known_cube(self) -> None:
        refs = {"invsqrt": 8.0, "dqi": 1.0, "dfthcsos": 1.0}
        costs = {"invsqrt": 1.0, "dqi": 1.0, "dfthcsos": 1.0}
        self.assertAlmostEqual(geometric_mean_ratio(refs, costs), 2.0)


if __name__ == "__main__":
    unittest.main()
