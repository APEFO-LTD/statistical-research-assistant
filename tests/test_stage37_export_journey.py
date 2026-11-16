"""Stage 37 (#67): the flow of the packaged-program journey `export-data`,
through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. This test walks the same flow in the workspace harness
with the journey's own texts and helpers: at each point the text it waits
for and the button it presses (named by its label) are there; the file the
Save dialog gives is written, and the journey's own check (`check_export`:
openpyxl, pyreadstat, pandas, every cell against the fixture as the driver
reads it with the csv module) accepts it. The program cannot show a
disabled button as disabled on Windows (UI Automation reports every button
as enabled), so nothing here relies on one. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

from test_stage368_acceptance import T, create_project_in_ui, label, on_screen, open_csv  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402

THE_EIGHTEEN = [
    "stage36-tasks", "stage36-charts", "stage36-groups", "project-a", "project-b", "import-30",
    "review-120", "responses", "blocked-design", "import-cope-docx", "import-scan-lv",
    "stage36-report", "import-damaged", "psychometrics", "import-resume", "negative-paths",
    "confirmations", "report-composition"]


def save_to(ws, target: Path):
    """The Save dialog of the journey: the file name typed is ``target``."""
    async def dialog(title, file_name, extension):
        ws.saved.append(target)
        return str(target)

    ws.app.save_dialog = dialog


class JourneyOrderTests(unittest.TestCase):
    def test_export_data_follows_the_eighteen_unchanged(self):
        self.assertEqual(list(e2e.JOURNEYS)[:18], THE_EIGHTEEN)
        # Merge-tolerant (review integration F1): other Stage 37 branches append
        # their journeys after the eighteen too, in an order the merge decides.
        self.assertIn("export-data", list(e2e.JOURNEYS)[18:])
        self.assertGreaterEqual(len(e2e.JOURNEYS), 19)
        self.assertIs(e2e.JOURNEYS["export-data"], e2e.journey_export_data)
        self.assertNotIn("export-data", e2e.STARTS_ITSELF)


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class _Clock:
    """Driver time without waiting: a look at the screen takes a second, as
    a UI Automation scan of the Results page does on the Windows runner."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _ResultsPage:
    """A scrolling page as the driver sees it through UI Automation: only
    what is inside the window is listed, a rectangle is where the element
    is now, and a click lands where it points. ``tail`` is the height below
    the Interpretation section's header; the Export card of Stage 37 adds
    its height to it (about 240 px, two rows and its folded options)."""

    VIEW_TOP, VIEW_BOTTOM = 115, 1005       # below the context bar, above the status line
    # A wheel notch scrolls 60 px: with it the first search for the note
    # (two wheel moves of five notches in its six seconds) scrolls the header
    # out of view on the longer page, as the failing run's screenshots show
    # (gui-e2e/steps/235-…: "Full report" at the top, the header above it).
    HEADER_AT, HEADER_HEIGHT, OPEN_HEIGHT, NOTCH = 400, 60, 700, 60

    def __init__(self, tail: int):
        self.tail, self.offset, self.open, self.clicks = tail, 0, False, []

    def length(self) -> int:
        return self.HEADER_AT + self.HEADER_HEIGHT + self.tail + \
            (self.OPEN_HEIGHT if self.open else 0)

    def items(self) -> list[tuple[str, str, int, int]]:
        found = [(e2e.T("results.interpretation") + "\n" + e2e.T("results.interpretation_hint"),
                  "Group", self.HEADER_AT, self.HEADER_HEIGHT)]
        if self.open:
            found.append((e2e.T("results.notes"), "Edit",
                          self.HEADER_AT + self.HEADER_HEIGHT + self.OPEN_HEIGHT - 80, 60))
        return found

    def screen_top(self, page_y: int) -> int:
        return self.VIEW_TOP + page_y - self.offset

    def wheel(self, clicks: int) -> None:
        most = max(0, self.length() - (self.VIEW_BOTTOM - self.VIEW_TOP))
        self.offset = min(most, max(0, self.offset - clicks * self.NOTCH))

    def click(self, x: int, y: int) -> None:
        self.clicks.append(y)
        top = self.screen_top(self.HEADER_AT)
        if self.VIEW_TOP <= y < self.VIEW_BOTTOM and top <= y < top + self.HEADER_HEIGHT:
            self.open = not self.open


class _Element:
    def __init__(self, page: _ResultsPage, name: str, kind: str, page_y: int, height: int):
        self.page, self.page_y, self.height = page, page_y, height
        self.element_info = self
        self.name, self.control_type = name, kind

    @property
    def rectangle(self):
        top = self.page.screen_top(self.page_y)
        return _Rect(700, top, 1800, top + self.height)

    def click_input(self):
        rect = self.rectangle
        self.page.click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)

    def expand(self):
        raise RuntimeError("no ExpandCollapse pattern")

    def invoke(self):
        raise RuntimeError("no Invoke pattern")


class _ModelGui(e2e.Gui):
    def __init__(self, page: _ResultsPage, clock: _Clock):
        self.page, self.clock = page, clock

    def window_box(self):
        return 0, 0, 1900, 1050

    def footer_top(self):
        return None

    def elements(self):
        self.clock.now += 1.0
        listed = []
        for name, kind, page_y, height in self.page.items():
            top = self.page.screen_top(page_y)
            if top + height > self.page.VIEW_TOP and top < self.page.VIEW_BOTTOM:
                listed.append(_Element(self.page, name, kind, page_y, height))
        return listed

    def wheel(self, clicks: int, at=None) -> None:
        self.page.wheel(clicks)
        self.clock.now += 0.35

    @staticmethod
    def value(element) -> str:
        return ""

    def dump(self, name):
        return None

    def shot(self, name):
        return None

    def log_screen(self, title):
        return None


class OpenInterpretationTests(unittest.TestCase):
    """PR #78's Windows failure, report-composition: "the Interpretation
    section did not open". The driver looked for the note first, which
    scrolls the page down, then clicked the header it had found before: on
    a page long enough to scroll the header out of view (the Results page
    with the Export card) the click landed above the content. A person sees
    the header and opens the section (the harness walk of the journey does
    that on the real page); the driver now finds the header again, scrolled
    into view, right before it presses it."""

    def walk(self, tail: int) -> _ResultsPage:
        from unittest import mock

        page, clock = _ResultsPage(tail), _Clock()
        with mock.patch.object(e2e, "time", clock):
            e2e.open_interpretation(_ModelGui(page, clock))
        return page

    def test_the_section_opens_on_the_page_without_the_export_card(self):
        self.assertTrue(self.walk(tail=800).open)

    def test_the_section_opens_on_the_longer_page_with_the_export_card(self):
        page = self.walk(tail=800 + 240)
        self.assertTrue(page.open)
        self.assertTrue(all(page.VIEW_TOP <= y < page.VIEW_BOTTOM for y in page.clicks),
                        f"every click inside the content: {page.clicks}")

    def test_an_open_section_is_not_closed(self):
        from unittest import mock

        page, clock = _ResultsPage(tail=1040), _Clock()
        page.open = True
        with mock.patch.object(e2e, "time", clock):
            e2e.open_interpretation(_ModelGui(page, clock))
        self.assertTrue(page.open)
        self.assertEqual(page.clicks, [])


class ExportDataJourneyTests(unittest.TestCase):
    """Journey `export-data`: .xlsx, .sav and .csv from the Data page."""

    def test_the_journey_flow_and_its_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work = root / "work"
            work.mkdir()
            csv_path = e2e.master_fixture(work / "stage37-master")
            source = e2e.master_source(csv_path)
            self.assertEqual((len(source["rows"]), len(source["header"])), (180, 98))
            ws = Workspace(root=root)
            try:
                create_project_in_ui(ws, e2e.EXPORT_PROJECT)
                open_csv(ws, csv_path)
                ws.click("nav-data")
                self.assertTrue(on_screen(ws, T("export.title.data")))
                self.assertEqual(label(ws, "export-save-data"), T("export.save.xlsx"))
                dropdown = ws.find("export-format-data", ft.Dropdown)
                self.assertEqual(dropdown.label, T("export.format"))
                self.assertEqual([o.text for o in dropdown.options], e2e.export_options())
                saved_prefix = T("export.saved", path="", rows="", columns="",
                                 signature="").split(":")[0]
                for kind, name in e2e.EXPORT_FILES:
                    target = work / name
                    if kind != "xlsx":
                        option = T(f"export.format.{kind}")
                        key = next(o.key for o in dropdown.options if o.text == option)
                        ws.choose("export-format-data", key)
                        dropdown = ws.find("export-format-data", ft.Dropdown)
                    if kind == "sav":
                        self.assertTrue(on_screen(ws, T("export.sav.limits")[:60]))
                    self.assertEqual(label(ws, "export-save-data"), T(f"export.save.{kind}"))
                    save_to(ws, target)
                    ws.click("export-save-data")
                    self.assertTrue(on_screen(ws, target.name), "wait_text(target.name)")
                    self.assertTrue(on_screen(ws, saved_prefix))
                    facts = e2e.check_export(target, kind, source)
                    self.assertEqual(facts["rows"], 180)
                    self.assertEqual(facts["cells"], 180 * 98)
                self.assertEqual(e2e.remembered_export(root / "settings.json"), "csv")
            finally:
                ws.close()
            again = Workspace(root=root)
            try:
                project = next(p for p in again.app.projects.projects()
                               if p.title == e2e.EXPORT_PROJECT)
                again.app.projects.open(project.id)
                again.click("nav-data")
                self.assertEqual(again.find("export-format-data", ft.Dropdown).value, "csv",
                                 "the last format is remembered after a restart")
                self.assertEqual(label(again, "export-save-data"), T("export.save.csv"))
            finally:
                again.close()

    def test_the_journey_check_finds_a_changed_cell(self):
        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            csv_path = e2e.master_fixture(root / "fixture")
            source = e2e.master_source(csv_path)
            ws = Workspace(root=root)
            try:
                open_csv(ws, csv_path)
                ws.click("nav-data")
                target = root / "changed.xlsx"
                save_to(ws, target)
                ws.click("export-save-data")
            finally:
                ws.close()
            e2e.check_export(target, "xlsx", source)
            book = load_workbook(target)
            book["Data"]["C2"] = 99
            book.save(target)
            with self.assertRaises(e2e.StepFailure):
                e2e.check_export(target, "xlsx", source)


if __name__ == "__main__":
    unittest.main()
