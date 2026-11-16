"""Stage 37 (#67): export fidelity, checked with readers written for the tests.

The .xlsx files are read with zipfile and ElementTree (tests/xlsx_zip.py),
not openpyxl, which writes them; the .sav files with a struct-based reader
of the system-file dictionary and data (tests/sav_struct.py), not
pyreadstat/ReadStat, which writes them. Round trips on the synthetic
180-case master fixture plus adversarial values, and the review findings
SAV-1, SAV-2, SAV-3, X1, X2/X3 and integrity F1 (docs/STAGE37_EXPORT.md §10).
Synthetic data only.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import data_export as de  # noqa: E402
from data_loader import load_dataset_with_report  # noqa: E402
import sav_struct  # noqa: E402
from test_stage37_export import Fixture, RATING_LABELS, RU_NAME  # noqa: E402
import xlsx_zip  # noqa: E402

ADVERSARIAL_XLSX = {
    "control": ["Line one\x0bline two", "ok", "a\x01b", None],
    "long_text": ["x" * 40_000 + " END", "short", "", None],
    "huge": pd.array([2 ** 60 + 1, 1, -(2 ** 55), None], dtype="Int64"),
    "infinite": [float("-inf"), 0.1 + 0.2, float("inf"), float("nan")],
    "born": pd.Series([dt.date(1899, 12, 31), dt.date(1900, 2, 28), dt.date(1900, 3, 1),
                       dt.date(1850, 6, 1)], dtype=object),
    "stamp": pd.Series([dt.datetime(1899, 12, 31, 14), dt.datetime(2024, 5, 6, 7, 8, 9),
                        None, dt.datetime(1900, 1, 1)], dtype=object),
}


def expected_cell(value, kind: str):
    """What an exact .xlsx Data cell holds for ``value`` (None: no cell)."""
    if de.is_missing(value):
        return None
    if kind == "category":
        return ("s", de.as_text(value))
    if isinstance(value, str):
        return ("s", value)
    if isinstance(value, (bool, np.bool_)):
        return ("b", bool(value))
    if isinstance(value, (int, np.integer, float, np.floating)):
        return ("n", float(value))
    if isinstance(value, (dt.datetime, pd.Timestamp)):
        return ("d", pd.Timestamp(value).to_pydatetime())
    if isinstance(value, dt.date):
        return ("d", dt.datetime.combine(value, dt.time()))
    raise AssertionError(f"no expectation for {value!r}")


def assert_cell(case, cell, expected, where):
    if expected is None:
        case.assertTrue(cell is None or cell == ("s", ""), where)
        return
    case.assertIsNotNone(cell, where)
    kind, value = expected
    if kind == "d":
        case.assertEqual(cell[0], "d", where)
        read = xlsx_zip.serial_to_datetime(cell[1])
        case.assertLess(abs(read - value), dt.timedelta(milliseconds=1), where)
    elif kind == "n":
        case.assertEqual(cell[0], "n", where)
        case.assertEqual(float(cell[1]), value, ("exactly the double", where))
    else:
        case.assertEqual(cell, expected, where)


class XlsxIndependentReaderTests(Fixture):
    """The master fixture's Data sheet, cell by cell, read without openpyxl."""

    def test_every_cell_of_the_fixture_is_exact(self):
        path = self.folder / "data.xlsx"
        facts = de.export_xlsx(path, self.df, self.book)
        self.assertEqual(facts["verified"]["changed_cells"], 0)
        self.assertEqual(facts["changes"], [])
        book = xlsx_zip.Workbook(path)
        self.addCleanup(book.close)
        self.assertEqual(list(book.sheets), ["Data", "Codebook", "Scales"])
        rows = book.rows("Data")
        self.assertEqual([c[1] for c in rows[0]], [str(c) for c in self.df.columns])
        self.assertEqual(len(rows), 181)
        self.assertNotIn("<f", book.raw_xml("Data"), "no formula anywhere")
        for position, name in enumerate(self.df.columns):
            kind = de.column_kind(self.df[name])
            for index, value in enumerate(self.df[name]):
                cell = rows[index + 1][position] if position < len(rows[index + 1]) else None
                assert_cell(self, cell, expected_cell(value, kind), (name, index))

    def test_adversarial_values_are_exact_or_changed_as_planned(self):
        """X1, X2, X3, integrity F1: never a wrong date, every change listed."""
        df = pd.DataFrame(ADVERSARIAL_XLSX)
        plan = {(name, reason): count for name, reason, count in de.plan_xlsx(df)}
        self.assertEqual(plan, {("control", "cleaned"): 2, ("long_text", "cut"): 1,
                                ("huge", "big_integer"): 2, ("infinite", "infinity"): 2,
                                ("born", "old_date"): 3, ("stamp", "old_date"): 2})
        path = self.folder / "adversarial.xlsx"
        facts = de.export_xlsx(path, df, de.build_codebook(df, "adversarial"),
                               sections=("data",))
        self.assertEqual(facts["verified"]["changed_cells"], 12)
        book = xlsx_zip.Workbook(path)
        self.addCleanup(book.close)
        cells = book.cells("Data")
        column = {name: i for i, name in enumerate(df.columns, start=1)}
        self.assertEqual(cells[(2, column["control"])], ("s", "Line one�line two"))
        self.assertEqual(len(cells[(2, column["long_text"])][1]), de.XLSX_MAX_TEXT)
        self.assertEqual(cells[(2, column["huge"])], ("s", str(2 ** 60 + 1)))
        self.assertEqual(cells[(3, column["infinite"])], ("n", 0.30000000000000004),
                         "17 significant digits are kept (X3)")
        self.assertEqual(cells[(2, column["born"])], ("s", "1899-12-31"))
        self.assertEqual(cells[(3, column["born"])], ("s", "1900-02-28"),
                         "serials below 61 mean other days in other programs")
        self.assertEqual(xlsx_zip.serial_to_datetime(cells[(4, column["born"])][1]),
                         dt.datetime(1900, 3, 1))
        self.assertEqual(cells[(5, column["born"])], ("s", "1850-06-01"))
        self.assertEqual(cells[(2, column["stamp"])], ("s", "1899-12-31T14:00:00"))
        for (row, _), (kind, value) in cells.items():
            if kind in ("n", "d") and row > 1 and kind == "d":
                self.assertGreaterEqual(value, 61, "no date serial a program reads otherwise")

    def test_characters_lxml_refuses_do_not_stop_the_export(self):
        """Review X5: U+FFFE, U+FFFF and lone surrogates in a cell or a name."""
        df = pd.DataFrame({"a\ufffeb": ["x\uffffy", "lone \ud800 surrogate", "ok"]})
        path = self.folder / "xml.xlsx"
        facts = de.export_xlsx(path, df, de.build_codebook(df, "xml"), sections=("data",))
        self.assertEqual(facts["verified"]["changed_cells"], 2)
        book = xlsx_zip.Workbook(path)
        self.addCleanup(book.close)
        self.assertEqual(book.cells("Data")[(1, 1)], ("s", "a\ufffdb"))
        self.assertEqual(book.cells("Data")[(2, 1)], ("s", "x\ufffdy"))

    def test_dates_before_1900_survive_or_become_text(self):
        """The review's red test for X1, through openpyxl as the program reads."""
        from openpyxl import load_workbook

        born = [dt.date(1899, 12, 31), dt.date(1899, 12, 30), dt.date(1895, 3, 12)]
        df = pd.DataFrame({"born": pd.Series(born, dtype=object)})
        path = self.folder / "old.xlsx"
        de.export_xlsx(path, df, de.build_codebook(df, "old"), sections=("data",))
        ws = load_workbook(path)["Data"]
        for row, value in enumerate(born, start=2):
            self.assertIn(ws.cell(row=row, column=1).value,
                          (dt.datetime.combine(value, dt.time()), value.isoformat()))

    def test_a_cell_the_writer_changes_unplanned_fails_the_check(self):
        """integrity F1: the check compares contents, not only the row count."""
        df = pd.DataFrame({"answer": ["Line one\x0bline two", "x" * 40000, "ok"]})
        with tempfile.TemporaryDirectory() as folder:
            facts = de.export_xlsx(Path(folder) / "p.xlsx", df, de.build_codebook(df, "p"))
            self.assertEqual(facts["verified"].get("changed_cells"), 2)
            target = Path(folder) / "q.xlsx"
            from unittest import mock

            with mock.patch.object(de, "_CellWriter", _wrong_writer(de._CellWriter)):
                with self.assertRaises(de.VerificationFailed):
                    de.export_xlsx(target, df, de.build_codebook(df, "q"))
            self.assertFalse(target.exists())


def _wrong_writer(base):
    class Wrong(base):
        def __call__(self, value):
            if value == "ok":
                return self.text("ZZ")
            return super().__call__(value)
    return Wrong


class SavIndependentReaderTests(Fixture):
    """The master fixture's .sav, read without pyreadstat/ReadStat."""

    def test_dictionary_and_data_of_the_fixture(self):
        path = self.folder / "data.sav"
        plan = de.plan_sav(self.df, self.book)
        de.export_sav(path, self.df, self.book, plan=plan)
        sav = sav_struct.read_sav(path.read_bytes())
        self.assertEqual(sav.cases, 180)
        self.assertEqual(sav.encoding, "utf-8")
        names = [c.name for c in plan.columns]
        self.assertEqual([v.long_name for v in sav.variables], names)
        shorts = [r.short.decode("utf-8").casefold() for r in sav.records]
        self.assertEqual(len(set(shorts)), len(shorts), "short names unique without case")
        variables = sav.by_name()
        for column in plan.columns:
            variable = variables[column.name]
            values = sav.column(column.name)
            source = self.df[column.original]
            self.assertEqual(variable.measure, column.measure, column.name)
            label = (variable.label or b"").decode("utf-8")
            self.assertEqual(label, column.label, column.name)
            if column.kind in ("number", "boolean", "category", "empty"):
                self.assertEqual(variable.width, 0, column.name)
                written = de._sav_values(source, column)
                for got, want in zip(values, written):
                    if pd.isna(want):
                        self.assertIsNone(got, column.name)
                    else:
                        self.assertEqual(got, float(want), column.name)
                self.assertEqual(variable.value_labels,
                                 {float(k): v for k, v in column.value_labels.items()},
                                 column.name)
                numbers = [m for m in variable.missing if not isinstance(m, tuple)]
                self.assertEqual(numbers, [m for m in column.missing if not isinstance(m, dict)],
                                 column.name)
            elif column.kind in ("text", "mixed", "duration"):
                self.assertGreater(variable.width, 0, column.name)
                for got, want in zip(values, source):
                    text = "" if de.is_missing(want) else de.as_text(want)
                    self.assertEqual(sav_struct.text_value(got), text.rstrip(" "),
                                     column.name)
                if column.missing:
                    declared = variable.missing
                    self.assertEqual([d.rstrip(b" ").decode("utf-8") for d in declared],
                                     [str(m) for m in column.missing], column.name)
        rating = variables["rating"]
        self.assertEqual(rating.missing, [-9.0, -8.0])
        self.assertEqual(rating.value_labels, {float(k): v for k, v in RATING_LABELS.items()})
        ru = variables[plan.renamed[RU_NAME]]
        self.assertEqual([sav_struct.text_value(v) for v in sav.column(ru.long_name)][:3],
                         ["Да", "Нет", ""])
        notes = b"".join(sav.documents).decode("utf-8")
        self.assertIn("Data SHA-256: " + self.book.sha256, notes)

    def test_string_missing_codes_fit_the_written_width(self):
        """SAV-1: a code longer than the variable is not declared (a reader
        would compare only its first bytes: 'N/A' as 'N')."""
        df = pd.DataFrame({"smoker": ["Y", "N", "Y", None]})
        book = de.build_codebook(df, "t", metadata={"smoker": {"missing_codes": ["N/A"],
                                                               "source": "sav"}})
        plan = de.plan_sav(df, book)
        self.assertIn(("smoker", "export.change.missing_width"),
                      {(name, key) for name, key, _ in plan.changes})
        path = self.folder / "m.sav"
        de.export_sav(path, df, book, plan=plan)
        variable = sav_struct.read_sav(path.read_bytes()).by_name()["smoker"]
        self.assertEqual(variable.width, 1)
        for value in variable.missing_raw:
            self.assertEqual(value[variable.width:].strip(b" "), b"", variable.missing_raw)
        back = sav_struct.read_sav(path.read_bytes()).column("smoker")
        self.assertEqual([sav_struct.text_value(v) for v in back], ["Y", "N", "Y", ""])

    def test_a_label_code_longer_than_the_variable_is_left_out_and_listed(self):
        """SAV-6: pyreadstat sizes the variable by the code's characters, a
        reader keys the label on the code's first bytes."""
        df = pd.DataFrame({"answer": ["Да", "Да", None]})
        book = de.build_codebook(df, "t", metadata={"answer": {
            "value_labels": {"Да": "yes", "Нет": "no"}, "source": "sav"}})
        plan = de.plan_sav(df, book)
        self.assertIn(("answer", "export.change.value_label_width"),
                      {(name, key) for name, key, _ in plan.changes})
        path = self.folder / "l.sav"
        de.export_sav(path, df, book, plan=plan)
        variable = sav_struct.read_sav(path.read_bytes()).by_name()["answer"]
        self.assertEqual(variable.value_labels, {"Да".encode("utf-8"): "yes"})

    def test_short_names_are_unique_ignoring_case(self):
        """SAV-2: ReadStat's 8-byte short names differ only in case for
        non-ASCII names; SPSS and PSPP compare them case-insensitively."""
        for cols in (["Возраст", "возраст_группа"], ["Ēdiens_1", "ēdiens_2"],
                     ["Ārsts", "ārsts_2", "ĀRSTS_3"]):
            df = pd.DataFrame({c: [1.0, 2.0] for c in cols})
            path = self.folder / "n.sav"
            facts = de.export_sav(path, df, de.build_codebook(df, "t"))
            sav = sav_struct.read_sav(path.read_bytes())
            shorts = [r.short.decode("utf-8") for r in sav.records]
            self.assertEqual(len({s.casefold() for s in shorts}), len(shorts), shorts)
            self.assertEqual([v.long_name for v in sav.variables], cols, "long names kept")
            self.assertEqual(facts["verified"]["rows"], 2)
            frame, _ = load_dataset_with_report(path)
            self.assertEqual(list(frame.columns), cols)

    def test_random_name_sets_give_unique_short_names(self):
        rng = random.Random(3767)
        letters = "ĒēĀāŠšЖжВвОоaAbB_1"
        for _ in range(40):
            stems = ["".join(rng.choice(letters) for _ in range(rng.randint(3, 6)))
                     for _ in range(4)]
            names = list(dict.fromkeys(de.spss_names(
                [stem + suffix for stem in stems for suffix in ("_1", "_22")]).values()))
            df = pd.DataFrame({n: [1.0] for n in names})
            path = self.folder / "fuzz.sav"
            de.write_sav(path, df, de.build_codebook(df, "t"))
            sav = sav_struct.read_sav(path.read_bytes())
            shorts = [r.short.decode("utf-8").casefold() for r in sav.records]
            self.assertEqual(len(set(shorts)), len(shorts), names)
            self.assertEqual([v.long_name for v in sav.variables], names)

    def test_cp1251_name_with_ya_imports(self):
        """SAV-3: ReadStat refuses 0xFF ('я' in windows-1251) in the long names."""
        path = self.folder / "ru.sav"
        path.write_bytes(sav_struct.minimal_sav(long_name="имя", codepage=1251,
                                                encoding=b"windows-1251",
                                                name_encoding="cp1251"))
        frame, report = load_dataset_with_report(path)
        self.assertEqual(list(frame.columns), ["имя"])
        self.assertEqual(frame["имя"].tolist(), [1.0])
        self.assertTrue(any("long variable names" in w for w in report.warnings))
        for name in ("моя_оценка", "семья", "возраст"):
            path.write_bytes(sav_struct.minimal_sav(long_name=name, codepage=1251,
                                                    encoding=b"windows-1251",
                                                    name_encoding="cp1251"))
            frame, _ = load_dataset_with_report(path)
            self.assertEqual(list(frame.columns), [name])
        path.write_bytes(sav_struct.minimal_sav(long_name="A˙B", codepage=1257,
                                                encoding=b"windows-1257",
                                                name_encoding="cp1257"))
        frame, _ = load_dataset_with_report(path)
        self.assertEqual(list(frame.columns), ["A˙B"])

    def test_the_minimal_writer_is_a_valid_system_file(self):
        data = sav_struct.minimal_sav(long_name="age", value=42.0)
        sav = sav_struct.read_sav(data)
        self.assertEqual([v.long_name for v in sav.variables], ["age"])
        self.assertEqual(sav.rows, [[42.0]])
        self.assertEqual(struct.unpack("<d", data[-8:])[0], 42.0)
        self.assertTrue(math.isfinite(sav.bias))


if __name__ == "__main__":
    unittest.main()
