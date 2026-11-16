"""A worksheet reader for the tests, with zipfile and ElementTree only:
independent of openpyxl, which the program uses to write (and check) its
.xlsx files. It reads the workbook's sheet names, the shared and inline
strings, the number formats of the styles (to tell a date serial from a
number) and every cell of a sheet as (type, value). Synthetic data only.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
BUILTIN_DATES = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}


class Workbook:
    def __init__(self, path):
        self.archive = zipfile.ZipFile(path)
        workbook = ET.fromstring(self.archive.read("xl/workbook.xml"))
        rels = ET.fromstring(self.archive.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels.findall("rel:Relationship", NS)}
        self.sheets = {}
        for sheet in workbook.find("m:sheets", NS):
            target = targets[sheet.get(f"{{{NS['r']}}}id")].lstrip("/")
            self.sheets[sheet.get("name")] = target if target.startswith("xl/") \
                else "xl/" + target
        self.shared = self._shared()
        self.date_styles = self._date_styles()

    def close(self):
        self.archive.close()

    def _text(self, element) -> str:
        return "".join(t.text or "" for t in element.iter(f"{{{NS['m']}}}t"))

    def _shared(self) -> list[str]:
        try:
            root = ET.fromstring(self.archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        return [self._text(si) for si in root.findall("m:si", NS)]

    def _date_styles(self) -> set[int]:
        try:
            root = ET.fromstring(self.archive.read("xl/styles.xml"))
        except KeyError:
            return set()
        custom = {}
        formats = root.find("m:numFmts", NS)
        for fmt in (formats if formats is not None else []):
            code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", fmt.get("formatCode", ""))
            custom[int(fmt.get("numFmtId"))] = bool(re.search(r"[dmyhs]", code, re.I))
        found = set()
        xfs = root.find("m:cellXfs", NS)
        for index, xf in enumerate(xfs if xfs is not None else []):
            number = int(xf.get("numFmtId", "0"))
            if number in BUILTIN_DATES or custom.get(number):
                found.add(index)
        return found

    def raw_xml(self, sheet: str) -> str:
        return self.archive.read(self.sheets[sheet]).decode("utf-8")

    def cells(self, sheet: str) -> dict[tuple[int, int], tuple[str, object]]:
        """{(row, column): (type, value)}, both 1-based. Types: "s" text,
        "n" number (int when whole), "d" a date serial (the number is kept),
        "b" boolean, "f" a formula (never expected), "e" an error."""
        root = ET.fromstring(self.archive.read(self.sheets[sheet]))
        out = {}
        for c in root.iter(f"{{{NS['m']}}}c"):
            row, column = _position(c.get("r"))
            kind = c.get("t", "n")
            if c.find("m:f", NS) is not None:
                out[(row, column)] = ("f", c.find("m:f", NS).text)
                continue
            value = c.find("m:v", NS)
            if kind == "inlineStr":
                node = c.find("m:is", NS)
                out[(row, column)] = ("s", self._text(node) if node is not None else "")
            elif kind == "s":
                out[(row, column)] = ("s", self.shared[int(value.text)])
            elif kind == "str":
                out[(row, column)] = ("s", value.text or "")
            elif kind == "b":
                out[(row, column)] = ("b", value.text == "1")
            elif kind == "e":
                out[(row, column)] = ("e", value.text)
            elif value is not None:
                number = float(value.text)
                text = value.text
                if int(c.get("s", "0")) in self.date_styles:
                    out[(row, column)] = ("d", number)
                elif re.fullmatch(r"-?\d+", text):
                    out[(row, column)] = ("n", int(text))
                else:
                    out[(row, column)] = ("n", number)
        return out

    def rows(self, sheet: str) -> list[list]:
        """The sheet as rows of (type, value) or None, the header included."""
        cells = self.cells(sheet)
        if not cells:
            return []
        height = max(r for r, _ in cells)
        width = max(c for _, c in cells)
        return [[cells.get((r, c)) for c in range(1, width + 1)] for r in range(1, height + 1)]


def _position(reference: str) -> tuple[int, int]:
    letters, digits = re.fullmatch(r"([A-Z]+)(\d+)", reference).groups()
    column = 0
    for ch in letters:
        column = column * 26 + ord(ch) - 64
    return int(digits), column


def serial_to_datetime(serial: float) -> dt.datetime:
    """Excel's 1900 date system: serial 1 is 1900-01-01, serial 60 the
    1900-02-29 that never was, so 61 is 1900-03-01 (days counted from
    1899-12-30 for serials from 61 on)."""
    if serial < 61:
        raise ValueError(f"serial {serial} is ambiguous in the 1900 date system")
    days = int(serial // 1)
    seconds = round((serial - days) * 86400 * 1_000_000) / 1_000_000
    return dt.datetime(1899, 12, 30) + dt.timedelta(days=days, seconds=seconds)
