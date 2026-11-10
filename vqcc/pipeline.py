#!/usr/bin/env python3
"""Steps the NoETL playbook runs.

Each subcommand prints one JSON object on stdout and nothing else. Blocked
competition checks exit 0. Usage errors and a missing kickmix install in
structural mode exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vqcc.orchestrator import (
    PipelineError,
    adapt_task,
    check_data,
    cost,
    optimize_task,
    package,
    prepare_run,
    record,
    verify,
    verify_official,
)


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo-root", type=Path, default=Path.cwd())
    common.add_argument("--runs-root", type=Path, default=Path("runs"))

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", parents=[common])
    prep.add_argument("--mode", required=True, choices=("competition", "structural"))
    prep.add_argument("--data-dir", type=Path, default=Path("data"))
    prep.add_argument("--seed", default="20261108")
    prep.add_argument(
        "--package-when-verified",
        action="store_true",
        help="write a zip only after all three official verifiers pass",
    )
    prep.set_defaults(func=_prepare)

    sub.add_parser("check-data", parents=[common]).set_defaults(func=_check)

    adapt = sub.add_parser("adapt", parents=[common])
    adapt.add_argument("--task", required=True)
    adapt.set_defaults(func=_adapt)

    sub.add_parser("verify", parents=[common]).set_defaults(func=_verify)
    one = sub.add_parser("verify-official", parents=[common])
    one.add_argument("--task", required=True)
    one.add_argument("--seed", default=None)
    one.add_argument("--timeout", type=int, default=None)
    one.set_defaults(func=_verify_one)
    opt = sub.add_parser("optimize", parents=[common])
    opt.add_argument("--task", required=True)
    opt.add_argument("--time-budget-s", type=float, default=None)
    opt.add_argument("--memory-budget-bytes", type=int, default=2 * 1024**3)
    opt.add_argument("--window", type=int, default=32)
    opt.add_argument("--max-candidates", type=int, default=1)
    opt.add_argument("--verify-timeout", type=int, default=None)
    opt.set_defaults(func=_optimize)
    cost_cmd = sub.add_parser("cost", parents=[common])
    cost_cmd.add_argument(
        "--aggregate",
        action="store_true",
        help="request the hub aggregate; it stays unconfirmed and is not an LB score",
    )
    cost_cmd.add_argument("--ref-invsqrt", type=float, default=None)
    cost_cmd.add_argument("--ref-dqi", type=float, default=None)
    cost_cmd.add_argument("--ref-dfthcsos", type=float, default=None)
    cost_cmd.set_defaults(func=_cost)
    sub.add_parser("package", parents=[common]).set_defaults(func=_package)
    sub.add_parser("record", parents=[common]).set_defaults(func=_record)

    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _prepare(args: argparse.Namespace) -> dict:
    return prepare_run(
        args.repo_root,
        args.runs_root,
        args.mode,
        args.data_dir,
        seed=args.seed,
        package_when_verified=args.package_when_verified,
    )


def _check(args: argparse.Namespace) -> dict:
    return check_data(args.repo_root, args.runs_root)


def _adapt(args: argparse.Namespace) -> dict:
    return adapt_task(args.repo_root, args.runs_root, args.task)


def _verify(args: argparse.Namespace) -> dict:
    return verify(args.repo_root, args.runs_root)


def _verify_one(args: argparse.Namespace) -> dict:
    return verify_official(
        args.repo_root,
        args.runs_root,
        args.task,
        seed=args.seed,
        timeout_s=args.timeout,
    )


def _optimize(args: argparse.Namespace) -> dict:
    return optimize_task(
        args.repo_root,
        args.runs_root,
        args.task,
        time_budget_s=args.time_budget_s,
        memory_budget_bytes=args.memory_budget_bytes,
        window=args.window,
        max_candidates=args.max_candidates,
        verify_timeout_s=args.verify_timeout,
    )


def _cost(args: argparse.Namespace) -> dict:
    refcosts = {
        task: getattr(args, f"ref_{task}")
        for task in ("invsqrt", "dqi", "dfthcsos")
        if getattr(args, f"ref_{task}") is not None
    }
    return cost(
        args.repo_root,
        args.runs_root,
        aggregate=args.aggregate,
        refcosts=refcosts or None,
    )


def _package(args: argparse.Namespace) -> dict:
    return package(args.repo_root, args.runs_root)


def _record(args: argparse.Namespace) -> dict:
    return record(args.repo_root, args.runs_root)


if __name__ == "__main__":
    raise SystemExit(main())
