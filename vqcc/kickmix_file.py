"""Read and write kickmix 1.0.0 circuit files without loading them into kickmix.

The binary layout is the public v2 format (magic, header, then packets in
fixed order). Columns stay in the file mapping; callers see one operation at
a time. That is what makes an 886 MB dqi ``.kmb`` a stream instead of a
``Circuit`` object.

Angles are the file's unsigned 128-bit turn fraction:
``value / 2**128`` turns, which is ``value / 2**127`` half-turns. Z_POW's
text exponent is that half-turn count (kickmix 1.0.0). Identity is 0.
A half-turn of exactly 1 is a Z.
"""

from __future__ import annotations

import mmap
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass

MAGIC = bytes.fromhex("d750c7d5c329d326e3cc9f6834f2b8bf")
VERSION = 2
HEADER_STRUCT = struct.Struct("<16s4I9Q")
HEADER_SIZE = HEADER_STRUCT.size
PACKET_HEAD = struct.Struct("<QQ")
ANGLE_MOD = 1 << 128
Z_ANGLE = 1 << 127
_POW5_127 = 5**127

OP_HAS_1Q = 0x10
OP_HAS_2Q = 0x20
OP_HAS_3Q = 0x30
OP_HAS_1B = 0x40
OP_HAS_COND = 0x80

# payload_type values from the v2 binary spec.
REGISTERS = 0
OP_TYPES = 1
Q3_0, Q3_1, Q3_2 = 2, 3, 4
Q2_0, Q2_1 = 5, 6
Q1_0 = 7
BIT_0 = 8
COND_0 = 9
ANGLES = 10
INFO = 11
PACKET_ORDER = (
    OP_TYPES,
    Q3_0,
    Q3_1,
    Q3_2,
    Q2_0,
    Q2_1,
    Q1_0,
    BIT_0,
    COND_0,
    ANGLES,
    INFO,
)

_BASE_OPCODE = {
    "NEG": 0x00,
    "POP_CONDITION": 0x01,
    "PUSH_CONDITION": 0x81,
    "Z": 0x10,
    "X": 0x11,
    "R": 0x12,
    "Z_POW": 0x13,
    "HMR": 0x50,
    "CZ": 0x20,
    "CX": 0x21,
    "SWAP": 0x22,
    "CCZ": 0x30,
    "CCX": 0x31,
    "CSWAP": 0x32,
    "BIT_STORE0": 0x40,
    "BIT_STORE1": 0x41,
    "BIT_INVERT": 0x42,
    "INFO_TAG": 0x06,
}

# opcode with the condition bit cleared -> name. DEBUG_PRINT is several rows.
_OPCODE_NAME = {value: name for name, value in _BASE_OPCODE.items()}
_OPCODE_NAME[0x07] = "DEBUG_PRINT"
_OPCODE_NAME[0x17] = "DEBUG_PRINT"
_OPCODE_NAME[0x47] = "DEBUG_PRINT"


class KickmixFormatError(ValueError):
    """The file is not a kickmix circuit this rewriter can copy faithfully."""


class OptimizeBudgetError(RuntimeError):
    """A configured time or size budget stopped the rewrite. Nothing was kept."""


@dataclass(slots=True)
class Op:
    """One kickmix operation. Metadata lines use the same shape on the kmx path."""

    name: str
    qubits: tuple[int, ...] = ()
    bits: tuple[int, ...] = ()
    condition: int | None = None
    angle: int | None = None
    info: bytes | None = None
    quote: str | None = None
    register: int | None = None

    def opcode(self) -> int:
        if self.name == "DEBUG_PRINT":
            flags = 0x07
            if self.qubits:
                flags |= OP_HAS_1Q
            if self.bits:
                flags |= OP_HAS_1B
            if self.condition is not None:
                flags |= OP_HAS_COND
            return flags
        if self.name == "PUSH_CONDITION":
            return 0x81
        base = _BASE_OPCODE[self.name]
        if self.condition is not None:
            return base | OP_HAS_COND
        return base


@dataclass(slots=True)
class GateCounts:
    """Local gate totals. Not a verifier score and not a leaderboard score."""

    toffoli_like: int = 0
    t_like: int = 0
    high_rotations: int = 0
    instructions: int = 0

    def add(self, op: Op) -> None:
        self.instructions += 1
        if op.name in {"CCX", "CCZ", "CSWAP"}:
            self.toffoli_like += 1
        if op.name == "Z_POW" and op.angle is not None:
            level = clifford_level(op.angle)
            if level == 3:
                self.t_like += 1
            elif level is not None and level >= 4:
                self.high_rotations += 1

    def key(self) -> tuple[int, int, int]:
        return (self.toffoli_like, self.t_like, self.high_rotations)

    def as_dict(self) -> dict[str, int]:
        return {
            "toffoli_like": self.toffoli_like,
            "t_like": self.t_like,
            "high_rotations": self.high_rotations,
            "instructions": self.instructions,
        }


def clifford_level(angle: int) -> int | None:
    """Clifford-hierarchy level of a Z_POW angle, matching kickmix 1.0.0.

    ``None`` is identity. Level 3 is T-like (``num_t_like``). Level 4 and
    above are finer rotations (``num_t_like`` stays 0 for those).
    """

    angle %= ANGLE_MOD
    if angle == 0:
        return None
    trailing = (angle & -angle).bit_length() - 1
    return 128 - trailing


def format_half_turns(angle: int) -> str:
    """Exact decimal half-turns in ``[0, 2)``, with a decimal point."""

    angle %= ANGLE_MOD
    numer = angle * _POW5_127
    text = str(numer)
    if len(text) <= 127:
        text = text.zfill(128)
    point = len(text) - 127
    whole, frac = text[:point], text[point:]
    frac = frac.rstrip("0") or "0"
    return f"{whole}.{frac}"


def parse_half_turns(text: str) -> int:
    """Inverse of :func:`format_half_turns` for a kickmix exponent token.

    Rounding is half away from zero, then reduced mod 2 half-turns. Exact
    dyadic values used by the peephole (multiples of 2**-127 half-turns)
    round-trip with no error.
    """

    raw = text.strip()
    if not raw or raw[0] not in "+-0123456789":
        raise KickmixFormatError(f"bad exponent {text!r}")
    sign = 1
    if raw[0] in "+-":
        sign = -1 if raw[0] == "-" else 1
        raw = raw[1:]
    if "." not in raw:
        raise KickmixFormatError(f"exponent needs a decimal point: {text!r}")
    whole, frac = raw.split(".", 1)
    if not whole.isdigit() or not frac.isdigit() or not frac:
        raise KickmixFormatError(f"bad exponent {text!r}")
    scale = 10 ** len(frac)
    magnitude = int(whole + frac)
    scaled = sign * magnitude * (1 << 127)
    if scaled >= 0:
        value = (scaled + scale // 2) // scale
    else:
        value = -(((-scaled) + scale // 2) // scale)
    return value % ANGLE_MOD


def detect_format(path: os.PathLike[str] | str, sample: int = 4096) -> str | None:
    """Return ``kmb``, ``kmx``, or ``None`` for a file that is not a circuit."""

    path_s = os.fspath(path)
    with open(path_s, "rb") as handle:
        head = handle.read(sample)
    if head.startswith(MAGIC):
        return "kmb"
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.splitlines():
        stripped = _strip_comment(line).strip()
        if not stripped:
            continue
        name = stripped.split()[0]
        if name in _KMX_NAMES or name == "DEBUG_PRINT":
            return "kmx"
        return None
    return None


_KMX_NAMES = set(_BASE_OPCODE) | {
    "DEBUG_PRINT",
    "REGISTER",
    "APPEND_TO_REGISTER",
    "PUSH_CONDITION",
    "POP_CONDITION",
}


@dataclass(slots=True)
class _KmbView:
    num_qubits: int
    num_bits: int
    registers: list[bytes]
    num_ops: int
    types: bytes | memoryview
    columns: dict
    info_tags: list[bytes]

    def release(self) -> None:
        for column in self.columns.values():
            if isinstance(column, memoryview):
                column.release()
        self.columns.clear()


def _parse_kmb(buf: mmap.mmap | bytes) -> _KmbView:
    if len(buf) < HEADER_SIZE:
        raise KickmixFormatError("kmb shorter than the header")
    magic, version, num_qubits, num_bits, num_registers, *counts = HEADER_STRUCT.unpack_from(buf, 0)
    if magic != MAGIC:
        raise KickmixFormatError("kmb magic mismatch")
    if version != VERSION:
        raise KickmixFormatError(f"unsupported kmb version {version}")
    (
        num_ops,
        n3,
        n2,
        n1,
        nbit,
        ncond,
        nangle,
        ninfo,
        ninfo_chars,
    ) = counts
    if num_qubits > 500_000_000 or num_bits > 500_000_000:
        raise KickmixFormatError("qubit or bit count exceeds the format cap")
    expected_len = {
        OP_TYPES: num_ops,
        Q3_0: 4 * n3,
        Q3_1: 4 * n3,
        Q3_2: 4 * n3,
        Q2_0: 4 * n2,
        Q2_1: 4 * n2,
        Q1_0: 4 * n1,
        BIT_0: 4 * nbit,
        COND_0: 4 * ncond,
        ANGLES: 16 * nangle,
    }
    # memoryview slices alias the mapping. Large gate columns are not copied.
    mapped = memoryview(buf)
    registers: list[bytes] = []
    columns: dict[int, memoryview | bytes] = {}
    offset = HEADER_SIZE
    limit = len(buf)
    while offset < limit:
        if offset + 16 > limit:
            raise KickmixFormatError("truncated kmb packet header")
        payload_type, payload_length = PACKET_HEAD.unpack_from(mapped, offset)
        start = offset + 16
        end = start + payload_length
        if end > limit:
            raise KickmixFormatError("truncated kmb packet payload")
        if payload_type == REGISTERS:
            registers.append(bytes(mapped[start:end]))
        else:
            if payload_type in columns:
                raise KickmixFormatError(f"duplicate kmb packet {payload_type}")
            # Info tags are small and are turned into owned bytes below.
            columns[payload_type] = bytes(mapped[start:end]) if payload_type == INFO else mapped[start:end]
        offset = end
    if offset != limit:
        raise KickmixFormatError("trailing bytes after the last kmb packet")
    if len(registers) != num_registers:
        raise KickmixFormatError("register packet count does not match the header")
    for payload_type in PACKET_ORDER:
        if payload_type not in columns:
            raise KickmixFormatError(f"missing kmb packet {payload_type}")
    # Packets must appear in spec order. Re-walk types to check, registers first.
    offset = HEADER_SIZE
    seen_types: list[int] = []
    reg_seen = 0
    while offset < limit:
        payload_type, payload_length = PACKET_HEAD.unpack_from(buf, offset)
        if reg_seen < num_registers:
            if payload_type != REGISTERS:
                raise KickmixFormatError("register packets must come first")
            reg_seen += 1
        else:
            seen_types.append(payload_type)
        offset += 16 + payload_length
    if seen_types != list(PACKET_ORDER):
        raise KickmixFormatError("kmb packets are not in the required order")
    for payload_type, nbytes in expected_len.items():
        if len(columns[payload_type]) != nbytes:
            raise KickmixFormatError(
                f"kmb packet {payload_type} length {len(columns[payload_type])} != {nbytes}"
            )
    info_tags = _parse_info(bytes(columns[INFO]), ninfo, ninfo_chars)
    return _KmbView(
        num_qubits=num_qubits,
        num_bits=num_bits,
        registers=registers,
        num_ops=num_ops,
        types=columns[OP_TYPES],
        columns=columns,
        info_tags=info_tags,
    )


def _parse_info(payload: bytes, ninfo: int, ninfo_chars: int) -> list[bytes]:
    if len(payload) < 8:
        raise KickmixFormatError("info packet is truncated")
    count = struct.unpack_from("<Q", payload, 0)[0]
    if count != ninfo:
        raise KickmixFormatError("info tag count does not match the header")
    need = 8 * (count + 1)
    if len(payload) < need:
        raise KickmixFormatError("info offsets are truncated")
    offsets = [struct.unpack_from("<Q", payload, 8 * (index + 1))[0] for index in range(count)]
    chars = payload[need:]
    if len(chars) != ninfo_chars:
        raise KickmixFormatError("info character count does not match the header")
    if count and offsets[-1] != ninfo_chars:
        raise KickmixFormatError("last info offset does not match the character count")
    tags: list[bytes] = []
    previous = 0
    for offset in offsets:
        if offset < previous or offset > ninfo_chars:
            raise KickmixFormatError("info offsets are not monotonic")
        tags.append(chars[previous:offset])
        previous = offset
    return tags


def iter_kmb_ops(view: _KmbView):
    """Yield operations in circuit order. Column cursors are local."""

    cursors = {key: 0 for key in (Q3_0, Q3_1, Q3_2, Q2_0, Q2_1, Q1_0, BIT_0, COND_0, ANGLES)}
    info_index = 0
    columns = view.columns
    for index in range(view.num_ops):
        opcode = view.types[index]
        if opcode == 0x81:
            name = "PUSH_CONDITION"
        else:
            name = _OPCODE_NAME.get(opcode & ~OP_HAS_COND)
        if name is None:
            raise KickmixFormatError(f"unknown opcode {opcode:#x} at operation {index}")
        qubits: list[int] = []
        bits: list[int] = []
        condition: int | None = None
        angle: int | None = None
        info: bytes | None = None
        qbits = opcode & OP_HAS_3Q
        if qbits == OP_HAS_3Q:
            qubits = [_take_u32(columns, cursors, key) for key in (Q3_0, Q3_1, Q3_2)]
        elif qbits == OP_HAS_2Q:
            qubits = [_take_u32(columns, cursors, key) for key in (Q2_0, Q2_1)]
        elif qbits == OP_HAS_1Q:
            qubits = [_take_u32(columns, cursors, Q1_0)]
        if opcode & OP_HAS_1B:
            bits = [_take_u32(columns, cursors, BIT_0)]
        if opcode & OP_HAS_COND:
            condition = _take_u32(columns, cursors, COND_0)
        if (opcode & ~OP_HAS_COND) == 0x13:
            angle = _take_angle(columns, cursors)
        if opcode == 0x06:
            if info_index >= len(view.info_tags):
                raise KickmixFormatError("INFO_TAG ran past the info packet")
            info = view.info_tags[info_index]
            info_index += 1
        yield Op(
            name=name,
            qubits=tuple(qubits),
            bits=tuple(bits),
            condition=condition,
            angle=angle,
            info=info,
        )
    for key, cursor in cursors.items():
        width = 16 if key == ANGLES else 4 if key != OP_TYPES else 1
        expect = len(columns[key]) // width
        if cursor != expect:
            raise KickmixFormatError(f"column {key} cursor {cursor} != {expect}")
    if info_index != len(view.info_tags):
        raise KickmixFormatError("info tags were not all consumed")


def _take_u32(columns: dict[int, bytes], cursors: dict[int, int], key: int) -> int:
    index = cursors[key]
    buf = columns[key]
    pos = index * 4
    if pos + 4 > len(buf):
        raise KickmixFormatError(f"column {key} exhausted")
    cursors[key] = index + 1
    return struct.unpack_from("<I", buf, pos)[0]


def _take_angle(columns: dict[int, bytes], cursors: dict[int, int]) -> int:
    index = cursors[ANGLES]
    buf = columns[ANGLES]
    pos = index * 16
    if pos + 16 > len(buf):
        raise KickmixFormatError("angle column exhausted")
    cursors[ANGLES] = index + 1
    low, high = struct.unpack_from("<QQ", buf, pos)
    return low | (high << 64)


def register_ids(payload: bytes) -> tuple[set[int], set[int]]:
    """Qubit and bit ids named by one register packet."""

    if len(payload) < 8:
        raise KickmixFormatError("register packet is truncated")
    name_length, register_length = struct.unpack_from("<II", payload, 0)
    body = 8 + name_length
    end = body + 4 * register_length
    if end != len(payload):
        raise KickmixFormatError("register packet length does not match its header")
    qubits: set[int] = set()
    bits: set[int] = set()
    for index in range(register_length):
        value = struct.unpack_from("<I", payload, body + 4 * index)[0]
        if value & 0x80000000:
            qubits.add(value & 0x7FFFFFFF)
        else:
            bits.add(value)
    return qubits, bits


class KmbWriter:
    """Stream a kmb to ``path``. Column payloads are temp files, not a second copy in RAM."""

    def __init__(self, path: str, registers: list[bytes]) -> None:
        self.path = path
        self.registers = registers
        self.counts = GateCounts()
        self._tmpdir = tempfile.mkdtemp(prefix="vqcc-kmb-")
        self._handles: dict[int, object] = {}
        self._paths: dict[int, str] = {}
        for key in PACKET_ORDER:
            if key == INFO:
                continue
            column = os.path.join(self._tmpdir, str(key))
            self._paths[key] = column
            self._handles[key] = open(column, "wb")
        self._info_path = os.path.join(self._tmpdir, "info")
        self._info_handle = open(self._info_path, "wb")
        self._info_count = 0
        self._info_chars = 0
        self._info_offsets = os.path.join(self._tmpdir, "info-offsets")
        self._info_offsets_handle = open(self._info_offsets, "wb")
        self._max_qubit = -1
        self._max_bit = -1
        self._n3 = self._n2 = self._n1 = 0
        self._nbit = self._ncond = self._nangle = 0
        self._nops = 0
        self._closed = False
        for payload in registers:
            qubits, bits = register_ids(payload)
            if qubits:
                self._max_qubit = max(self._max_qubit, max(qubits))
            if bits:
                self._max_bit = max(self._max_bit, max(bits))

    def emit(self, op: Op) -> None:
        if op.name in {"REGISTER", "APPEND_TO_REGISTER"}:
            raise KickmixFormatError("kmx register lines are not kmb operations")
        opcode = op.opcode()
        self._handles[OP_TYPES].write(bytes((opcode,)))
        self._nops += 1
        self.counts.add(op)
        self._note_ids(op)
        qbits = opcode & OP_HAS_3Q
        if qbits == OP_HAS_3Q:
            if len(op.qubits) != 3:
                raise KickmixFormatError(f"{op.name} needs 3 qubits")
            for key, qubit in zip((Q3_0, Q3_1, Q3_2), op.qubits):
                self._u32(key, qubit)
            self._n3 += 1
        elif qbits == OP_HAS_2Q:
            if len(op.qubits) != 2:
                raise KickmixFormatError(f"{op.name} needs 2 qubits")
            for key, qubit in zip((Q2_0, Q2_1), op.qubits):
                self._u32(key, qubit)
            self._n2 += 1
        elif qbits == OP_HAS_1Q:
            if len(op.qubits) != 1:
                raise KickmixFormatError(f"{op.name} needs 1 qubit")
            self._u32(Q1_0, op.qubits[0])
            self._n1 += 1
        if opcode & OP_HAS_1B:
            if len(op.bits) != 1:
                raise KickmixFormatError(f"{op.name} needs 1 bit")
            self._u32(BIT_0, op.bits[0])
            self._nbit += 1
        if opcode & OP_HAS_COND:
            if op.condition is None:
                raise KickmixFormatError(f"{op.name} needs a condition bit")
            self._u32(COND_0, op.condition)
            self._ncond += 1
        if (opcode & ~OP_HAS_COND) == 0x13:
            if op.angle is None:
                raise KickmixFormatError("Z_POW needs an angle")
            self._angle(op.angle)
            self._nangle += 1
        if opcode == 0x06:
            tag = op.info or b""
            self._info_handle.write(tag)
            self._info_chars += len(tag)
            self._info_count += 1
            self._info_offsets_handle.write(struct.pack("<Q", self._info_chars))

    def close(self) -> None:
        if self._closed:
            return
        self._close_handles()
        try:
            num_qubits = 0 if self._max_qubit < 0 else self._max_qubit + 1
            num_bits = 0 if self._max_bit < 0 else self._max_bit + 1
            header = HEADER_STRUCT.pack(
                MAGIC,
                VERSION,
                num_qubits,
                num_bits,
                len(self.registers),
                self._nops,
                self._n3,
                self._n2,
                self._n1,
                self._nbit,
                self._ncond,
                self._nangle,
                self._info_count,
                self._info_chars,
            )
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.path, "wb") as handle:
                handle.write(header)
                for payload in self.registers:
                    _write_packet(handle, REGISTERS, payload)
                for key in PACKET_ORDER:
                    if key == INFO:
                        continue
                    _write_packet_file(handle, key, self._paths[key])
                _write_info_packet(handle, self._info_count, self._info_offsets, self._info_path)
        finally:
            self._closed = True
            self._cleanup()

    def abort(self) -> None:
        if self._closed:
            self._cleanup()
            return
        self._closed = True
        self._close_handles()
        self._cleanup()

    def _u32(self, key: int, value: int) -> None:
        if value < 0 or value > 0xFFFFFFFF:
            raise KickmixFormatError(f"id {value} does not fit in uint32")
        self._handles[key].write(struct.pack("<I", value))

    def _angle(self, value: int) -> None:
        value %= ANGLE_MOD
        low = value & ((1 << 64) - 1)
        high = value >> 64
        self._handles[ANGLES].write(struct.pack("<QQ", low, high))

    def _note_ids(self, op: Op) -> None:
        if op.qubits:
            self._max_qubit = max(self._max_qubit, max(op.qubits))
        ids = list(op.bits)
        if op.condition is not None:
            ids.append(op.condition)
        if ids:
            self._max_bit = max(self._max_bit, max(ids))

    def _close_handles(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
        if not self._info_handle.closed:
            self._info_handle.close()
        if not self._info_offsets_handle.closed:
            self._info_offsets_handle.close()

    def _cleanup(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)


def _write_packet(handle, payload_type: int, payload: bytes | bytearray) -> None:
    handle.write(PACKET_HEAD.pack(payload_type, len(payload)))
    handle.write(payload)


def _write_packet_file(handle, payload_type: int, path: str) -> None:
    size = os.path.getsize(path)
    handle.write(PACKET_HEAD.pack(payload_type, size))
    with open(path, "rb") as source:
        shutil.copyfileobj(source, handle, length=1024 * 1024)


def _write_info_packet(handle, count: int, offsets_path: str, chars_path: str) -> None:
    size = 8 + os.path.getsize(offsets_path) + os.path.getsize(chars_path)
    handle.write(PACKET_HEAD.pack(INFO, size))
    handle.write(struct.pack("<Q", count))
    with open(offsets_path, "rb") as source:
        shutil.copyfileobj(source, handle, length=1024 * 1024)
    with open(chars_path, "rb") as source:
        shutil.copyfileobj(source, handle, length=1024 * 1024)


def open_kmb(path: str, memory_budget_bytes: int) -> tuple[mmap.mmap, object]:
    """Map ``path`` read-only if it fits in the byte budget."""

    size = os.path.getsize(path)
    if size > memory_budget_bytes:
        raise OptimizeBudgetError(
            f"{path} is {size} bytes, above the memory budget of {memory_budget_bytes} bytes. "
            "No candidate was written."
        )
    handle = open(path, "rb")
    try:
        mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    except ValueError as exc:
        handle.close()
        raise KickmixFormatError(f"cannot map {path}: {exc}") from exc
    return mapped, handle


def transcribe_kmb(src: str, dst: str, memory_budget_bytes: int) -> GateCounts:
    """Copy a kmb through the reader and writer. Used to prove the codec."""

    mapped, handle = open_kmb(src, memory_budget_bytes)
    writer: KmbWriter | None = None
    try:
        view = _parse_kmb(mapped)
        writer = KmbWriter(dst, view.registers)
        for op in iter_kmb_ops(view):
            writer.emit(op)
        writer.close()
        return writer.counts
    except Exception:
        if writer is not None:
            writer.abort()
        if os.path.exists(dst):
            os.unlink(dst)
        raise
    finally:
        if "view" in locals():
            view.release()
        mapped.close()
        handle.close()


def read_kmx_ops(path: str, memory_budget_bytes: int):
    """Stream kmx instructions. Comments are dropped; they are not semantic."""

    size = os.path.getsize(path)
    if size > memory_budget_bytes:
        raise OptimizeBudgetError(
            f"{path} is {size} bytes, above the memory budget of {memory_budget_bytes} bytes. "
            "No candidate was written."
        )
    with open(path, "rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise KickmixFormatError(f"kmx line {line_number} is not utf-8") from exc
            if text.endswith("\n"):
                text = text[:-1]
            if text.endswith("\r"):
                text = text[:-1]
            body = _strip_comment(text).strip()
            if not body:
                continue
            try:
                yield _parse_kmx_instruction(body)
            except KickmixFormatError as exc:
                raise KickmixFormatError(f"kmx line {line_number}: {exc}") from exc


def write_kmx(path: str, ops) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for op in ops:
            handle.write(_format_kmx(op))
            handle.write("\n")


def _strip_comment(line: str) -> str:
    in_quote = False
    for index, char in enumerate(line):
        if char == '"':
            in_quote = not in_quote
        elif char == "#" and not in_quote:
            return line[:index]
    return line


def _tokenize(body: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    length = len(body)
    while index < length:
        while index < length and body[index] in " \t":
            index += 1
        if index >= length:
            break
        if body[index] == '"':
            end = index + 1
            while end < length and body[end] != '"':
                end += 1
            if end >= length:
                raise KickmixFormatError("unterminated quote")
            tokens.append(body[index : end + 1])
            index = end + 1
        else:
            end = index
            while end < length and body[end] not in " \t":
                end += 1
            tokens.append(body[index:end])
            index = end
    return tokens


def _qid(token: str) -> int:
    if len(token) < 2 or token[0] != "q" or not token[1:].isdigit():
        raise KickmixFormatError(f"expected a qubit id, got {token!r}")
    return int(token[1:])


def _bid(token: str) -> int:
    if len(token) < 2 or token[0] != "b" or not token[1:].isdigit():
        raise KickmixFormatError(f"expected a bit id, got {token!r}")
    return int(token[1:])


def _rid(token: str) -> int:
    if len(token) < 2 or token[0] != "r" or not token[1:].isdigit():
        raise KickmixFormatError(f"expected a register id, got {token!r}")
    return int(token[1:])


def _parse_kmx_instruction(body: str) -> Op:
    tokens = _tokenize(body)
    if not tokens:
        raise KickmixFormatError("empty instruction")
    name = tokens[0]
    rest = tokens[1:]
    condition: int | None = None
    if len(rest) >= 2 and rest[-2] == "if":
        condition = _bid(rest[-1])
        rest = rest[:-2]
    elif name == "PUSH_CONDITION":
        raise KickmixFormatError("PUSH_CONDITION needs a condition bit")
    if name in {"X", "Z", "R"}:
        if len(rest) != 1:
            raise KickmixFormatError(f"{name} needs 1 qubit")
        return Op(name=name, qubits=(_qid(rest[0]),), condition=condition)
    if name in {"CX", "CZ", "SWAP"}:
        if len(rest) != 2:
            raise KickmixFormatError(f"{name} needs 2 qubits")
        return Op(name=name, qubits=(_qid(rest[0]), _qid(rest[1])), condition=condition)
    if name in {"CCX", "CCZ", "CSWAP"}:
        if len(rest) != 3:
            raise KickmixFormatError(f"{name} needs 3 qubits")
        return Op(
            name=name,
            qubits=(_qid(rest[0]), _qid(rest[1]), _qid(rest[2])),
            condition=condition,
        )
    if name == "Z_POW":
        if len(rest) != 2:
            raise KickmixFormatError("Z_POW needs a qubit and an exponent")
        return Op(
            name="Z_POW",
            qubits=(_qid(rest[0]),),
            angle=parse_half_turns(rest[1]),
            condition=condition,
        )
    if name == "NEG":
        if rest:
            raise KickmixFormatError("NEG takes no targets")
        return Op(name="NEG", condition=condition)
    if name == "POP_CONDITION":
        if rest or condition is not None:
            raise KickmixFormatError("POP_CONDITION takes no arguments")
        return Op(name="POP_CONDITION")
    if name == "PUSH_CONDITION":
        if rest or condition is None:
            raise KickmixFormatError("PUSH_CONDITION takes only a condition")
        return Op(name="PUSH_CONDITION", condition=condition)
    if name == "HMR":
        if len(rest) != 2:
            raise KickmixFormatError("HMR needs a qubit and a bit")
        return Op(name="HMR", qubits=(_qid(rest[0]),), bits=(_bid(rest[1]),), condition=condition)
    if name in {"BIT_INVERT", "BIT_STORE0", "BIT_STORE1"}:
        if len(rest) != 1:
            raise KickmixFormatError(f"{name} needs 1 bit")
        return Op(name=name, bits=(_bid(rest[0]),), condition=condition)
    if name == "INFO_TAG":
        if condition is not None or len(rest) != 1 or not rest[0].startswith('"'):
            raise KickmixFormatError("INFO_TAG needs one quoted string")
        return Op(name="INFO_TAG", info=_unescape_quote(rest[0]), quote=rest[0])
    if name == "REGISTER":
        if condition is not None or not rest or len(rest) > 2:
            raise KickmixFormatError("REGISTER needs a register id and an optional name")
        quote = rest[1] if len(rest) == 2 else None
        if quote is not None and not quote.startswith('"'):
            raise KickmixFormatError("REGISTER name must be quoted")
        return Op(name="REGISTER", register=_rid(rest[0]), quote=quote)
    if name == "APPEND_TO_REGISTER":
        if condition is not None or len(rest) != 2:
            raise KickmixFormatError("APPEND_TO_REGISTER needs a qubit or bit and a register")
        if rest[0].startswith("q"):
            return Op(name="APPEND_TO_REGISTER", qubits=(_qid(rest[0]),), register=_rid(rest[1]))
        return Op(name="APPEND_TO_REGISTER", bits=(_bid(rest[0]),), register=_rid(rest[1]))
    if name == "DEBUG_PRINT":
        if len(rest) > 1:
            raise KickmixFormatError("DEBUG_PRINT takes at most one target")
        if not rest:
            return Op(name="DEBUG_PRINT", condition=condition)
        token = rest[0]
        if token.startswith("q"):
            return Op(name="DEBUG_PRINT", qubits=(_qid(token),), condition=condition)
        if token.startswith("b"):
            return Op(name="DEBUG_PRINT", bits=(_bid(token),), condition=condition)
        if token.startswith("r"):
            return Op(name="DEBUG_PRINT", register=_rid(token), condition=condition)
        raise KickmixFormatError(f"bad DEBUG_PRINT target {token!r}")
    raise KickmixFormatError(f"unknown instruction {name}")


def _unescape_quote(token: str) -> bytes:
    """Decode a kmx quoted string to the raw bytes stored in a kmb info packet.

    The kmx path keeps ``quote`` and re-emits it. The bytes are for kmb info
    tags that were produced by kickmix (no extra escaping layer in the binary).
    """

    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        raise KickmixFormatError("expected quoted text")
    inner = token[1:-1]
    out = bytearray()
    index = 0
    while index < len(inner):
        char = inner[index]
        if char != "\\":
            out.append(ord(char))
            index += 1
            continue
        if index + 1 >= len(inner):
            raise KickmixFormatError("dangling escape in quoted text")
        code = inner[index + 1]
        mapped = {"B": "\\", "Q": '"', "P": "#", "n": "\n", "r": "\r"}.get(code)
        if mapped is None:
            raise KickmixFormatError(f"bad escape \\{code}")
        out.extend(mapped.encode("utf-8"))
        index += 2
    return bytes(out)


def _format_kmx(op: Op) -> str:
    if op.name == "INFO_TAG":
        if not op.quote:
            raise KickmixFormatError("INFO_TAG is missing its quoted text")
        return f"INFO_TAG {op.quote}"
    if op.name == "REGISTER":
        if op.register is None:
            raise KickmixFormatError("REGISTER is missing an id")
        if op.quote:
            return f"REGISTER r{op.register} {op.quote}"
        return f"REGISTER r{op.register}"
    if op.name == "APPEND_TO_REGISTER":
        if op.register is None:
            raise KickmixFormatError("APPEND_TO_REGISTER is missing a register")
        if op.qubits:
            target = f"q{op.qubits[0]}"
        elif op.bits:
            target = f"b{op.bits[0]}"
        else:
            raise KickmixFormatError("APPEND_TO_REGISTER is missing a target")
        return f"APPEND_TO_REGISTER {target} r{op.register}"
    if op.name == "DEBUG_PRINT" and op.register is not None:
        line = f"DEBUG_PRINT r{op.register}"
        if op.condition is not None:
            line += f" if b{op.condition}"
        return line
    parts: list[str] = [op.name]
    if op.name == "Z_POW":
        if op.angle is None or len(op.qubits) != 1:
            raise KickmixFormatError("Z_POW cannot be formatted")
        parts.append(f"q{op.qubits[0]}")
        parts.append(format_half_turns(op.angle))
    else:
        parts.extend(f"q{qubit}" for qubit in op.qubits)
        parts.extend(f"b{bit}" for bit in op.bits)
    if op.condition is not None:
        parts.append("if")
        parts.append(f"b{op.condition}")
    if op.name in {"NEG", "POP_CONDITION", "DEBUG_PRINT"} and len(parts) == 1:
        return op.name
    return " ".join(parts)
