"""Relative links in the tutorial, the wiki mirror, and the README resolve."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)

# Pages a reviewer opens from the README or the wiki home.
SCOPE = [
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
]


def _markdown_files() -> list[Path]:
    files = list(SCOPE)
    files.extend(sorted((ROOT / "docs" / "tutorial").glob("*.md")))
    files.extend(sorted((ROOT / "docs" / "wiki").glob("*.md")))
    return files


def _visible_links(text: str) -> list[str]:
    return LINK.findall(FENCE.sub("", text))


def _resolves(source: Path, target: str) -> bool:
    path = target.split("#", 1)[0].strip()
    if not path or path.startswith(("http://", "https://", "mailto:")):
        return True
    if path.startswith("<") or "://" in path:
        return True
    candidate = (source.parent / path).resolve()
    names = [candidate]
    if candidate.suffix == "":
        names.append(candidate.with_suffix(".md"))
        names.append(candidate / "README.md")
    return any(item.is_file() for item in names)


class DocLinkTests(unittest.TestCase):
    def test_relative_links_resolve(self) -> None:
        missing: list[str] = []
        for path in _markdown_files():
            text = path.read_text(encoding="utf-8")
            for target in _visible_links(text):
                if not _resolves(path, target):
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
