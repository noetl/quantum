#!/usr/bin/env python3
"""Kaggle entrypoint for the per-task optimization loop.

Run this on a Kaggle CPU notebook that already has the competition dataset
attached. It does not accept the rules, it does not call the Kaggle submit
API, and it does not write a submission zip (packaging stays disarmed).

The NoETL playbook that orchestrates the same steps is
``playbooks/vqcc_optimize.yaml``. From the repository root, with NoETL 5.3.2:

    noetl run playbooks/vqcc_optimize.yaml --runtime local --json \\
      --set data_dir=/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation \\
      --set runs_root=/kaggle/working/runs \\
      --set repo_root="$PWD" \\
      --set seed=20261108

This script calls those same ``python3 -m vqcc.pipeline`` steps so it still
runs when the notebook image has no ``noetl`` binary. Pass ``--task`` to
optimize one task and leave the other two unimported.

What to check in the run JSON:

- ``leaderboard_score`` is null on every step.
- ``package.zip_written`` is false.
- A task with ``optimization.status`` ``accepted`` has a strictly lower
  ``retained_cost`` than ``baseline_cost``, and ``competition_verified`` true.
- ``rejected`` or ``unchanged`` leaves that task's artifact path on the
  baseline file. A rejected proposal is not the retained path.
- The other tasks' sha256 values are unchanged when you passed ``--task``.
- No file was written under the read-only dataset mount.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.official_verifier import REFERENCE_SEED  # noqa: E402
from vqcc.orchestrator import TASKS  # noqa: E402
from vqcc.pipeline import main as pipeline_main  # noqa: E402

KAGGLE_DATA = Path(
    "/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=KAGGLE_DATA)
    parser.add_argument("--runs-root", type=Path, default=Path("/kaggle/working/runs"))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--seed", default=REFERENCE_SEED)
    parser.add_argument("--task", choices=TASKS, default=None)
    parser.add_argument("--time-budget-s", type=float, default=14400)
    parser.add_argument("--memory-budget-bytes", type=int, default=2 * 1024**3)
    parser.add_argument("--window", type=int, default=32)
    parser.add_argument("--max-candidates", type=int, default=1)
    args = parser.parse_args(argv)
    tasks = (args.task,) if args.task else TASKS
    common = [
        "--repo-root",
        str(args.repo_root),
        "--runs-root",
        str(args.runs_root),
    ]
    steps: list[list[str]] = [
        [
            "prepare",
            "--mode",
            "competition",
            "--data-dir",
            str(args.data_dir),
            "--seed",
            str(args.seed),
            *common,
        ],
        ["check-data", *common],
    ]
    for task in tasks:
        steps.append(["adapt", "--task", task, *common])
    for task in tasks:
        steps.append(["verify-official", "--task", task, "--seed", str(args.seed), *common])
    for task in tasks:
        steps.append(
            [
                "optimize",
                "--task",
                task,
                "--time-budget-s",
                str(args.time_budget_s),
                "--memory-budget-bytes",
                str(args.memory_budget_bytes),
                "--window",
                str(args.window),
                "--max-candidates",
                str(args.max_candidates),
                *common,
            ]
        )
    steps.extend(
        [
            ["cost", *common],
            ["package", *common],
            ["record", *common],
        ]
    )
    last = 0
    for argv_step in steps:
        code = pipeline_main(argv_step)
        last = code
        if code != 0:
            print(json.dumps({"step": argv_step[0], "exit_code": code}), file=sys.stderr)
            return code
    print(
        json.dumps(
            {
                "entrypoint": "kaggle/vqcc_optimize.py",
                "playbook": "playbooks/vqcc_optimize.yaml",
                "tasks": list(tasks),
                "submitted_to_kaggle": False,
                "leaderboard_score": None,
                "check": [
                    "optimization.status is accepted only with retained_cost < baseline_cost",
                    "rejected and unchanged leave the previous artifact in place",
                    "other tasks are unmodified when --task is set",
                    "package.zip_written is false",
                    "leaderboard_score is null",
                ],
            },
            indent=2,
        )
    )
    return last


if __name__ == "__main__":
    raise SystemExit(main())
