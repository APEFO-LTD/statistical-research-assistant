"""Test helpers: build the Stage 33 workspace on a fake page and click it."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

from ux_inventory import FakePage as _InventoryPage, walk  # noqa: E402


class LostUpdate(AssertionError):
    """A control on screen was changed but the change never reached the
    client (Flet 1.1 does not diff inside a frozen subtree)."""


class FletTree:
    """The control tree as a Flet 1.1 client holds it (Issue #80).

    ``update()`` computes the patch with Flet's own differ
    (``ObjectPatch.from_diff``, as ``Session.patch_control`` does) and
    serialises it with Flet's own MessagePack encoder (which takes the
    ``__prev_*`` snapshots the next diff starts from, as the transport does).
    The differ therefore freezes controls exactly as on the installed app:
    a new control in a list that takes the place of one with the same
    explicit ``key`` is diffed as a *frozen* pair, and it and every control
    below it get ``_frozen``; from then on assigning any property of it
    raises ``RuntimeError: Frozen controls cannot be updated``. A no-op
    ``update()`` hid exactly that (the scales register crash of Issue #80).

    After a page-wide update no control on screen may still hold a change
    that was not sent (``_dirty``): the differ does not look inside a frozen
    control, so a control below one, changed in place, would show its old
    state on the installed app (:class:`LostUpdate`).
    """

    def __init__(self):
        from flet.controls.base_control import BaseControl
        from flet.controls.object_patch import ObjectPatch
        from flet.messaging.protocol import configure_encode_object_for_msgpack
        import msgpack

        self._diff = lambda old, new: ObjectPatch.from_diff(old, new, control_cls=BaseControl)
        encode = configure_encode_object_for_msgpack(BaseControl)
        self._send = lambda patch: msgpack.packb(patch.to_message(), default=encode)
        self.root = None
        self.patches = 0

    def update(self, roots: list, controls: tuple = ()) -> None:
        """The whole tree (``page.update()``) or only ``controls``
        (``page.update(control)``: each subtree diffed in place)."""
        import warnings

        with warnings.catch_warnings():    # Flet's validate(): deprecated properties
            warnings.simplefilter("ignore", DeprecationWarning)
            if self.root is None:
                self.root = ft.Column(controls=list(roots))
                patch, _, _ = self._diff(None, self.root)   # the first page sent
                self._send(patch)
            elif controls:
                for control in controls:
                    patch, _, _ = self._diff(control, control)
                    self._send(patch)
            else:
                self.root.controls = list(roots)
                patch, _, _ = self._diff(self.root, self.root)
                self._send(patch)
                self.check_nothing_lost()
        self.patches += 1

    def check_nothing_lost(self) -> None:
        stack = [self.root]
        seen = set()
        while stack:
            item = stack.pop()
            if id(item) in seen:
                continue
            seen.add(id(item))
            dirty = getattr(item, "_dirty", None)
            if dirty and not hasattr(item, "_frozen"):
                raise LostUpdate(f"{type(item).__name__}(data={getattr(item, 'data', None)!r}) "
                                 f"changed {sorted(dirty)} but page.update() did not send it: "
                                 "it is inside a frozen (re-rendered) page")
            for name in ("controls", "content", "actions", "title", "label", "leading",
                         "trailing", "subtitle"):
                child = getattr(item, name, None)
                if isinstance(child, list):
                    stack.extend(c for c in child if isinstance(c, ft.Control))
                elif isinstance(child, ft.Control):
                    stack.append(child)


class FakePage(_InventoryPage):
    def __init__(self, width: int = 1440):
        super().__init__(width)
        self.dialog = None
        self.on_keyboard_event = None
        self.on_resize = None
        self.tree = FletTree()
        self.tasks: list = []          # page.run_task(...) requests, in order

    def update(self, *controls):
        """Flet 1.1's ``page.update()`` (the whole tree, a shown dialog
        included) or ``page.update(control, ...)`` (those subtrees), diffed
        and serialised as Flet does (see :class:`FletTree`)."""
        roots = list(self.controls) + ([self.dialog] if self.dialog is not None else [])
        if roots:
            self.tree.update(roots, controls)

    def run_task(self, handler, *args, **kwargs):
        """Recorded, not run: there is no client to answer ``focus()`` or
        ``scroll_to()``. A test reads :attr:`tasks` (``focus_requests``)."""
        self.tasks.append((handler, args, kwargs))

    def focus_requests(self) -> list:
        """The controls ``focus()`` was requested for, in order."""
        return [getattr(handler, "__self__", None) for handler, _, _ in self.tasks
                if getattr(handler, "__name__", "") == "focus"]

    def show_dialog(self, dialog):
        self.dialog = dialog
        self.update()

    def pop_dialog(self):
        self.dialog = None
        self.update()


class Workspace:
    """A live WorkspaceApp plus helpers to find and operate controls."""

    def __init__(self, width: int = 1440, *, language: str = "en", bridge=None,
                 root: Path | None = None):
        """``root`` reuses a data folder (an application restart); by default
        every workspace gets its own temporary folder."""
        from flet.controls.context import _context_page
        from workspace_shell import ClassicBridge, WorkspaceApp

        self.temp = None if root is not None else TemporaryDirectory()
        self.root = Path(root) if root is not None else Path(self.temp.name)
        # Settings live in the test folder, not in $HOME: the settings file
        # (root/settings.json, beside the projects) and the files of earlier
        # versions it is made from on the first start.
        from unittest import mock
        import app_preferences
        import workspace_shell

        self._settings = mock.patch.object(workspace_shell, "workspace_settings_path",
                                           lambda: self.root / "workspace.json")
        self._preferences = mock.patch.object(app_preferences, "preferences_path",
                                              lambda: self.root / "preferences.json")
        self._settings.start()
        self._preferences.start()
        self.page = FakePage(width)
        self._token = _context_page.set(self.page)
        self.app = WorkspaceApp(
            self.page, language=language,
            bridge=bridge or ClassicBridge(survey_root=self.root / "surveys"))
        self.app.mount()
        self.saved: list[Path] = []

        async def save_dialog(title, file_name, extension):
            path = self.root / file_name
            self.saved.append(path)
            return str(path)

        self.app.save_dialog = save_dialog

    def close(self):
        """Quit the application: the open project is closed, its lock released."""
        from flet.controls.context import _context_page

        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.app.projects.close(clear=False)
        self._settings.stop()
        self._preferences.stop()
        import workspace_tokens

        workspace_tokens.apply_density(workspace_tokens.DEFAULT_DENSITY)  # no leak between tests
        _context_page.reset(self._token)
        if self.temp is not None:
            self.temp.cleanup()

    # ------------------------------------------------------------ queries
    def controls(self, root=None) -> list:
        found = []
        walk(root or self.page.controls[0], lambda c, d: found.append(c))
        if self.page.dialog is not None:
            walk(self.page.dialog, lambda c, d: found.append(c))
        return found

    def find(self, data: str, kind=None):
        for control in self.controls():
            if getattr(control, "data", None) == data and (kind is None or isinstance(control, kind)):
                return control
        raise AssertionError(f"No control with data={data!r} on route {self.app.route}")

    def find_all(self, prefix: str) -> list:
        return [c for c in self.controls()
                if isinstance(getattr(c, "data", None), str) and c.data.startswith(prefix)]

    def texts(self) -> list[str]:
        return [c.value for c in self.controls()
                if isinstance(c, ft.Text) and isinstance(c.value, str)]

    def has_text(self, fragment: str) -> bool:
        return any(fragment in text for text in self.texts())

    # ------------------------------------------------------------ actions
    def run(self, result):
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return result

    def dispatch(self, handler, event):
        """Call an event handler exactly as Flet 1.x does
        (``flet/controls/base_control.py``): a coroutine function is awaited;
        any other callable is called and whatever it returns is dropped. A
        plain handler, such as a lambda, that returns a coroutine therefore does
        nothing in the application: it fails here instead of being run."""
        from flet.utils.object_model import get_param_count

        def call():
            return handler() if get_param_count(handler) == 0 else handler(event)

        if inspect.iscoroutinefunction(handler):
            return asyncio.run(call())
        result = call()
        if inspect.iscoroutine(result):
            result.close()
            raise AssertionError(f"{handler!r} returns a coroutine that Flet never awaits: "
                                 "the action would do nothing in the application")
        return result

    def click(self, data: str):
        control = self.find(data)
        handler = getattr(control, "on_click", None)
        if handler is None:
            raise AssertionError(f"{data} is not clickable")
        if getattr(control, "disabled", False):
            raise AssertionError(f"{data} is disabled")
        return self.dispatch(handler, SimpleNamespace(control=control, data=None))

    @staticmethod
    def client_sets(control, **values) -> None:
        """What the user changed in the client reaches the control as Flet
        1.1 applies it (``Session.apply_patch`` → ``patch_dataclass``): a
        mounted, possibly frozen, control takes it without a frozen check."""
        from flet.utils.object_model import patch_dataclass

        patch_dataclass(control, values)

    def choose(self, data: str, value):
        control = self.find(data, ft.Dropdown)
        self.client_sets(control, value=value)
        return self.dispatch(control.on_select, SimpleNamespace(control=control, data=value))

    def check(self, data: str, value: bool = True):
        control = self.find(data, ft.Checkbox)
        self.client_sets(control, value=value)
        return self.dispatch(control.on_change, SimpleNamespace(control=control, data=value))

    def type(self, data: str, value: str):
        control = self.find(data, ft.TextField)
        self.client_sets(control, value=value)
        return self.dispatch(control.on_change, SimpleNamespace(control=control, data=value))

    def segment(self, data: str, key: str):
        group = self.find(data)
        for control in self.controls(group):
            if isinstance(control, ft.Button) and control.data == key:
                return self.dispatch(control.on_click, SimpleNamespace(control=control))
        raise AssertionError(f"segment {key} not in {data}")

    def key(self, key: str, *, ctrl=False, shift=False, alt=False):
        event = SimpleNamespace(key=key, ctrl=ctrl, shift=shift, alt=alt, meta=False)
        return self.dispatch(self.app.on_keyboard, event)
