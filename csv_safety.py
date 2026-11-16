"""Formula protection of CSV text cells (Stage 37, issue #67).

A spreadsheet program that opens a CSV file treats a cell that begins with
``=``, ``+``, ``-`` or ``@`` as a formula, and a tab, a carriage return or a
line feed at the start of a cell can hide one (OWASP, "CSV Injection"). The
full-width forms ``＝ ＋ － ＠`` are treated the same way by some spreadsheet
programs. The CSV export therefore writes such a *text* cell with an
apostrophe before the character, as OWASP recommends. Numbers are never
changed: ``-5`` in a numeric column is written as ``-5``.

A cell does not only start at the beginning of a text. Excel opens a ``.csv``
by splitting on the list separator of Windows, which is ``;`` in Latvian and
Russian settings, and a reader that ignores quotes splits on every separator
and line break. So the rule looks at every place where *some* reader could
start a cell (review finding F1-separator-split): the beginning of the text
and every position after ``,``, ``;``, a tab, a carriage return or a line
feed, each time after any spaces and double quotes that follow. Where the
text there begins with a trigger (or with apostrophes followed by one), one
apostrophe is put in front of it: ``ok;=1+1`` is written ``ok;'=1+1`` and
`` =x`` is written `` '=x``.

The rule is reversible, so the program's own importer gives back exactly the
text that was exported:

* :func:`protect` adds one apostrophe at every such place that holds a
  trigger or apostrophes followed by one (``'=x`` is written ``''=x``);
* :func:`restore` removes one apostrophe at every such place that holds
  apostrophes followed by a trigger, and leaves every other text alone.

``restore(protect(text)) == text`` for every text: an apostrophe is neither
a separator, a space nor a quote, so adding or removing one never moves a
place where a cell could start. A text that has an apostrophe followed by
anything else (``'quoted'``) is written unchanged.

The importer (``data_loader``) applies :func:`restore` only when the file
written next to the CSV says that the program exported exactly this file
(its SHA-256) and names the rule: the codebook ``<name>_codebook.json`` (data
and questionnaire exports) or the transformation log ``<name>_steps.json``
(Data → Prepare). Files of the first rule (``owasp-leading-apostrophe-v1``,
the beginning of a text only) are restored with that rule. In a CSV from
anywhere else an apostrophe is the researcher's own text and stays.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")
SEPARATORS = frozenset(",;\t\r\n")       # where a reader may start a new cell
LEADING = frozenset(' "')                  # skipped at the start of a cell
RULE = "owasp-separator-apostrophe-v2"
RULE_V1 = "owasp-leading-apostrophe-v1"    # the first rule: the beginning of a text only
RULES = (RULE, RULE_V1)
CODEBOOK_FORMAT = "statistical-research-assistant-codebook"
CODEBOOK_SUFFIX = "_codebook.json"
PREPARATION_FORMAT = "statistical-research-assistant-prep-v1"
PREPARATION_SUFFIX = "_steps.json"
SIDECARS = ((CODEBOOK_SUFFIX, CODEBOOK_FORMAT), (PREPARATION_SUFFIX, PREPARATION_FORMAT))
MAX_CODEBOOK_BYTES = 50 * 1024 * 1024
DESCRIPTION = ("at the start of a text and after every , ; tab, carriage return or line feed "
               "(each time after any spaces and double quotes), a text that begins with "
               "= + - @ (also full-width), a tab, a carriage return or a line feed, or with "
               "apostrophes followed by one, gets one apostrophe in front; numbers are never "
               "changed; remove one such apostrophe at each of those places to get the "
               "exported text back")

_TRIGGER = "".join(TRIGGERS)
_PROTECTED_V1 = re.compile(r"'+[=+\-@\t\r]")


def _armed(text: str, start: int, apostrophes: int) -> bool:
    """Whether ``text[start:]`` is at least ``apostrophes`` apostrophes,
    then possibly more, then a trigger."""
    end = start
    while end < len(text) and text[end] == "'":
        end += 1
    return end - start >= apostrophes and end < len(text) and text[end] in _TRIGGER


def _rewrite(text: str, add: bool) -> str:
    out: list[str] = []
    pending, index, size = True, 0, len(text)
    while index < size:
        ch = text[index]
        if pending and ch in LEADING:
            out.append(ch)
            index += 1
            continue
        if pending:
            pending = False
            if add and _armed(text, index, 0):
                out.append("'")
            elif not add and _armed(text, index, 1):
                index += 1                 # one apostrophe less
                continue
        out.append(ch)
        pending = ch in SEPARATORS
        index += 1
    return "".join(out)


def needs_protection(text: str) -> bool:
    return bool(text) and protect(text) != text


def protect(text: str) -> str:
    """``text`` as a CSV cell that no spreadsheet evaluates, however it splits it."""
    if not text or not any(c in _TRIGGER for c in text):
        return text
    return _rewrite(text, True)


def restore(text: str, rule: str = RULE) -> str:
    """The text :func:`protect` was given (``rule``: the rule the file names)."""
    if rule == RULE_V1:
        return text[1:] if _PROTECTED_V1.match(text) else text
    if not text or "'" not in text:
        return text
    return _rewrite(text, False)


def codebook_path(csv_path: Path) -> Path:
    """Where the CSV export writes its codebook: ``<stem>_codebook.json``."""
    csv_path = Path(csv_path)
    return csv_path.with_name(csv_path.stem + CODEBOOK_SUFFIX)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def exported_codebook(csv_path: Path, data: bytes | None = None) -> dict | None:
    """The codebook (or transformation log) of a CSV this program exported,
    when it vouches for exactly this file (SHA-256 and the protection rule);
    otherwise None."""
    csv_path = Path(csv_path)
    digest = None
    for suffix, expected in SIDECARS:
        sidecar = csv_path.with_name(csv_path.stem + suffix)
        try:
            if not sidecar.is_file() or sidecar.stat().st_size > MAX_CODEBOOK_BYTES:
                continue
            book = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(book, dict) or book.get("format") != expected:
            continue
        info = book.get("data_file")
        protection = info.get("formula_protection") if isinstance(info, dict) else None
        if not isinstance(protection, dict) or protection.get("rule") not in RULES:
            continue
        if digest is None:
            digest = (hashlib.sha256(data).hexdigest() if data is not None
                      else sha256_file(csv_path))
        if info.get("sha256") == digest:
            return book
    return None


def protect_frame(frame):
    """A copy of ``frame`` whose text cells and column names are protected
    (numbers, dates and missing values untouched), and how many cells changed."""
    copy = frame.copy()
    changed = 0
    for position in range(copy.shape[1]):
        values = copy.iloc[:, position]
        if values.dtype.kind in "biufcmM":       # numbers, booleans and dates
            continue
        needs = values.map(lambda v: isinstance(v, str) and needs_protection(v)).astype(bool)
        count = int(needs.sum())
        if count:
            protected = values.astype(object).where(
                ~needs, values[needs].map(protect).reindex(values.index))
            copy.isetitem(position, protected)
            changed += count
    names = [protect(str(c)) for c in copy.columns]
    changed += sum(1 for name, column in zip(names, copy.columns) if name != str(column))
    copy.columns = names
    return copy, changed


def book_rule(book: dict | None) -> str:
    """The protection rule a codebook or log names (the current one if none)."""
    info = (book or {}).get("data_file")
    protection = info.get("formula_protection") if isinstance(info, dict) else None
    rule = protection.get("rule") if isinstance(protection, dict) else None
    return rule if rule in RULES else RULE


def protected_cells(path: Path, delimiter: str = ",") -> int:
    """How many cells of a CSV carry the protection: exactly the cells that
    :func:`protect` changed, since only they hold apostrophes followed by a
    trigger where a cell could start."""
    import csv
    import io

    text = Path(path).read_text(encoding="utf-8-sig")
    return sum(1 for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
               for cell in row if restore(cell) != cell)


def data_file(path: Path, cells: int | None = None) -> dict:
    """What a codebook says about the CSV it describes (``data_file``)."""
    path = Path(path)
    cells = protected_cells(path) if cells is None else cells
    return {"name": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size,
            "format": "csv", "encoding": "utf-8",
            "formula_protection": {"rule": RULE, "cells": int(cells),
                                   "description": DESCRIPTION}}


def sidecar_name(csv_path: Path, book: dict) -> str:
    """The file name of the codebook or log that vouched for ``csv_path``."""
    csv_path = Path(csv_path)
    suffix = next((s for s, f in SIDECARS if f == book.get("format")), CODEBOOK_SUFFIX)
    return csv_path.stem + suffix
