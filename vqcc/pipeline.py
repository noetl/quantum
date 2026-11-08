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
    package,
    prepare_run,
    record,
    verify,
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
    prep.set_defaults(func=_prepare)

    sub.add_parser("check-data", parents=[common]).set_defaults(func=_check)

    adapt = sub.add_parser("adapt", parents=[common])
    adapt.add_argument("--task", required=True)
    adapt.set_defaults(func=_adapt)

    sub.add_parser("verify", parents=[common]).set_defaults(func=_verify)
    cost_cmd = sub.add_parser("cost", parents=[common])
    cost_cmd.add_argument(
        "--aggregate",
        action="store_true",
        help="request the hub aggregate; it stays unconfirmed and is not an LB score",
    )
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
    return prepare_run(args.repo_root, args.runs_root, args.mode, args.data_dir)


def _check(args: argparse.Namespace) -> dict:
    return check_data(args.repo_root, args.runs_root)


def _adapt(args: argparse.Namespace) -> dict:
    return adapt_task(args.repo_root, args.runs_root, args.task)


def _verify(args: argparse.Namespace) -> dict:
    return verify(args.repo_root, args.runs_root)


def _cost(args: argparse.Namespace) -> dict:
    return cost(args.repo_root, args.runs_root, aggregate=args.aggregate)


def _package(args: argparse.Namespace) -> dict:
    return package(args.repo_root, args.runs_root)


def _record(args: argparse.Namespace) -> dict:
    return record(args.repo_root, args.runs_root)


if __name__ == "__main__":
    raise SystemExit(main())
