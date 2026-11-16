"""Stage 37 (#67, review finding D8): CSV exports never hand a spreadsheet a
formula.

A text cell that begins with ``=``, ``+``, ``-`` or ``@`` (or a tab or a
carriage return) is written with a leading apostrophe (OWASP "CSV
Injection"); numbers are never changed; the program's own importer removes
the apostrophe again when the codebook next to the CSV vouches for the file
(csv_safety). Covers the two CSV exports that existed before Stage 37: the
questionnaire responses (survey_storage) and the prepared dataset
(data_preparation). Synthetic data only.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import csv_safety  # noqa: E402
from data_loader import load_dataset_with_report  # noqa: E402

ATTACKS = ("=1+1", "+x", "-2+3", "@SUM(A1)", "=HYPERLINK(\"http://example.invalid\")")


def cells(path: Path) -> list[list[str]]:
    """The CSV as the cells a spreadsheet gets (quotes removed)."""
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


class RuleTests(unittest.TestCase):
    def test_every_trigger_gets_one_apostrophe_and_numbers_never_do(self):
        for text in (*ATTACKS, "\tTAB", "\rCR"):
            self.assertEqual(csv_safety.protect(text), "'" + text)
        for text in ("plain", "", "'quoted'", "007", "1,5", "[\"a\"]", "a=b", "x-y"):
            self.assertEqual(csv_safety.protect(text), text, text)

    def test_a_formula_after_a_separator_space_or_quote_is_protected_too(self):
        """Review F1-separator-split and F3: Excel in Latvian or Russian splits
        on ``;``, a reader that ignores quotes on every separator."""
        cases = {
            "ok;=1+1;x": "ok;'=1+1;x", "ok,=2+2,x": "ok,'=2+2,x", "a\t@x": "a\t'@x",
            " =spaced": " '=spaced", 'x;"=1': 'x;"\'=1', "a; -1": "a; '-1",
            "\uff1d1+1": "'\uff1d1+1", "ok;\uff0bx": "ok;'\uff0bx", "\nline": "'\nline",
            "a\n=b": "a\n'=b", "ok;'=x": "ok;''=x",
        }
        for text, protected in cases.items():
            self.assertEqual(csv_safety.protect(text), protected, repr(text))
            self.assertEqual(csv_safety.restore(protected), text, repr(text))

    def test_files_of_the_first_rule_are_restored_with_that_rule(self):
        self.assertEqual(csv_safety.restore("'=x", csv_safety.RULE_V1), "=x")
        self.assertEqual(csv_safety.restore("a;'=x", csv_safety.RULE_V1), "a;'=x")
        self.assertEqual(csv_safety.restore("a;'=x"), "a;=x")

    def test_restore_undoes_protect_for_every_text(self):
        generator = random.Random(37067)
        alphabet = "'=+-@\t\r\nab1 ,;\"ĀЖ\uff1d\uff20"
        samples = ["", "'", "''", "'=", "''=x", "'-", "'a", *ATTACKS]
        samples += ["".join(generator.choice(alphabet) for _ in range(generator.randint(0, 6)))
                    for _ in range(4000)]
        for text in samples:
            protected = csv_safety.protect(text)
            self.assertEqual(csv_safety.restore(protected), text, repr(text))
            self.assertFalse(protected[:1] in csv_safety.TRIGGERS, repr(text))
            for separator in ",;\t\r\n":
                for cell in protected.split(separator):
                    self.assertFalse(cell.lstrip(' "')[:1] in csv_safety.TRIGGERS,
                                     (repr(text), separator))

    def test_an_apostrophe_of_the_researcher_is_text_unless_the_codebook_vouches(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "elsewhere.csv"
            path.write_text("note\n'=kept as typed\nplain\n", encoding="utf-8")
            frame, _ = load_dataset_with_report(path)
            self.assertEqual(frame["note"].tolist(), ["'=kept as typed", "plain"])


def formula_cells(text: str, separator: str) -> list[str]:
    """The cells a reader that splits on ``separator`` gets that a
    spreadsheet would evaluate (after spaces and quotes; numbers aside)."""
    import re

    found = []
    for row in csv.reader(io.StringIO(text, newline=""), delimiter=separator):
        for cell in row:
            for piece in re.split(r"[\r\n]", cell):
                core = piece.lstrip(' "')
                if core[:1] in csv_safety.TRIGGERS and \
                        not re.fullmatch(r"[-+]?\d+([.,]\d+)?", core):
                    found.append(core)
    return found


class SeparatorSplitTests(unittest.TestCase):
    """Review F1-separator-split: no export gives any reader a formula cell,
    whichever separator it splits on."""

    TEXTS = ["ok;=1+1;x", "ok,=2+2,x", " =spaced", "a\t@x", "\uff1dSUM(A1)", "line\n=1",
             'q;"=HYPERLINK(1)', "plain"]

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame({"id": [f"r{i}" for i in range(len(self.TEXTS))],
                             "answer": self.TEXTS, "n": [-1.5, 2, 3, -4, 5, 6, 7, 8]})

    def test_no_formula_cell_in_the_data_export_or_the_prepared_csv(self):
        import data_export
        from data_preparation import save_prepared_dataset

        df = self.frame()
        with tempfile.TemporaryDirectory() as folder:
            outputs = []
            for layout in ("comma", "semicolon"):
                path = Path(folder) / f"{layout}.csv"
                data_export.write_csv(path, df, bom=False, layout=layout)
                outputs.append(path.read_text(encoding="utf-8"))
            prepared, _ = save_prepared_dataset(df, [], Path(folder) / "prepared.csv")
            outputs.append(prepared.read_text(encoding="utf-8-sig"))
            protected, _ = csv_safety.protect_frame(df)
            outputs.append(protected.to_csv(index=False))
            for text in outputs:
                for separator in (",", ";", "\t"):
                    self.assertEqual(formula_cells(text, separator), [], (separator, text))
            back, _ = load_dataset_with_report(prepared)
            self.assertEqual(back["answer"].tolist(), self.TEXTS)
            self.assertEqual(back["n"].tolist(), [-1.5, 2, 3, -4, 5, 6, 7, 8])

    def test_the_program_reads_both_layouts_back_exactly(self):
        import data_export

        df = self.frame()
        with tempfile.TemporaryDirectory() as folder:
            for layout in ("comma", "semicolon"):
                path = Path(folder) / f"{layout}.csv"
                book = data_export.build_codebook(df, "split")
                data_export.export_csv(path, df, book, bom=True, layout=layout)
                back, _ = load_dataset_with_report(path)
                self.assertEqual(back["answer"].tolist(), self.TEXTS, layout)

    def test_an_infinity_is_never_a_bare_cell_that_begins_with_minus(self):
        """Review F7: ``-inf`` unquoted is a formula to a spreadsheet."""
        import data_export

        df = pd.DataFrame({"x": [float("-inf"), 1.5, float("inf")]})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "inf.csv"
            data_export.write_csv(path, df, bom=False)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\r\n-inf", text)
            self.assertEqual(formula_cells(text, ","), [])


class SurveyExportTests(unittest.TestCase):
    """Questionnaire responses: Questionnaires → Export CSV + codebook."""

    def setUp(self):
        from survey_storage import create_survey

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "surveys"
        self.survey = create_survey(self.root, "Fictional formula check", "", [
            {"key": "comment", "prompt": "Any comment?", "kind": "short_text"},
            {"key": "change", "prompt": "Change in points", "kind": "number"},
        ])

    def export(self) -> tuple[Path, Path]:
        from survey_storage import save_survey_codebook, save_survey_csv, submit_response

        for text, number in zip(ATTACKS, (-5, -2.5, 3, 0, 1)):
            submit_response(self.root, self.survey.survey_id, {"comment": text, "change": number})
        submit_response(self.root, self.survey.survey_id, {"comment": "fine", "change": -1})
        folder = Path(self.tmp.name)
        written = save_survey_csv(self.root, self.survey.survey_id, folder / "pilot.csv")
        book = save_survey_codebook(self.root, self.survey.survey_id,
                                    csv_safety.codebook_path(written), data_file=written)
        return written, book

    def test_formula_text_is_written_as_text_and_numbers_unchanged(self):
        written, _ = self.export()
        rows = cells(written)
        header, body = rows[0], rows[1:]
        comments = [row[header.index("comment")] for row in body]
        self.assertEqual(comments, ["'" + text for text in ATTACKS] + ["fine"])
        changes = [row[header.index("change")] for row in body]
        self.assertEqual([float(c) for c in changes], [-5, -2.5, 3, 0, 1, -1],
                         "numbers are never changed (no apostrophe before -5)")
        self.assertFalse(any(c.startswith("'") for c in changes))

    def test_the_program_reads_back_exactly_what_was_answered(self):
        written, book = self.export()
        info = json.loads(book.read_text(encoding="utf-8"))
        self.assertEqual(info["data_file"]["formula_protection"]["rule"], csv_safety.RULE)
        self.assertEqual(info["questions"][0]["key"], "comment", "the codebook is as before")
        frame, report = load_dataset_with_report(written)
        self.assertEqual(frame["comment"].tolist(), [*ATTACKS, "fine"])
        self.assertTrue(any("Formula protection removed from 5" in w for w in report.warnings))

    def test_an_edited_csv_keeps_its_apostrophes(self):
        written, _ = self.export()
        written.write_text(written.read_text(encoding="utf-8-sig") + '"x","\'=edited",7\n',
                           encoding="utf-8-sig")
        frame, report = load_dataset_with_report(written)
        self.assertEqual(frame["comment"].iloc[0], "'=1+1", "the codebook no longer vouches")
        self.assertFalse(any("Formula protection" in w for w in report.warnings))


class ClassicSurveyExportTests(unittest.TestCase):
    """Review F2: the classic Survey panel's export (the default interface)
    writes the bound codebook too, through the one survey_storage helper."""

    setUp = SurveyExportTests.setUp

    def test_classic_survey_export_reads_back_exactly(self):
        from survey_storage import export_survey_responses, submit_response

        answers = ["-", "+371 20000000", "@home", "ok;=1+1"]
        for text in answers:
            submit_response(self.root, self.survey.survey_id, {"comment": text, "change": 1})
        out, book = export_survey_responses(self.root, self.survey.survey_id,
                                            Path(self.tmp.name) / "survey_responses.csv")
        self.assertEqual(book, csv_safety.codebook_path(out))
        info = json.loads(book.read_text(encoding="utf-8"))
        self.assertEqual(info["format"], csv_safety.CODEBOOK_FORMAT)
        self.assertEqual(info["data_file"]["sha256"], csv_safety.sha256_file(out))
        frame, _ = load_dataset_with_report(out)
        self.assertEqual(frame["comment"].tolist(), answers)

    def test_both_interfaces_export_with_the_helper(self):
        for module in ("survey_ui.py", "workspace_questionnaires.py"):
            source = (ROOT / module).read_text(encoding="utf-8")
            self.assertIn("export_survey_responses", source, module)
            self.assertNotIn("save_survey_codebook", source, module)


class PreparedExportTests(unittest.TestCase):
    """Data → Prepare → Save a new prepared CSV and transformation log."""

    def test_formula_text_and_header_are_protected_numbers_are_not(self):
        from data_preparation import save_prepared_dataset

        frame = pd.DataFrame({"answer": [*ATTACKS, "fine"], "=score": [-5, -1.5, 0, 2, 3, 4],
                              "code": ["007", "-01", "+3", "x", "y", "z"]})
        with tempfile.TemporaryDirectory() as folder:
            path, recipe = save_prepared_dataset(frame, [], Path(folder) / "prepared.csv")
            rows = cells(path)
            self.assertEqual(rows[0], ["answer", "'=score", "code"])
            self.assertEqual([r[0] for r in rows[1:]], ["'" + t for t in ATTACKS] + ["fine"])
            self.assertEqual([float(r[1]) for r in rows[1:]], [-5, -1.5, 0, 2, 3, 4])
            self.assertEqual([r[2] for r in rows[1:]], ["007", "'-01", "'+3", "x", "y", "z"])
            log = json.loads(recipe.read_text(encoding="utf-8"))
            self.assertEqual(log["format"], "statistical-research-assistant-prep-v1")
            self.assertEqual(log["data_file"]["formula_protection"]["rule"], csv_safety.RULE)
            back, _ = load_dataset_with_report(path)
            self.assertEqual(list(back.columns), ["answer", "=score", "code"])
            self.assertEqual(back["answer"].tolist(), [*ATTACKS, "fine"])
            self.assertEqual(back["code"].tolist(), ["007", "-01", "+3", "x", "y", "z"])


if __name__ == "__main__":
    unittest.main()
