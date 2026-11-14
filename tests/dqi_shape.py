"""Synthetic kmb with dqi's shape: many live ANDs, then CX and SWAP traffic.

The competition sample is not in this repository. The counts are the public
shape from the version 9 profile and the version 12 summary: peak open ANDs
857, and a CX-heavy stream. Gate ratios are scaled; the file is not a score.
"""

from __future__ import annotations

import array
import struct

from vqcc.kickmix_file import (
    ANGLES,
    BIT_0,
    COND_0,
    HEADER_STRUCT,
    INFO,
    MAGIC,
    OP_TYPES,
    PACKET_HEAD,
    Q1_0,
    Q2_0,
    Q2_1,
    Q3_0,
    Q3_1,
    Q3_2,
    REGISTERS,
    VERSION,
)

# CX controls repeat every 8192, which is outside the 4096 cancellation
# window, so a commuting run has no inverse partner inside the horizon.
_CX_PERIOD = 8192


def register_packet(name: bytes, qubits: list[int]) -> bytes:
    body = b"".join(struct.pack("<I", qubit | 0x80000000) for qubit in qubits)
    return struct.pack("<II", len(name), len(qubits)) + name + body


def write_dqi_shaped_kmb(path: str, n_gates: int = 10_000_000, live_ands: int = 857) -> int:
    """Write a kmb of at least ``n_gates`` operations. Returns the gate count."""

    if live_ands < 1:
        raise ValueError("live_ands must be positive")
    n_swap = 200_000 if n_gates > 300_000 else 0
    if n_swap % 2:
        n_swap -= 1
    fixed = live_ands * 2 + n_swap
    if n_gates < fixed + _CX_PERIOD:
        n_gates = fixed + _CX_PERIOD
    n_cx = n_gates - fixed
    # Round up to a whole control period so the file is at least n_gates
    # and no inverse partner sits inside the 4096-gate horizon.
    remainder = n_cx % _CX_PERIOD
    if remainder:
        n_cx += _CX_PERIOD - remainder
    n_ops = fixed + n_cx

    opcodes = bytearray()
    opcodes += bytes([0x12]) * live_ands  # R
    opcodes += bytes([0x31]) * live_ands  # CCX
    opcodes += bytes([0x22]) * n_swap  # SWAP
    opcodes += bytes([0x21]) * n_cx  # CX

    q1 = array.array("I", (200 + index for index in range(live_ands)))
    q3_0 = array.array("I", [0]) * live_ands
    q3_1 = array.array("I", (1 + (index % 8) for index in range(live_ands)))
    q3_2 = array.array("I", (200 + index for index in range(live_ands)))
    if n_swap:
        swap_left = array.array("I", [2, 2]) * (n_swap // 2)
        swap_right = array.array("I", [3, 3]) * (n_swap // 2)
    else:
        swap_left = array.array("I")
        swap_right = array.array("I")
    pattern = array.array("I", range(1, _CX_PERIOD + 1))
    controls = pattern * (n_cx // _CX_PERIOD)
    targets = array.array("I", [50]) * n_cx
    q2_0 = swap_left + controls
    q2_1 = swap_right + targets

    named = list(range(16))
    register = register_packet(b"q", named)
    num_qubits = max(8192, 200 + live_ands) + 1
    header = HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        num_qubits,
        0,
        1,
        n_ops,
        live_ands,
        n_swap + n_cx,
        live_ands,
        0,
        0,
        0,
        0,
        0,
    )
    columns = {
        OP_TYPES: bytes(opcodes),
        Q3_0: q3_0.tobytes(),
        Q3_1: q3_1.tobytes(),
        Q3_2: q3_2.tobytes(),
        Q2_0: q2_0.tobytes(),
        Q2_1: q2_1.tobytes(),
        Q1_0: q1.tobytes(),
        BIT_0: b"",
        COND_0: b"",
        ANGLES: b"",
        INFO: struct.pack("<Q", 0),
    }
    with open(path, "wb") as handle:
        handle.write(header)
        _packet(handle, REGISTERS, register)
        for key in (OP_TYPES, Q3_0, Q3_1, Q3_2, Q2_0, Q2_1, Q1_0, BIT_0, COND_0, ANGLES, INFO):
            _packet(handle, key, columns[key])
    return n_ops


def _packet(handle, payload_type: int, payload: bytes) -> None:
    handle.write(PACKET_HEAD.pack(payload_type, len(payload)))
    handle.write(payload)
