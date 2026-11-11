"""Semantics-preserving kickmix rewrite, then a verifier gate.

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

What the official score charges, and what this gate does with that:

- invsqrt: ``Q * (Toffoli + T/4)``. Clifford ``Z_POW`` is free. A level-3
  ``Z_POW`` is one T. A finer ``Z_POW`` is priced from the remaining
  phase-error margin (synthesis), not from ``num_t_like``.
- dqi: ``R(ε) * Q² * T`` with ``T`` the Toffoli count (paper equation 43;
  FR-006 still open on ``R``). T gates and fine rotations are not in ``T``.
- dfthcsos: ``λ_eff * T * Q`` with ``T`` the Toffoli count (FR-007 still open
  on ``λ_eff``). ``submission.npz`` is copied, not rewritten.

Kickmix charges a conditional gate only on the shots where it fires, and
``Q`` is the largest qubit id plus one. This module cannot see the shot
mean, so the local weights are a static stand-in, not a score.

The run in issue #9 (``20261111T000307Z-0d076b2d``) cancelled Clifford pairs
and dropped the instruction count (dqi by about 1.1e6) while
``(toffoli_like, t_like, high_rotations)`` stayed put, so no file was
written and the verifier never scored the circuit. Those three counters
are not the verifier's key: Cliffords are free, and a fine rotation costs
more than a T. A structural shrink (fewer instructions) is now written and
scored. A rewrite that raises the task's static cost is not written.
Acceptance is still an authoritative PASS and a strictly lower JSON score.
"""

from __future__ import annotations

import bisect
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
_TASKS = ("invsqrt", "dqi", "dfthcsos")

# Integer stand-in for the published product. Toffoli = 4 so one T (T/4)
# is 1 and the kickmix "~20 T ≈ 4 Toffoli" fine-rotation stand-in is 16.
# Not a verifier score and not a leaderboard score.
_TOFFOLI_UNIT = 4
_T_UNIT = 1
_FINE_UNIT = 16


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
    task: str | None = None

    def as_dict(self) -> dict:
        return {
            "wrote": self.wrote,
            "reason": self.reason,
            "before": self.before,
            "after": self.after,
            "path": self.path,
            "stats": self.stats,
            "format": self.format,
            "task": self.task,
            "passes": list(_PASS_NAMES),
            "cost_model": _cost_model(self.task),
            "proxy_note": (
                "before/after include a static cost_units stand-in for the "
                "gates the official score charges, plus the instruction count. "
                "Neither number is a verifier score or a leaderboard score. "
                "A written file is kept only after the verifier PASS score is strictly lower."
            ),
        }


_PASS_NAMES = (
    "indexed_self_inverse_cancellation",
    "arithmetic_commutation",
    "deferred_z_rotation_merge",
    "store_overwrite",
    "empty_condition",
)


def _cost_model(task: str | None) -> str:
    if task == "dqi":
        return (
            "dqi charges R(eps) * Q^2 * Toffoli (paper equation 43; FR-006 is open on R). "
            "The local regression veto is the Toffoli count. T and fine rotations are not in T. "
            "Q stays at the source header width."
        )
    if task == "dfthcsos":
        return (
            "dfthcsos charges lambda_eff * Toffoli * Q (FR-007 is open on lambda_eff). "
            "The local regression veto is the Toffoli count. submission.npz is copied, not rewritten. "
            "Each angle file keeps its source header width."
        )
    return (
        "invsqrt charges Q * (Toffoli + T/4), and finer Z_POW angles are synthesis-priced. "
        "Local weights: Toffoli=4, level-3 Z_POW=1, level>=4 Z_POW=16 "
        "(16 is the kickmix 4-Toffoli synthesis stand-in, not a verifier score). "
        "Q stays at the source header width."
    )


def _cost_units(counts: GateCounts, task: str | None) -> int:
    """Static weight of the gates the named task's published cost charges.

    ``dqi`` and ``dfthcsos`` charge Toffolis, not T gates. ``invsqrt`` (and a
    task-less call) also charges level-3 and finer ``Z_POW``.
    """

    toffoli = _TOFFOLI_UNIT * counts.toffoli_like
    if task in {"dqi", "dfthcsos"}:
        return toffoli
    return toffoli + _T_UNIT * counts.t_like + _FINE_UNIT * counts.high_rotations


def should_materialize(before: GateCounts, after: GateCounts, task: str | None = None) -> bool:
    """Return whether the rewrite is worth an official verifier call.

    A strictly smaller instruction stream is a structural reduction and is
    written even when the cancelled gates are free Cliffords. A rewrite that
    raises the task's static cost is not written: the published formulas
    cannot score that as an improvement, and the verifier budget stays on
    the baseline. Equal size and equal cost writes nothing (FR-003).
    """

    if _cost_units(after, task) > _cost_units(before, task):
        return False
    if after.instructions < before.instructions:
        return True
    return _cost_units(after, task) < _cost_units(before, task)


def _payload(counts: GateCounts, task: str | None) -> dict:
    data = counts.as_dict()
    data["cost_units"] = _cost_units(counts, task)
    return data


def _check_task(task: str | None) -> None:
    if task is not None and task not in _TASKS:
        raise OptimizeBudgetError(f"unknown task {task}")


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


def peephole(
    ops: list[Op],
    window: int,
    stats: PassStats | None = None,
    task: str | None = None,
) -> list[Op]:
    """In-memory rewrite used by tests and by the kmx stream."""

    if window < 1:
        raise OptimizeBudgetError("window must be at least 1")
    _check_task(task)
    stats = stats or PassStats()
    emitted: list[Op] = []
    _rewrite_ops(
        ops,
        emitted.append,
        window=window,
        stats=stats,
        before=GateCounts(),
        deadline=None,
        task=task,
    )
    return emitted


def optimize_artifact(
    src: str,
    dst: str,
    *,
    window: int = 32,
    memory_budget_bytes: int = 2 * 1024**3,
    deadline: float | None = None,
    task: str | None = None,
) -> RewriteResult:
    """Write ``dst`` when the rewrite is a structural or cost reduction.

    ``src`` is never modified. ``dst`` is not created when the circuit does
    not shrink, the static cost rises, the file is not a circuit, or a
    budget trips. Acceptance of ``dst`` is not decided here.
    """

    if window < 1 or window > 4096:
        raise OptimizeBudgetError("window must be from 1 to 4096")
    _check_task(task)
    _assert_separate(src, dst)
    if not os.path.exists(src):
        return RewriteResult(False, f"missing source {src}", {}, {}, task=task)
    if os.path.isdir(src):
        return _optimize_directory(
            src,
            dst,
            window=window,
            memory_budget_bytes=memory_budget_bytes,
            deadline=deadline,
            task=task,
        )
    return _optimize_file(
        src,
        dst,
        window=window,
        memory_budget_bytes=memory_budget_bytes,
        deadline=deadline,
        task=task,
    )


def _optimize_file(
    src: str,
    dst: str,
    *,
    window: int,
    memory_budget_bytes: int,
    deadline: float | None,
    task: str | None,
) -> RewriteResult:
    kind = detect_format(src)
    if kind == "kmb":
        return _optimize_kmb(
            src,
            dst,
            window=window,
            memory_budget_bytes=memory_budget_bytes,
            deadline=deadline,
            task=task,
        )
    if kind == "kmx":
        return _optimize_kmx(
            src,
            dst,
            window=window,
            memory_budget_bytes=memory_budget_bytes,
            deadline=deadline,
            task=task,
        )
    return RewriteResult(
        False,
        f"{src} is not a kickmix circuit. It was not rewritten.",
        {},
        {},
        task=task,
    )


def _optimize_kmb(
    src: str,
    dst: str,
    *,
    window: int,
    memory_budget_bytes: int,
    deadline: float | None,
    task: str | None,
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
        seen = 0
        emitted_span = _Span()

        def ops():
            nonlocal seen
            for op in iter_kmb_ops(view):
                seen += 1
                if seen % 100_000 == 0:
                    _check_deadline(deadline)
                yield op

        def emit(op: Op) -> None:
            emitted_span.note(op)
            writer.emit(op)

        _rewrite_ops(
            ops(),
            emit,
            window=window,
            stats=stats,
            before=before,
            deadline=deadline,
            task=task,
        )
        # kickmix rejects a header whose qubit count is not max_id+1.
        # Two Z gates are identity and free, and they keep that id so Q
        # does not shrink when a cancelled gate was the only user.
        source_max = view.num_qubits - 1
        if source_max > emitted_span.max_qubit:
            pad = Op(name="Z", qubits=(source_max,))
            emit(pad)
            emit(pad)
        if seen != view.num_ops:
            raise KickmixFormatError(f"read {seen} operations, header says {view.num_ops}")
        _check_deadline(deadline)
        after = writer.counts
        if not should_materialize(before, after, task):
            writer.abort()
            _unlink(partial)
            return _refused(before, after, stats, "kmb", task)
        writer.close()
        os.replace(partial, dst)
        return _accepted(before, after, stats, dst, "kmb", task)
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
    task: str | None,
) -> RewriteResult:
    partial_handle = tempfile.NamedTemporaryFile(prefix="vqcc-kmx-", suffix=".kmx", delete=False)
    partial = partial_handle.name
    partial_handle.close()
    stats = PassStats()
    before = GateCounts()
    after = GateCounts()
    source_span = _Span()
    emitted_span = _Span()
    try:
        _check_deadline(deadline)

        def ops():
            for op in read_kmx_ops(src, memory_budget_bytes):
                source_span.note(op)
                yield op

        def emit(op: Op) -> None:
            emitted_span.note(op)
            _emit_kmx(handle, op, after)

        with open(partial, "w", encoding="utf-8", newline="\n") as handle:
            _rewrite_ops(
                ops(),
                emit,
                window=window,
                stats=stats,
                before=before,
                deadline=deadline,
                task=task,
            )
            # Keep Q = max qubit id + 1. Two Z gates are identity and free.
            if source_span.max_qubit > emitted_span.max_qubit:
                pad = Op(name="Z", qubits=(source_span.max_qubit,))
                emit(pad)
                emit(pad)
        _check_deadline(deadline)
        if not should_materialize(before, after, task):
            _unlink(partial)
            return _refused(before, after, stats, "kmx", task)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.replace(partial, dst)
        return _accepted(before, after, stats, dst, "kmx", task)
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
    task: str | None,
) -> RewriteResult:
    """Rewrite a dfthcsos-style directory. Non-circuits are copied byte for byte.

    A circuit file is rewritten when that file's own gate shrinks. The
    directory is kept when the summed circuit shrinks. ``submission.npz``
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
                    task=task,
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
        if not wrote_any or not should_materialize(before, after, task):
            _unlink_tree(partial)
            _prune_empty(os.path.dirname(partial))
            return _refused(before, after, stats, "directory", task)
        _unlink_tree(dst)
        os.replace(partial, dst)
        return _accepted(before, after, stats, dst, "directory", task)
    except Exception:
        _unlink_tree(partial)
        raise


def _refused(before: GateCounts, after: GateCounts, stats: PassStats, fmt: str, task: str | None) -> RewriteResult:
    if _cost_units(after, task) > _cost_units(before, task):
        reason = (
            "rewrite raised the verifier-aligned cost proxy. No candidate was written."
        )
    else:
        reason = (
            "rewrite did not reduce the instruction count or the verifier-aligned "
            "cost proxy. No candidate was written."
        )
    return RewriteResult(
        False,
        reason,
        _payload(before, task),
        _payload(after, task),
        stats=stats.as_dict(),
        format=fmt,
        task=task,
    )


def _accepted(
    before: GateCounts,
    after: GateCounts,
    stats: PassStats,
    path: str,
    fmt: str,
    task: str | None,
) -> RewriteResult:
    return RewriteResult(
        True,
        "rewrite shrank the circuit. The candidate is not retained until the verifier accepts a strictly lower score.",
        _payload(before, task),
        _payload(after, task),
        path=path,
        stats=stats.as_dict(),
        format=fmt,
        task=task,
    )


class _Span:
    def __init__(self) -> None:
        self.max_qubit = -1
        self.max_bit = -1

    def note(self, op: Op) -> None:
        if op.qubits:
            self.max_qubit = max(self.max_qubit, max(op.qubits))
        ids = list(op.bits)
        if op.condition is not None:
            ids.append(op.condition)
        if ids:
            self.max_bit = max(self.max_bit, max(ids))


class _Pending:
    """Single-qubit Z phases waiting to merge across gates they commute with.

    The phase is not held in the cancellation window, so two rotations on
    the same qubit merge at any distance until a non-commuting gate.
    """

    def __init__(self) -> None:
        self.angles: dict[tuple[int, int | None], int] = {}
        self.by_qubit: dict[int, set[tuple[int, int | None]]] = {}
        self.by_bit: dict[int, set[tuple[int, int | None]]] = {}

    def add(self, op: Op, stats: PassStats) -> None:
        angle = _phase_angle(op)
        if angle is None or len(op.qubits) != 1:
            return
        key = (op.qubits[0], op.condition)
        if key in self.angles:
            stats.merged_rotations += 1
            angle = (self.angles[key] + angle) % ANGLE_MOD
            if angle == 0:
                self._drop(key)
                stats.dropped_identity_rotations += 1
                return
            self.angles[key] = angle
            return
        self.angles[key] = angle
        self.by_qubit.setdefault(key[0], set()).add(key)
        if key[1] is not None:
            self.by_bit.setdefault(key[1], set()).add(key)

    def flush_blocked(self, op: Op) -> list[Op]:
        if op.name in _BARRIER:
            return self.flush_all()
        seen: set[tuple[int, int | None]] = set()
        keys: list[tuple[int, int | None]] = []
        for qubit in op.qubits:
            for key in self.by_qubit.get(qubit, ()):
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        for bit in _bits_of(op):
            for key in self.by_bit.get(bit, ()):
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        blocked = [key for key in keys if not _commutes(self._as_op(key), op)]
        blocked.sort(key=_phase_key)
        return [self._pop(key) for key in blocked]

    def flush_all(self) -> list[Op]:
        keys = sorted(self.angles, key=_phase_key)
        return [self._pop(key) for key in keys]

    def _as_op(self, key: tuple[int, int | None]) -> Op:
        qubit, condition = key
        angle = self.angles[key]
        if angle == Z_ANGLE:
            return Op(name="Z", qubits=(qubit,), condition=condition)
        return Op(name="Z_POW", qubits=(qubit,), condition=condition, angle=angle)

    def _pop(self, key: tuple[int, int | None]) -> Op:
        op = self._as_op(key)
        self._drop(key)
        return op

    def _drop(self, key: tuple[int, int | None]) -> None:
        self.angles.pop(key, None)
        qubit, condition = key
        bucket = self.by_qubit.get(qubit)
        if bucket is not None:
            bucket.discard(key)
            if not bucket:
                del self.by_qubit[qubit]
        if condition is not None:
            bits = self.by_bit.get(condition)
            if bits is not None:
                bits.discard(key)
                if not bits:
                    del self.by_bit[condition]


def _phase_key(key: tuple[int, int | None]) -> tuple[int, int]:
    qubit, condition = key
    return (qubit, -1 if condition is None else condition)


class _Hold:
    """Bounded window of gates that can still cancel or merge.

    Lookup walks only gates that share a qubit or bit, plus condition
    barriers. Disjoint gates commute and are not scanned, so a wide window
    stays cheap on a circuit whose gates are local.
    """

    def __init__(self, window: int) -> None:
        self.window = window
        self.ops: list[Op | None] = []
        self.start = 0
        self.live = 0
        self.qtouch: dict[int, list[int]] = {}
        self.btouch: dict[int, list[int]] = {}
        self.barriers: list[int] = []

    def push(self, op: Op, stats: PassStats) -> None:
        index = len(self.ops)
        self.ops.append(op)
        self.live += 1
        self._index(index, op)
        self._reduce(stats)

    def overflow(self) -> bool:
        return self.live > self.window

    def pop_front(self) -> Op:
        while self.start < len(self.ops) and self.ops[self.start] is None:
            self.start += 1
        if self.start >= len(self.ops) or self.ops[self.start] is None:
            raise KickmixFormatError("internal window underflow")
        op = self.ops[self.start]
        assert op is not None
        self.ops[self.start] = None
        self.start += 1
        self.live -= 1
        self._maybe_compact()
        return op

    def drain(self) -> list[Op]:
        emitted: list[Op] = []
        while self.live:
            emitted.append(self.pop_front())
        return emitted

    def _reduce(self, stats: PassStats) -> None:
        while self.live >= 2 and self._match_last(stats):
            pass

    def _match_last(self, stats: PassStats) -> bool:
        last = self._last_live()
        if last is None:
            return False
        current = self.ops[last]
        assert current is not None
        previous = self._prev_live(last)
        previous_op = None if previous is None else self.ops[previous]
        if (
            previous_op is not None
            and current.name == "POP_CONDITION"
            and previous_op.name == "PUSH_CONDITION"
        ):
            self._delete(last)
            self._delete(previous)
            stats.empty_conditions += 1
            return True
        cursor = last
        while True:
            earlier_index = self._next_relevant(current, cursor)
            if earlier_index is None:
                return False
            earlier = self.ops[earlier_index]
            assert earlier is not None
            if _cancels(earlier, current):
                self._delete(last)
                self._delete(earlier_index)
                stats.cancelled_pairs += 1
                return True
            merged = _try_merge(earlier, current)
            if merged is not _NO_MERGE:
                self._delete(last)
                if merged is None:
                    self._delete(earlier_index)
                else:
                    self.ops[earlier_index] = merged
                stats.merged_rotations += 1
                return True
            if _overwrites(current, earlier):
                self._delete(earlier_index)
                stats.store_overwrites += 1
                return True
            if earlier.name in _BARRIER or current.name in _BARRIER or not _commutes(earlier, current):
                return False
            cursor = earlier_index

    def _next_relevant(self, current: Op, before: int) -> int | None:
        best: int | None = None

        def consider(idx: int | None) -> None:
            nonlocal best
            if idx is None:
                return
            if best is None or idx > best:
                best = idx

        for qubit in current.qubits:
            consider(self._latest_before(self.qtouch.get(qubit), before))
        for bit in _bits_of(current):
            consider(self._latest_before(self.btouch.get(bit), before))
        consider(self._latest_before(self.barriers, before))
        return best

    def _latest_before(self, indices: list[int] | None, before: int) -> int | None:
        if not indices:
            return None
        position = bisect.bisect_left(indices, before) - 1
        while position >= 0:
            idx = indices[position]
            if idx >= self.start and self.ops[idx] is not None:
                return idx
            position -= 1
        return None

    def _last_live(self) -> int | None:
        index = len(self.ops) - 1
        while index >= self.start:
            if self.ops[index] is not None:
                return index
            index -= 1
        return None

    def _prev_live(self, index: int) -> int | None:
        cursor = index - 1
        while cursor >= self.start:
            if self.ops[cursor] is not None:
                return cursor
            cursor -= 1
        return None

    def _index(self, index: int, op: Op) -> None:
        for qubit in op.qubits:
            self.qtouch.setdefault(qubit, []).append(index)
        for bit in _bits_of(op):
            self.btouch.setdefault(bit, []).append(index)
        if op.name in _BARRIER:
            self.barriers.append(index)

    def _delete(self, index: int) -> None:
        if self.ops[index] is None:
            return
        self.ops[index] = None
        self.live -= 1

    def _maybe_compact(self) -> None:
        if self.start < self.window:
            return
        live = [op for op in self.ops[self.start :] if op is not None]
        self.ops = live
        self.start = 0
        self.live = len(live)
        self.qtouch.clear()
        self.btouch.clear()
        self.barriers.clear()
        for index, op in enumerate(live):
            self._index(index, op)


def _rewrite_ops(ops, emit, *, window: int, stats: PassStats, before: GateCounts, deadline, task: str | None) -> None:
    hold = _Hold(window)
    pending = _Pending()
    seen = 0

    def push(op: Op) -> None:
        hold.push(op, stats)
        while hold.overflow():
            emit(hold.pop_front())

    for op in ops:
        seen += 1
        if seen % 100_000 == 0:
            _check_deadline(deadline)
        before.add(op)
        reduced = normalize(op, stats)
        if reduced is None:
            continue
        if reduced.name in _PHASE and len(reduced.qubits) == 1:
            pending.add(reduced, stats)
            continue
        for flushed in pending.flush_blocked(reduced):
            push(flushed)
        push(reduced)
    for flushed in pending.flush_all():
        push(flushed)
    for op in hold.drain():
        emit(op)


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


def _overwrites(later: Op, earlier: Op) -> bool:
    if later.name not in {"BIT_STORE0", "BIT_STORE1"}:
        return False
    if earlier.name not in {"BIT_STORE0", "BIT_STORE1"}:
        return False
    return earlier.bits == later.bits and earlier.condition == later.condition


def _commutes(left: Op, right: Op) -> bool:
    """Kickmix commutation used to slide a cancellation or a phase.

    The extra rules were checked with kickmix 1.0.0 ``Simulator``, including
    the shot phase, on unconditional gates and on gates that share a
    condition bit:

    - ``X`` on the target commutes with ``CX`` and with ``CCX``. ``X`` on a
      control does not. ``X`` does not commute with ``CSWAP``.
    - ``Z`` / ``Z_POW`` on a control commutes with ``CX``, ``CCX``, and
      ``CSWAP``. The same phase on a target or a swapped qubit does not.
    - ``CX`` gates that share only a control, or only a target, commute.
    - ``CCX`` gates that share both controls and have different targets commute.
    - ``CZ`` on the two controls commutes with ``CCX``. ``CZ`` that touches
      the target does not. ``CCZ`` that covers both controls and not the
      target commutes with ``CCX``.
    - ``CX`` commutes with ``CZ`` on its control and a third qubit.

    Different conditions do not use these rules. Diagonal gates still commute
    with each other, and disjoint gates still commute.
    """

    if left.name in _BARRIER or right.name in _BARRIER:
        return False
    if left.name in _METADATA or right.name in _METADATA:
        return True
    if not _overlaps(left, right):
        return True
    if left.name in _DIAGONAL and right.name in _DIAGONAL:
        return True
    if left.condition != right.condition:
        return False
    return _commutes_matched(left, right) or _commutes_matched(right, left)


def _commutes_matched(perm: Op, other: Op) -> bool:
    if perm.name == "CX" and len(perm.qubits) == 2:
        control, target = perm.qubits
        if other.name == "X" and other.qubits == (target,):
            return True
        if other.name in _PHASE and other.qubits == (control,):
            return True
        if other.name == "CX" and len(other.qubits) == 2:
            ocontrol, otarget = other.qubits
            if ocontrol == control and otarget != target:
                return True
            if otarget == target and ocontrol != control:
                return True
        if other.name == "CZ" and target not in other.qubits and control in other.qubits:
            return True
        if other.name == "CCX" and len(other.qubits) == 3:
            controls = set(other.qubits[:2])
            ccx_target = other.qubits[2]
            if control in controls and target == ccx_target:
                return True
            if control in controls and target not in controls and target != ccx_target:
                return True
            if target == ccx_target and control not in controls and control != ccx_target:
                return True
        return False
    if perm.name == "CCX" and len(perm.qubits) == 3:
        controls = set(perm.qubits[:2])
        target = perm.qubits[2]
        if other.name == "X" and other.qubits == (target,):
            return True
        if other.name in _PHASE and len(other.qubits) == 1 and other.qubits[0] in controls:
            return True
        if other.name == "CCX" and len(other.qubits) == 3:
            if set(other.qubits[:2]) == controls and other.qubits[2] != target:
                return True
        if other.name == "CZ" and set(other.qubits) == controls:
            return True
        if other.name == "CCZ" and len(other.qubits) == 3:
            qubits = set(other.qubits)
            if controls <= qubits and target not in qubits:
                return True
        return False
    if perm.name == "CSWAP" and len(perm.qubits) == 3:
        control = perm.qubits[0]
        if other.name in _PHASE and other.qubits == (control,):
            return True
        return False
    return False


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
