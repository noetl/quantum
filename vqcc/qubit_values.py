"""Computational-value tracking for clean AND controls.

A clean AND stays equal to the AND of its controls when those controls are
only permuted, or when a self-inverse write is applied and then undone.
This module tracks that fact. It does not track phases.

The tracked value of a qubit is the XOR of original qubit atoms, a constant
flip, and nonlinear tokens (AND, conditional write, conditional swap). XOR
is its own inverse, so X·X, CX·CX, CCX·CCX, CSWAP·CSWAP, and SWAP·SWAP
cancel when the values they depend on are unchanged. An unconditional SWAP
exchanges values, which is how a control moves to another qubit.

A reset or a measurement writes a constant or an opaque value. That is not
the original atom, so the match stays rejected. An expression that grows
past the term cap collapses to a fresh opaque atom and also stays rejected.
Both choices are incomplete on purpose: a value that compares equal really
was restored or relocated.
"""

from __future__ import annotations

from dataclasses import dataclass

from vqcc.kickmix_file import Op

_CAP = 8
_OPAQUE_BASE = 1 << 40
# Open (not yet undone) writes kept per qubit. Past this the qubit's
# pending history is dropped and every AND that was opened before the
# overflow is no longer treated as restored. That is incomplete and sound:
# a value the log cannot prove is not rewritten. Self-inverse pairs cancel
# inside the cap, so X·X and CX·CX still match.
OPEN_WRITE_LIMIT = 8
MUTATION_GATES = ("X", "CX", "CCX", "SWAP", "CSWAP", "R", "HMR", "other")
_PHASE_OR_META = {
    "Z",
    "Z_POW",
    "CZ",
    "CCZ",
    "NEG",
    "PUSH_CONDITION",
    "POP_CONDITION",
    "INFO_TAG",
    "DEBUG_PRINT",
    "REGISTER",
    "APPEND_TO_REGISTER",
}


@dataclass(frozen=True, slots=True)
class Val:
    """XOR of ``terms``, a constant ``flip``, and nonlinear ``extra`` tokens."""

    terms: frozenset[int]
    flip: bool
    extra: frozenset[tuple]

    def is_atom(self, qubit: int) -> bool:
        return self.terms == frozenset((qubit,)) and not self.flip and not self.extra


_ZERO = Val(frozenset(), False, frozenset())
_ONE = Val(frozenset(), True, frozenset())
_ATOMS: dict[int, Val] = {}


def atom(qubit: int) -> Val:
    found = _ATOMS.get(qubit)
    if found is None:
        found = Val(frozenset((qubit,)), False, frozenset())
        _ATOMS[qubit] = found
    return found


def zero() -> Val:
    return _ZERO


def mutation_gate(name: str) -> str | None:
    """Opcode class that can change a control's computational value.

    Phase, metadata, and classical bit ops are not control mutations.
    ``other`` is a qubit write this tracker does not model.
    """

    if name in {"X", "CX", "CCX", "SWAP", "CSWAP", "R", "HMR"}:
        return name
    if name in _PHASE_OR_META or name in {"BIT_STORE0", "BIT_STORE1", "BIT_INVERT"}:
        return None
    return "other"


def empty_mutation_row() -> dict[str, dict[str, int]]:
    return {gate: {"undone": 0, "relabelled": 0, "open": 0} for gate in MUTATION_GATES}


def _freeze(value: Val) -> tuple:
    return (tuple(sorted(value.terms)), value.flip, tuple(sorted(value.extra)))


def _xor(left: Val, right: Val, opaque) -> Val:
    if right is _ZERO:
        return left
    if left is _ZERO:
        return right
    if not right.terms and not right.extra:
        return Val(left.terms, left.flip ^ right.flip, left.extra)
    if not left.terms and not left.extra:
        return Val(right.terms, left.flip ^ right.flip, right.extra)
    terms = left.terms.symmetric_difference(right.terms)
    extra = left.extra.symmetric_difference(right.extra)
    flip = left.flip ^ right.flip
    if len(terms) + len(extra) > _CAP:
        return opaque()
    if not extra and not flip and len(terms) == 1:
        (only,) = terms
        if only < _OPAQUE_BASE:
            return atom(only)
    if not terms and not extra:
        return _ONE if flip else _ZERO
    return Val(terms, flip, extra)


class _WriteLog:
    """Uncancelled writes on one qubit. The stack length is at most K."""

    __slots__ = ("epoch", "overflow", "overflow_epoch", "stack")

    def __init__(self) -> None:
        self.epoch = 0
        self.overflow = False
        self.overflow_epoch = 0
        self.stack: list[tuple] = []


class ValueMap:
    """Per-qubit computational values. Missing entries are the original atom.

    Each qubit also keeps a pending-write stack of length at most
    ``OPEN_WRITE_LIMIT``. The stack is the mutation history. It is indexed
    by qubit, so a gate updates one or two logs and does not walk live ANDs.
    """

    def __init__(self) -> None:
        self._v: dict[int, Val] = {}
        self._bit_epoch: dict[int, int] = {}
        self._logs: dict[int, _WriteLog] = {}
        self._opaque_id = _OPAQUE_BASE

    def epoch(self, qubit: int) -> int:
        log = self._logs.get(qubit)
        return 0 if log is None else log.epoch

    def gave_up(self, bases: dict[int, int]) -> bool:
        """True when a control's pending history overflowed after ``bases``.

        ``bases`` maps a control qubit to the epoch recorded when the AND
        was opened. An overflow older than that epoch happened before the
        snapshot and does not retire the AND.
        """

        for qubit, base in bases.items():
            log = self._logs.get(qubit)
            if log is not None and log.overflow and log.overflow_epoch > base:
                return True
        return False

    def read(self, qubit: int) -> Val:
        return self._v.get(qubit, atom(qubit))

    def force_zero(self, qubit: int) -> None:
        self._v[qubit] = _ZERO

    def bump_bit(self, bit: int) -> None:
        self._bit_epoch[bit] = self._bit_epoch.get(bit, 0) + 1

    def epoch_key(self, bits: frozenset[int]) -> tuple:
        if not bits:
            return ()
        return tuple((bit, self._bit_epoch.get(bit, 0)) for bit in sorted(bits))

    def apply(self, op: Op, firing: frozenset[int]) -> None:
        """Update values for one op under this firing condition.

        ``firing`` is the explicit condition bit plus the ``PUSH_CONDITION``
        stack. An empty set is unconditional.
        """

        name = op.name
        if name in {"BIT_STORE0", "BIT_STORE1", "BIT_INVERT"} and op.bits:
            self.bump_bit(op.bits[0])
            return
        if name in _PHASE_OR_META:
            return
        if name == "X" and op.qubits:
            qubit = op.qubits[0]
            self._note(qubit, ("X", self.epoch_key(firing)))
            self._xor_into(qubit, self._under(firing, _ONE))
            return
        if name == "CX" and len(op.qubits) == 2:
            control, target = op.qubits
            control_value = self.read(control)
            self._note(target, ("CX", _freeze(control_value), self.epoch_key(firing)))
            self._xor_into(target, self._under(firing, control_value))
            return
        if name == "CCX" and len(op.qubits) == 3:
            left, right, target = op.qubits
            token = ("and", _freeze(self.read(left)), _freeze(self.read(right)))
            self._note(target, ("CCX", token, self.epoch_key(firing)))
            self._xor_into(target, self._under(firing, Val(frozenset(), False, frozenset((token,)))))
            return
        if name == "SWAP" and len(op.qubits) == 2:
            left, right = op.qubits
            if not firing:
                # An unconditional SWAP permutes values. The exchange is
                # exact at any length, so it is not an open write and it
                # does not spend the pending-write cap. Routing chains on
                # dqi are millions of SWAPs long.
                if left != right:
                    self._exchange(left, right)
                return
            token = _freeze(self._under(firing, _ONE))
            mark = ("CSWAP", token, self.epoch_key(firing))
            self._note(left, mark)
            self._note(right, mark)
            self._cswap(self._under(firing, _ONE), left, right)
            return
        if name == "CSWAP" and len(op.qubits) == 3:
            control, left, right = op.qubits
            control_value = self._under(firing, self.read(control))
            mark = ("CSWAP", _freeze(control_value), self.epoch_key(firing))
            self._note(left, mark)
            self._note(right, mark)
            self._cswap(control_value, left, right)
            return
        if name == "HMR" and op.bits:
            self.bump_bit(op.bits[0])
        if name in {"R", "HMR"} and op.qubits:
            qubit = op.qubits[0]
            self._note(qubit, (name, self.epoch_key(firing)))
            if firing:
                self._v[qubit] = self._fresh_opaque()
            else:
                self._v[qubit] = _ZERO
            return
        if mutation_gate(name) == "other" and op.qubits:
            for qubit in op.qubits:
                self._opaque_id += 1
                self._note(qubit, ("other", self._opaque_id))
                self._v[qubit] = self._fresh_opaque()

    def _under(self, firing: frozenset[int], payload: Val) -> Val:
        if not firing:
            return payload
        if len(payload.terms) + len(payload.extra) > _CAP:
            return self._fresh_opaque()
        token = ("when", tuple(sorted(firing)), self.epoch_key(firing), _freeze(payload))
        return Val(frozenset(), False, frozenset((token,)))

    def _xor_into(self, qubit: int, operand: Val) -> None:
        self._write(qubit, _xor(self.read(qubit), operand, self._fresh_opaque))

    def _write(self, qubit: int, value: Val) -> None:
        if value.is_atom(qubit):
            self._v.pop(qubit, None)
            return
        self._v[qubit] = value

    def _exchange(self, left: int, right: int) -> None:
        if left == right:
            return
        held_left = self.read(left)
        held_right = self.read(right)
        self._write(left, held_right)
        self._write(right, held_left)

    def _cswap(self, control: Val, left: int, right: int) -> None:
        held_left = self.read(left)
        held_right = self.read(right)
        diff = _xor(held_left, held_right, self._fresh_opaque)
        token = ("and", _freeze(control), _freeze(diff))
        delta = Val(frozenset(), False, frozenset((token,)))
        self._write(left, _xor(held_left, delta, self._fresh_opaque))
        # Re-read right: the opaque collapse of diff does not change it.
        held_right = self.read(right)
        self._write(right, _xor(held_right, delta, self._fresh_opaque))

    def _fresh_opaque(self) -> Val:
        self._opaque_id += 1
        return Val(frozenset((self._opaque_id,)), False, frozenset())

    def _log(self, qubit: int) -> _WriteLog:
        log = self._logs.get(qubit)
        if log is None:
            log = _WriteLog()
            self._logs[qubit] = log
        return log

    def _note(self, qubit: int, fingerprint: tuple) -> None:
        """Push one open write, or pop it when the same write is repeated.

        The stack is the pending history for this qubit. Identical
        self-inverse fingerprints cancel, which is X·X, CX·CX with the
        same control value, CCX·CCX, CSWAP·CSWAP, and SWAP·SWAP. A stack
        longer than ``OPEN_WRITE_LIMIT`` is discarded. Callers then refuse
        to treat an older AND on this qubit as restored.
        """

        log = self._log(qubit)
        log.epoch += 1
        if log.overflow:
            return
        if log.stack and log.stack[-1] == fingerprint:
            log.stack.pop()
            return
        log.stack.append(fingerprint)
        if len(log.stack) > OPEN_WRITE_LIMIT:
            log.overflow = True
            log.overflow_epoch = log.epoch
            log.stack.clear()
