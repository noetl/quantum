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

The run in issue #9 cancelled Clifford pairs and left the charged counts
unchanged, so no file was written. A later gate wrote those shorter
circuits. Kaggle version 7 (issue #9, run ``20261111T052032Z-e1a4aedc``)
then scored them: the verifier passed and the JSON scores did not move,
because the deleted gates were Cliffords. This module no longer sends a
candidate whose charged weight and qubit count are unchanged.

A clean Toffoli uncompute whose target was used in between does not
commute, so the cancellation horizon cannot see it. Kickmix's own
``del_and`` replaces that uncompute with ``HMR`` plus a ``CZ`` conditioned
on the measurement bit. The replacement is applied only when the target
is known to have been ``|0>`` before the compute (unnamed scratch when the
file has registers, or a qubit just reset by ``R`` or ``HMR``). Named
register qubits are not assumed to start at ``|0>``.

Two further rewrites use that same ``|0>`` proof.

- Shared-control factoring. While a clean AND is still stored on its
  target, a later ``CCX`` with the same controls and a different target
  is the same XOR. It is replaced by ``CX`` from the AND target. Kickmix
  idioms usually copy with ``CX`` already; the rewrite fires only when a
  second ``CCX`` is still present.
- Qubit lifetime compaction. Scratch wires whose lifetimes are split by
  an unconditional ``R`` or ``HMR`` can share a physical id that is known
  ``|0>``. Named register ids are never renumbered and are never given
  to scratch. The pass is off when the file has no quantum register,
  because the system qubits cannot be told from scratch. A wire rename
  is constant for one lifetime, so ``SWAP`` and ``CSWAP`` are renamed
  like any other gate.
"""

from __future__ import annotations

import bisect
import heapq
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field

from vqcc.profile import StructureProfiler
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
    Q1_0,
    Q2_0,
    Q2_1,
    Q3_0,
    Q3_1,
    Q3_2,
    detect_format,
    iter_kmb_ops,
    open_kmb,
    read_kmx_ops,
    register_ids,
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
    and_uncomputes: int = 0
    clean_and_opens: int = 0
    shared_control_factors: int = 0
    qubit_reuses: int = 0
    qubit_relabels: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "cancelled_pairs": self.cancelled_pairs,
            "merged_rotations": self.merged_rotations,
            "store_overwrites": self.store_overwrites,
            "empty_conditions": self.empty_conditions,
            "dropped_identity_rotations": self.dropped_identity_rotations,
            "and_uncomputes": self.and_uncomputes,
            "clean_and_opens": self.clean_and_opens,
            "shared_control_factors": self.shared_control_factors,
            "qubit_reuses": self.qubit_reuses,
            "qubit_relabels": self.qubit_relabels,
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
    profile: dict = field(default_factory=dict)

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
            "structure": self.profile,
            "passes": list(_PASS_NAMES),
            "cost_model": _cost_model(self.task),
            "proxy_note": (
                "before/after include a static cost_units stand-in for the "
                "gates the official score charges, the instruction count, and "
                "the qubit count. None of these is a verifier score or a "
                "leaderboard score. "
                "A written file is kept only after the verifier PASS score is strictly lower."
            ),
        }


_PASS_NAMES = (
    "indexed_self_inverse_cancellation",
    "arithmetic_commutation",
    "measurement_and_uncompute",
    "shared_control_toffoli_factor",
    "qubit_lifetime_reuse",
    "deferred_z_rotation_merge",
    "store_overwrite",
    "empty_condition",
)


def _cost_model(task: str | None) -> str:
    if task == "dqi":
        return (
            "dqi charges R(eps) * Q^2 * Toffoli (paper equation 43; FR-006 is open on R). "
            "The local regression veto is the Toffoli count. T and fine rotations are not in T. "
            "Q is the highest qubit id still named or used. A freed scratch id is not padded."
        )
    if task == "dfthcsos":
        return (
            "dfthcsos charges lambda_eff * Toffoli * Q (FR-007 is open on lambda_eff). "
            "The local regression veto is the Toffoli count. submission.npz is copied, not rewritten. "
            "Each angle file's Q is the highest id still named or used."
        )
    return (
        "invsqrt charges Q * (Toffoli + T/4), and finer Z_POW angles are synthesis-priced. "
        "Local weights: Toffoli=4, level-3 Z_POW=1, level>=4 Z_POW=16 "
        "(16 is the kickmix 4-Toffoli synthesis stand-in, not a verifier score). "
        "Q is the highest qubit id still named or used. A freed scratch id is not padded."
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


def should_materialize(
    before: GateCounts,
    after: GateCounts,
    task: str | None = None,
    *,
    qubits_before: int | None = None,
    qubits_after: int | None = None,
) -> bool:
    """Return whether the rewrite is worth an official verifier call.

    The published scores charge Toffoli count, and for invsqrt also T and
    fine ``Z_POW``. ``Q`` multiplies every task and is squared for dqi.
    Kaggle version 7 showed that a shorter instruction stream of free
    Cliffords does not move the JSON score, so that case is not written
    (FR-003, FR-004). A higher charged weight or a wider header is not
    written. A lower charged weight or a smaller qubit count is written.
    """

    if _cost_units(after, task) > _cost_units(before, task):
        return False
    if qubits_before is not None and qubits_after is not None and qubits_after > qubits_before:
        return False
    if _cost_units(after, task) < _cost_units(before, task):
        return True
    if qubits_before is not None and qubits_after is not None and qubits_after < qubits_before:
        return True
    return False


def _payload(counts: GateCounts, task: str | None, qubits: int | None = None) -> dict:
    data = counts.as_dict()
    data["cost_units"] = _cost_units(counts, task)
    if qubits is not None:
        data["qubits"] = qubits
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


def _value_writes(op: Op) -> set[int]:
    """Qubits whose computational bit this op can change."""

    if op.name == "X" and op.qubits:
        return {op.qubits[0]}
    if op.name == "CX" and len(op.qubits) == 2:
        return {op.qubits[1]}
    if op.name == "CCX" and len(op.qubits) == 3:
        return {op.qubits[2]}
    if op.name == "SWAP" and len(op.qubits) == 2:
        return {op.qubits[0], op.qubits[1]}
    if op.name == "CSWAP" and len(op.qubits) == 3:
        return {op.qubits[1], op.qubits[2]}
    if op.name in {"R", "HMR"} and op.qubits:
        return {op.qubits[0]}
    return set()


def _bit_writes(op: Op) -> set[int]:
    if op.name in {"BIT_STORE0", "BIT_STORE1", "BIT_INVERT"} and op.bits:
        return {op.bits[0]}
    if op.name == "HMR" and op.bits:
        return {op.bits[0]}
    return set()


class _OpenAnd:
    __slots__ = ("target", "order", "controls", "stack", "explicit", "blocked", "born")

    def __init__(self, target: int, order: tuple[int, int], stack: tuple[int, ...], explicit: int | None, born: int) -> None:
        self.target = target
        self.order = order
        self.controls = frozenset(order)
        self.stack = stack
        self.explicit = explicit
        self.blocked = False
        self.born = born

    def as_op(self) -> Op:
        return Op(name="CCX", qubits=(self.order[0], self.order[1], self.target), condition=self.explicit)

    def condition_bits(self) -> set[int]:
        bits = set(self.stack)
        if self.explicit is not None:
            bits.add(self.explicit)
        return bits


class _AndTracker:
    """Replace a clean Toffoli uncompute with HMR and a conditional CZ.

    The compute CCX stays. The matching uncompute is rewritten only when
    the target still holds the AND (no bit-flip on the controls or the
    target) and either some intervening gate does not commute with the
    CCX, or the pair is farther apart than the cancellation horizon. A
    pair the horizon can still cancel is left alone, because deleting
    both Toffolis is cheaper than replacing one of them.
    """

    def __init__(
        self,
        *,
        named: set[int],
        has_registers: bool,
        fresh_bit: int,
        window: int,
        stats: PassStats,
    ) -> None:
        self.named = named
        self.has_registers = has_registers
        self.fresh_bit = fresh_bit
        self.window = window
        self.stats = stats
        self.stack: list[int] = []
        self.open: dict[int, _OpenAnd] = {}
        self.by_q: dict[int, set[int]] = {}
        self.proven_zero: set[int] = set()
        self.proven_dirty: set[int] = set()
        self.steps = 0

    def feed(self, op: Op) -> list[Op]:
        self.steps += 1
        if op.name == "PUSH_CONDITION":
            if op.condition is not None:
                self.stack.append(op.condition)
            return [op]
        if op.name == "POP_CONDITION":
            if self.stack:
                self.stack.pop()
            depth = len(self.stack)
            for target, rec in list(self.open.items()):
                if len(rec.stack) > depth:
                    self._kill_dirty(target)
            return [op]
        if op.name == "CCX" and len(op.qubits) == 3:
            rewritten = self._try_uncompute(op)
            if rewritten is not None:
                return rewritten
            factored = self._try_factor(op)
            if factored is not None:
                return factored
            self._touch(op)
            if self._can_open(op):
                self._open(op)
            else:
                self._kill_dirty(op.qubits[2])
            return [op]
        self._touch(op)
        if op.name in {"R", "HMR"} and op.qubits:
            self._mark_zero(op.qubits[0])
        else:
            for qubit in _value_writes(op):
                self._kill_dirty(qubit)
        return [op]

    def _is_zero(self, qubit: int) -> bool:
        if qubit in self.open or qubit in self.proven_dirty:
            return False
        if qubit in self.proven_zero:
            return True
        return self.has_registers and qubit not in self.named

    def _can_open(self, op: Op) -> bool:
        if len(self.open) >= 100_000:
            return False
        control_a, control_b, target = op.qubits
        if len({control_a, control_b, target}) < 3:
            return False
        if not self._is_zero(target):
            return False
        for control in (control_a, control_b):
            if len(self.by_q.get(control, ())) >= 64:
                return False
        return True

    def _open(self, op: Op) -> None:
        control_a, control_b, target = op.qubits
        rec = _OpenAnd(
            target,
            (control_a, control_b),
            tuple(self.stack),
            op.condition,
            self.steps,
        )
        self.open[target] = rec
        self.stats.clean_and_opens += 1
        self.proven_dirty.add(target)
        self.proven_zero.discard(target)
        for qubit in (control_a, control_b, target):
            self.by_q.setdefault(qubit, set()).add(target)

    def _try_uncompute(self, op: Op) -> list[Op] | None:
        target = op.qubits[2]
        rec = self.open.get(target)
        if rec is None:
            return None
        if frozenset(op.qubits[:2]) != rec.controls:
            return None
        if rec.explicit != op.condition or rec.stack != tuple(self.stack):
            return None
        gap = self.steps - rec.born
        if not rec.blocked and gap <= self.window:
            self._mark_zero(target)
            return [op]
        order = rec.order
        self._mark_zero(target)
        self.stats.and_uncomputes += 1
        fresh = self.fresh_bit
        hmr = Op(name="HMR", qubits=(target,), bits=(fresh,), condition=op.condition)
        store = Op(name="BIT_STORE0", bits=(fresh,))
        fix = Op(name="CZ", qubits=order, condition=fresh)
        return [store, hmr, fix]

    def _try_factor(self, op: Op) -> list[Op] | None:
        """Replace a second CCX of a live clean AND with CX from that AND.

        The open target still holds the control AND, so XORing it into the
        new target is the same operation as another CCX. The open record
        stays. The new target is marked dirty.
        """

        control_a, control_b, target = op.qubits
        if control_a == control_b or target in (control_a, control_b):
            return None
        controls = frozenset((control_a, control_b))
        left = self.by_q.get(control_a)
        right = self.by_q.get(control_b)
        if not left or not right:
            return None
        stack = tuple(self.stack)
        chosen: _OpenAnd | None = None
        for candidate in left:
            if candidate == target or candidate not in right:
                continue
            record = self.open.get(candidate)
            if record is None or record.controls != controls:
                continue
            if record.explicit != op.condition or record.stack != stack:
                continue
            chosen = record
            break
        if chosen is None:
            return None
        self.stats.shared_control_factors += 1
        copied = Op(name="CX", qubits=(chosen.target, target), condition=op.condition)
        return self._emit_instead(copied)

    def _emit_instead(self, op: Op) -> list[Op]:
        self._touch(op)
        if op.name in {"R", "HMR"} and op.qubits:
            self._mark_zero(op.qubits[0])
        else:
            for qubit in _value_writes(op):
                self._kill_dirty(qubit)
        return [op]

    def _touch(self, op: Op) -> None:
        seen: set[int] = set()
        targets: list[int] = []
        for qubit in op.qubits:
            for target in self.by_q.get(qubit, ()):
                if target not in seen:
                    seen.add(target)
                    targets.append(target)
        written_bits = _bit_writes(op)
        resets = {op.qubits[0]} if op.name in {"R", "HMR"} and op.qubits else set()
        for target in targets:
            rec = self.open.get(target)
            if rec is None:
                continue
            if written_bits & rec.condition_bits():
                self._kill_dirty(target)
                continue
            changed = _value_writes(op) & (rec.controls | {rec.target})
            if changed:
                # The AND value moved or was overwritten. Drop the record,
                # then record the new bit on every qubit this op writes.
                self._drop(target)
                for qubit in changed:
                    if qubit in resets:
                        self.proven_dirty.discard(qubit)
                        self.proven_zero.add(qubit)
                    else:
                        self.proven_zero.discard(qubit)
                        self.proven_dirty.add(qubit)
                continue
            if not _commutes(rec.as_op(), op):
                rec.blocked = True

    def _mark_zero(self, qubit: int) -> None:
        self._drop(qubit)
        self.proven_dirty.discard(qubit)
        self.proven_zero.add(qubit)

    def _kill_dirty(self, qubit: int) -> None:
        self._drop(qubit)
        self.proven_zero.discard(qubit)
        self.proven_dirty.add(qubit)

    def _drop(self, target: int) -> None:
        rec = self.open.pop(target, None)
        if rec is None:
            return
        for qubit in rec.controls | {rec.target}:
            bucket = self.by_q.get(qubit)
            if bucket is None:
                continue
            bucket.discard(target)
            if not bucket:
                del self.by_q[qubit]


def peephole(
    ops: list[Op],
    window: int,
    stats: PassStats | None = None,
    task: str | None = None,
    *,
    named_qubits: set[int] | None = None,
    fresh_bit: int | None = None,
) -> list[Op]:
    """In-memory rewrite used by tests and by the kmx stream."""

    if window < 1:
        raise OptimizeBudgetError("window must be at least 1")
    _check_task(task)
    stats = stats or PassStats()
    named = set(named_qubits or ())
    if fresh_bit is None:
        fresh_bit = 0
        for op in ops:
            for bit in _bits_of(op):
                if bit + 1 > fresh_bit:
                    fresh_bit = bit + 1
    used: set[int] = set()
    highest = -1
    for op in ops:
        if op.qubits:
            used.update(op.qubits)
            highest = max(highest, max(op.qubits))
    if named:
        highest = max(highest, max(named))
    emitted: list[Op] = []
    _rewrite_ops(
        ops,
        emitted.append,
        window=window,
        stats=stats,
        before=GateCounts(),
        deadline=None,
        task=task,
        named_qubits=named,
        has_registers=bool(named),
        fresh_bit=fresh_bit,
        used_ids=used,
        header_qubits=None if highest < 0 else highest + 1,
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


def _qubit_width(max_id: int, named: set[int]) -> int:
    """Header width kickmix requires: one past the highest id."""

    if named:
        max_id = max(max_id, max(named))
    if max_id < 0:
        return 0
    return max_id + 1


def _start_profiler(
    named: set[int],
    has_registers: bool,
    *,
    header_qubits: int | None,
    header_bits: int | None,
) -> StructureProfiler:
    if not has_registers:
        blocked = "no_registers"
    elif not named:
        blocked = "no_named_qubits"
    else:
        blocked = None
    return StructureProfiler(
        named=named,
        has_registers=has_registers,
        header_qubits=header_qubits,
        header_bits=header_bits,
        reuse_blocked=blocked,
    )


def _register_scope(registers: list[bytes], num_bits: int) -> tuple[set[int], int]:
    named: set[int] = set()
    max_bit = num_bits - 1
    for payload in registers:
        qubits, bits = register_ids(payload)
        named |= qubits
        if bits:
            max_bit = max(max_bit, max(bits))
    return named, max_bit + 1


def _scan_kmx_scope(src: str, memory_budget_bytes: int) -> tuple[set[int], int, bool, set[int]]:
    named: set[int] = set()
    used: set[int] = set()
    max_bit = -1
    has_registers = False
    for op in read_kmx_ops(src, memory_budget_bytes):
        if op.name in {"REGISTER", "APPEND_TO_REGISTER"}:
            has_registers = True
        if op.name == "APPEND_TO_REGISTER" and op.qubits:
            named.add(op.qubits[0])
        if op.qubits:
            used.update(op.qubits)
        for bit in _bits_of(op):
            if bit > max_bit:
                max_bit = bit
    return named, max_bit + 1, has_registers, used


def _used_qubit_ids(view) -> set[int]:
    """Qubit ids named by a kmb operand column. This does not build Op objects."""

    found: set[int] = set()
    for key in (Q1_0, Q2_0, Q2_1, Q3_0, Q3_1, Q3_2):
        column = view.columns.get(key)
        if not column:
            continue
        buffer = memoryview(column)
        try:
            found.update(buffer.cast("I"))
        except (TypeError, ValueError):
            for offset in range(0, len(buffer) - 3, 4):
                found.add(int.from_bytes(buffer[offset : offset + 4], "little"))
    return found


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

        named, fresh_bit = _register_scope(view.registers, view.num_bits)
        used_ids = _used_qubit_ids(view) | named
        header = view.num_qubits
        if used_ids:
            header = max(header, max(used_ids) + 1)
        profiler = _start_profiler(
            named,
            bool(view.registers),
            header_qubits=view.num_qubits,
            header_bits=view.num_bits,
        )
        _rewrite_ops(
            ops(),
            emit,
            window=window,
            stats=stats,
            before=before,
            deadline=deadline,
            task=task,
            named_qubits=named,
            has_registers=bool(view.registers),
            fresh_bit=fresh_bit,
            profiler=profiler,
            used_ids=used_ids,
            header_qubits=header,
        )
        profile = profiler.finish()
        # Q is max qubit id + 1, including ids named by a register. A scratch
        # id that no longer appears is not padded back: the published costs
        # multiply by Q, and a named register still pins its own ids.
        if seen != view.num_ops:
            raise KickmixFormatError(f"read {seen} operations, header says {view.num_ops}")
        _check_deadline(deadline)
        after = writer.counts
        qubits_before = view.num_qubits
        qubits_after = _qubit_width(emitted_span.max_qubit, named)
        if not should_materialize(
            before, after, task, qubits_before=qubits_before, qubits_after=qubits_after
        ):
            writer.abort()
            _unlink(partial)
            return _refused(before, after, stats, "kmb", task, qubits_before, qubits_after, profile)
        writer.close()
        os.replace(partial, dst)
        return _accepted(before, after, stats, dst, "kmb", task, qubits_before, qubits_after, profile)
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
    named, fresh_bit, has_registers, used_ids = _scan_kmx_scope(src, memory_budget_bytes)
    try:
        _check_deadline(deadline)

        def ops():
            for op in read_kmx_ops(src, memory_budget_bytes):
                source_span.note(op)
                yield op

        def emit(op: Op) -> None:
            emitted_span.note(op)
            _emit_kmx(handle, op, after)

        profiler = _start_profiler(named, has_registers, header_qubits=None, header_bits=None)
        with open(partial, "w", encoding="utf-8", newline="\n") as handle:
            _rewrite_ops(
                ops(),
                emit,
                window=window,
                stats=stats,
                before=before,
                deadline=deadline,
                task=task,
                named_qubits=named,
                has_registers=has_registers,
                fresh_bit=fresh_bit,
                profiler=profiler,
                used_ids=used_ids | named,
                header_qubits=(max(used_ids | named) + 1) if (used_ids or named) else 0,
            )
        _check_deadline(deadline)
        qubits_before = _qubit_width(source_span.max_qubit, named)
        qubits_after = _qubit_width(emitted_span.max_qubit, named)
        profiler.header_qubits = qubits_before
        profile = profiler.finish()
        if not should_materialize(
            before, after, task, qubits_before=qubits_before, qubits_after=qubits_after
        ):
            _unlink(partial)
            return _refused(before, after, stats, "kmx", task, qubits_before, qubits_after, profile)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.replace(partial, dst)
        return _accepted(before, after, stats, dst, "kmx", task, qubits_before, qubits_after, profile)
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
    qubits_before = 0
    qubits_after = 0
    sum_before = 0
    sum_after = 0
    profiles: list[dict] = []
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
                file_before_q = int((file_result.before or {}).get("qubits") or 0)
                file_after_q = int((file_result.after or {}).get("qubits") or 0)
                if not file_result.wrote:
                    file_after_q = file_before_q
                qubits_before = max(qubits_before, file_before_q)
                qubits_after = max(qubits_after, file_after_q)
                sum_before += file_before_q
                sum_after += file_after_q
                if file_result.profile:
                    profiles.append(
                        {
                            "path": relative,
                            "wrote": file_result.wrote,
                            "qubits": file_result.profile.get("qubits"),
                            "toffoli": file_result.profile.get("toffoli"),
                            "resets": file_result.profile.get("resets"),
                            "registers": file_result.profile.get("registers"),
                        }
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
        directory_profile = {
            "directory": True,
            "not_a_score": True,
            "qubit_width_max_before": qubits_before,
            "qubit_width_max_after": qubits_after,
            "qubit_width_sum_before": sum_before,
            "qubit_width_sum_after": sum_after,
            "files": profiles,
        }
        if not wrote_any or not _directory_worth(
            before,
            after,
            task,
            max_before=qubits_before,
            max_after=qubits_after,
            sum_before=sum_before,
            sum_after=sum_after,
        ):
            _unlink_tree(partial)
            _prune_empty(os.path.dirname(partial))
            return _refused(
                before, after, stats, "directory", task, qubits_before, qubits_after, directory_profile
            )
        _unlink_tree(dst)
        os.replace(partial, dst)
        return _accepted(
            before, after, stats, dst, "directory", task, qubits_before, qubits_after, directory_profile
        )
    except Exception:
        _unlink_tree(partial)
        raise


def _directory_worth(
    before: GateCounts,
    after: GateCounts,
    task: str | None,
    *,
    max_before: int,
    max_after: int,
    sum_before: int,
    sum_after: int,
) -> bool:
    """A dfthcsos directory is worth a verifier call when weight or width drops.

    The official ``Q`` is not the per-file header (version 7 printed 730
    while each angle file was width 119). A drop in the sum of file widths
    is still sent, and a wider file is not. The verifier score decides
    whether that candidate is kept.
    """

    if _cost_units(after, task) > _cost_units(before, task):
        return False
    if max_after > max_before or sum_after > sum_before:
        return False
    if _cost_units(after, task) < _cost_units(before, task):
        return True
    if max_after < max_before or sum_after < sum_before:
        return True
    return False


def _refused(
    before: GateCounts,
    after: GateCounts,
    stats: PassStats,
    fmt: str,
    task: str | None,
    qubits_before: int | None = None,
    qubits_after: int | None = None,
    profile: dict | None = None,
) -> RewriteResult:
    if _cost_units(after, task) > _cost_units(before, task):
        reason = (
            "rewrite raised the verifier-aligned cost proxy. No candidate was written."
        )
    elif (
        qubits_before is not None
        and qubits_after is not None
        and qubits_after > qubits_before
    ):
        reason = "rewrite raised the qubit count. No candidate was written."
    else:
        reason = (
            "rewrite did not lower the charged gate weight or the qubit count. "
            "No candidate was written."
        )
    return RewriteResult(
        False,
        reason,
        _payload(before, task, qubits_before),
        _payload(after, task, qubits_after),
        stats=stats.as_dict(),
        format=fmt,
        task=task,
        profile=profile or {},
    )


def _accepted(
    before: GateCounts,
    after: GateCounts,
    stats: PassStats,
    path: str,
    fmt: str,
    task: str | None,
    qubits_before: int | None = None,
    qubits_after: int | None = None,
    profile: dict | None = None,
) -> RewriteResult:
    return RewriteResult(
        True,
        "rewrite lowered the charged gate weight or the qubit count. The candidate is not retained until the verifier accepts a strictly lower score.",
        _payload(before, task, qubits_before),
        _payload(after, task, qubits_after),
        path=path,
        stats=stats.as_dict(),
        format=fmt,
        task=task,
        profile=profile or {},
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


class _LifetimeMap:
    """Rename scratch wires onto ids that are known to be ``|0>``.

    A lifetime is the stretch between unconditional resets. The physical
    id is fixed for that stretch, which is why ``SWAP`` and ``CSWAP`` are
    ordinary renamed gates. Named register ids stay on themselves and are
    never placed in the free set.

    An id is a hole only when the pre-scan did not see it and it is not a
    named register. Ids that show up later in the circuit are not holes,
    so a wire keeps its own id until a reset frees some other id. That is
    what makes a dense circuit stay put, and what lets a high scratch id
    fall into a real gap or onto a qubit that ``R`` / ``HMR`` has cleared.

    The pass is disabled without a named quantum register. System qubits
    and scratch cannot be separated from the op stream alone, and moving
    a system id fails the verifier.
    """

    def __init__(
        self,
        named: set[int],
        enabled: bool,
        stats: PassStats,
        *,
        used: set[int] | None = None,
        header: int | None = None,
    ) -> None:
        self.named = named
        self.enabled = enabled
        self.stats = stats
        self.map: dict[int, int] = {}
        self.occupied: set[int] = set()
        self.recycled: list[int] = []
        self.holes: list[int] = []
        self.stack = 0
        if enabled and header is not None and used is not None:
            for qubit in range(header):
                if qubit not in named and qubit not in used:
                    self.holes.append(qubit)
            heapq.heapify(self.holes)

    def apply(self, op: Op) -> Op:
        if not self.enabled:
            return op
        if op.name == "PUSH_CONDITION":
            self.stack += 1
            return op
        if op.name == "POP_CONDITION":
            if self.stack:
                self.stack -= 1
            return op
        if not op.qubits:
            return op
        qubits = tuple(self._wire(qubit) for qubit in op.qubits)
        mapped = Op(
            name=op.name,
            qubits=qubits,
            bits=op.bits,
            condition=op.condition,
            angle=op.angle,
            info=op.info,
            quote=op.quote,
            register=op.register,
        )
        if self._hard_reset(op):
            self._free(op.qubits[0])
        return mapped

    def _hard_reset(self, op: Op) -> bool:
        return (
            op.name in {"R", "HMR"}
            and bool(op.qubits)
            and op.qubits[0] not in self.named
            and op.condition is None
            and self.stack == 0
        )

    def _wire(self, qubit: int) -> int:
        if qubit in self.named:
            return qubit
        current = self.map.get(qubit)
        if current is not None:
            return current
        physical, kind = self._alloc(qubit)
        self.map[qubit] = physical
        self.occupied.add(physical)
        if kind == "recycled":
            self.stats.qubit_reuses += 1
        elif kind == "hole":
            self.stats.qubit_relabels += 1
        return physical

    def _alloc(self, qubit: int) -> tuple[int, str]:
        self._drop_stale(self.recycled)
        self._drop_stale(self.holes)
        recycled = self.recycled[0] if self.recycled else None
        hole = self.holes[0] if self.holes else None
        if recycled is not None and recycled < qubit and (hole is None or recycled <= hole):
            return heapq.heappop(self.recycled), "recycled"
        if hole is not None and hole < qubit:
            return heapq.heappop(self.holes), "hole"
        if qubit not in self.occupied and qubit not in self.named:
            # A reset of this same wire pushed its id. Taking the id back
            # has to remove that heap entry, or the next wire will be given
            # an id that is already live.
            if self.recycled and self.recycled[0] == qubit:
                heapq.heappop(self.recycled)
            return qubit, "same"
        if self.recycled:
            return heapq.heappop(self.recycled), "recycled"
        if self.holes:
            return heapq.heappop(self.holes), "hole"
        cursor = 0
        while cursor in self.named or cursor in self.occupied:
            cursor += 1
        return cursor, "fresh"

    def _drop_stale(self, heap: list[int]) -> None:
        while heap and heap[0] in self.occupied:
            heapq.heappop(heap)

    def _free(self, qubit: int) -> None:
        physical = self.map.pop(qubit, None)
        if physical is None:
            return
        self.occupied.discard(physical)
        heapq.heappush(self.recycled, physical)


def _rewrite_ops(
    ops,
    emit,
    *,
    window: int,
    stats: PassStats,
    before: GateCounts,
    deadline,
    task: str | None,
    named_qubits: set[int] | None = None,
    has_registers: bool = False,
    fresh_bit: int = 0,
    profiler: StructureProfiler | None = None,
    used_ids: set[int] | None = None,
    header_qubits: int | None = None,
) -> None:
    named = set(named_qubits or ())
    hold = _Hold(window)
    pending = _Pending()
    tracker = _AndTracker(
        named=named,
        has_registers=has_registers,
        fresh_bit=fresh_bit,
        window=window,
        stats=stats,
    )
    reuse = _LifetimeMap(
        named=named,
        enabled=has_registers and bool(named),
        stats=stats,
        used=used_ids,
        header=header_qubits,
    )
    if profiler is not None and named and has_registers:
        profiler.note_register_qubits(named)
    seen = 0

    def push(op: Op) -> None:
        for produced in tracker.feed(op):
            hold.push(produced, stats)
            while hold.overflow():
                emit(reuse.apply(hold.pop_front()))

    for op in ops:
        seen += 1
        if seen % 100_000 == 0:
            _check_deadline(deadline)
        if profiler is not None:
            profiler.note(op)
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
        emit(reuse.apply(op))


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
    total.and_uncomputes += int(part.get("and_uncomputes") or 0)
    total.clean_and_opens += int(part.get("clean_and_opens") or 0)
    total.shared_control_factors += int(part.get("shared_control_factors") or 0)
    total.qubit_reuses += int(part.get("qubit_reuses") or 0)
    total.qubit_relabels += int(part.get("qubit_relabels") or 0)


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
