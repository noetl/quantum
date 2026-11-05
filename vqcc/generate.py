"""Shared stop for task generators that are not implemented yet."""

from __future__ import annotations

from pathlib import Path


def refuse_unimplemented(task: str, repo_root: Path | None = None) -> int:
    """Print why no circuit was written, and return a non-zero status."""

    root = repo_root or Path.cwd()
    verifiers = root / "data" / "verifiers"
    if not verifiers.is_dir():
        print(
            f"{task}: blocked. {verifiers} is absent. "
            "Fetch the competition data with scripts/fetch_data.sh. "
            "No circuit was written."
        )
        return 2
    print(
        f"{task}: {verifiers} is present, but no generator is implemented. "
        "No circuit was written."
    )
    return 2
