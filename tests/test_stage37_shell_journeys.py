"""Stage 37 (issue #68): the flows of the packaged-program journeys
`startup-workspace` and `settings-language`, through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. These tests start the program the way the launcher does
(``research_app.main``: no ``SRA_UI``, a data folder of its own, the
preferences file of earlier versions patched into it) and walk the same
flows, checking at each point that every text, button name, dropdown entry
and settings-file value the journey waits for is there, with the journey's
own texts and helpers. UI Automation reports every button as enabled, so
nothing here relies on a disabled state. Synthetic data only.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402

import app_preferences  # noqa: E402
from test_stage368_acceptance import T, folder_of  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import FakePage, Workspace  # noqa: E402


class Program(Workspace):
    """The program as the launcher starts it, on a fake page: the classic
    interface built and the start interface shown (the harness otherwise
    builds the workspace alone). ``restart()`` is a new start on the same
    data folder."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.temp = None
        self._closed = False
        self.saved = []
        self._patches = [
            mock.patch.dict(os.environ, {"SRA_DATA_DIR": str(self.root), "SRA_UI": ""}),
            mock.patch.object(app_preferences, "preferences_path",
                              lambda: self.root / "home" / "preferences.json"),
        ]
        for patch in self._patches:
            patch.start()
        self._start()

    def _start(self):
        import research_app
        from flet.controls.context import _context_page

        self.page = FakePage(1440)
        self._token = _context_page.set(self.page)
        asyncio.run(research_app.main(self.page))
        self._token_page = self.page

    @property
    def app(self):
        from workspace_shell import active_app

        return active_app()

    @property
    def in_workspace(self) -> bool:
        return getattr(self.page.controls[0], "data", None) == "workspace-root"

    def restart(self):
        self.stop()
        self._start()

    def stop(self):
        from flet.controls.context import _context_page

        app = self.app
        if app is not None:
            app.projects.close(clear=False)
        _context_page.reset(self._token)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop()
        import workspace_tokens

        workspace_tokens.apply_density(workspace_tokens.DEFAULT_DENSITY)
        for patch in reversed(self._patches):
            patch.stop()

    def names(self) -> list[str]:
        """Texts, button names and checkbox labels (what UI Automation lists)."""
        found = list(self.texts())
        for control in self.controls():
            content = getattr(control, "content", None)
            if isinstance(control, (ft.Button, ft.TextButton)):
                if isinstance(content, str):
                    found.append(content)
                elif isinstance(content, ft.Text) and isinstance(content.value, str):
                    found.append(content.value)
        return found

    def button(self, name: str):
        """The button UI Automation names ``name`` (its label)."""
        for control in self.controls():
            if isinstance(control, (ft.Button, ft.TextButton)):
                content = control.content
                label = content if isinstance(content, str) else getattr(content, "value", None)
                if label == name:
                    return control
        raise AssertionError(f"no button named {name!r}")

    def press(self, name: str):
        control = self.button(name)
        return self.dispatch(control.on_click, SimpleNamespace(control=control, data=None))

    def dropdown(self, label: str) -> ft.Dropdown:
        found = [c for c in self.controls() if isinstance(c, ft.Dropdown) and c.label == label]
        assert len(found) == 1, (label, found)
        return found[0]

    def pick(self, label: str, entry: str):
        """``gui.choose(label, entry)``: the entry named ``entry``."""
        field = self.dropdown(label)
        key = next(o.key for o in field.options if o.text == entry)
        field.value = key
        return self.dispatch(field.on_select, SimpleNamespace(control=field, data=key))


class StartupWorkspaceJourneyTests(unittest.TestCase):
    """Journey `startup-workspace`."""

    def test_the_normal_start_the_classic_interface_and_the_start_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            program = Program(Path(folder))
            self.addCleanup(program.close)
            disk = folder_of(Path(folder))

            # A normal start opens the research workspace (no SRA_UI).
            self.assertTrue(program.in_workspace)
            self.assertIn(T("project.create"), program.names(), "the journey's ready text")
            self.assertNotIn(e2e.CLASSIC_BANNER, program.names())
            self.assertIn(e2e.stored_settings(disk).get("start_interface"), (None, "workspace"))
            self.assertEqual(e2e.settings_file(disk), Path(folder) / "settings.json")
            classic_item = program.find("nav-classic")
            self.assertEqual(classic_item.content.controls[-1].value, T("nav.classic"))

            # The classic interface is one click away, and its Home leads back.
            program.click("nav-classic")
            self.assertFalse(program.in_workspace)
            self.assertIn(e2e.CLASSIC_BANNER, program.names())
            program.press(e2e.CLASSIC_OPEN_WORKSPACE)
            self.assertTrue(program.in_workspace)
            self.assertIn(T("project.create"), program.names())

            # Settings: the classic interface as the start interface (the index
            # chip "Start" leads to it).
            program.app.navigate("settings")
            self.assertIn(T("settings.section.start"), [
                c.content.controls[-1].value for c in program.find_all("settings-jump-")])
            field = program.dropdown(T("settings.start_interface"))
            self.assertEqual([o.text for o in field.options], e2e.START_OPTIONS)
            program.pick(T("settings.start_interface"), T("settings.start.classic"))
            self.assertEqual(e2e.stored_settings(disk)["start_interface"], "classic")

            # The next start opens the classic interface.
            program.restart()
            self.assertFalse(program.in_workspace)
            self.assertIn(e2e.CLASSIC_OPEN_WORKSPACE, program.names(), "the journey's ready text")
            self.assertIn(e2e.CLASSIC_BANNER, program.names())

            # The research workspace as the start interface again.
            program.press(e2e.CLASSIC_OPEN_WORKSPACE)
            program.app.navigate("settings")
            program.pick(T("settings.start_interface"), T("settings.start.workspace"))
            self.assertEqual(e2e.stored_settings(disk)["start_interface"], "workspace")
            program.restart()
            self.assertTrue(program.in_workspace)
            self.assertNotIn(e2e.CLASSIC_BANNER, program.names())


class SettingsLanguageJourneyTests(unittest.TestCase):
    """Journey `settings-language`."""

    def test_an_earlier_russian_preference_lv_after_a_restart_and_text_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disk = folder_of(root)
            legacy = root / "home" / "preferences.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps(e2e.UPGRADE_PREFERENCES), encoding="utf-8")
            before = legacy.read_bytes()
            self.assertFalse(e2e.settings_file(disk).exists(), "this version never ran")

            program = Program(root)
            self.addCleanup(program.close)
            with mock.patch.object(app_preferences, "preferences_path", lambda: legacy):
                self.assertEqual(e2e.legacy_preferences(), legacy)

            # The program starts in Russian; the old file is unchanged.
            self.assertTrue(program.in_workspace)
            names = program.names()
            self.assertIn(e2e.text_in("ru", "project.create"), names, "the journey's ready text")
            self.assertIn(e2e.text_in("ru", "nav.analyze"), names)
            self.assertEqual(e2e.stored_settings(disk)["language"], "ru")
            self.assertEqual(legacy.read_bytes(), before)

            # The top bar offers EN and LV only (buttons named by their code).
            quick = {code: code.upper() in names for code in ("en", "lv", "ru")}
            self.assertEqual(quick, {"en": True, "lv": True, "ru": False})

            # Settings show Russian.
            program.click("nav-settings")
            self.assertIn(e2e.text_in("ru", "settings.section.language"), [
                c.content.controls[-1].value for c in program.find_all("settings-jump-")])
            self.assertIn(e2e.text_in("ru", "settings.language_note"), program.names())
            field = program.dropdown(e2e.text_in("ru", "settings.language"))
            shown = next(o.text for o in field.options if o.key == field.value)
            self.assertEqual(shown, "Русский")
            self.assertEqual([o.text for o in field.options], e2e.LANGUAGE_OPTIONS)

            # LV in the top bar: still on Settings, now in Latvian, saved.
            program.press("LV")
            self.assertEqual(program.app.route, "settings")
            self.assertIn(e2e.text_in("lv", "settings.language_note"), program.names())
            self.assertEqual(e2e.stored_settings(disk)["language"], "lv")

            # After a restart: Latvian.
            program.restart()
            names = program.names()
            self.assertIn(e2e.text_in("lv", "project.create"), names)
            self.assertIn(e2e.text_in("lv", "nav.analyze"), names)

            # Text size 125 %: the label above the sizes is larger (the index
            # chip the journey clicks first leads to it).
            program.click("nav-settings")
            chip = program.find("settings-jump-typography")
            self.assertEqual(chip.content.controls[-1].value,
                             e2e.text_in("lv", "settings.section.typography"))
            program.click("settings-jump-typography")
            label = e2e.text_in("lv", "settings.text_size")

            def label_size():
                sizes = [c.size for c in program.controls()
                         if isinstance(c, ft.Text) and c.value == label and c.size]
                self.assertEqual(len(sizes), 1, "one text of that name")
                return sizes[0]

            normal = label_size()
            program.press("125 %")
            self.assertEqual(e2e.stored_settings(disk)["text_scale"], 125)
            self.assertGreaterEqual(label_size() / normal, 1.15)
            self.assertEqual(program.app.route, "settings", "the page stays open")

            # Back to 100 % and English (the journeys after this one start so).
            program.press("100 %")
            program.press("EN")
            self.assertIn(T("settings.language_note"), program.names())
            stored = e2e.stored_settings(disk)
            self.assertEqual((stored["language"], stored["text_scale"]), ("en", 100))
            self.assertEqual(legacy.read_bytes(), before, "never written")

    def test_restore_settings_repairs_a_half_finished_run(self):
        with tempfile.TemporaryDirectory() as folder:
            disk = folder_of(Path(folder))
            (Path(folder) / "settings.json").write_text(json.dumps(
                {"format": 1, "language": "lv", "text_scale": 125, "accent": "teal"}),
                encoding="utf-8")
            e2e.restore_settings(disk, language="en", text_scale=100)
            self.assertEqual(e2e.stored_settings(disk),
                             {"format": 1, "language": "en", "text_scale": 100, "accent": "teal"})


class JourneyListTests(unittest.TestCase):
    def test_the_stage37_journeys_follow_the_others(self):
        names = list(e2e.JOURNEYS)
        self.assertEqual(names[16:18], ["confirmations", "report-composition"])
        self.assertEqual(names[18:20], ["startup-workspace", "settings-language"])
        self.assertTrue(set(names).isdisjoint(e2e.STARTS_ITSELF))

    def test_a_segmented_button_is_found_with_or_without_its_tooltip(self):
        import re

        for name in ("LV", "LV. Latviešu", "LV\nLatviešu"):
            self.assertTrue(re.search(e2e.segment("LV"), name), name)
        for label, name in (("LV", "LVA"), ("LV", "ELV"), ("125 %", "125 %x")):
            self.assertFalse(re.search(e2e.segment(label), name), name)
        self.assertTrue(re.search(e2e.segment("125 %"), "125 %"))

    def test_the_program_starts_without_sra_ui_unless_a_journey_forces_one(self):
        with tempfile.TemporaryDirectory() as folder:
            gui = e2e.Gui(Path("program.exe"), Path(folder), Path(folder))
            self.assertNotIn("SRA_UI", gui.environment())
            gui.start_ui = "classic"
            self.assertEqual(gui.environment()["SRA_UI"], "classic")
            self.assertEqual(gui.environment()["SRA_DATA_DIR"], folder)


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class _Element:
    """An element as UI Automation lists it (name, type and rectangle)."""

    def __init__(self, kind, name, rect):
        self.element_info = SimpleNamespace(name=name, control_type=kind,
                                            rectangle=_Rect(*rect))
        self.clicks = 0

    def click_input(self, **_):
        self.clicks += 1


class _Window:
    def __init__(self, rect, elements):
        self._rect, self._elements = _Rect(*rect), elements

    def rectangle(self):
        return self._rect

    def descendants(self):
        return list(self._elements)


# The maximized window and elements of the Windows CI run (run 43497797412):
# UI Automation's own names and rectangles.
MAXIMIZED = (-8, -8, 1928, 1040)
RUSSIAN_SETTINGS = [
    _Element("Group", "Язык. English", (1708, 35, 1848, 74)),
    _Element("Button", "EN", (1711, 38, 1777, 71)),
    _Element("Button", "LV", (1781, 38, 1845, 71)),
    _Element("Group", "Язык: Русский. Все языки", (1856, 34, 1896, 75)),
    _Element("Button", "Настройки", (10, 896, 221, 936)),
    _Element("Text", "Внешний вид", (621, 256, 746, 286)),
    _Element("Text", "Язык", (913, 256, 985, 286)),          # the hub's index
    _Element("Text", "Язык", (621, 1300, 660, 1324)),        # the section, below
    _Element("Button", "Язык", (621, 1336, 881, 1389)),
    _Element("Button", "Классический интерфейс", (10, 980, 221, 1020)),
]


class DriverGeometryTests(unittest.TestCase):
    """The driver finds what a researcher sees on the Windows screen (the
    failures of the first Windows run of the Stage 37 journeys)."""

    def gui(self, window, elements):
        gui = e2e.Gui(Path("program.exe"), Path("."), Path("."))
        gui.win = _Window(window, elements)
        for name in ("dump", "shot", "log_screen", "wheel"):
            setattr(gui, name, lambda *a, **k: None)
        gui.footer_top = lambda: None
        return gui

    def test_the_last_sidebar_entry_is_on_screen_at_any_window_size(self):
        # Maximized: the classic interface ends 20 px above the window's
        # outer edge (12 px sidebar padding, 8 px overhang), fully visible.
        classic = _Element("Button", "Classic interface", (10, 980, 221, 1020))
        gui = self.gui(MAXIMIZED, [classic])
        self.assertIs(gui.find("Classic interface", control_type=("Button", "Text"),
                               scroll=False, timeout=0.3), classic)
        # 1200 x 720 at (100, 100): the same 20 px.
        classic = _Element("Button", "Classic interface", (108, 760, 319, 800))
        gui = self.gui((100, 100, 1300, 820), [classic])
        self.assertTrue(gui.on_screen(classic))
        # Below the window it is not on screen.
        hidden = _Element("Button", "Classic interface", (108, 800, 319, 840))
        self.assertFalse(gui.on_screen(hidden))
        # The page keeps its margin above the status line.
        content = _Element("Button", "Create project", (700, 1000, 900, 1020))
        self.assertFalse(self.gui(MAXIMIZED, [content]).on_screen(content))

    def test_a_settings_chip_is_not_the_top_bar_language_group(self):
        gui = self.gui(MAXIMIZED, RUSSIAN_SETTINGS)
        e2e.click_chip(gui, "Язык")
        self.assertEqual(RUSSIAN_SETTINGS[6].clicks, 1)
        self.assertEqual(RUSSIAN_SETTINGS[0].clicks, 0)

    def test_the_top_bar_language_buttons_are_clickable(self):
        gui = self.gui(MAXIMIZED, RUSSIAN_SETTINGS)
        gui.click(regex=e2e.segment("LV"), control_type="Button", settle=0)
        self.assertEqual(RUSSIAN_SETTINGS[2].clicks, 1)
        # Not anything else that scrolled under the context bar.
        under = _Element("Button", "Run", (700, 60, 800, 100))
        self.assertFalse(self.gui(MAXIMIZED, [under]).clickable(under))


if __name__ == "__main__":
    unittest.main()
