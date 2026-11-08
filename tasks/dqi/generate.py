#!/usr/bin/env python3
"""Stop before writing a dqi circuit.

Real generation needs kickmix and the competition verifiers in data/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqcc.generate import refuse_unimplemented  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(refuse_unimplemented("dqi", ROOT))
