"""Local desktop preferences only; never synchronize respondent data.

Since Stage 37 (issue #68) the preferences live in the one settings file of
``user_settings`` (``<data folder>/settings.json``). This module keeps the
interface the classic screens use: ``load_preferences()`` and
``save_preferences()`` without a path read and write that file.
``preferences_path()`` is where versions before Stage 37 kept them; the
settings file is made from it once, and it is never changed again. With an
explicit ``path`` the old single-file format is read and written as before.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

# Re-exported: the export choices' values (Stage 37, #67) are validated by the
# settings file (#68).
from user_settings import CSV_LAYOUTS, EXPORT_CONTEXTS, EXPORT_FORMATS, clean_export


DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en", "lv", "ru"}
MAX_RECENTS = 8
APPEARANCES = {"windows", "macos"}
DEFAULT_APPEARANCE = "windows"


@dataclass(frozen=True)
class AppPreferences:
    language: str = DEFAULT_LANGUAGE
    recent_files: tuple[str, ...] = ()
    appearance: str = DEFAULT_APPEARANCE


def preferences_path() -> Path:
    """The preferences file of versions before Stage 37 (only read since)."""
    return Path.home() / ".statistical_research_assistant" / "preferences.json"


def _settings(path: Path | None = None):
    from user_settings import UserSettings

    return UserSettings.load(path)


def load_preferences(path: Path | None = None) -> AppPreferences:
    """English / Windows on first launch. A language or style this version
    does not know is shown as the default; the stored value is kept."""
    if path is not None:
        return _load_file(path)
    try:
        settings = _settings()
        return AppPreferences(settings.get("language"), tuple(settings.get("recent_files")),
                              settings.get("corners"))
    except Exception:
        return AppPreferences()


def update_preferences(**changes) -> Path:
    """Save only the given preferences (``language``, ``recent_files``,
    ``appearance``) in the settings file; raises OSError if it cannot be
    written, ValueError for a value that is not offered."""
    if "language" in changes and changes["language"] not in LANGUAGES:
        raise ValueError("Language must be en, lv or ru.")
    if "appearance" in changes and changes["appearance"] not in APPEARANCES:
        raise ValueError("Appearance must be windows or macos.")
    values = {}
    if "language" in changes:
        values["language"] = changes["language"]
    if "recent_files" in changes:
        values["recent_files"] = list(changes["recent_files"])[:MAX_RECENTS]
    if "appearance" in changes:
        values["corners"] = changes["appearance"]
    settings = _settings()
    if not settings.update(**values):
        raise OSError(settings.error or "the settings file could not be written")
    return settings.path


def save_preferences(
    preferences: AppPreferences, path: Path | None = None,
) -> Path:
    if preferences.language not in LANGUAGES:
        raise ValueError("Language must be en, lv or ru.")
    if preferences.appearance not in APPEARANCES:
        raise ValueError("Appearance must be windows or macos.")
    if path is not None:
        return _save_file(preferences, path)
    # Only what differs from the settings file as the program shows it is
    # written: a value the program shows as its default because this
    # version does not know it is never replaced by that default.
    current = load_preferences()
    changes = {}
    if preferences.language != current.language:
        changes["language"] = preferences.language
    if tuple(preferences.recent_files) != current.recent_files:
        changes["recent_files"] = preferences.recent_files
    if preferences.appearance != current.appearance:
        changes["appearance"] = preferences.appearance
    if not changes:
        return _settings().path
    return update_preferences(**changes)


def _load_file(location: Path) -> AppPreferences:
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return AppPreferences()
        language = raw.get("language", DEFAULT_LANGUAGE)
        if language not in LANGUAGES:
            language = DEFAULT_LANGUAGE
        files = raw.get("recent_files", [])
        if not isinstance(files, list):
            files = []
        recent = tuple(
            value for value in files[:MAX_RECENTS]
            if isinstance(value, str) and len(value) <= 4096
        )
        appearance = raw.get("appearance", DEFAULT_APPEARANCE)
        if appearance not in APPEARANCES:
            appearance = DEFAULT_APPEARANCE
        return AppPreferences(language, recent, appearance)
    except (FileNotFoundError, ValueError, OSError, TypeError):
        return AppPreferences()


def _save_file(preferences: AppPreferences, destination: Path) -> Path:
    # Stage 37: keys this function does not manage (an earlier build's export
    # choices) stay in the old single-file format too.
    serialized = json.dumps({
        **_other_keys(destination),
        "language": preferences.language,
        "recent_files": list(preferences.recent_files[:MAX_RECENTS]),
        "appearance": preferences.appearance,
    }, ensure_ascii=False, indent=2)
    return _write_atomic(destination, serialized)


MANAGED = ("language", "recent_files", "appearance")


def _other_keys(location: Path) -> dict:
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if k not in MANAGED} if isinstance(raw, dict) else {}


def _write_atomic(destination: Path, serialized: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Atomic update protects preferences from abrupt process termination.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".preferences-", suffix=".tmp", delete=False,
        ) as fh:
            temporary = Path(fh.name)
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def remember_file(
    preferences: AppPreferences, path: str | Path,
) -> AppPreferences:
    selected = Path(path).expanduser()
    if not selected.is_file():
        return preferences
    location = str(selected.resolve())
    unique = [location] + [
        old for old in preferences.recent_files if old != location
    ]
    return AppPreferences(
        preferences.language, tuple(unique[:MAX_RECENTS]),
        preferences.appearance,
    )


# ------------------------------------------------- export choices (Stage 37)
# The last export choices (#67) live in the one settings file (#68), key
# ``export``, validated by ``user_settings``. With an explicit ``path`` the
# old single-file format (``preferences.json``, key ``export``) is read and
# written as before; the settings file is made from it once (migration), and
# while it holds no export choices an earlier build's are read from it.
def _export_in_file(location: Path) -> dict:
    """The raw ``export`` document of a single-file preferences file ({})."""
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    export = raw.get("export") if isinstance(raw, dict) else None
    return dict(export) if isinstance(export, dict) else {}


def _merge_export(current: dict, values: dict) -> dict:
    """``current`` (as stored; unknown keys kept) with the valid ``values``."""
    merged = dict(current)
    if isinstance(values.get("formats"), dict):
        stored = merged.get("formats") if isinstance(merged.get("formats"), dict) else {}
        merged["formats"] = {**stored, **{
            k: v for k, v in values["formats"].items()
            if k in EXPORT_CONTEXTS and v in EXPORT_FORMATS}}
    if values.get("csv_layout") in CSV_LAYOUTS:
        merged["csv_layout"] = values["csv_layout"]
    if isinstance(values.get("csv_bom"), bool):
        merged["csv_bom"] = values["csv_bom"]
    return merged


def _stored_export(settings) -> dict:
    """The export choices as the settings file holds them; while it holds
    none, those an earlier build kept in ``preferences.json`` (only read)."""
    stored = settings.stored("export")
    if isinstance(stored, dict):
        return dict(stored)
    return _export_in_file(preferences_path())


def export_preferences(path: Path | None = None, *, settings=None) -> dict:
    """The last export choices: {"formats": {context: format}, "csv_layout",
    "csv_bom"}; anything unknown or malformed is left out. ``settings`` is
    the program's :class:`user_settings.UserSettings` (default: the user's
    settings file); ``path`` reads an old single-file preferences file."""
    if path is not None:
        return clean_export(_export_in_file(path)) or {}
    return clean_export(_stored_export(settings or _settings())) or {}


def remember_export(values: dict, path: Path | None = None, *, settings=None) -> Path:
    """Merge ``values`` into the remembered export choices (only valid ones).
    Raises OSError when the settings file cannot be written."""
    if path is not None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            raw = {}
        raw["export"] = _merge_export(_export_in_file(path), values)
        return _write_atomic(path, json.dumps(raw, ensure_ascii=False, indent=2))
    settings = settings or _settings()
    if not settings.update(export=_merge_export(_stored_export(settings), values)):
        raise OSError(settings.error or "the settings file could not be written")
    return settings.path
