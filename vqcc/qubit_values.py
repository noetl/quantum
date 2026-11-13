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


class ValueMap:
    """Per-qubit computational values. Missing entries are the original atom."""

    def __init__(self) -> None:
        self._v: dict[int, Val] = {}
        self._bit_epoch: dict[int, int] = {}
        self._opaque_id = _OPAQUE_BASE

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
            self._xor_into(op.qubits[0], self._under(firing, _ONE))
            return
        if name == "CX" and len(op.qubits) == 2:
            control, target = op.qubits
            self._xor_into(target, self._under(firing, self.read(control)))
            return
        if name == "CCX" and len(op.qubits) == 3:
            left, right, target = op.qubits
            token = ("and", _freeze(self.read(left)), _freeze(self.read(right)))
            self._xor_into(target, self._under(firing, Val(frozenset(), False, frozenset((token,)))))
            return
        if name == "SWAP" and len(op.qubits) == 2:
            left, right = op.qubits
            if not firing:
                self._exchange(left, right)
                return
            self._cswap(self._under(firing, _ONE), left, right)
            return
        if name == "CSWAP" and len(op.qubits) == 3:
            control, left, right = op.qubits
            self._cswap(self._under(firing, self.read(control)), left, right)
            return
        if name == "HMR" and op.bits:
            self.bump_bit(op.bits[0])
        if name in {"R", "HMR"} and op.qubits:
            qubit = op.qubits[0]
            if firing:
                self._v[qubit] = self._fresh_opaque()
            else:
                self._v[qubit] = _ZERO
            return
        if mutation_gate(name) == "other" and op.qubits:
            for qubit in op.qubits:
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
