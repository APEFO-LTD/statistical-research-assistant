"""Stage 37 integration: what the feature branches do together.

Each branch tests its own work; these tests check the seams between them on
the integrated tree (docs/STAGE37_INTEGRATION.md):

* 0b × methods: the confirmations of a path model (methods' scopes for the
  moderated path of Model 7 or 14) decide 0b's design step of a task, and
  the Word report holds 0b's hypothesis rows and methods' path-model results
  side by side.
* export × 0b and methods: the Results workbook keeps methods' path-model
  quantities unrounded with their bootstrap seed and 0b's hypothesis
  snapshot in its provenance; the reproducibility bundle's Word report holds
  0b's hypothesis rows.
* library × export: the research library's backup choice (in the library
  folder) and the export choices (in the preferences file) are separate; the
  reproducibility bundle never carries the library, whatever the backup
  choice, while a .sra backup carries it only when chosen.
* UX × export and library: the export choices live in the one settings file
  (key ``export``), migrated from an earlier build's ``preferences.json``
  without loss and with Russian kept; Settings → *Export defaults* shows and
  changes the choices the Export cards use; Settings → *Research library and
  privacy* shows the library's real backup choice, search backend and the
  state of *Ask with sources*.

Synthetic data only.
"""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from docx import Document  # noqa: E402

import research_report as rr  # noqa: E402
import research_workflow as rw  # noqa: E402
from test_process_workspace import ROLES, session_for, synthetic  # noqa: E402
from test_stage37_ui import H1, Case, run_correlations  # noqa: E402
from workspace_methods import (  # noqa: E402
    METHODS, confirmation_scope, default_options, required_confirmations, run_method,
)
from workspace_state import ResearchTask  # noqa: E402

MEDIATION_ROLES = {"x": "UCLA", "mediators": ["SocialJoining"], "y": "AssertiveAction",
                   "covariates": ["Age"]}


def path_task(session, model: str) -> ResearchTask:
    """A conditional-process task whose confirmations were given for ``model``."""
    roles = ROLES["conditional_process"]
    spec = METHODS["conditional_process"]
    options = {**default_options(spec), "method": model}
    needed = required_confirmations(spec, options)
    scopes = {c.key: confirmation_scope(c, "conditional_process", roles, options, session)
              for c in needed}
    return ResearchTask("t1", "Fictional path model", "process", dict(roles),
                        method="conditional_process", options=options,
                        confirms={c.key: True for c in needed},
                        state={"confirm_scopes": scopes})


class ConfirmationScopeTests(unittest.TestCase):
    """K1 of 0b (the design step counts the confirmations that hold) with the
    option-bound design confirmations of methods (review integration F1)."""

    def test_the_design_step_holds_only_for_the_model_confirmed(self):
        session = session_for(synthetic())
        task = path_task(session, "7")
        ready = rw.task_facts(task, session, method="conditional_process",
                              options={**task.options, "method": "7"})
        self.assertTrue(ready.design_ready)
        moved = rw.task_facts(task, session, method="conditional_process",
                              options={**task.options, "method": "14"})
        self.assertFalse(moved.design_ready, "Model 7's path confirmation is not Model 14's")

    def test_other_variables_clear_the_design_step(self):
        session = session_for(synthetic())
        task = path_task(session, "14")
        other = {**task.selection, "mediators": ["m2"]}
        facts = rw.task_facts(task, session, selection=other, method="conditional_process",
                              options=task.options)
        self.assertFalse(facts.design_ready, "given for m1, not for m2")


class TwoResults(Case):
    """H1's correlations (0b's link and snapshot) and a path model (methods)."""

    def two_results(self):
        ws, hid = self.planned()
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        session = ws.app.session
        correlation = session.results[-1]
        session.toggle_report(correlation.id)
        spec = METHODS["mediation"]
        options = {**default_options(spec), "resamples": "1000"}
        run = run_method("mediation", session, MEDIATION_ROLES, options,
                         {c.key: True for c in required_confirmations(spec, options)})
        mediation = session.add_result(run, (), method="mediation", roles=MEDIATION_ROLES,
                                       options=options)
        session.toggle_report(mediation.id)
        return ws, hid, correlation, mediation


class WordReportTests(TwoResults):
    """0b's Hypotheses section and evidence table next to methods' path model."""

    def test_the_report_holds_the_hypothesis_rows_and_the_path_model(self):
        ws, _, _, _ = self.two_results()
        ws.app.session.update_report(language="en")
        ws.run(ws.app.pages["reports"]._export_docx())
        document = Document(str(ws.saved[-1]))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("H1 (primary): " + H1, text)                       # 0b
        self.assertIn("result current, in this report.", text)            # 0b
        self.assertIn("Mediation (PROCESS-equivalent Model 4)", text)     # methods
        self.assertIn("not by the PROCESS macro", text)                   # methods
        tables = [[[c.text for c in row.cells] for row in table.rows] for table in document.tables]
        evidence = next(t for t in tables if tuple(t[0]) == rr.TEXT["en"]["evidence_columns"])
        self.assertEqual(len(evidence), 2, "H1 × its one result; the path model tests no H")
        cells = [c for t in tables for row in t for c in row]
        self.assertTrue(any(c.startswith("Indirect effect via SocialJoining") for c in cells),
                        "the path model's effects table")



class ExportTests(TwoResults):
    def test_the_results_workbook_keeps_the_path_model_and_the_hypothesis(self):
        from openpyxl import load_workbook

        ws, hid, correlation, mediation = self.two_results()
        ws.click("nav-results")
        ws.click("export-save-results")
        book = load_workbook(ws.saved[-1], read_only=True)
        self.addCleanup(book.close)
        self.assertEqual(len(book.sheetnames), 2 + 2, book.sheetnames)
        rows = {}
        for name in book.sheetnames[1:3]:
            for row in book[name].iter_rows(values_only=True):
                if len(row) > 1 and isinstance(row[0], str):
                    rows.setdefault(row[0], row[1])
        indirect = mediation.run.result.estimate("indirect:m0")
        self.assertEqual(rows["indirect:m0"], indirect.value, "unrounded (methods)")
        self.assertEqual(rows["indirect:m0.ci_low"], indirect.ci_low)
        provenance = [row for row in book[book.sheetnames[-1]].iter_rows(values_only=True)
                      if row and row[0] in ("R1", "R2")]
        columns = next(row for row in book[book.sheetnames[-1]].iter_rows(values_only=True)
                       if row and row[0] == "Result")
        by = {row[0]: dict(zip(columns, row)) for row in provenance}
        self.assertEqual(json.loads(by["R1"]["Hypothesis (JSON)"])["id"], hid, "0b's snapshot")
        self.assertEqual(json.loads(by["R2"]["Seeds (JSON)"])["resamples"], 1000)
        self.assertIn("seed", json.loads(by["R2"]["Seeds (JSON)"]))

    def test_the_bundle_word_report_holds_the_hypothesis_rows(self):
        ws, _, _, _ = self.two_results()
        ws.app.session.update_report(language="en")
        ws.click("nav-reports")
        ws.click("export-save-reports")
        with zipfile.ZipFile(ws.saved[-1]) as archive:
            name = next(n for n in archive.namelist()
                        if n.startswith("report/") and n.endswith(".docx"))
            document = Document(BytesIO(archive.read(name)))
            manifest = json.loads(archive.read("manifest.json"))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("H1 (primary): " + H1, text)
        self.assertIn("Mediation (PROCESS-equivalent Model 4)", text)
        self.assertEqual(len(manifest["analyses"]), 2)



class LibraryExportTests(unittest.TestCase):
    def test_the_backup_choice_and_the_export_bundle_do_not_collide(self):
        import library_fixtures as lfx
        import research_library as rl
        import stage36_fixtures as fx
        from test_workspace_library import picked
        from workspace_harness import Workspace

        ws = Workspace()
        self.addCleanup(ws.close)
        ws.click("nav-home")
        ws.type("project-new-title", "Fictional library and export study")
        ws.click("project-create")
        project = ws.app.projects.project
        ws.app.navigate("project")
        ws.click("project-library-open")
        page = ws.app.pages["library"]
        document = lfx.write(lfx.EN_NOTES, ws.root / "documents", "txt")
        self.assertTrue(ws.run(page.add_files(picked(document))))
        ws.check("library-backup", True)
        self.assertTrue(rl.travels(project.path))
        self.assertTrue(ws.run(ws.app.load_path(str(fx.fixture(fx.CSV)))))
        ws.click("nav-data")
        ws.choose("export-format-data", "bundle")
        ws.click("export-save-data")
        with zipfile.ZipFile(ws.saved[-1]) as archive:
            names = archive.namelist()
        self.assertTrue(any(n.startswith("data/") for n in names), names)
        self.assertFalse([n for n in names if "library" in n.lower()
                          or n.endswith((".sqlite3", "backup.json"))], names)
        # Each choice is kept where its own branch keeps it, untouched by the other.
        self.assertTrue(rl.travels(project.path), "exporting leaves the backup choice")
        remembered = json.loads((ws.root / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(remembered["export"]["formats"]["data"], "bundle")
        self.assertNotIn("library", json.dumps(remembered).lower())
        backup = ws.app.projects.store.export_package(project.id, ws.root / "with.sra")
        with zipfile.ZipFile(backup) as archive:
            self.assertIn("project/library/backup.json", archive.namelist())
        ws.app.navigate("library")
        ws.check("library-backup", False)
        self.assertFalse(rl.travels(project.path))
        self.assertEqual(json.loads((ws.root / "settings.json").read_text(encoding="utf-8")),
                         remembered, "the backup choice leaves the settings file")



class SettingsFileTests(unittest.TestCase):
    """Part 2 of the integration: app_preferences × user_settings × the hub."""

    EXPORT = {"formats": {"data": "sav", "results": "bundle"}, "csv_layout": "semicolon",
              "csv_bom": False}

    def workspace(self, root=None):
        from workspace_harness import Workspace

        ws = Workspace(root=root)
        self.addCleanup(ws.close)
        return ws

    def test_an_earlier_builds_choices_migrate_without_loss_and_russian_stays(self):
        import tempfile

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        legacy = root / "preferences.json"
        legacy.write_text(json.dumps({"language": "ru", "recent_files": [],
                                      "appearance": "windows", "export": self.EXPORT}),
                          encoding="utf-8")
        before = legacy.read_bytes()
        ws = self.workspace(root)
        stored = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["export"], self.EXPORT)
        self.assertEqual(stored["language"], "ru")
        self.assertEqual(ws.app.session.language, "ru")
        self.assertEqual(legacy.read_bytes(), before, "the old file is only read")
        ws.click("nav-data")
        self.assertEqual(ws.app.pages["data"].export.format, "sav")
        self.assertEqual(ws.app.pages["data"].export.layout, "semicolon")
        self.assertFalse(ws.app.pages["data"].export.bom)
        # Remembering a new choice writes only the export key: Russian stays.
        ws.app.pages["data"].export._choose("csv")
        stored = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["language"], "ru")
        self.assertEqual(stored["export"]["formats"], {"data": "csv", "results": "bundle"})
        self.assertEqual(stored["export"]["csv_layout"], "semicolon")

    def test_choices_written_by_an_earlier_build_after_the_settings_file_are_read(self):
        import tempfile

        import app_preferences
        import user_settings as us

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        settings = us.UserSettings.load(us.path_for(root), legacy=us.LegacySources())
        legacy = root / "preferences.json"
        legacy.write_text(json.dumps({"export": self.EXPORT}), encoding="utf-8")
        from unittest import mock

        with mock.patch.object(app_preferences, "preferences_path", lambda: legacy):
            self.assertEqual(app_preferences.export_preferences(settings=settings), self.EXPORT)
            app_preferences.remember_export({"csv_bom": True}, settings=settings)
        self.assertEqual(settings.stored("export"), {**self.EXPORT, "csv_bom": True})

    def test_the_start_interface_survives_the_other_writers_of_the_settings_file(self):
        # PR #79, startup-workspace: the start interface stayed "workspace".
        # Not a lost update: interleaved with the export choices (this
        # instance and the cards'), a second instance of the settings (the
        # launcher's window keeper) and the library choice, the start
        # interface chosen in Settings is kept, and so is every other key.
        import flet as ft

        import user_settings as us

        ws = self.workspace()
        ws.app.navigate("settings")
        other = us.UserSettings.load(ws.app.settings.path, migrate=False)   # read before
        ws.choose("settings-export-format-data", "sav")
        ws.app.set_start_interface("classic")
        other.update(window={"left": 10, "top": 20, "width": 1200, "height": 800})
        ws.app.pages["data"].export._choose("csv")
        ws.app.navigate("settings")
        self.assertEqual(ws.find("settings-start-interface", ft.Dropdown).value, "classic")
        stored = json.loads(ws.app.settings.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["start_interface"], "classic")
        self.assertEqual(stored["export"]["formats"], {"data": "csv"})
        self.assertEqual(stored["window"]["width"], 1200)
        self.assertEqual(us.UserSettings.load(ws.app.settings.path).get("start_interface"),
                         "classic")

    def test_the_export_defaults_section_is_the_cards_choices(self):
        ws = self.workspace()
        ws.app.navigate("settings")
        self.assertTrue(ws.find("settings-section-export"))
        self.assertEqual(ws.find("settings-export-format-data").value, "xlsx")
        self.assertEqual(ws.find("settings-export-csv-layout").value, "comma")
        self.assertTrue(ws.find("settings-export-csv-layout-note"))
        ws.choose("settings-export-format-data", "sav")
        ws.choose("settings-export-csv-layout", "semicolon")
        ws.check("settings-export-csv-bom", False)
        stored = json.loads(ws.app.settings.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["export"], {"formats": {"data": "sav"},
                                            "csv_layout": "semicolon", "csv_bom": False})
        ws.click("nav-data")
        card = ws.app.pages["data"].export
        self.assertEqual((card.format, card.layout, card.bom), ("sav", "semicolon", False))
        card._choose("csv")                                  # chosen on the card
        ws.app.navigate("settings")
        self.assertEqual(ws.find("settings-export-format-data").value, "csv")
        # Reset settings: the export defaults are settings too.
        ws.app.reset_settings()
        ws.app.navigate("settings")
        self.assertEqual(ws.find("settings-export-format-data").value, "xlsx")
        self.assertEqual(ws.app.pages["data"].export.format, "xlsx")

    def test_the_library_section_shows_and_changes_the_real_backup_choice(self):
        import research_library as rl

        ws = self.workspace()
        ws.app.navigate("settings")
        self.assertTrue(ws.find("settings-section-library"))
        self.assertTrue(ws.find("settings-library-no-project"))
        caps = rl.capabilities()
        self.assertIn(caps.sqlite, ws.find("settings-library-backend").value)
        ws.app.projects.create("Fictional privacy study")
        project = ws.app.projects.project
        ws.app.navigate("settings")
        self.assertFalse(ws.find("settings-library-backup").value, "off by default")
        ws.check("settings-library-backup", True)
        self.assertTrue(rl.travels(project.path))
        ws.app.navigate("library")
        self.assertTrue(ws.find("library-backup").value, "the Library page shows the same")
        ws.check("library-backup", False)
        ws.app.navigate("settings")
        self.assertFalse(ws.find("settings-library-backup").value)
        self.assertEqual(ws.find("settings-library-backup-note").value,
                         ws.app.t("library.backup_off"))


if __name__ == "__main__":
    unittest.main()
