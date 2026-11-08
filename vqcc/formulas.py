"""Labeled cost formulas for the three VQCC tasks.

Every function evaluates the inputs it is given under a named source. The
team hub and the companion paper (arXiv:2610.23832) disagree on dqi and
dfthcsos. Callers choose the source. Nothing here is a leaderboard score
or a result produced by this repository.
"""

from __future__ import annotations

import math
from enum import Enum

# Shared by the hub and the paper. The paper states these as strict floors:
# Lambda must be greater than 49.0 Ha and E_gap greater than 3.914898 Ha.
# The hub lists the same two numbers and points at
# verifiers/dfthcsos/SCORING_README.md, which was not available here.
LAMBDA_FLOOR_HA = 49.0
E_GAP_FLOOR_HA = 3.914898
QUBIT_CAP = 128
FROBENIUS_TOLERANCE_HA = 0.020  # 20 mHa

TASKS = ("invsqrt", "dqi", "dfthcsos")


class FormulaSource(str, Enum):
    """Which published write-up a formula follows."""

    HUB = "hub"
    PAPER = "paper"


class FormulaError(ValueError):
    """The inputs do not define a finite cost under the chosen source."""


def invsqrt_cost(qubits: int, toffoli: float, t_gates: float) -> float:
    """Return Q × (Toffoli + T/4).

    The hub and the paper agree on this expression. The paper prices
    non-Clifford Z_POW rotations into the T count before the formula is
    applied. This function does not do that pricing. Pass a T count that
    already includes it when you have one.
    """

    _nonnegative("qubits", qubits)
    _nonnegative("toffoli", toffoli)
    _nonnegative("t_gates", t_gates)
    return float(qubits) * (float(toffoli) + float(t_gates) / 4.0)


def dqi_repetition(epsilon: float, source: FormulaSource) -> float:
    """Return R(ε) under one source.

    Hub, marked unconfirmed on the hub:
        R(ε) = ln 2 − ln(1/2 + 2ε)
    Paper equation 43:
        R(ε) = ln 2 / (−ln(1/2 + 2√ε))
    The paper gives no finite score for ε ≥ 1/16.
    """

    source = _source(source)
    if epsilon < 0:
        raise FormulaError("epsilon must be non-negative")
    if source is FormulaSource.HUB:
        # The hub marks this rendering unconfirmed.
        argument = 0.5 + 2.0 * float(epsilon)
        if argument <= 0.0:
            raise FormulaError("hub R is undefined for this epsilon")
        return math.log(2.0) - math.log(argument)
    if float(epsilon) >= 1.0 / 16.0:
        raise FormulaError(
            "paper R has no finite value for epsilon >= 1/16 "
            "(arXiv:2610.23832, section III.2.3)"
        )
    inside = 0.5 + 2.0 * math.sqrt(float(epsilon))
    if inside >= 1.0:
        raise FormulaError("paper R is undefined for this epsilon")
    return math.log(2.0) / (-math.log(inside))


def dqi_cost(
    qubits: int,
    toffoli: float,
    epsilon_plus: float,
    source: FormulaSource,
) -> float:
    """Return R(ε⁺) × Q² × T under one source.

    The paper defines T as the single-run Toffoli count, including workspace
    cleanup. The hub writes T without that sentence. The caller passes the
    count they intend, and the source flag records which write-up they mean.
    """

    _nonnegative("qubits", qubits)
    _nonnegative("toffoli", toffoli)
    repetition = dqi_repetition(epsilon_plus, source)
    return repetition * (float(qubits) ** 2) * float(toffoli)


def lambda_eff(
    e_gap_ha: float,
    lambda_ha: float,
    source: FormulaSource,
) -> float:
    """Return λ_eff in Hartree under one source.

    Hub, not marked unconfirmed there:
        λ_eff = E_gap (2Λ − E_gap)
    Paper equation 44:
        λ_eff = sqrt(E_gap (2Λ − E_gap))
    """

    source = _source(source)
    product = float(e_gap_ha) * (2.0 * float(lambda_ha) - float(e_gap_ha))
    if product < 0.0:
        raise FormulaError("E_gap * (2*Lambda - E_gap) is negative")
    if source is FormulaSource.HUB:
        return product
    return math.sqrt(product)


def dfthcsos_cost(
    e_gap_ha: float,
    lambda_ha: float,
    t_count: float,
    qubits: float,
    source: FormulaSource,
) -> float:
    """Return λ_eff × T × Q under one source.

    The paper's T_tot and Q_tot include heuristic costs for Outer, Inner, and
    Givens rotations plus the simulated angle circuits. This function does
    not build those pieces. Pass the T and Q you already assembled.
    """

    _nonnegative("t_count", t_count)
    _nonnegative("qubits", qubits)
    return lambda_eff(e_gap_ha, lambda_ha, source) * float(t_count) * float(qubits)


def dfthcsos_constraint_notes(
    *,
    qubits: int | None = None,
    lambda_ha: float | None = None,
    e_gap_ha: float | None = None,
) -> list[str]:
    """Return human-readable constraint hits. Empty means no hit was detected.

    These compare the caller's numbers with the published caps. They are not
    a measurement of a circuit in this repository.
    """

    notes: list[str] = []
    if qubits is not None and qubits > QUBIT_CAP:
        notes.append(
            f"qubit cap: {qubits} exceeds {QUBIT_CAP} "
            "(hub and arXiv:2610.23832)"
        )
    if lambda_ha is not None and lambda_ha <= LAMBDA_FLOOR_HA:
        notes.append(
            f"paper floor: Lambda {lambda_ha} Ha is not greater than "
            f"{LAMBDA_FLOOR_HA} Ha"
        )
    if e_gap_ha is not None and e_gap_ha <= E_GAP_FLOOR_HA:
        notes.append(
            f"paper floor: E_gap {e_gap_ha} Ha is not greater than "
            f"{E_GAP_FLOOR_HA} Ha"
        )
    return notes


def geometric_mean_ratio(refcosts: dict[str, float], costs: dict[str, float]) -> float:
    """Evaluate the hub's aggregate expression.

    The hub writes

        Score = (Π_b refcost_b / cost_b) ^ (1/3)

    over invsqrt, dqi, and dfthcsos, and marks it unconfirmed. The paper
    does not state this aggregate. Callers must label the result unconfirmed.
    """

    product = 1.0
    for task in TASKS:
        if task not in refcosts or task not in costs:
            raise FormulaError(f"missing refcost or cost for {task}")
        ref = float(refcosts[task])
        cost = float(costs[task])
        if ref <= 0.0 or cost <= 0.0:
            raise FormulaError("refcost and cost must be positive")
        product *= ref / cost
    return product ** (1.0 / 3.0)


def _source(source: FormulaSource | str) -> FormulaSource:
    if isinstance(source, FormulaSource):
        return source
    try:
        return FormulaSource(source)
    except ValueError as exc:
        raise FormulaError("source must be 'hub' or 'paper'") from exc


def _nonnegative(name: str, value: float) -> None:
    if value < 0:
        raise FormulaError(f"{name} must be non-negative")
