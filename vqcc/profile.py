"""Streaming structure profile of a kickmix circuit.

The Kaggle sample circuits are not in this repository. The optimize step
runs this profile on whatever circuit it is given and puts the report in
the step JSON, so the next Kaggle run records it.

The report is a structural description. It is not a verifier score and not
a leaderboard score.

What it counts, in one pass:

- opcode histogram
- repeated 32-gate windows, as lossy heavy hitters of a qubit-relative hash
- Toffoli shape: clean AND opens, matching uncompute pairs, shared-control
  candidates, and why each of those candidates is or is not a strict match.
  A control write is split by opcode and by whether tracking restored it
  or a SWAP moved it.
  adjacent same-control runs, ripple-like shifts, AND cascades
- qubit lifetimes. A qubit is live from its first use after a verified
  ``|0>`` until the next unconditional ``R`` or ``HMR``. A second peak also
  treats a matching clean-AND uncompute as death. Named register ids stay
  live for the whole circuit when the file has registers, because the
  verifier reads those ids.

Memory stays bounded. The heavy-hitter maps drop count-1 keys once they
pass a cap, so a circuit with millions of distinct windows does not retain
every window. Peak-live tracking keeps one set of live qubit ids. If that
set would pass 200_000 ids, lifetime detail stops and the report says so.
"""

from __future__ import annotations

import json
import os
import sys

from vqcc.kickmix_file import (
    KickmixFormatError,
    Op,
    detect_format,
    iter_kmb_ops,
    open_kmb,
    read_kmx_ops,
    register_ids,
    _parse_kmb,
)
from vqcc.qubit_values import ValueMap, empty_mutation_row, mutation_gate, zero

_WINDOW = 32
_PAIR_CAP = 4096
_BLOCK_CAP = 4096
_LIVE_CAP = 200_000
_TOP = 5
_MATCH_REASONS = (
    "eligible",
    "control_mutated",
    "condition_bit_written",
    "condition_mismatch",
)
_LABEL_RANK = {label: index for index, label in enumerate(_MATCH_REASONS)}


def firing_bits(stack, explicit: int | None) -> frozenset[int]:
    """Bits that are 1 when a gate under this stack and explicit condition fires."""

    bits = set(stack)
    if explicit is not None:
        bits.add(explicit)
    return frozenset(bits)


class _ProfAnd:
    """Loose AND record. ``invalid`` is why the transform will not use it.

    ``origin_order`` is the control qubits at the compute. ``order`` is where
    those values sit now. A SWAP moves ``order``. ``ctrl_vals`` and
    ``and_val`` are the values that have to be present for a match.
    ``first_mutation`` is the first opcode that took a control off that value.
    """

    __slots__ = (
        "origin",
        "origin_order",
        "order",
        "controls",
        "required",
        "invalid",
        "ctrl_vals",
        "and_val",
        "sig",
        "first_mutation",
        "target",
    )

    def __init__(self, controls: frozenset[int], required: frozenset[int]) -> None:
        self.origin = controls
        self.origin_order: tuple[int, ...] = tuple(controls)
        self.order: tuple[int, ...] = tuple(controls)
        self.controls = controls
        self.required = required
        self.invalid: str | None = None
        self.ctrl_vals: tuple = ()
        self.and_val = zero()
        self.sig: frozenset = frozenset()
        self.first_mutation: str | None = None
        self.target = -1

_NAME_CODE = {
    "NEG": 1,
    "POP_CONDITION": 2,
    "PUSH_CONDITION": 3,
    "Z": 4,
    "X": 5,
    "R": 6,
    "Z_POW": 7,
    "HMR": 8,
    "CZ": 9,
    "CX": 10,
    "SWAP": 11,
    "CCZ": 12,
    "CCX": 13,
    "CSWAP": 14,
    "BIT_STORE0": 15,
    "BIT_STORE1": 16,
    "BIT_INVERT": 17,
    "INFO_TAG": 18,
    "DEBUG_PRINT": 19,
}


class StructureProfiler:
    """One pass over operations. ``finish`` returns a JSON-ready dict."""

    def __init__(
        self,
        *,
        named: set[int] | None = None,
        has_registers: bool = False,
        header_qubits: int | None = None,
        header_bits: int | None = None,
        reuse_blocked: str | None = None,
    ) -> None:
        self.named = set(named or ())
        self.has_registers = has_registers
        self.header_qubits = header_qubits
        self.header_bits = header_bits
        if reuse_blocked is not None:
            self.reuse_blocked = reuse_blocked
        elif not has_registers:
            self.reuse_blocked = "no_registers"
        elif not self.named:
            self.reuse_blocked = "no_named_qubits"
        else:
            self.reuse_blocked = None
        self.instructions = 0
        self.opcodes: dict[str, int] = {}
        self.stack = 0
        self.unconditional_r = 0
        self.unconditional_hmr = 0
        self.conditional_resets = 0
        self.clean_and_opens = 0
        self.matching_uncompute_pairs = 0
        self.shared_control_candidates = 0
        self.and_cascade_links = 0
        self.ripple_like_links = 0
        self.longest_same_control_run = 0
        self._run_len = 0
        self._run_controls: frozenset[int] | None = None
        self._pairs: dict[tuple[int, int], int] = {}
        self._blocks: dict[int, tuple[int, str]] = {}
        self._buf: list[Op] = []
        self._cond: list[int] = []
        self._open: dict[int, _ProfAnd] = {}
        self._by_q: dict[int, set[int]] = {}
        self._by_bit: dict[int, set[int]] = {}
        self._proven_zero: set[int] = set()
        self.measurement_and_closes = 0
        self._shared_match = {reason: 0 for reason in _MATCH_REASONS}
        self._uncompute_match = {reason: 0 for reason in _MATCH_REASONS}
        self._mutation = {
            "shared_control": empty_mutation_row(),
            "uncompute": empty_mutation_row(),
        }
        self._by_sig: dict[frozenset, set[int]] = {}
        self.values = ValueMap()
        self._proven_dirty: set[int] = set()
        self._prev_ccx: tuple[int, ...] | None = None
        self.max_id = -1
        self.touched = 0
        self._seen: set[int] = set()
        self._live: set[int] = set()
        self._live_u: set[int] = set()
        self.peak_live_reset_only = 0
        self.peak_live_with_uncompute = 0
        self.qubits_reset = 0
        self._reset_qubits: set[int] = set()
        self.truncated = False
        self._peak_open = 0

    def note_register_qubits(self, qubits: set[int]) -> None:
        for qubit in qubits:
            self._born(qubit)

    def note(self, op: Op) -> None:
        self.instructions += 1
        self.opcodes[op.name] = self.opcodes.get(op.name, 0) + 1
        self._buf.append(op)
        if len(self._buf) == _WINDOW:
            self._flush_window()
            self._buf.clear()
        if op.name == "PUSH_CONDITION":
            self.stack += 1
            if op.condition is not None:
                self._cond.append(op.condition)
            return
        if op.name == "POP_CONDITION":
            if self.stack:
                self.stack -= 1
            if self._cond:
                self._cond.pop()
            return
        self._invalidate_condition_bits(op)
        hard_reset = (
            op.name in {"R", "HMR"}
            and bool(op.qubits)
            and op.condition is None
            and self.stack == 0
        )
        if op.name in {"R", "HMR"} and op.qubits:
            if hard_reset:
                if op.name == "R":
                    self.unconditional_r += 1
                else:
                    self.unconditional_hmr += 1
            else:
                self.conditional_resets += 1
            if op.qubits[0] in self._open:
                self.measurement_and_closes += 1
        for qubit in op.qubits:
            self._touch_seen(qubit)
            self._born(qubit)
        firing = firing_bits(self._cond, op.condition)
        if hard_reset:
            qubit = op.qubits[0]
            if qubit not in self._reset_qubits and not self.truncated:
                self._reset_qubits.add(qubit)
                self.qubits_reset += 1
            self.values.apply(op, firing)
            self._stamp_mutation(op)
            self._mark_zero(qubit)
            self._drop(qubit)
            self._die_reset(qubit)
            return
        if op.name == "CCX" and len(op.qubits) == 3:
            self._note_ccx(op)
            return
        if op.name == "SWAP" and len(op.qubits) == 2:
            self._track_swap(op, firing)
            return
        if op.name == "CSWAP" and len(op.qubits) == 3:
            self.values.apply(op, firing)
            self._stamp_mutation(op)
            for qubit in op.qubits[1:]:
                self._taint(qubit)
            return
        self.values.apply(op, firing)
        self._stamp_mutation(op)
        if op.name in {"R", "HMR"} and op.qubits:
            # Conditional reset. The value map has already made this opaque.
            # Drop an AND stored on this qubit. A control that is only
            # conditionally reset stays on its record so a later CCX is
            # still labelled.
            self._kill(op.qubits[0])
            return
        for qubit in _value_writes(op):
            self._taint(qubit)

    def finish(self) -> dict:
        if self._buf:
            # A short tail is not a 32-gate block. It is not hashed, so a
            # circuit shorter than the window does not pretend to repeat.
            self._buf.clear()
        top_pairs = sorted(self._pairs.items(), key=lambda item: (-item[1], item[0]))[:_TOP]
        top_blocks = sorted(self._blocks.items(), key=lambda item: (-item[1][0], item[0]))
        repeated = [
            {"count": count, "fingerprint": f"{digest:08x}", "opcodes": preview}
            for digest, (count, preview) in top_blocks
            if count >= 2
        ][:_TOP]
        header = self.header_qubits
        holes = None
        if header is not None and not self.truncated and self.max_id < header:
            holes = header - self.touched
        named_max = max(self.named) if self.named else -1
        peak = self.peak_live_reset_only
        return {
            "source": "input circuit",
            "not_a_score": True,
            "instructions": self.instructions,
            "opcodes": {name: self.opcodes[name] for name in sorted(self.opcodes)},
            "registers": {
                "has_registers": self.has_registers,
                "named_qubits": len(self.named),
                "max_named_id": named_max,
            },
            "resets": {
                "unconditional_r": self.unconditional_r,
                "unconditional_hmr": self.unconditional_hmr,
                "conditional_resets": self.conditional_resets,
                "qubits_reset": self.qubits_reset,
            },
            "toffoli": {
                "ccx": self.opcodes.get("CCX", 0),
                "ccz": self.opcodes.get("CCZ", 0),
                "cswap": self.opcodes.get("CSWAP", 0),
                "clean_and_opens": self.clean_and_opens,
                "matching_uncompute_pairs": self.matching_uncompute_pairs,
                "shared_control_candidates": self.shared_control_candidates,
                "measurement_and_closes": self.measurement_and_closes,
                "match": {
                    "shared_control": dict(self._shared_match),
                    "uncompute": dict(self._uncompute_match),
                    "control_mutation": {
                        "shared_control": self._mutation["shared_control"],
                        "uncompute": self._mutation["uncompute"],
                        "note": (
                            "Candidates whose controls were written after the AND. "
                            "open is still changed at the later CCX and sums to "
                            "control_mutated. undone means tracking put the original "
                            "value back on the original qubit (X·X, CX·CX, CCX·CCX, "
                            "CSWAP·CSWAP, SWAP·SWAP). relabelled means an unconditional "
                            "SWAP moved that value onto the later CCX's controls. "
                            "undone and relabelled are not part of control_mutated. "
                            "A reset or a measurement is never undone. Not a score."
                        ),
                    },
                    "note": (
                        "One label per profiled candidate. The four labels sum "
                        "to that candidate count. eligible is a strict match the "
                        "transform can apply, including a control that tracking "
                        "restored or moved with SWAP. control_mutated means a "
                        "control write was still in effect; the opcode split is "
                        "control_mutation. condition_bit_written means the profile "
                        "still counted an AND after a condition bit was overwritten. "
                        "condition_mismatch is a live AND whose firing condition "
                        "does not match the later CCX. Not a score."
                    ),
                },
                "and_cascade_links": self.and_cascade_links,
                "ripple_like_links": self.ripple_like_links,
                "longest_same_control_run": self.longest_same_control_run,
                "peak_open_ands": self._peak_open,
                "top_control_pairs": [
                    {"controls": [left, right], "count": count}
                    for (left, right), count in top_pairs
                    if count >= 2
                ],
            },
            "qubits": {
                "header": header,
                "header_bits": self.header_bits,
                "max_id_used": self.max_id,
                "touched": self.touched,
                "unused_below_header": holes,
                "peak_live_reset_only": peak,
                "peak_live_with_uncompute": self.peak_live_with_uncompute,
                "lifetimes_truncated": self.truncated,
                "reuse_blocked": self.reuse_blocked,
                "reuse_headroom_vs_header": (
                    None if header is None else max(0, header - max(peak, named_max + 1))
                ),
            },
            "repeated_blocks": {
                "window": _WINDOW,
                "top": repeated,
                "note": (
                    "Lossy heavy hitters of non-overlapping 32-gate windows. "
                    "Qubit ids are relative to the window minimum, so a shifted "
                    "copy of the same block can share a fingerprint. Count-1 "
                    "windows are dropped once the map is full. This is not an "
                    "exhaustive catalog."
                ),
            },
        }

    def _note_ccx(self, op: Op) -> None:
        control_a, control_b, target = op.qubits
        controls = frozenset((control_a, control_b))
        ordered = (control_a, control_b) if control_a < control_b else (control_b, control_a)
        self._bump_pair(ordered)
        if self._run_controls == controls:
            self._run_len += 1
        else:
            self._run_len = 1
            self._run_controls = controls
        if self._run_len > self.longest_same_control_run:
            self.longest_same_control_run = self._run_len
        if self._prev_ccx is not None and len(self._prev_ccx) == 3:
            if all(qubit == previous + 1 for qubit, previous in zip(op.qubits, self._prev_ccx)):
                self.ripple_like_links += 1
            if self._prev_ccx[2] in (control_a, control_b):
                self.and_cascade_links += 1
        self._prev_ccx = op.qubits
        self._match_open(op, controls, target)

    def _match_open(self, op: Op, controls: frozenset[int], target: int) -> None:
        active = firing_bits(self._cond, op.condition)
        view = self._open.get(target)
        if (
            view is not None
            and len(view.controls) == 2
            and target not in view.controls
            and target not in controls
        ):
            label, disposition = self._label(view, controls, active, uncompute=True)
            if label is not None:
                self._uncompute_match[label] += 1
                self.matching_uncompute_pairs += 1
                self._note_mutation("uncompute", view, disposition)
                self._finish_uncompute(op, view, label, active)
                return
        reason, winner, disposition = self._shared_choice(op, controls, target, active)
        if reason is not None and winner is not None:
            self._shared_match[reason] += 1
            self.shared_control_candidates += 1
            self._note_mutation("shared_control", winner, disposition)
        opening = self._is_zero(target) and len(controls) == 2 and target not in controls
        if opening:
            self.values.force_zero(target)
        held = (self.values.read(op.qubits[0]), self.values.read(op.qubits[1]))
        self.values.apply(op, active)
        self._stamp_mutation(op)
        if opening and len(self._open) < 100_000:
            self._record_open(op, controls, active, held)
            return
        self._kill(target)

    def _finish_uncompute(self, op: Op, view: _ProfAnd, label: str, active: frozenset[int]) -> None:
        target = view.target
        if label == "control_mutated":
            self.values.apply(op, active)
            self._stamp_mutation(op)
            self._drop(target)
            self._taint(target)
            return
        # The controls' current values match, so this CCX clears the AND.
        # Stamp first so any other AND that used this ancilla as a control
        # records the write.
        self.values.force_zero(target)
        self._stamp_mutation(op)
        self._drop(target)
        self._mark_zero(target)
        self._die_uncompute(target)

    def _record_open(
        self,
        op: Op,
        controls: frozenset[int],
        required: frozenset[int],
        held: tuple,
    ) -> None:
        target = op.qubits[2]
        view = _ProfAnd(controls, required)
        view.origin_order = (op.qubits[0], op.qubits[1])
        view.order = view.origin_order
        view.target = target
        view.ctrl_vals = held
        view.and_val = self.values.read(target)
        view.sig = frozenset(held)
        self._open[target] = view
        self.clean_and_opens += 1
        self._proven_dirty.add(target)
        self._proven_zero.discard(target)
        self._index_and(view)
        if len(self._open) > self._peak_open:
            self._peak_open = len(self._open)

    def _shared_choice(
        self,
        op: Op,
        controls: frozenset[int],
        target: int,
        active: frozenset[int],
    ) -> tuple[str | None, _ProfAnd | None, str | None]:
        sig = frozenset((self.values.read(op.qubits[0]), self.values.read(op.qubits[1])))
        seen: set[int] = set()
        found: list[_ProfAnd] = []
        for candidate in self._by_sig.get(sig, ()):
            if candidate == target or candidate in seen:
                continue
            view = self._open.get(candidate)
            if view is None:
                continue
            seen.add(candidate)
            found.append(view)
        for qubit in op.qubits[:2]:
            for candidate in self._by_q.get(qubit, ()):
                if candidate == target or candidate in seen:
                    continue
                view = self._open.get(candidate)
                if view is None:
                    continue
                if view.origin != controls and view.controls != controls:
                    continue
                seen.add(candidate)
                found.append(view)
        best_rank = 9
        best: tuple[str, _ProfAnd, str | None] | None = None
        for view in found:
            label, disposition = self._label(view, controls, active, uncompute=False)
            if label is None:
                continue
            rank = _LABEL_RANK[label]
            if rank < best_rank:
                best_rank = rank
                best = (label, view, disposition)
        if best is None:
            return None, None, None
        return best

    def _label(
        self,
        view: _ProfAnd,
        controls: frozenset[int],
        active: frozenset[int],
        *,
        uncompute: bool,
    ) -> tuple[str | None, str | None]:
        # ``controls`` is the later CCX's control-qubit set.
        sig = frozenset(self.values.read(qubit) for qubit in controls)
        control_values_ok = sig == view.sig
        target_ok = self.values.read(view.target) == view.and_val
        same_wires = view.origin == controls or view.controls == controls
        if view.invalid == "condition_bit_written" and (control_values_ok or same_wires):
            return "condition_bit_written", self._mutation_disposition(view, control_values_ok, "condition_bit_written")
        if not control_values_ok:
            if same_wires:
                return "control_mutated", "open"
            return None, None
        if not target_ok:
            # The control wires match and the stored bit does not. That is a
            # write of the AND target, which drops the candidate instead of
            # counting as a control mutation.
            return None, None
        if uncompute:
            condition_ok = view.required == active
        else:
            condition_ok = view.required <= active
        label = "eligible" if condition_ok else "condition_mismatch"
        return label, self._mutation_disposition(view, True, label)

    def _mutation_disposition(self, view: _ProfAnd, control_values_ok: bool, label: str) -> str | None:
        if view.first_mutation is None:
            return None
        if label == "control_mutated":
            return "open"
        if not control_values_ok:
            return None
        if view.first_mutation in {"R", "HMR"}:
            # A reset or a measurement does not put the old value back.
            return None
        if self._pristine(view):
            return "undone"
        return "relabelled"

    def _note_mutation(self, kind: str, view: _ProfAnd, disposition: str | None) -> None:
        if disposition is None:
            return
        gate = view.first_mutation or "other"
        if gate not in self._mutation[kind]:
            gate = "other"
        self._mutation[kind][gate][disposition] += 1

    def _invalidate_condition_bits(self, op: Op) -> None:
        bits = _bit_writes(op)
        if not bits:
            return
        touched: list[int] = []
        for bit in bits:
            touched.extend(self._by_bit.get(bit, ()))
        for target in touched:
            view = self._open.get(target)
            if view is not None and view.invalid is None and bits & view.required:
                view.invalid = "condition_bit_written"

    def _track_swap(self, op: Op, firing: frozenset[int]) -> None:
        left, right = op.qubits
        if firing:
            self.values.apply(op, firing)
            self._stamp_mutation(op)
            self._taint(left)
            self._taint(right)
            return
        self._sync_zero(left)
        self._sync_zero(right)
        self.values.apply(op, firing)
        self._relocate(left, right)
        self._swap_flags(left, right)
        self._stamp_mutation(op)

    def _stamp_mutation(self, op: Op) -> None:
        gate = mutation_gate(op.name)
        if gate is None:
            return
        seen: set[int] = set()
        for qubit in op.qubits:
            for target in self._by_q.get(qubit, ()):
                if target in seen:
                    continue
                seen.add(target)
                view = self._open.get(target)
                if view is None or view.first_mutation is not None:
                    continue
                if not self._pristine(view):
                    view.first_mutation = gate

    def _pristine(self, view: _ProfAnd) -> bool:
        if view.order != view.origin_order:
            return False
        for qubit, expected in zip(view.origin_order, view.ctrl_vals):
            if self.values.read(qubit) != expected:
                return False
        return True

    def _sync_zero(self, qubit: int) -> None:
        if qubit in self._proven_zero:
            self.values.force_zero(qubit)

    def _swap_flags(self, left: int, right: int) -> None:
        left_zero = left in self._proven_zero
        right_zero = right in self._proven_zero
        left_dirty = left in self._proven_dirty
        right_dirty = right in self._proven_dirty
        self._set_flag(left, right_zero, right_dirty)
        self._set_flag(right, left_zero, left_dirty)

    def _set_flag(self, qubit: int, is_zero: bool, dirty: bool) -> None:
        if is_zero:
            self._proven_zero.add(qubit)
        else:
            self._proven_zero.discard(qubit)
        if dirty:
            self._proven_dirty.add(qubit)
        else:
            self._proven_dirty.discard(qubit)

    def _relocate(self, left: int, right: int) -> None:
        if left == right:
            return
        seen: set[int] = set()
        views: list[_ProfAnd] = []
        for qubit in (left, right):
            for target in list(self._by_q.get(qubit, ())):
                if target in seen:
                    continue
                seen.add(target)
                view = self._open.get(target)
                if view is not None:
                    views.append(view)
        for view in views:
            self._unindex_and(view)
        for view in views:
            view.order = tuple(
                right if qubit == left else left if qubit == right else qubit for qubit in view.order
            )
            view.controls = frozenset(view.order)
            if view.target == left:
                view.target = right
            elif view.target == right:
                view.target = left
        for view in views:
            self._index_and(view)

    def _index_and(self, view: _ProfAnd) -> None:
        self._open[view.target] = view
        for qubit in set(view.controls) | {view.target}:
            self._by_q.setdefault(qubit, set()).add(view.target)
        self._by_sig.setdefault(view.sig, set()).add(view.target)
        for bit in view.required:
            self._by_bit.setdefault(bit, set()).add(view.target)

    def _unindex_and(self, view: _ProfAnd) -> None:
        current = self._open.get(view.target)
        if current is view:
            del self._open[view.target]
        for qubit in set(view.controls) | {view.target} | set(view.origin):
            bucket = self._by_q.get(qubit)
            if bucket is None:
                continue
            bucket.discard(view.target)
            if not bucket:
                del self._by_q[qubit]
        bucket = self._by_sig.get(view.sig)
        if bucket is not None:
            bucket.discard(view.target)
            if not bucket:
                del self._by_sig[view.sig]
        for bit in view.required:
            bucket = self._by_bit.get(bit)
            if bucket is None:
                continue
            bucket.discard(view.target)
            if not bucket:
                del self._by_bit[bit]

    def _taint(self, qubit: int) -> None:
        self._proven_zero.discard(qubit)
        self._proven_dirty.add(qubit)

    def _is_zero(self, qubit: int) -> bool:
        if qubit in self._open or qubit in self._proven_dirty:
            return False
        if qubit in self._proven_zero:
            return True
        return self.has_registers and qubit not in self.named

    def _mark_zero(self, qubit: int) -> None:
        self._proven_dirty.discard(qubit)
        self._proven_zero.add(qubit)

    def _kill(self, qubit: int) -> None:
        self._drop(qubit)
        self._proven_zero.discard(qubit)
        self._proven_dirty.add(qubit)

    def _drop(self, target: int) -> None:
        view = self._open.get(target)
        if view is None:
            # The target qubit may have moved. Drop whatever record still
            # names this id, and also a record whose key is stale.
            return
        self._unindex_and(view)

    def _touch_seen(self, qubit: int) -> None:
        if qubit > self.max_id:
            self.max_id = qubit
        if self.truncated:
            return
        if qubit not in self._seen:
            if len(self._seen) >= _LIVE_CAP:
                self.truncated = True
                self._seen.clear()
                self._live.clear()
                self._live_u.clear()
                return
            self._seen.add(qubit)
            self.touched += 1

    def _born(self, qubit: int) -> None:
        if self.truncated:
            return
        if qubit not in self._live:
            self._live.add(qubit)
            if len(self._live) > self.peak_live_reset_only:
                self.peak_live_reset_only = len(self._live)
        if qubit not in self._live_u:
            self._live_u.add(qubit)
            if len(self._live_u) > self.peak_live_with_uncompute:
                self.peak_live_with_uncompute = len(self._live_u)

    def _die_reset(self, qubit: int) -> None:
        if self.truncated or qubit in self.named:
            return
        self._live.discard(qubit)
        self._live_u.discard(qubit)

    def _die_uncompute(self, qubit: int) -> None:
        if self.truncated or qubit in self.named:
            return
        self._live_u.discard(qubit)

    def _bump_pair(self, key: tuple[int, int]) -> None:
        self._pairs[key] = self._pairs.get(key, 0) + 1
        if len(self._pairs) <= _PAIR_CAP:
            return
        victims = [item for item, count in self._pairs.items() if count == 1]
        if not victims:
            victim = min(self._pairs, key=self._pairs.get)
            del self._pairs[victim]
            return
        for item in victims[: max(1, len(victims) // 2)]:
            del self._pairs[item]

    def _flush_window(self) -> None:
        ids = [qubit for op in self._buf for qubit in op.qubits]
        base = min(ids) if ids else 0
        digest = 2166136261
        names: list[str] = []
        for op in self._buf:
            names.append(op.name)
            digest = (digest * 16777619) ^ _NAME_CODE.get(op.name, 0)
            digest &= 0xFFFFFFFF
            for qubit in op.qubits:
                digest = (digest * 16777619) ^ ((qubit - base) & 0xFFFF)
                digest &= 0xFFFFFFFF
        preview = ",".join(names)
        current = self._blocks.get(digest)
        if current is None:
            if len(self._blocks) >= _BLOCK_CAP:
                victims = [item for item, (count, _) in self._blocks.items() if count == 1]
                if not victims:
                    return
                for item in victims[: max(1, len(victims) // 2)]:
                    del self._blocks[item]
            self._blocks[digest] = (1, preview)
            return
        self._blocks[digest] = (current[0] + 1, current[1])


def _bit_writes(op: Op) -> set[int]:
    if op.name in {"BIT_STORE0", "BIT_STORE1", "BIT_INVERT"} and op.bits:
        return {op.bits[0]}
    if op.name == "HMR" and op.bits:
        return {op.bits[0]}
    return set()


def _value_writes(op: Op) -> set[int]:
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


def profile_ops(
    ops,
    *,
    named: set[int] | None = None,
    has_registers: bool = False,
    header_qubits: int | None = None,
    header_bits: int | None = None,
    reuse_blocked: str | None = None,
) -> dict:
    profiler = StructureProfiler(
        named=named,
        has_registers=has_registers,
        header_qubits=header_qubits,
        header_bits=header_bits,
        reuse_blocked=reuse_blocked,
    )
    if named and has_registers:
        profiler.note_register_qubits(set(named))
    for op in ops:
        profiler.note(op)
    return profiler.finish()


def profile_path(path: str, *, memory_budget_bytes: int = 2 * 1024**3) -> dict:
    """Profile a ``.kmb``, a ``.kmx``, or a directory of circuits.

    Non-circuit files in a directory are skipped. ``submission.npz`` is not
    opened.
    """

    if os.path.isdir(path):
        files = []
        for dirpath, _dirnames, filenames in os.walk(path):
            for name in sorted(filenames):
                source = os.path.join(dirpath, name)
                if detect_format(source) is None:
                    continue
                report = profile_path(source, memory_budget_bytes=memory_budget_bytes)
                report["path"] = os.path.relpath(source, path)
                files.append(report)
        return {"directory": True, "files": files, "not_a_score": True}
    kind = detect_format(path)
    if kind == "kmb":
        mapped, handle = open_kmb(path, memory_budget_bytes)
        try:
            view = _parse_kmb(mapped)
            named: set[int] = set()
            for payload in view.registers:
                qubits, _bits = register_ids(payload)
                named |= qubits
            blocked = None
            if not view.registers:
                blocked = "no_registers"
            elif not named:
                blocked = "no_named_qubits"
            report = profile_ops(
                iter_kmb_ops(view),
                named=named,
                has_registers=bool(view.registers),
                header_qubits=view.num_qubits,
                header_bits=view.num_bits,
                reuse_blocked=blocked,
            )
            view.release()
            report["format"] = "kmb"
            return report
        finally:
            mapped.close()
            handle.close()
    if kind == "kmx":
        named = set()
        has_registers = False
        ops = list(read_kmx_ops(path, memory_budget_bytes))
        for op in ops:
            if op.name in {"REGISTER", "APPEND_TO_REGISTER"}:
                has_registers = True
            if op.name == "APPEND_TO_REGISTER" and op.qubits:
                named.add(op.qubits[0])
        blocked = None
        if not has_registers:
            blocked = "no_registers"
        elif not named:
            blocked = "no_named_qubits"
        max_id = -1
        for op in ops:
            if op.qubits:
                max_id = max(max_id, max(op.qubits))
        report = profile_ops(
            (op for op in ops if op.name not in {"REGISTER", "APPEND_TO_REGISTER"}),
            named=named,
            has_registers=has_registers,
            header_qubits=None if max_id < 0 else max_id + 1,
            reuse_blocked=blocked,
        )
        report["format"] = "kmx"
        return report
    raise KickmixFormatError(f"{path} is not a kickmix circuit")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python3 -m vqcc.profile CIRCUIT", file=sys.stderr)
        return 2
    try:
        report = profile_path(args[0])
    except (OSError, KickmixFormatError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
