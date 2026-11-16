"""Stage 35 (#44): the dialogs that show where research data is kept and
copy an earlier version's data. Synthetic data only."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import data_ui  # noqa: E402
import legacy_data as ld  # noqa: E402
from test_legacy_data import LegacyCase  # noqa: E402


class FakePage:
    def __init__(self):
        self.dialogs, self.services, self.updates = [], [], 0

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def update(self, *controls):
        self.updates += 1


def texts(control) -> list[str]:
    found = []

    def walk(node):
        if isinstance(node, ft.Text) and isinstance(node.value, str):
            found.append(node.value)
        for name in ("content", "controls", "title", "actions"):
            child = getattr(node, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    walk(item)
    walk(control)
    return found


def button(dialog, data):
    return next(b for b in dialog.actions if b.data == data)


class TextTests(unittest.TestCase):
    def test_every_language_has_every_text(self):
        for language in ("lv", "ru"):
            with self.subTest(language=language):
                self.assertEqual(set(data_ui.TEXT[language]), set(data_ui.TEXT["en"]))


class MigrationDialogTests(LegacyCase):
    def test_the_dialog_lists_what_it_would_copy(self):
        source = ld.inspect(self.old, self.new, "preview")
        shown = " ".join(texts(data_ui.migration_dialog(FakePage(), source, self.new, "en")))
        self.assertIn(str(self.old), shown)
        self.assertIn(str(self.new), shown)
        self.assertIn("Projects (2): Second fictional study, Sleep and stress (fictional)", shown,
                      "listed in alphabetical order")
        self.assertIn("Questionnaires with their responses (1): Synthetic pilot", shown)
        self.assertIn("nothing in the earlier folder is changed or deleted", shown)
        russian = " ".join(texts(data_ui.migration_dialog(FakePage(), source, self.new, "ru")))
        self.assertIn("Проекты (2)", russian)

    def test_copy_reports_what_was_copied_and_checked(self):
        page = FakePage()
        source = ld.inspect(self.old, self.new, "preview")
        dialog = data_ui.migration_dialog(page, source, self.new, "en")
        page.show_dialog(dialog)
        asyncio.run(button(dialog, "migration-copy").on_click(None))
        shown = " ".join(texts(dialog))
        self.assertIn("Copied: 2 project(s), 1 questionnaire(s), the researcher profile. "
                      "Each copy was checked against its original.", shown)
        self.assertIn(f"The originals are unchanged in {self.old}.", shown)
        self.assertEqual([b.data for b in dialog.actions], ["migration-close"])
        import project_store as ps

        self.assertEqual(len(ps.ProjectStore(self.new / "projects").list()), 2)

    def test_not_now_is_remembered(self):
        page = FakePage()
        source = ld.inspect(self.old, self.new, "preview")
        dialog = data_ui.migration_dialog(page, source, self.new, "en")
        page.show_dialog(dialog)
        button(dialog, "migration-later").on_click(None)
        self.assertTrue(ld.is_dismissed(self.old, self.new))
        self.assertEqual(page.dialogs, [])
        self.assertFalse((self.new / "projects").exists(), "nothing copied")

    def test_offered_once_at_startup_in_a_known_place(self):
        page = FakePage()
        environment = {"APPDATA": str(self.base / "AppData" / "Roaming"),
                       "SRA_DATA_DIR": str(self.new), "SRA_OFFER_MIGRATION": "1"}
        with mock.patch.dict(os.environ, environment), \
                mock.patch("startup_diagnostics.is_packaged", return_value=False):
            offered = asyncio.run(data_ui.offer_at_startup(page, ROOT, "en"))
            self.assertEqual(offered.folder, self.old)
            self.assertEqual(page.dialogs[0].data, "migration-dialog")
            button(page.dialogs[0], "migration-later").on_click(None)
            self.assertIsNone(asyncio.run(data_ui.offer_at_startup(page, ROOT, "en")))

    def test_not_offered_automatically_when_tests_choose_the_data_folder(self):
        page = FakePage()
        environment = {"APPDATA": str(self.base / "AppData" / "Roaming"),
                       "SRA_DATA_DIR": str(self.new), "SRA_OFFER_MIGRATION": ""}
        with mock.patch.dict(os.environ, environment):
            self.assertIsNone(asyncio.run(data_ui.offer_at_startup(page, ROOT, "en")))
        self.assertEqual(page.dialogs, [])

    def test_a_chosen_folder_without_new_data_says_so(self):
        page = FakePage()
        note = asyncio.run(data_ui.find_in_chosen_folder(page, str(self.base / "empty"),
                                                         self.new, "en"))
        self.assertIn("No data of an earlier version was found", note)
        asyncio.run(data_ui.find_in_chosen_folder(page, str(self.old.parent), self.new, "en"))
        self.assertEqual(page.dialogs[0].data, "migration-dialog")


def snapshot_bytes(folder: Path) -> dict[str, bytes]:
    """Every file under ``folder`` with its bytes (SQLite's shared-memory
    index and an empty write-ahead log, which any reader creates, aside)."""
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file()
            and not p.name.endswith("-shm")
            and not (p.name.endswith("-wal") and p.stat().st_size == 0)}


def coloured_texts(control) -> list[ft.Text]:
    found = []

    def walk(node):
        if isinstance(node, ft.Text):
            found.append(node)
        for name in ("content", "controls", "title", "actions"):
            child = getattr(node, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    walk(item)
    walk(control)
    return found


class ThemedPage(FakePage):
    def __init__(self, theme_mode=None, brightness=None, width=None):
        super().__init__()
        self.theme_mode, self.platform_brightness = theme_mode, brightness
        self.theme = self.dark_theme = None
        if width is not None:
            self.width = width


class MigrationDialogReadabilityTests(LegacyCase):
    """Issue #80 (P1): light text stood on a near-white surface on the
    installed first run. The dialog's surface and every foreground now come
    from one token palette; computed WCAG contrast (AA: 4.5:1) for the
    title, the body, the paths and the status on that surface."""

    PAGES = {
        "light": lambda: ThemedPage(ft.ThemeMode.LIGHT),
        "dark": lambda: ThemedPage(ft.ThemeMode.DARK),
        "system-dark": lambda: ThemedPage(ft.ThemeMode.SYSTEM, ft.Brightness.DARK),
        "system-light": lambda: ThemedPage(ft.ThemeMode.SYSTEM, ft.Brightness.LIGHT),
        "no theme (classic start)": lambda: FakePage(),
    }

    def assert_readable(self, dialog, label: str):
        import workspace_tokens as tk

        surface = dialog.bgcolor
        self.assertIsNotNone(surface, f"{label}: the dialog chooses its surface")
        roles = {"migration-title": "title", "migration-path": "path",
                 "migration-status": "status", "migration-line": "body",
                 "migration-result": "body", "migration-note": "body"}
        seen = set()
        for text in coloured_texts(dialog):
            self.assertIsNotNone(text.color, f"{label}: {text.value!r} has no colour")
            ratio = tk.contrast_ratio(text.color, surface)
            self.assertGreaterEqual(ratio, 4.5, f"{label}: {text.value!r} {text.color} "
                                                f"on {surface} is {ratio:.2f}:1")
            seen.add(roles.get(text.data, "body"))
        for button in dialog.actions:
            style = button.style
            self.assertIsNotNone(style, f"{label}: {button.data} has no style")
            states = ft.ControlState
            background = (style.bgcolor or {}).get(states.DEFAULT, surface) \
                if isinstance(style.bgcolor, dict) else (style.bgcolor or surface)
            ratio = tk.contrast_ratio(style.color[states.DEFAULT], background)
            self.assertGreaterEqual(ratio, 4.5, f"{label}: {button.data} label {ratio:.2f}:1")
            disabled_bg = (style.bgcolor or {}).get(states.DISABLED, surface) \
                if isinstance(style.bgcolor, dict) else surface
            ratio = tk.contrast_ratio(style.color[states.DISABLED], disabled_bg)
            self.assertGreaterEqual(ratio, 4.5, f"{label}: disabled {button.data} {ratio:.2f}:1")
        return seen

    def test_title_body_paths_and_status_meet_aa_in_every_theme(self):
        import workspace_tokens as tk

        source = ld.inspect(self.old, self.new, "preview")
        for name, make in self.PAGES.items():
            for language in ("en", "lv", "ru"):
                with self.subTest(theme=name, language=language):
                    page = make()
                    dialog = data_ui.migration_dialog(page, source, self.new, language)
                    status = next(c for c in coloured_texts(dialog)
                                  if c.data == "migration-status")
                    status.value = data_ui.t(language, "copying", i=1, n=4, name="X")
                    seen = self.assert_readable(dialog, f"{name}/{language}")
                    self.assertEqual(seen, {"title", "path", "status", "body"})
                    dark = name in ("dark", "system-dark")
                    self.assertEqual(dialog.bgcolor, (tk.DARK if dark else tk.LIGHT).surface,
                                     "surface and text from the same theme")
        # The workspace passes its own palette (accent included).
        for mode in ("light", "dark"):
            p = tk.palette(mode, "violet")
            dialog = data_ui.migration_dialog(FakePage(), source, self.new, "en", palette=p)
            self.assertEqual(dialog.bgcolor, p.surface)
            self.assert_readable(dialog, f"workspace {mode}")
            self.assertEqual(button(dialog, "migration-copy").style.bgcolor[
                ft.ControlState.DEFAULT], p.accent)

    def test_the_report_after_copying_is_readable_too(self):
        for name in ("light", "dark"):
            with self.subTest(theme=name):
                page = self.PAGES[name]()
                new = self.new / name
                source = ld.inspect(self.old, new, "preview")
                dialog = data_ui.migration_dialog(page, source, new, "en")
                page.show_dialog(dialog)
                asyncio.run(button(dialog, "migration-copy").on_click(None))
                self.assertEqual([b.data for b in dialog.actions], ["migration-close"])
                self.assertTrue(any(c.data == "migration-result" for c in coloured_texts(dialog)))
                self.assert_readable(dialog, f"report {name}")

    def test_long_names_and_several_sources_stay_inside_the_dialog(self):
        source = ld.inspect(self.old, self.new, "preview")
        dialog = data_ui.migration_dialog(FakePage(), source, self.new, "en")
        body = dialog.content
        self.assertEqual(body.scroll, ft.ScrollMode.AUTO, "long content scrolls")
        self.assertEqual(body.width, 620)
        # 100-175 % display scaling: the window's logical width shrinks
        # (1366 px screen at 175 % = 780 logical px; 1280 px at 175 % = 731).
        for scale, physical in ((1.0, 1366), (1.25, 1366), (1.5, 1366), (1.75, 1366),
                                (1.75, 1280)):
            width = int(physical / scale)
            with self.subTest(scale=scale, width=width):
                narrow = data_ui.migration_dialog(ThemedPage(width=width), source, self.new,
                                                  "ru")
                # content + the dialog's own paddings (2 x 24) and insets (2 x 24)
                self.assertLessEqual(narrow.content.width + 96, width)
                self.assertGreaterEqual(narrow.content.width, 260)
                self.assertEqual(narrow.actions_overflow_button_spacing, 8,
                                 "actions wrap onto a second line instead of clipping")
        many = ld.Source(self.old, "preview", tuple(
            ld.Item("project", "Fictional study with a very long name " * 4 + str(n),
                    self.old / f"p{n}", self.new / f"p{n}", "x", 1) for n in range(40)))
        shown = data_ui.migration_dialog(FakePage(), many, self.new, "en")
        line = next(c for c in coloured_texts(shown) if c.data == "migration-line")
        self.assertIn("(+36)", line.value, "at most four names, then a count")

    def test_a_synthetic_legacy_folder_is_copied_byte_for_byte(self):
        """Project (database, dataset copy), questionnaire and profile: the
        copies equal the originals, which are not changed. Plain files are
        equal byte for byte; a SQLite database is copied with SQLite's backup
        API (it takes changes still in the write-ahead log with it), so its
        header bytes may differ while its content -- schema, every row and
        the format number -- is equal, which is what is compared for it."""
        before = snapshot_bytes(self.old)
        source = ld.inspect(self.old, self.new, "preview")
        self.assertEqual(sorted(i.kind for i in source.pending),
                         ["profile", "project", "project", "questionnaire"])
        page = ThemedPage(ft.ThemeMode.LIGHT)
        dialog = data_ui.migration_dialog(page, source, self.new, "en")
        page.show_dialog(dialog)
        asyncio.run(button(dialog, "migration-copy").on_click(None))
        self.assertEqual(snapshot_bytes(self.old), before, "the originals are unchanged")
        compared = {"file": 0, "database": 0}
        for item in source.pending:
            pairs = ([(item.source, item.target)] if item.source.is_file() else
                     [(f, item.target / f.relative_to(item.source))
                      for f in sorted(item.source.rglob("*")) if f.is_file()
                      and not f.name.endswith(("-shm", "-wal"))])
            for original, copy in pairs:
                self.assertTrue(copy.is_file(), copy)
                if original.suffix == ".sqlite3":
                    self.assertEqual(ld.database_digest(copy), ld.database_digest(original),
                                     original.name)
                    compared["database"] += 1
                else:
                    self.assertEqual(copy.read_bytes(), original.read_bytes(), original.name)
                    compared["file"] += 1
        self.assertEqual(compared, {"file": 2, "database": 3},
                         "the dataset copy, the profile; two projects and the questionnaire")

    def test_not_now_copies_deletes_and_changes_nothing(self):
        before_old, before_new = snapshot_bytes(self.old), snapshot_bytes(self.new)
        for remember in (False, True):
            with self.subTest(remember=remember):
                page = FakePage()
                source = ld.inspect(self.old, self.new, "preview")
                dialog = data_ui.migration_dialog(page, source, self.new, "en",
                                                  remember_later=remember)
                page.show_dialog(dialog)
                button(dialog, "migration-later").on_click(None)
                self.assertEqual(page.dialogs, [])
                self.assertEqual(snapshot_bytes(self.old), before_old)
                after = snapshot_bytes(self.new)
                if not remember:
                    self.assertEqual(after, before_new, "nothing written at all")
                else:   # only the remembered answer, beside no research data
                    self.assertEqual(set(after) - set(before_new), {ld.RECORD})
                    self.assertTrue(ld.is_dismissed(self.old, self.new))


class ScreenContrastTests(unittest.TestCase):
    """The installed-program journey ``legacy-migration`` measures the
    dialog's texts on its own screenshot (``measured_contrast``): the
    measurement tells the reported failure from the fix."""

    def image(self, text_colour: str, surface: str):
        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (330, 30), surface)      # a title's own rectangle
        ImageDraw.Draw(image).text((4, 3), "Data from an earlier version", fill=text_colour,
                                   font=ImageFont.load_default(size=20))
        return image

    def test_light_text_on_a_near_white_surface_fails_and_the_tokens_pass(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import windows_gui_e2e as e2e
        import workspace_tokens as tk

        reported = e2e.measured_contrast(self.image(tk.DARK.text, tk.LIGHT.surface_alt))
        self.assertLess(reported["ratio"], 1.5, reported)
        self.assertEqual(reported["background"], tk.LIGHT.surface_alt)
        for p in (tk.LIGHT, tk.DARK):
            for role in ("text", "text_secondary"):
                measured = e2e.measured_contrast(self.image(getattr(p, role), p.surface))
                self.assertGreaterEqual(measured["ratio"], 4.5, (p.mode, role, measured))
                self.assertAlmostEqual(measured["ratio"],
                                       tk.contrast_ratio(getattr(p, role), p.surface), delta=0.3)


class WorkspaceSettingsTests(unittest.TestCase):
    def test_settings_show_the_data_folder(self):
        from workspace_harness import Workspace

        ws = Workspace()
        self.addCleanup(ws.close)
        ws.app.navigate("settings")
        card = ws.find("settings-data")
        shown = " ".join(c.value for c in ws.controls(card)
                         if isinstance(c, ft.Text) and isinstance(c.value, str))
        self.assertIn(str(ws.app.project_root.parent), shown)
        self.assertIn("never changes this folder", shown)
        self.assertIsNotNone(ws.find("settings-data-find"))


if __name__ == "__main__":
    unittest.main()
