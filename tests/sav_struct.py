"""An SPSS system file (.sav) reader and a minimal writer, written for the
tests from the file format's documentation (the GNU PSPP manual, "System
File Format"), with ``struct`` only: independent of pyreadstat/ReadStat,
which the program uses to write and read .sav files.

The reader handles what the program's exports contain: the header, variable
records (numeric, strings up to 255 bytes with their continuation records,
very long strings split into 255-byte segments), value labels (record 3/4
and, for long strings, 7/21), documents (record 6), the machine records 7/3
and 7/4, variable display (7/11, the measurement level), long names (7/13),
very long strings (7/14), the character encoding (7/20), long string
missing values (7/22), and the data, uncompressed or bytecode-compressed.
Synthetic data only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct

SYSMIS = -1.7976931348623157e308       # -DBL_MAX, the system-missing value
HIGHEST = 1.7976931348623157e308
LOWEST = -1.7976931348623155e308       # the next double above -DBL_MAX
MEASURES = {0: "unknown", 1: "nominal", 2: "ordinal", 3: "scale"}


@dataclass
class SavVariable:
    short: bytes                       # the 8-byte name field, spaces stripped
    width: int                         # 0 numeric, else the string width in bytes
    label: bytes | None = None
    missing: list = field(default_factory=list)   # numbers, ("range", lo, hi) or bytes
    missing_raw: list = field(default_factory=list)  # 8-byte missing value fields as written
    print_format: int = 0
    slots: int = 1                     # 8-byte data slots
    long_name: str = ""
    measure: str = "unknown"
    value_labels: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)  # very long strings: the segment variables


@dataclass
class SavFile:
    layout: int
    compression: int
    cases: int
    bias: float
    file_label: bytes
    records: list                      # every type-2 record, continuation records left out
    variables: list                    # after very long strings are put together
    encoding: str
    documents: list
    rows: list = field(default_factory=list)   # values per variable, in dictionary order

    def by_name(self) -> dict[str, SavVariable]:
        return {v.long_name: v for v in self.variables}

    def column(self, name: str) -> list:
        index = [v.long_name for v in self.variables].index(name)
        return [row[index] for row in self.rows]


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def take(self, size: int) -> bytes:
        if self.at + size > len(self.data):
            raise ValueError("the file ends inside a record")
        chunk = self.data[self.at:self.at + size]
        self.at += size
        return chunk

    def int32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def float64(self) -> float:
        return struct.unpack("<d", self.take(8))[0]


def _pad(size: int, unit: int) -> int:
    return (size + unit - 1) // unit * unit


def read_sav(data: bytes, encoding: str | None = None) -> SavFile:
    """The dictionary and the data of a little-endian .sav file."""
    r = _Reader(data)
    signature = r.take(4)
    if signature not in (b"$FL2", b"$FL3"):
        raise ValueError(f"not a system file: {signature!r}")
    r.take(60)
    layout, _nominal, compression, _weight, cases = (r.int32() for _ in range(5))
    bias = r.float64()
    r.take(9 + 8)
    file_label = r.take(64).rstrip(b" ")
    r.take(3)
    records: list[SavVariable] = []
    slot_owner: list[int] = []         # dictionary index (1-based) -> record position
    documents: list[bytes] = []
    pending_labels: list = []
    extensions: dict[int, list[bytes]] = {}
    while True:
        kind = r.int32()
        if kind == 2:
            width = r.int32()
            has_label, n_missing, print_format, _write = r.int32(), r.int32(), r.int32(), \
                r.int32()
            name = r.take(8).rstrip(b" ")
            label = None
            if has_label:
                size = r.int32()
                label = r.take(_pad(size, 4))[:size]
            raw = [r.take(8) for _ in range(abs(n_missing))]
            if width == -1:            # a continuation of the previous string
                records[-1].slots += 1
                slot_owner.append(len(records) - 1)
                continue
            variable = SavVariable(name, width, label, missing_raw=raw,
                                   print_format=print_format)
            if width == 0:
                values = [struct.unpack("<d", m)[0] for m in raw]
                if n_missing < 0:
                    variable.missing = [("range", values[0], values[1]), *values[2:]]
                else:
                    variable.missing = values
            else:
                variable.missing = raw
            records.append(variable)
            slot_owner.append(len(records) - 1)
        elif kind == 3:
            count = r.int32()
            labels = []
            for _ in range(count):
                value = r.take(8)
                size = r.take(1)[0]
                text = r.take(_pad(size + 1, 8) - 1)[:size]
                labels.append((value, text))
            if r.int32() != 4:
                raise ValueError("a value label record without its variable record")
            indexes = [r.int32() for _ in range(r.int32())]
            pending_labels.append((labels, indexes))
        elif kind == 6:
            documents = [r.take(80) for _ in range(r.int32())]
        elif kind == 7:
            subtype, size, count = r.int32(), r.int32(), r.int32()
            extensions.setdefault(subtype, []).append(r.take(size * count))
        elif kind == 999:
            r.int32()
            break
        else:
            raise ValueError(f"unknown record type {kind}")
    names_encoding = encoding or _encoding(extensions)
    for variable in records:
        variable.long_name = variable.short.decode(names_encoding)
    for labels, indexes in pending_labels:
        for index in indexes:
            variable = records[slot_owner[index - 1]]
            for value, text in labels:
                key = struct.unpack("<d", value)[0] if variable.width == 0 else \
                    value.rstrip(b" ")
                variable.value_labels[key] = text.decode(names_encoding)
    for chunk in extensions.get(13, []):
        for pair in chunk.split(b"\t"):
            short, _, long = pair.partition(b"=")
            for variable in records:
                if variable.short == short:
                    variable.long_name = long.decode(names_encoding)
    variables = list(records)
    for chunk in extensions.get(14, []):
        for item in chunk.split(b"\x00\t"):
            item = item.strip(b"\x00\t")
            if not item:
                continue
            short, _, width = item.partition(b"=")
            first = next(i for i, v in enumerate(variables) if v.short == short)
            total = int(width)
            count = (total + 251) // 252
            head = variables[first]
            head.segments = variables[first:first + count]
            head.width = total
            del variables[first + 1:first + count]
    by_long = {v.long_name: v for v in variables}
    for chunk in extensions.get(11, []):
        values = struct.unpack(f"<{len(chunk) // 4}i", chunk)
        step = len(values) // len(records) if records else 3
        for position, variable in enumerate(records):
            measure = values[position * step]
            variable.measure = MEASURES.get(measure, "unknown")
    for chunk in extensions.get(21, []):
        _long_labels(chunk, by_long, names_encoding)
    for chunk in extensions.get(22, []):
        _long_missing(chunk, by_long, names_encoding)
    sav = SavFile(layout, compression, cases, bias, file_label, records, variables,
                  names_encoding, documents)
    sav.rows = _data(data[r.at:], records, variables, compression, cases, bias)
    return sav


def _encoding(extensions: dict[int, list[bytes]]) -> str:
    for chunk in extensions.get(20, []):
        name = chunk.decode("ascii").strip().lower()
        return {"utf-8": "utf-8", "windows-1251": "cp1251",
                "windows-1257": "cp1257"}.get(name, name)
    return "utf-8"


def _long_labels(chunk: bytes, by_long: dict, encoding: str) -> None:
    r = _Reader(chunk)
    while r.at < len(chunk):
        name = r.take(r.int32()).decode(encoding)
        _width = r.int32()
        for _ in range(r.int32()):
            value = r.take(r.int32()).rstrip(b" ")
            label = r.take(r.int32()).decode(encoding)
            if name in by_long:
                by_long[name].value_labels[value] = label


def _long_missing(chunk: bytes, by_long: dict, encoding: str) -> None:
    r = _Reader(chunk)
    while r.at < len(chunk):
        name = r.take(r.int32()).decode(encoding)
        count = r.take(1)[0]
        size = r.int32()
        values = [r.take(size) for _ in range(count)]
        if name in by_long:
            by_long[name].missing = values


def _slots(data: bytes, compression: int, bias: float, total: int):
    """Every 8-byte slot of the data, as bytes (numbers) or bytes (text)."""
    if compression == 0:
        for at in range(0, min(len(data), total * 8), 8):
            yield data[at:at + 8]
        return
    if compression != 1:
        raise ValueError("only bytecode compression is read here")
    at, produced = 0, 0
    while produced < total and at + 8 <= len(data):
        codes, at = data[at:at + 8], at + 8
        for code in codes:
            if produced >= total:
                break
            if code == 0:
                continue
            if code == 252:
                return
            if code == 253:
                yield data[at:at + 8]
                at += 8
            elif code == 254:
                yield b" " * 8
            elif code == 255:
                yield struct.pack("<d", SYSMIS)
            else:
                yield struct.pack("<d", code - bias)
            produced += 1


def _data(data: bytes, records: list, variables: list, compression: int, cases: int,
          bias: float) -> list:
    per_case = sum(v.slots for v in records)
    if cases < 0:
        cases = len(data) // (per_case * 8) if compression == 0 else 10 ** 9
    slots = _slots(data, compression, bias, per_case * cases)
    rows = []
    while len(rows) < cases:
        raw: list = []
        try:
            for variable in records:
                chunks = [next(slots) for _ in range(variable.slots)]
                raw.append(b"".join(chunks))
        except StopIteration:
            break
        values = {}
        for variable, chunk in zip(records, raw):
            if variable.width == 0:
                number = struct.unpack("<d", chunk)[0]
                values[id(variable)] = None if number == SYSMIS else number
            else:
                values[id(variable)] = chunk[:variable.width]
        row = []
        for variable in variables:
            if variable.segments:
                text = b"".join(values[id(s)][:252] if i < len(variable.segments) - 1
                                else values[id(s)] for i, s in enumerate(variable.segments))
                row.append(text[:variable.width])
            else:
                row.append(values[id(variable)])
        rows.append(row)
    return rows


def text_value(raw: bytes | None, encoding: str = "utf-8") -> str | None:
    """A string value as a reader sees it: trailing spaces are padding."""
    return None if raw is None else raw.rstrip(b" ").decode(encoding)


# ================================================================== writer
def minimal_sav(*, short: bytes = b"V1", long_name: str = "V1", codepage: int = 65001,
                encoding: bytes = b"UTF-8", value: float = 1.0, name_encoding: str = "utf-8",
                label: bytes | None = None) -> bytes:
    """A one-variable, one-case uncompressed system file, written byte by
    byte as the format's documentation describes it (for import tests)."""
    out = bytearray()
    out += b"$FL2" + b"@(#) SPSS DATA FILE minimal test writer".ljust(60, b" ")
    out += struct.pack("<iiiii", 2, 1, 0, 0, 1) + struct.pack("<d", 100.0)
    out += b"01 Jan 26" + b"00:00:00" + b"".ljust(64, b" ") + b"\x00\x00\x00"
    out += struct.pack("<iiiiii", 2, 0, 1 if label else 0, 0, 0x050800, 0x050800)
    out += short.ljust(8, b" ")
    if label:
        out += struct.pack("<i", len(label)) + label.ljust(_pad(len(label), 4), b" ")
    out += struct.pack("<iiii", 7, 3, 4, 8) + struct.pack("<8i", 1, 0, 0, -1, 1, 1, 2, codepage)
    out += struct.pack("<iiii", 7, 4, 8, 3) + struct.pack("<ddd", SYSMIS, HIGHEST, LOWEST)
    out += struct.pack("<iiii", 7, 11, 4, 3) + struct.pack("<iii", 3, 8, 1)
    pair = short + b"=" + long_name.encode(name_encoding)
    out += struct.pack("<iiii", 7, 13, 1, len(pair)) + pair
    out += struct.pack("<iiii", 7, 20, 1, len(encoding)) + encoding
    out += struct.pack("<ii", 999, 0)
    out += struct.pack("<d", value)
    return bytes(out)
