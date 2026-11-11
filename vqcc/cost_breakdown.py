"""Split a published task cost into the factors the verifier charges.

The official task cost is the verifier JSON ``score`` (spec FR-004). These
helpers explain that score from the other JSON fields. They do not invent
a dqi repetition factor or a dfthcsos lambda: the caller passes the values
the verifier already printed. FR-006 and FR-007 stay open as formula
questions; this module does not choose between the hub and the paper.

Nothing here is a leaderboard score.
"""

from __future__ import annotations

import math


class CostBreakdownError(ValueError):
    """The supplied verifier fields do not multiply to the score."""


def _share(part: float, whole: float) -> float:
    if whole == 0.0:
        return 0.0
    return part / whole


def invsqrt_breakdown(
    *,
    qubits: int,
    toffoli_count: float,
    t_count: float,
    toffoli_equivalent: float,
    score: float,
    rotation_count: float | None = None,
    rotation_eps: float | None = None,
) -> dict:
    """Split ``Q * toffoli_equivalent`` into Toffoli, T/4, and rotations.

    ``toffoli_equivalent`` is the verifier's ``C``. The rotation residual is
    ``C - Toffoli - T/4``. When ``rotation_count`` and ``rotation_eps`` are
    both supplied, the paper's mixed-fallback price
    ``0.56 log2(1/eps) + 5.3`` T gates per fine rotation is reported beside
    that residual. It is an explanation of verifier fields, not a second score.
    """

    gate = float(toffoli_count) + float(t_count) / 4.0
    rotation = float(toffoli_equivalent) - gate
    reconstructed = float(qubits) * float(toffoli_equivalent)
    if not math.isclose(reconstructed, float(score), rel_tol=0.0, abs_tol=1e-6):
        raise CostBreakdownError(
            f"Q * toffoli_equivalent = {reconstructed} does not match score {score}"
        )
    synthesis = None
    if rotation_count is not None and rotation_eps is not None:
        if float(rotation_eps) <= 0.0:
            raise CostBreakdownError("rotation_eps must be positive")
        t_per = 0.56 * math.log2(1.0 / float(rotation_eps)) + 5.3
        synthesis = {
            "t_gates_per_rotation": t_per,
            "toffoli_equivalent": float(rotation_count) * t_per / 4.0,
            "source": "paper mixed-fallback 0.56*log2(1/eps)+5.3 T per fine Z_POW",
        }
    return {
        "task": "invsqrt",
        "score": float(score),
        "expression": "Q * (Toffoli + T/4 + rotation synthesis)",
        "qubits": int(qubits),
        "toffoli_count": float(toffoli_count),
        "t_over_4": float(t_count) / 4.0,
        "rotation_toffoli_equivalent": rotation,
        "parts": {
            "toffoli": float(qubits) * float(toffoli_count),
            "t": float(qubits) * float(t_count) / 4.0,
            "rotation": float(qubits) * rotation,
        },
        "shares_of_gate_factor": {
            "toffoli": _share(float(toffoli_count), float(toffoli_equivalent)),
            "t": _share(float(t_count) / 4.0, float(toffoli_equivalent)),
            "rotation": _share(rotation, float(toffoli_equivalent)),
        },
        "marginal": {
            "one_toffoli": float(qubits),
            "one_qubit": float(toffoli_equivalent),
        },
        "synthesis": synthesis,
    }


def dqi_breakdown(
    *,
    qubits: int,
    toffoli_count: float,
    repetition_factor: float,
    score: float,
    max_toffoli_count: float | None = None,
) -> dict:
    """Split ``R * Q^2 * Toffoli`` using the verifier's own ``R`` and ``T``.

    ``R`` is the printed ``repetition_factor``. This does not evaluate the
    hub or paper formula for ``R`` (FR-006).
    """

    qubit_factor = float(qubits) ** 2
    reconstructed = float(repetition_factor) * qubit_factor * float(toffoli_count)
    if not math.isclose(reconstructed, float(score), rel_tol=0.0, abs_tol=1e-4):
        raise CostBreakdownError(
            f"R * Q^2 * Toffoli = {reconstructed} does not match score {score}"
        )
    conditional = None
    if max_toffoli_count is not None:
        conditional = float(max_toffoli_count) - float(toffoli_count)
    next_qubits = float(qubits) - 1.0
    one_qubit = float(repetition_factor) * float(toffoli_count) * (qubit_factor - next_qubits**2)
    return {
        "task": "dqi",
        "score": float(score),
        "expression": "R * Q^2 * Toffoli",
        "qubits": int(qubits),
        "qubit_factor": qubit_factor,
        "toffoli_count": float(toffoli_count),
        "repetition_factor": float(repetition_factor),
        "conditional_toffoli_gap": conditional,
        "shares": {"toffoli_and_qubits": 1.0},
        "marginal": {
            "one_toffoli": float(repetition_factor) * qubit_factor,
            "one_qubit": one_qubit,
        },
    }


def dfthcsos_breakdown(
    *,
    qubits: int,
    toffoli_count: float,
    lambda_eff: float,
    score: float,
    file_toffoli_count: float | None = None,
) -> dict:
    """Split ``lambda_eff * Toffoli * Q`` using the verifier's lambda.

    ``lambda_eff`` is the printed field. This does not choose the hub or
    paper expression for it (FR-007). When ``file_toffoli_count`` is the
    kickmix Toffoli total of the angle files, the residual
    ``toffoli_count - 2 * file_toffoli_count`` is the part not explained by
    counting each file once forward and once in reverse (paper eq. A14).
    """

    reconstructed = float(lambda_eff) * float(toffoli_count) * float(qubits)
    if not math.isclose(reconstructed, float(score), rel_tol=0.0, abs_tol=1e-4):
        raise CostBreakdownError(
            f"lambda_eff * Toffoli * Q = {reconstructed} does not match score {score}"
        )
    doubled = None
    heuristic = None
    if file_toffoli_count is not None:
        doubled = 2.0 * float(file_toffoli_count)
        heuristic = float(toffoli_count) - doubled
    return {
        "task": "dfthcsos",
        "score": float(score),
        "expression": "lambda_eff * Toffoli * Q",
        "qubits": int(qubits),
        "toffoli_count": float(toffoli_count),
        "lambda_eff": float(lambda_eff),
        "forward_and_reverse_file_toffolis": doubled,
        "unexplained_toffolis": heuristic,
        "marginal": {
            "one_toffoli": float(lambda_eff) * float(qubits),
            "one_qubit": float(lambda_eff) * float(toffoli_count),
            "one_file_toffoli_if_counted_twice": float(lambda_eff) * 2.0 * float(qubits),
        },
    }
