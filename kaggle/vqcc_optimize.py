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
- ``unchanged`` means the rewrite did not lower the charged weight or the
  qubit count, so the verifier was not asked to score one. A Clifford-only
  shrink is not sent. ``structure`` on the optimize step is the circuit
  profile (opcodes, lifetimes, repeated blocks). It is not a score.
- The other tasks' sha256 values are unchanged when you passed ``--task``.
- No file was written under the read-only dataset mount.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUNBUFFERED", "1")
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.official_verifier import REFERENCE_SEED  # noqa: E402
from vqcc.orchestrator import TASKS  # noqa: E402
from vqcc.pipeline import main as pipeline_main  # noqa: E402

KAGGLE_DATA = Path(
    "/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation"
)
# Nine hours for every optimize step together, under the 12-hour Kaggle kill.
# dqi is the large circuit. Each transform is capped on its own.
_OPTIMIZE_BUDGET_S = 9 * 60 * 60
_TRANSFORM_BUDGET_S = 2 * 60 * 60
_TASK_SHARE = {"invsqrt": 0.15, "dqi": 0.70, "dfthcsos": 0.15}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=KAGGLE_DATA)
    parser.add_argument("--runs-root", type=Path, default=Path("/kaggle/working/runs"))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--seed", default=REFERENCE_SEED)
    parser.add_argument("--task", choices=TASKS, default=None)
    parser.add_argument("--time-budget-s", type=float, default=None)
    parser.add_argument("--transform-budget-s", type=float, default=None)
    parser.add_argument("--optimize-budget-s", type=float, default=None)
    parser.add_argument("--memory-budget-bytes", type=int, default=2 * 1024**3)
    parser.add_argument("--window", type=int, default=4096)
    parser.add_argument("--max-candidates", type=int, default=1)
    args = parser.parse_args(argv)
    tasks = (args.task,) if args.task else TASKS
    overall = args.optimize_budget_s
    if overall is None:
        overall = _env_float("VQCC_OPTIMIZE_BUDGET_S", _OPTIMIZE_BUDGET_S)
    transform = args.transform_budget_s
    if transform is None:
        transform = _env_float("VQCC_TRANSFORM_BUDGET_S", _TRANSFORM_BUDGET_S)
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
        task_budget = args.time_budget_s
        if task_budget is None:
            task_budget = _env_float("VQCC_TASK_BUDGET_S", _TASK_SHARE[task] * overall)
        steps.append(
            [
                "optimize",
                "--task",
                task,
                "--time-budget-s",
                str(task_budget),
                "--transform-budget-s",
                str(transform),
                "--optimize-budget-s",
                str(overall),
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
        task_name = "-"
        if "--task" in argv_step:
            task_name = argv_step[argv_step.index("--task") + 1]
        print(f"progress step={argv_step[0]} task={task_name}", flush=True)
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
