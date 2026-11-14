"""Wall-clock deadline shared by the optimize passes.

The streaming loops call :func:`check` so a long inner scan cannot run past
the task deadline. That check is cooperative. The optimize step also runs
the heavy transform in a child process and kills it when the same deadline
passes, which is what stops a loop that never reaches :func:`check`.
"""

from __future__ import annotations

import time

from vqcc.kickmix_file import OptimizeBudgetError


class _Armed:
    deadline: float | None = None
    transform_deadline: float | None = None
    depth: int = 0


def arm(deadline: float | None, transform_deadline: float | None) -> None:
    """Remember the deadlines for nested loops that do not take them as arguments."""

    _Armed.depth += 1
    _Armed.deadline = deadline
    _Armed.transform_deadline = transform_deadline


def disarm() -> None:
    _Armed.depth = max(0, _Armed.depth - 1)
    if _Armed.depth == 0:
        _Armed.deadline = None
        _Armed.transform_deadline = None


_MISSING = object()


def check(
    deadline: float | None | object = _MISSING,
    transform_deadline: float | None | object = _MISSING,
) -> None:
    """Raise when the task deadline or the transform deadline has passed.

    A call with no arguments uses the deadlines :func:`arm` stored.
    ``None`` means that clock is not set.
    """

    if deadline is _MISSING and transform_deadline is _MISSING:
        deadline = _Armed.deadline
        transform_deadline = _Armed.transform_deadline
    else:
        if deadline is _MISSING:
            deadline = None
        if transform_deadline is _MISSING:
            transform_deadline = None
    now = time.monotonic()
    if transform_deadline is not None and now >= transform_deadline:
        raise OptimizeBudgetError(
            "transform time budget exhausted (profile, restore, cancel, reuse). "
            "The unmodified circuit for this task was kept."
        )
    if deadline is not None and now >= deadline:
        raise OptimizeBudgetError(
            "time budget exhausted. The unmodified circuit for this task was kept."
        )
