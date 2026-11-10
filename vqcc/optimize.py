"""Semantics-preserving kickmix peephole, then a verifier gate.

Spec ``specs/001-noetl-pipeline/spec.md``:

- User story 2. A cheaper circuit for one task is kept only when that task's
  verifier accepts it. The other tasks stay untouched.
- FR-011. A candidate that fails verification is ineligible for the bundle,
  so a rejected proposal never becomes the retained artifact.
- FR-003. No circuit file is written unless this pass actually built one.
- FR-004. The number compared on acceptance is the official verifier JSON
  ``score``. Hub and paper formulas are not substituted for that score.
- FR-001 and FR-010. Each task is a separate artifact, checked by its own
  official verifier.

Lower is better. User story 2 asks for a cheaper circuit. The hub aggregate
is a ratio of reference cost over cost, so a smaller cost is the improvement.
``docs/wiki/Architecture.md`` records the same direction for the JSON score.
This module does not invent a dqi repetition factor, a dfthcsos lambda, or a
leaderboard aggregate (FR-006, FR-007, FR-008 stay unresolved).

The local ``(toffoli_like, t_like, high_rotations)`` key only decides whether
a rewrite is worth a verifier call. Toffoli-like gates are CCX, CCZ, and
CSWAP. T-like gates are Clifford-hierarchy level-3 Z_POW, which is kickmix
``num_t_like``. Level 4 and above are counted separately because kickmix does
not put them in ``num_t_like``. The key is not a task cost.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field

from vqcc.kickmix_file import (
    ANGLE_MOD,
    Z_ANGLE,
    GateCounts,
    KickmixFormatError,
    KmbWriter,
    Op,
    OptimizeBudgetError,
    _format_kmx,
    _parse_kmb,
    clifford_level,
    detect_format,
    iter_kmb_ops,
    open_kmb,
    read_kmx_ops,
)

# Gates that are their own inverse when the targets and condition match.
# CCX controls are unordered. CCZ and CZ and SWAP are fully symmetric.
# CSWAP's swapped pair is unordered. CX is ordered.
_SELF_INVERSE = {"X", "CX", "CCX", "Z", "CZ", "CCZ", "SWAP", "CSWAP", "NEG", "BIT_INVERT"}
_PHASE = {"Z", "Z_POW"}
_DIAGONAL = {"Z", "CZ", "CCZ", "Z_POW", "NEG"}
_METADATA = {"INFO_TAG", "DEBUG_PRINT", "REGISTER", "APPEND_TO_REGISTER"}
_BARRIER = {"PUSH_CONDITION", "POP_CONDITION"}
_NO_MERGE = object()


@dataclass(slots=True)
class PassStats:
    cancelled_pairs: int = 0
    merged_rotations: int = 0
    store_overwrites: int = 0
    empty_conditions: int = 0
    dropped_identity_rotations: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "cancelled_pairs": self.cancelled_pairs,
            "merged_rotations": self.merged_rotations,
            "store_overwrites": self.store_overwrites,
            "empty_conditions": self.empty_conditions,
            "dropped_identity_rotations": self.dropped_identity_rotations,
        }


@dataclass(slots=True)
class RewriteResult:
    wrote: bool
    reason: str
    before: dict
    after: dict
    path: str | None = None
    stats: dict = field(default_factory=dict)
    format: str | None = None

    def as_dict(self) -> dict:
        return {
            "wrote": self.wrote,
            "reason": self.reason,
            "before": self.before,
            "after": self.after,
            "path": self.path,
            "stats": self.stats,
            "format": self.format,
            "proxy_note": (
                "before/after are a local gate-count proxy, not a verifier score "
                "and not a leaderboard score"
            ),
        }


def normalize(op: Op, stats: PassStats | None = None) -> Op | None:
    """Drop an exact identity rotation and spell an exact Z as Z."""

    if op.name != "Z_POW" or op.angle is None:
        return op
    angle = op.angle % ANGLE_MOD
    if angle == 0:
        if stats is not None:
            stats.dropped_identity_rotations += 1
        return None
    if angle == Z_ANGLE:
        return Op(name="Z", qubits=op.qubits, condition=op.condition)
    if angle != op.angle:
        return Op(
            name="Z_POW",
            qubits=op.qubits,
            condition=op.condition,
            angle=angle,
        )
    return op


def reduce_window(window: list[Op], stats: PassStats) -> None:
    """Fold the newest operation into the window. Total work is O(n * window)."""

    while len(window) >= 2 and _match_last(window, stats):
        pass


def peephole(ops: list[Op], window: int, stats: PassStats | None = None) -> list[Op]:
    """In-memory peephole used by tests and by the kmx stream."""

    if window < 1:
        raise OptimizeBudgetError("window must be at least 1")
    stats = stats or PassStats()
    held: list[Op] = []
    emitted: list[Op] = []
    for op in ops:
        reduced = normalize(op, stats)
        if reduced is None:
            continue
        held.append(reduced)
        reduce_window(held, stats)
        while len(held) > window:
            emitted.append(held.pop(0))
    reduce_window(held, stats)
    emitted.extend(held)
    return emitted


def optimize_artifact(
    src: str,
    dst: str,
    *,
    window: int = 32,
    memory_budget_bytes: int = 2 * 1024**3,
    deadline: float | None = None,
) -> RewriteResult:
    """Write ``dst`` only when the peephole strictly improves the local proxy.

    ``src`` is never modified. ``dst`` is not created when the proxy does not
    improve, the file is not a circuit, or a budget trips.
    """

    if window < 1 or window > 4096:
        raise OptimizeBudgetError("window must be from 1 to 4096")
    _assert_separate(src, dst)
    if not os.path.exists(src):
        return RewriteResult(False, f"missing source {src}", {}, {})
    if os.path.isdir(src):
        return _optimize_directory(
            src,
            dst,
            window=window,
            memory_budget_bytes=memory_budget_bytes,
            deadline=deadline,
        )
    return _optimize_file(
        src,
        dst,
        window=window,
        memory_budget_bytes=memory_budget_bytes,
        deadline=deadline,
    )


def _optimize_file(
    src: str,
    dst: str,
    *,
    window: int,
    memory_budget_bytes: int,
    deadline: float | None,
) -> RewriteResult:
    kind = detect_format(src)
    if kind == "kmb":
        return _optimize_kmb(
            src,
            dst,
            window=window,
            memory_budget_bytes=memory_budget_bytes,
            deadline=deadline,
        )
    if kind == "kmx":
        return _optimize_kmx(
            src,
            dst,
            window=window,
            memory_budget_bytes=memory_budget_bytes,
            deadline=deadline,
        )
    return RewriteResult(
        False,
        f"{src} is not a kickmix circuit. It was not rewritten.",
        {},
        {},
    )


def _optimize_kmb(
    src: str,
    dst: str,
    *,
    window: int,
    memory_budget_bytes: int,
    deadline: float | None,
) -> RewriteResult:
    mapped, handle = open_kmb(src, memory_budget_bytes)
    partial = dst + ".partial"
    writer: KmbWriter | None = None
    stats = PassStats()
    before = GateCounts()
    try:
        _check_deadline(deadline)
        view = _parse_kmb(mapped)
        writer = KmbWriter(partial, view.registers)
        held: list[Op] = []
        seen = 0
        for op in iter_kmb_ops(view):
            seen += 1
            if seen % 100_000 == 0:
                _check_deadline(deadline)
            before.add(op)
            reduced = normalize(op, stats)
            if reduced is None:
                continue
            held.append(reduced)
            reduce_window(held, stats)
            while len(held) > window:
                writer.emit(held.pop(0))
        if seen != view.num_ops:
            raise KickmixFormatError(f"read {seen} operations, header says {view.num_ops}")
        reduce_window(held, stats)
        for op in held:
            writer.emit(op)
        _check_deadline(deadline)
        after = writer.counts
        if not _improved(before, after):
            writer.abort()
            _unlink(partial)
            return RewriteResult(
                False,
                "peephole did not reduce the local gate-count proxy. No candidate was written.",
                before.as_dict(),
                after.as_dict(),
                stats=stats.as_dict(),
                format="kmb",
            )
        writer.close()
        os.replace(partial, dst)
        return RewriteResult(
            True,
            "peephole reduced the local gate-count proxy. The candidate is not retained until the verifier accepts a lower score.",
            before.as_dict(),
            after.as_dict(),
            path=dst,
            stats=stats.as_dict(),
            format="kmb",
        )
    except Exception:
        if writer is not None:
            writer.abort()
        _unlink(partial)
        raise
    finally:
        if "view" in locals():
            view.release()
        mapped.close()
        handle.close()


def _optimize_kmx(
    src: str,
    dst: str,
    *,
    window: int,
    memory_budget_bytes: int,
    deadline: float | None,
) -> RewriteResult:
    partial_handle = tempfile.NamedTemporaryFile(prefix="vqcc-kmx-", suffix=".kmx", delete=False)
    partial = partial_handle.name
    partial_handle.close()
    stats = PassStats()
    before = GateCounts()
    after = GateCounts()
    held: list[Op] = []
    seen = 0
    try:
        _check_deadline(deadline)
        with open(partial, "w", encoding="utf-8", newline="\n") as handle:
            for op in read_kmx_ops(src, memory_budget_bytes):
                seen += 1
                if seen % 100_000 == 0:
                    _check_deadline(deadline)
                before.add(op)
                reduced = normalize(op, stats)
                if reduced is None:
                    continue
                held.append(reduced)
                reduce_window(held, stats)
                while len(held) > window:
                    _emit_kmx(handle, held.pop(0), after)
            reduce_window(held, stats)
            for op in held:
                _emit_kmx(handle, op, after)
        _check_deadline(deadline)
        if not _improved(before, after):
            _unlink(partial)
            return RewriteResult(
                False,
                "peephole did not reduce the local gate-count proxy. No candidate was written.",
                before.as_dict(),
                after.as_dict(),
                stats=stats.as_dict(),
                format="kmx",
            )
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.replace(partial, dst)
        return RewriteResult(
            True,
            "peephole reduced the local gate-count proxy. The candidate is not retained until the verifier accepts a lower score.",
            before.as_dict(),
            after.as_dict(),
            path=dst,
            stats=stats.as_dict(),
            format="kmx",
        )
    except Exception:
        _unlink(partial)
        raise


def _emit_kmx(handle, op: Op, after: GateCounts) -> None:
    after.add(op)
    handle.write(_format_kmx(op))
    handle.write("\n")


def _optimize_directory(
    src: str,
    dst: str,
    *,
    window: int,
    memory_budget_bytes: int,
    deadline: float | None,
) -> RewriteResult:
    """Rewrite a dfthcsos-style directory. Non-circuits are copied byte for byte.

    A circuit file is rewritten only when that file's own proxy improves.
    The directory is kept only when the summed proxy improves. ``submission.npz``
    is copied as a stream and is not opened as an array.
    """

    partial = dst + ".partial"
    _unlink_tree(partial)
    before = GateCounts()
    after = GateCounts()
    stats = PassStats()
    wrote_any = False
    try:
        for dirpath, _dirnames, filenames in os.walk(src):
            for name in filenames:
                _check_deadline(deadline)
                source = os.path.join(dirpath, name)
                relative = os.path.relpath(source, src)
                target = os.path.join(partial, relative)
                kind = detect_format(source)
                if kind is None:
                    _copy_stream(source, target)
                    continue
                file_result = _optimize_file(
                    source,
                    target,
                    window=window,
                    memory_budget_bytes=memory_budget_bytes,
                    deadline=deadline,
                )
                _add_dict(before, file_result.before)
                if file_result.wrote:
                    wrote_any = True
                    _add_dict(after, file_result.after)
                    _add_stats(stats, file_result.stats)
                else:
                    _copy_stream(source, target)
                    _add_dict(after, file_result.before or file_result.after)
                    _add_stats(stats, file_result.stats)
        if not wrote_any or not _key(after) < _key(before):
            _unlink_tree(partial)
            _prune_empty(os.path.dirname(partial))
            return RewriteResult(
                False,
                "peephole did not reduce the local gate-count proxy. No candidate was written.",
                before.as_dict(),
                after.as_dict(),
                stats=stats.as_dict(),
                format="directory",
            )
        _unlink_tree(dst)
        os.replace(partial, dst)
        return RewriteResult(
            True,
            "peephole reduced the local gate-count proxy of the directory. The candidate is not retained until the verifier accepts a lower score.",
            before.as_dict(),
            after.as_dict(),
            path=dst,
            stats=stats.as_dict(),
            format="directory",
        )
    except Exception:
        _unlink_tree(partial)
        raise


def _match_last(window: list[Op], stats: PassStats) -> bool:
    current = window[-1]
    last = len(window) - 1
    for earlier_index in range(last - 1, -1, -1):
        earlier = window[earlier_index]
        if _cancels(earlier, current):
            del window[last]
            del window[earlier_index]
            stats.cancelled_pairs += 1
            return True
        if (
            earlier_index == last - 1
            and earlier.name == "PUSH_CONDITION"
            and current.name == "POP_CONDITION"
        ):
            del window[last]
            del window[earlier_index]
            stats.empty_conditions += 1
            return True
        merged = _try_merge(earlier, current)
        if merged is not _NO_MERGE:
            del window[last]
            if merged is not None:
                window[earlier_index] = merged
            else:
                del window[earlier_index]
            stats.merged_rotations += 1
            return True
        if _overwrites(current, earlier):
            del window[earlier_index]
            stats.store_overwrites += 1
            return True
        if not _commutes(earlier, current):
            break
    return False


def _cancels(earlier: Op, current: Op) -> bool:
    if earlier.name not in _SELF_INVERSE or earlier.name != current.name:
        return False
    if earlier.condition != current.condition:
        return False
    return _same_targets(earlier, current)


def _same_targets(earlier: Op, current: Op) -> bool:
    name = earlier.name
    if name in {"CZ", "SWAP"}:
        return set(earlier.qubits) == set(current.qubits)
    if name == "CCZ":
        return set(earlier.qubits) == set(current.qubits)
    if name == "CCX":
        return (
            set(earlier.qubits[:2]) == set(current.qubits[:2])
            and earlier.qubits[2] == current.qubits[2]
        )
    if name == "CSWAP":
        return earlier.qubits[0] == current.qubits[0] and set(earlier.qubits[1:]) == set(
            current.qubits[1:]
        )
    return earlier.qubits == current.qubits and earlier.bits == current.bits


def _try_merge(earlier: Op, current: Op):
    if earlier.name not in _PHASE or current.name not in _PHASE:
        return _NO_MERGE
    if earlier.condition != current.condition:
        return _NO_MERGE
    if len(earlier.qubits) != 1 or earlier.qubits != current.qubits:
        return _NO_MERGE
    left = _phase_angle(earlier)
    right = _phase_angle(current)
    if left is None or right is None:
        return _NO_MERGE
    merged = (left + right) % ANGLE_MOD
    if not _merge_allowed(left, right, merged):
        return _NO_MERGE
    if merged == 0:
        return None
    if merged == Z_ANGLE:
        return Op(name="Z", qubits=earlier.qubits, condition=earlier.condition)
    return Op(
        name="Z_POW",
        qubits=earlier.qubits,
        condition=earlier.condition,
        angle=merged,
    )


def _phase_angle(op: Op) -> int | None:
    if op.name == "Z":
        return Z_ANGLE
    if op.name == "Z_POW" and op.angle is not None:
        return op.angle % ANGLE_MOD
    return None


def _rotation_weight(angle: int) -> tuple[int, int]:
    level = clifford_level(angle)
    if level is None or level <= 2:
        return (0, 0)
    if level == 3:
        return (1, 0)
    return (0, 1)


def _merge_allowed(left: int, right: int, merged: int) -> bool:
    """Refuse a fusion that adds a T-like gate or a level>=4 rotation."""

    t_left, h_left = _rotation_weight(left)
    t_right, h_right = _rotation_weight(right)
    t_merged, h_merged = _rotation_weight(merged)
    return t_merged <= t_left + t_right and h_merged <= h_left + h_right


def _overwrites(later: Op, earlier: Op) -> bool:
    if later.name not in {"BIT_STORE0", "BIT_STORE1"}:
        return False
    if earlier.name not in {"BIT_STORE0", "BIT_STORE1"}:
        return False
    return earlier.bits == later.bits and earlier.condition == later.condition


def _commutes(left: Op, right: Op) -> bool:
    if left.name in _BARRIER or right.name in _BARRIER:
        return False
    if left.name in _METADATA or right.name in _METADATA:
        return True
    if not _overlaps(left, right):
        return True
    return left.name in _DIAGONAL and right.name in _DIAGONAL


def _overlaps(left: Op, right: Op) -> bool:
    for qubit in left.qubits:
        if qubit in right.qubits:
            return True
    for bit in _bits_of(left):
        if bit in _bits_of(right):
            return True
    return False


def _bits_of(op: Op) -> tuple[int, ...]:
    if op.condition is None:
        return op.bits
    if op.condition in op.bits:
        return op.bits
    return op.bits + (op.condition,)


def _improved(before: GateCounts, after: GateCounts) -> bool:
    return after.key() < before.key()


def _key(counts: GateCounts) -> tuple[int, int, int]:
    return (counts.toffoli_like, counts.t_like, counts.high_rotations)


def _add_dict(total: GateCounts, part: dict) -> None:
    total.toffoli_like += int(part.get("toffoli_like") or 0)
    total.t_like += int(part.get("t_like") or 0)
    total.high_rotations += int(part.get("high_rotations") or 0)
    total.instructions += int(part.get("instructions") or 0)


def _add_stats(total: PassStats, part: dict) -> None:
    total.cancelled_pairs += int(part.get("cancelled_pairs") or 0)
    total.merged_rotations += int(part.get("merged_rotations") or 0)
    total.store_overwrites += int(part.get("store_overwrites") or 0)
    total.empty_conditions += int(part.get("empty_conditions") or 0)
    total.dropped_identity_rotations += int(part.get("dropped_identity_rotations") or 0)


def _assert_separate(src: str, dst: str) -> None:
    src_real = os.path.realpath(src)
    dst_real = os.path.realpath(dst)
    if src_real == dst_real:
        raise KickmixFormatError("refusing to overwrite the source circuit")
    if src_real.startswith(dst_real + os.sep) or dst_real.startswith(src_real + os.sep):
        raise KickmixFormatError("refusing to write a candidate inside the source artifact")


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise OptimizeBudgetError("time budget exhausted. No candidate was written.")


def _unlink(path: str) -> None:
    if os.path.isfile(path):
        os.unlink(path)


def _prune_empty(path: str) -> None:
    """Remove an empty proposal directory and an empty proposals directory.

    Stops after two levels so a run directory is never removed.
    """

    current = path
    for _ in range(2):
        if not current or not os.path.isdir(current) or os.listdir(current):
            break
        os.rmdir(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def _unlink_tree(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.isfile(path):
        os.unlink(path)


def _copy_stream(src: str, dst: str) -> None:
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(src, "rb") as source, open(dst, "wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
