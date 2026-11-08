#!/usr/bin/env python3
"""Append one row to the experiment log.

Local and LB default to a blank em dash. This command will not invent a score.
Pass only numbers you measured or that a verifier returned.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "docs" / "experiments.md"
HEADER = "| Date | Run | Description | Local | LB | Notes |"
SEPARATOR = "| --- | --- | --- | --- | --- | --- |"
BLANK = "—"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--run", required=True, help="run id")
    parser.add_argument("--description", required=True)
    parser.add_argument("--local", default=BLANK, help="measured local value, or omit")
    parser.add_argument("--lb", default=BLANK, help="leaderboard return, or omit")
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_LOG,
        help="markdown log to update",
    )
    args = parser.parse_args(argv)
    try:
        row = format_row(
            args.date,
            args.run,
            args.description,
            args.local,
            args.lb,
            args.notes,
        )
        append_row(args.file, row)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"appended to {args.file}")
    print(row)
    return 0


def format_row(
    date: str,
    run: str,
    description: str,
    local: str,
    lb: str,
    notes: str,
) -> str:
    cells = [date, run, description, local, lb, notes]
    if any(cell is None or str(cell).strip() == "" for cell in cells[:3]):
        raise ValueError("date, run, and description are required")
    for cell in cells:
        text = str(cell)
        if "|" in text or "\n" in text:
            raise ValueError("cells cannot contain '|' or newlines")
    lowered = {str(local).strip().lower(), str(lb).strip().lower()}
    if lowered & {"auto", "sample", "todo", "guess", "tbd", "unknown"}:
        raise ValueError("use a measured value or omit --local/--lb; do not pass a placeholder word")
    return "| " + " | ".join(str(cell).strip() for cell in cells) + " |"


def append_row(path: Path, row: str) -> None:
    if not path.is_file():
        raise ValueError(f"log not found: {path}")
    text = path.read_text(encoding="utf-8")
    if HEADER not in text:
        raise ValueError("experiments table header is missing")
    lines = text.splitlines()
    header_at = next(index for index, line in enumerate(lines) if line.strip() == HEADER)
    if header_at + 1 >= len(lines) or lines[header_at + 1].strip() != SEPARATOR:
        lines.insert(header_at + 1, SEPARATOR)
    lines.append(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
