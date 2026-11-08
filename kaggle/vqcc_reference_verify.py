#!/usr/bin/env python3
"""Kaggle bootstrap for the official reference-circuit verifiers.

Run this file as a script notebook on a Kaggle CPU kernel that already has
the competition dataset attached. It does not accept rules, submit, or edit
itself in the browser.

    python kaggle/vqcc_reference_verify.py

The dataset mount used by the recorded reference run is:

    /kaggle/input/competitions/google-verifiable-quantum-circuit-compilation

Override with VQCC_DATA_ROOT or --data-root. Seed defaults to 20261108, the
seed of that private reference run, not the leaderboard salt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.official_verifier import (  # noqa: E402
    REFERENCE_SEED,
    discover_dataset_root,
    run_official_task,
)
from vqcc.orchestrator import TASKS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--seed", default=REFERENCE_SEED)
    parser.add_argument("--log-dir", type=Path, default=Path("/kaggle/working/reference-verification"))
    parser.add_argument("--timeout", type=int, default=None)
    args = parser.parse_args(argv)
    if args.data_root is not None:
        located = discover_dataset_root(explicit=args.data_root, require=True)
    else:
        located = discover_dataset_root(require=False)
    print(json.dumps({"dataset": located}, indent=2))
    if not located.get("found"):
        print("official verifier scripts were not found", file=sys.stderr)
        return 2
    root = Path(located["root"])
    args.log_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for task in TASKS:
        report = run_official_task(
            root=root,
            task=task,
            seed=args.seed,
            timeout_s=args.timeout,
            log_dir=args.log_dir,
        )
        results.append(report)
        print(json.dumps({"task": task, "status": report["status"], "exit_code": report.get("exit_code"), "parsed_cost": report.get("parsed_cost"), "competition_verified": report["competition_verified"], "leaderboard_score": None}, indent=2))
    summary = {
        "leaderboard_score": None,
        "aggregate_score": None,
        "all_competition_verified": all(item["competition_verified"] for item in results),
        "tasks": results,
    }
    (args.log_dir / "run-metadata.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if summary["all_competition_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
