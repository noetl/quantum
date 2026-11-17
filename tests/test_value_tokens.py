"""Value-tracking cost on nested ANDs, and interning soundness.

Kaggle version 13 (scriptVersionId 370491848) spent 2109.6 s on the first
4096 gates of invsqrt and was killed at its budget. The cause was
``vqcc/qubit_values.py``: a CCX token embedded the full frozen value of
both controls. An AND whose controls are earlier ANDs doubles that size, so
a carry chain grew exponentially (about 4 million characters after 256
invsqrt ops). Tokens are now interned to integer ids. Issues
https://github.com/noetl/quantum/issues/19 and
https://github.com/noetl/quantum/issues/9.
"""

from __future__ import annotations

import time
import unittest
from unittest import mock

from vqcc import qubit_values
from vqcc.kickmix_file import Op
from vqcc.profile import profile_ops
from vqcc.qubit_values import ValueMap, _freeze

_CHUNK = 4096
# A 4096-gate chunk took 2109.6 s on Kaggle before the fix. Interned it is
# a few milliseconds locally, so this cap only trips on superlinear growth.
_CHUNK_CAP_S = 5.0


def _nested_and_chain(n: int, *, width: int = 64) -> list[Op]:
    """Each CCX target is a control of the next two CCX gates.

    The value of qubit ``i`` is AND(value(i-1), value(i-2)). Untinterned,
    the frozen size of that value grows like the Fibonacci numbers.
    """

    ops: list[Op] = []
    for index in range(n):
        target = 2 + (index % width)
        left = 2 + ((index - 1) % width) if index >= 1 else 0
        right = 2 + ((index - 2) % width) if index >= 2 else 1
        ops.append(Op(name="CCX", qubits=(left, right, target)))
    return ops


def _largest_frozen(values: ValueMap) -> int:
    return max((len(repr(_freeze(v))) for v in values._v.values()), default=0)


class ChunkTimeTests(unittest.TestCase):
    def test_value_map_chunk_is_bounded(self) -> None:
        values = ValueMap()
        ops = _nested_and_chain(_CHUNK)
        started = time.perf_counter()
        for op in ops:
            values.apply(op, frozenset())
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, _CHUNK_CAP_S, f"{_CHUNK} nested ANDs took {elapsed:.2f}s")
        self.assertLess(_largest_frozen(values), 1_000)

    def test_profile_chunk_is_bounded(self) -> None:
        ops = _nested_and_chain(_CHUNK)
        started = time.perf_counter()
        profile_ops(ops, has_registers=False, header_qubits=128)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, _CHUNK_CAP_S, f"profile of {_CHUNK} nested ANDs took {elapsed:.2f}s")

    def test_time_per_chunk_does_not_grow(self) -> None:
        values = ValueMap()
        ops = _nested_and_chain(8 * _CHUNK)
        times = []
        for start in range(0, len(ops), _CHUNK):
            began = time.perf_counter()
            for op in ops[start : start + _CHUNK]:
                values.apply(op, frozenset())
            times.append(time.perf_counter() - began)
        # Linear work keeps later chunks near the first. Allow noise.
        self.assertLess(max(times), _CHUNK_CAP_S)
        self.assertLess(max(times[1:]), 20 * max(times[0], 0.01), times)


class InterningSoundnessTests(unittest.TestCase):
    def test_repeated_ccx_on_nested_controls_restores_the_target(self) -> None:
        values = ValueMap()
        values.apply(Op(name="CCX", qubits=(0, 1, 2)), frozenset())
        values.apply(Op(name="CCX", qubits=(2, 3, 4)), frozenset())
        values.apply(Op(name="CCX", qubits=(2, 3, 5)), frozenset())
        values.apply(Op(name="CCX", qubits=(2, 3, 5)), frozenset())
        self.assertTrue(values.read(5).is_atom(5))
        # The same nested AND built twice gets the same token.
        values.apply(Op(name="CCX", qubits=(2, 3, 6)), frozenset())
        self.assertEqual(values.read(4).extra, values.read(6).extra)

    def test_different_controls_do_not_cancel(self) -> None:
        values = ValueMap()
        values.apply(Op(name="CCX", qubits=(0, 1, 5)), frozenset())
        values.apply(Op(name="CCX", qubits=(0, 2, 5)), frozenset())
        self.assertFalse(values.read(5).is_atom(5))

    def test_table_reset_never_makes_values_equal(self) -> None:
        with mock.patch.object(qubit_values, "_TOKEN_LIMIT", 2):
            values = ValueMap()
            values.apply(Op(name="CCX", qubits=(0, 1, 5)), frozenset())
            values.apply(Op(name="CCX", qubits=(0, 2, 6)), frozenset())
            values.apply(Op(name="CCX", qubits=(1, 2, 7)), frozenset())
            self.assertGreaterEqual(values.token_resets, 1)
            # The first token was evicted. Rebuilding it gets a new id, so
            # the pair does not cancel. That rejects a match, never accepts one.
            values.apply(Op(name="CCX", qubits=(0, 1, 5)), frozenset())
            self.assertFalse(values.read(5).is_atom(5))
            ids = [next(iter(values.read(q).extra)) for q in (6, 7)]
            self.assertEqual(len(set(ids)), 2)


if __name__ == "__main__":
    unittest.main()
