"""Hardening of the research library (Stage 37.3, Issue #69, independent
review ``verify-stage37-rag``): what a library database restored from
someone else's backup may make the program do, project isolation when a
library cannot be opened, what a removed document leaves behind, damaged or
older library files, and hostile documents (zip and content-stream bombs,
pathological Markdown and PDF lines).

Finding IDs are those of the review (storage F1-F5, injection F1-F6,
privacy F4/F5). Synthetic documents only; no test opens a network
connection.
"""

from __future__ import annotations

from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("MPLBACKEND", "Agg")

import library_fixtures as fx  # noqa: E402
from project_store import ProjectStore, sha256_bytes  # noqa: E402
import research_library as rl  # noqa: E402

NOTES = (b"Synthetic lab notes\n\nThe pilot session starts on Tuesday in room 214. "
         b"Double-sided printing saves paper.\n")
SECRET = (b"Transcript\n\nParticipant Qwertyuiop Zxcvbnmova said she lives at Synthetic "
          b"Street 17.\n")


class StoreCase(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.store = ProjectStore(self.base / "projects")
        self.info = self.store.create("Fictional hardening study")
        self.library = rl.Library.for_project(self.info.path)

    def add(self, data: bytes = NOTES, name: str = "lab_notes.txt"):
        return self.library.add_document(data=data, file_name=name).document

    def set_row(self, document_id: int, **values):
        with closing(sqlite3.connect(self.library.path)) as db:
            for column, value in values.items():
                db.execute(f"UPDATE documents SET {column} = ? WHERE id = ?",
                           (value, document_id))
            db.commit()


# ================================================= storage F1 / injection F1
class StoredNameTests(StoreCase):
    """A stored copy's name comes from the library database, which a restored
    backup supplies: it is never joined to a path unchecked."""

    BAD = ("../../evil.bat", "payload.cmd", "C:\\Windows\\System32\\calc.exe",
           "\\\\server\\share\\x.txt", "/etc/passwd", "CON.txt")

    def test_a_stored_name_from_the_database_is_never_trusted(self):
        document = self.add()
        good = self.library.source_file(document)
        self.assertEqual(good, self.library.folder / rl.SOURCES / document.stored_name)
        digest = document.sha256
        names = (*self.BAD, digest + ".txt:secret", digest.upper() + ".txt",
                 digest + ".pdf", digest + ".TXT", "0" * 64 + ".txt", digest + ".txt ",
                 digest + ".txt\n")
        for name in names:
            with self.subTest(name=name):
                self.set_row(document.id, stored_name=name)
                row = self.library.document(document.id)
                with self.assertRaises(rl.LibraryError) as refused:
                    self.library.source_file(row)
                self.assertEqual(refused.exception.reason, "unsafe_source")
                with self.assertRaises(rl.LibraryError):
                    self.library.verified_source(row)

    def test_a_copy_that_changed_or_points_elsewhere_is_refused(self):
        document = self.add()
        copy = self.library.source_file(document)
        self.assertEqual(self.library.verified_source(document)[1], NOTES)
        copy.write_bytes(b"@echo off\r\ncalc.exe\r\n")
        with self.assertRaises(rl.LibraryError) as changed:
            self.library.verified_source(document)
        self.assertEqual(changed.exception.reason, "changed")
        if not hasattr(os, "symlink"):
            return
        outside = self.base / "outside.txt"
        outside.write_bytes(NOTES)
        copy.unlink()
        try:
            copy.symlink_to(outside)
        except OSError:
            self.skipTest("symbolic links are not allowed here")
        with self.assertRaises(rl.LibraryError) as linked:
            self.library.verified_source(document)
        self.assertEqual(linked.exception.reason, "unsafe_source")

    def test_a_sources_folder_that_is_a_link_is_refused(self):
        document = self.add()
        sources = self.library.folder / rl.SOURCES
        elsewhere = self.base / "elsewhere"
        sources.rename(elsewhere)
        try:
            sources.symlink_to(elsewhere, target_is_directory=True)
        except OSError:
            self.skipTest("symbolic links are not allowed here")
        with self.assertRaises(rl.LibraryError) as refused:
            self.library.verified_source(document)
        self.assertEqual(refused.exception.reason, "unsafe_source")

    def test_a_malformed_row_does_not_break_the_list(self):
        document = self.add()
        self.set_row(document.id, ocr_pages="{")
        self.assertEqual([d.id for d in self.library.documents()], [document.id])
        self.assertEqual(self.library.document(document.id).ocr_pages, ())

    def test_render_and_reindex_read_only_a_verified_copy(self):
        document = self.add(fx.pdf(fx.EN_NOTES), "notes.pdf")
        self.assertTrue(self.library.render_page(document, 1).startswith(b"\x89PNG"))
        self.set_row(document.id, stored_name="../../../evil.pdf")
        row = self.library.document(document.id)
        for action in (lambda: self.library.render_page(row, 1),
                       lambda: self.library.reindex(row.id)):
            with self.assertRaises(rl.LibraryError) as refused:
                action()
            self.assertEqual(refused.exception.reason, "unsafe_source")


def crafted_backup(store: ProjectStore, project_id: str, target: Path, *, rows=None,
                   extra: dict[str, bytes] | None = None) -> Path:
    """A backup of ``project_id`` whose library database was edited (``rows``:
    stored_name per document title) and with ``extra`` files added, its
    manifest recomputed: the package is not signed, so anyone can do this."""
    plain = store.export_package(project_id, target.with_name("plain.sra"))
    with zipfile.ZipFile(plain) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries.pop("manifest.json"))
    with TemporaryDirectory() as temp:
        database = Path(temp) / "library.sqlite3"
        database.write_bytes(entries["project/library/library.sqlite3"])
        with closing(sqlite3.connect(database)) as db:
            for title, stored in (rows or {}).items():
                db.execute("UPDATE documents SET stored_name = ? WHERE title = ?",
                           (stored, title))
            db.commit()
        entries["project/library/library.sqlite3"] = database.read_bytes()
    entries.update(extra or {})
    manifest["files"] = [{"path": name, "size": len(data), "sha256": sha256_bytes(data)}
                         for name, data in entries.items()]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, data in entries.items():
            archive.writestr(name, data)
    return target


class RestoredBackupTests(StoreCase):
    def test_a_crafted_backup_cannot_make_open_run_a_file(self):
        notes = self.add()
        manual = self.add(b"Supervisor notes\n\nMeet on Friday.\n", "supervisor.txt")
        rl.set_travels(self.info.path, True)
        payload = b"@echo off\r\ncalc.exe\r\n"
        package = crafted_backup(
            self.store, self.info.id, self.base / "crafted.sra",
            rows={notes.title: "payload.cmd", manual.title: "../../../../outside.txt"},
            extra={"project/library/sources/payload.cmd": payload,
                   "project/library/sources/notes.lnk": b"L\x00\x00\x00"})
        restored, warnings = self.store.import_package(package)
        sources = restored.path / rl.FOLDER / rl.SOURCES
        self.assertFalse((sources / "payload.cmd").exists(), "a file not named by its hash")
        self.assertFalse((sources / "notes.lnk").exists())
        self.assertTrue(any("research library" in w for w in warnings), warnings)
        library = rl.Library.for_project(restored.path)
        self.assertEqual(len(library.documents()), 2)
        for document in library.documents():
            with self.assertRaises(rl.LibraryError) as refused:
                library.verified_source(document)
            self.assertEqual(refused.exception.reason, "unsafe_source")

    def test_restore_keeps_only_copies_named_by_their_own_hash(self):
        document = self.add()
        rl.set_travels(self.info.path, True)
        forged = "f" * 64 + ".txt"
        package = crafted_backup(self.store, self.info.id, self.base / "forged.sra",
                                 extra={f"project/library/sources/{forged}": b"not that hash"})
        restored, warnings = self.store.import_package(package)
        sources = restored.path / rl.FOLDER / rl.SOURCES
        self.assertEqual(sorted(p.name for p in sources.iterdir()), [document.stored_name])
        self.assertTrue(warnings)
        library = rl.Library.for_project(restored.path)
        self.assertEqual(library.verified_source(library.documents()[0])[1], NOTES)


# ======================================================= privacy F4/F5, storage F4
class RemovalTests(StoreCase):
    def packed(self) -> bytes:
        rl.set_travels(self.info.path, True)
        return b"".join(data for _, data in rl.travelling_files(self.info.path)).lower()

    def test_a_removed_document_leaves_nothing_in_the_library_file_or_its_backup(self):
        self.add()
        gone = self.add(SECRET, "interview_p07.txt")
        self.library.remove_document(gone.id)
        packed = self.packed()
        self.assertNotIn(b"qwertyuiop", packed)
        self.assertNotIn(b"zxcvbnmova", packed)
        self.assertNotIn(b"interview_p07", packed)
        self.assertIn(b"double-sided", packed)
        on_disk = b"".join(p.read_bytes() for p in self.library.folder.glob("library.sqlite3*"))
        self.assertNotIn(b"Qwertyuiop", on_disk)
        self.assertNotIn(b"qwertyuiop", on_disk.lower())
        self.assertEqual(self.library.integrity(), [])

    def test_a_copy_held_open_never_travels_and_goes_later(self):
        keep = self.add()
        gone = self.add(SECRET, "interview_p07.txt")
        copy = self.library.source_file(gone)
        real_unlink = Path.unlink

        def held_open(path, *args, **kwargs):
            if path == copy:
                raise PermissionError(13, "The process cannot access the file", str(path))
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", held_open):
            self.library.remove_document(gone.id)
            self.assertTrue(copy.exists())
            rl.set_travels(self.info.path, True)
            names = [name for name, _ in rl.travelling_files(self.info.path)]
            self.assertNotIn(f"library/sources/{gone.stored_name}", names)
            self.assertIn(f"library/sources/{keep.stored_name}", names)
            exported = self.store.export_package(self.info.id, self.base / "b.sra")
            with zipfile.ZipFile(exported) as archive:
                self.assertNotIn(f"project/library/sources/{gone.stored_name}",
                                 archive.namelist())
            duplicate = self.store.duplicate(self.info.id, "Copy")
            self.assertFalse((duplicate.path / rl.FOLDER / rl.SOURCES / gone.stored_name).exists())
        rl.Library.for_project(self.info.path)
        self.assertFalse(copy.exists(), "deleted once it is no longer held open")


# ====================================================================== storage F3
class StoredCopiesSurviveTests(StoreCase):
    def three(self):
        return [self.add(data, name) for data, name in (
            (NOTES, "a.txt"), (b"Second synthetic note\n\nAbout coping.\n", "b.txt"),
            (b"Third synthetic note\n\nAbout support.\n", "c.txt"))]

    def copies(self) -> int:
        return len([p for p in (self.library.folder / rl.SOURCES).iterdir() if p.is_file()])

    def test_an_empty_or_missing_database_never_deletes_the_stored_copies(self):
        self.three()
        self.assertEqual(self.copies(), 3)
        for damage in ("empty", "missing"):
            with self.subTest(damage=damage):
                for side in self.library.folder.glob("library.sqlite3-*"):
                    side.unlink()
                if damage == "empty":
                    self.library.path.write_bytes(b"")
                else:
                    self.library.path.unlink(missing_ok=True)
                try:
                    rl.Library(self.library.folder)
                except rl.LibraryError:
                    pass
                self.assertEqual(self.copies(), 3, damage)

    def test_an_older_copy_of_the_database_never_deletes_newer_copies(self):
        first = self.add()
        older = self.base / "older.sqlite3"
        with closing(sqlite3.connect(self.library.path)) as db, \
                closing(sqlite3.connect(older)) as out:
            db.backup(out)
        self.add(b"Second synthetic note\n\nAbout coping.\n", "b.txt")
        self.add(b"Third synthetic note\n\nAbout support.\n", "c.txt")
        for side in self.library.folder.glob("library.sqlite3-*"):
            side.unlink()
        self.library.path.write_bytes(older.read_bytes())
        reopened = rl.Library(self.library.folder)
        self.assertEqual([d.id for d in reopened.documents()], [first.id])
        self.assertEqual(self.copies(), 3)


# ====================================================================== storage F5
class DamagedLibraryTests(StoreCase):
    def damage(self):
        self.add()
        rl.set_travels(self.info.path, True)
        for side in self.library.folder.glob("library.sqlite3-*"):
            side.unlink()
        self.library.path.write_bytes(b"\0" * 8192)

    def test_a_damaged_library_is_reported_as_such(self):
        self.damage()
        with self.assertRaises(rl.LibraryError) as refused:
            rl.Library(self.library.folder)
        self.assertEqual(refused.exception.reason, "damaged")
        with self.assertRaises(rl.LibraryError):
            rl.travelling_files(self.info.path)

    def test_a_damaged_library_does_not_block_a_backup_or_a_copy(self):
        self.damage()
        warnings: list[str] = []
        exported = self.store.export_package(self.info.id, self.base / "b.sra",
                                             warnings=warnings)
        with zipfile.ZipFile(exported) as archive:
            names = archive.namelist()
        self.assertIn("project/project.sqlite3", names)
        self.assertFalse([n for n in names if "/library/" in n])
        self.assertTrue(warnings and "research library" in warnings[0], warnings)
        warnings = []
        copy = self.store.duplicate(self.info.id, "Copy", warnings=warnings)
        self.assertFalse((copy.path / rl.FOLDER).exists())
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
