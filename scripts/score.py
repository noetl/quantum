#!/usr/bin/env python3
"""Evaluate a labeled VQCC formula on numbers you supply.

This does not read the competition data and it does not report a leaderboard
score. dqi and dfthcsos require --source hub or --source paper because those
write-ups disagree. The aggregate subcommand implements the hub's geometric
mean and always labels it unconfirmed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.formulas import (  # noqa: E402
    FormulaError,
    FormulaSource,
    dfthcsos_constraint_notes,
    dfthcsos_cost,
    dqi_cost,
    geometric_mean_ratio,
    invsqrt_cost,
)

DISCLAIMER = (
    "Formula evaluation of the inputs below. Not a leaderboard score. "
    "Not a result from this repository."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("invsqrt", help="Q * (Toffoli + T/4)")
    _add_common_output(inv)
    inv.add_argument("--qubits", type=int, required=True)
    inv.add_argument("--toffoli", type=float, required=True)
    inv.add_argument("--t-gates", type=float, required=True)
    inv.set_defaults(func=_invsqrt)

    dqi = sub.add_parser("dqi", help="R(eps+) * Q^2 * T, source required")
    _add_common_output(dqi)
    _add_source(dqi)
    dqi.add_argument("--qubits", type=int, required=True)
    dqi.add_argument("--toffoli", type=float, required=True)
    dqi.add_argument("--epsilon-plus", type=float, required=True)
    dqi.set_defaults(func=_dqi)

    chem = sub.add_parser("dfthcsos", help="lambda_eff * T * Q, source required")
    _add_common_output(chem)
    _add_source(chem)
    chem.add_argument("--e-gap-ha", type=float, required=True)
    chem.add_argument("--lambda-ha", type=float, required=True)
    chem.add_argument("--t-count", type=float, required=True)
    chem.add_argument("--qubits", type=float, required=True)
    chem.set_defaults(func=_dfthcsos)

    agg = sub.add_parser(
        "aggregate",
        help="Hub geometric mean, always marked unconfirmed",
    )
    _add_common_output(agg)
    for task in ("invsqrt", "dqi", "dfthcsos"):
        agg.add_argument(f"--ref-{task}", type=float, required=True)
        agg.add_argument(f"--cost-{task}", type=float, required=True)
    agg.set_defaults(func=_aggregate)

    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except FormulaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    payload["disclaimer"] = DISCLAIMER
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(DISCLAIMER)
        for key, value in payload.items():
            if key == "disclaimer":
                continue
            print(f"{key}: {value}")
    return 0


def _add_common_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print a JSON object")


def _add_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        required=True,
        choices=[source.value for source in FormulaSource],
        help="hub or paper; required because the write-ups disagree",
    )


def _invsqrt(args: argparse.Namespace) -> dict[str, object]:
    value = invsqrt_cost(args.qubits, args.toffoli, args.t_gates)
    return {
        "task": "invsqrt",
        "source": "hub and paper agree on Q*(Toffoli+T/4)",
        "unconfirmed": False,
        "rotation_pricing": "not applied; paper Z_POW pricing needs per-rotation error inputs",
        "inputs": {
            "qubits": args.qubits,
            "toffoli": args.toffoli,
            "t_gates": args.t_gates,
        },
        "cost": value,
        "leaderboard_score": None,
    }


def _dqi(args: argparse.Namespace) -> dict[str, object]:
    value = dqi_cost(args.qubits, args.toffoli, args.epsilon_plus, args.source)
    return {
        "task": "dqi",
        "source": args.source,
        "unconfirmed": args.source == FormulaSource.HUB.value,
        "inputs": {
            "qubits": args.qubits,
            "toffoli": args.toffoli,
            "epsilon_plus": args.epsilon_plus,
        },
        "cost": value,
        "leaderboard_score": None,
        "note": (
            "Hub R is marked unconfirmed on the hub. "
            "Paper T is a Toffoli count. See docs/open-questions.md."
        ),
    }


def _dfthcsos(args: argparse.Namespace) -> dict[str, object]:
    value = dfthcsos_cost(
        args.e_gap_ha,
        args.lambda_ha,
        args.t_count,
        args.qubits,
        args.source,
    )
    notes = dfthcsos_constraint_notes(
        qubits=int(args.qubits) if float(args.qubits).is_integer() else None,
        lambda_ha=args.lambda_ha,
        e_gap_ha=args.e_gap_ha,
    )
    return {
        "task": "dfthcsos",
        "source": args.source,
        "unconfirmed": False,
        "conflict": "hub lambda_eff has no square root; paper equation 44 does",
        "inputs": {
            "e_gap_ha": args.e_gap_ha,
            "lambda_ha": args.lambda_ha,
            "t_count": args.t_count,
            "qubits": args.qubits,
        },
        "constraint_notes": notes,
        "cost": value,
        "leaderboard_score": None,
    }


def _aggregate(args: argparse.Namespace) -> dict[str, object]:
    refcosts = {
        "invsqrt": args.ref_invsqrt,
        "dqi": args.ref_dqi,
        "dfthcsos": args.ref_dfthcsos,
    }
    costs = {
        "invsqrt": args.cost_invsqrt,
        "dqi": args.cost_dqi,
        "dfthcsos": args.cost_dfthcsos,
    }
    value = geometric_mean_ratio(refcosts, costs)
    return {
        "task": "aggregate",
        "source": "hub",
        "unconfirmed": True,
        "expression": "(prod refcost/cost) ** (1/3)",
        "inputs": {"refcosts": refcosts, "costs": costs},
        "value": value,
        "leaderboard_score": None,
        "note": "Hub marks this metric unconfirmed. Do not write it to the LB column.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
