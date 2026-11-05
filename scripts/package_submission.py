#!/usr/bin/env python3
"""Package an existing three-task submission zip.

Refuses to invent missing circuits. Default output is under submissions/,
which is git-ignored. See docs/brief.md for the layout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.packaging import PackageError, build_submission_zip  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invsqrt", type=Path, required=True, help="existing .kmb or .kmx")
    parser.add_argument("--dqi", type=Path, required=True, help="existing .kmb or .kmx")
    parser.add_argument(
        "--dfthcsos",
        type=Path,
        required=True,
        help="directory with angle_k_0..N and submission.npz",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "submissions" / "submission.zip",
        help="zip path to write (default: submissions/submission.zip)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_submission_zip(
            invsqrt=args.invsqrt,
            dqi=args.dqi,
            dfthcsos_dir=args.dfthcsos,
            output=args.output,
        )
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(payload["disclaimer"])
        print(f"wrote {payload['output']}")
        for entry in payload["entries"]:
            print(f"  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
