"""One Export action for the Data, Results and Reports pages (Stage 37, #67).

Each page shows the same small card: a format (the last one used is
remembered in the settings file, ``user_settings``, key ``export``; Settings →
*Export defaults* shows and changes the same choices), one button that opens the system's Save
dialog, and the advanced options folded away. The data page's default is a
copy of the data (.xlsx with its codebook), exact unless the card lists the
values the format cannot hold; the results page's an
editable results workbook; the reports page's the reproducibility bundle.
Exporting a dataset never needs a report.

Before saving, the card says what a format cannot carry (.sav), lists every
name or field that changes for SPSS and every value the .xlsx format cannot
hold exactly (with CSV as the exact alternative), and warns when the rows look as if they
could identify participants. Nothing is uploaded: files are written only
where the researcher chooses, to a temporary file first, re-opened with an
independent reader (signature and row count) and then moved into place
(data_export.save_atomic). The outcome names the file and what was checked.
"""

from __future__ import annotations

import asyncio
import time

import flet as ft

import workspace_components as wc
import workspace_tokens as tk

CONTEXTS = ("data", "results", "reports")
FORMATS = {"data": ("xlsx", "sav", "csv", "bundle"), "results": ("results", "bundle"),
           "reports": ("bundle", "results")}
DEFAULTS = {"data": "xlsx", "results": "results", "reports": "bundle"}
EXTENSIONS = {"xlsx": "xlsx", "sav": "sav", "csv": "csv", "bundle": "zip", "results": "xlsx"}
ROW_LEVEL = ("xlsx", "sav", "csv", "bundle")
SCOPES = ("all", "selected", "report")
PROGRESS_SECONDS = 0.5


def forget_choices(app) -> None:
    """The Export cards read the remembered choices again (after Settings →
    *Export defaults* or *Reset settings* changed them)."""
    for name in CONTEXTS:
        panel = getattr(app.pages.get(name), "export", None)
        if isinstance(panel, ExportPanel):
            panel._chosen = panel._layout = panel._bom = None


class ExportPanel:
    """The Export card of one page (``context``: data, results or reports)."""

    def __init__(self, app, context: str):
        if context not in CONTEXTS:
            raise ValueError(context)
        self.app, self.context = app, context
        self.opened: set[str] = set()
        self.feedback: tuple[str, str] | None = None
        self.sections = {"data", "codebook", "scales"}
        self.scope = "all"
        self.include_report = True
        self._chosen: str | None = None
        self._layout: str | None = None
        self._bom: bool | None = None
        self._cache: tuple | None = None       # (key, codebook)
        self._plans: tuple | None = None       # (key, {"xlsx": …, "sav": …})
        self._facts: dict = {}

    # ------------------------------------------------------------ choices
    def _preferences(self) -> dict:
        from app_preferences import export_preferences

        try:
            return export_preferences(settings=self.app.settings)
        except Exception:
            return {}

    def _remember(self, **values) -> None:
        from app_preferences import remember_export

        try:
            remember_export(values, settings=self.app.settings)
        except Exception:
            pass        # a convenience: never block an export

    @property
    def format(self) -> str:
        if self._chosen is None:
            remembered = (self._preferences().get("formats") or {}).get(self.context)
            self._chosen = remembered if remembered in FORMATS[self.context] \
                else DEFAULTS[self.context]
        return self._chosen

    @property
    def layout(self) -> str:
        if self._layout is None:
            remembered = self._preferences().get("csv_layout")
            self._layout = remembered if remembered in ("comma", "semicolon") else (
                "semicolon" if self.app.session.language in ("lv", "ru") else "comma")
        return self._layout

    @property
    def bom(self) -> bool:
        if self._bom is None:
            remembered = self._preferences().get("csv_bom")
            self._bom = bool(remembered) if isinstance(remembered, bool) else True
        return self._bom

    def _choose(self, value: str | None) -> None:
        if value in FORMATS[self.context]:
            self._chosen = value
            self.feedback = None
            formats = dict(self._preferences().get("formats") or {})
            formats[self.context] = value
            self._remember(formats=formats)
        self.app.render()

    def _set_layout(self, value: str | None) -> None:
        if value in ("comma", "semicolon"):
            self._layout = value
            self._remember(csv_layout=value)
        self.app.render()

    def _set_bom(self, value: bool) -> None:
        self._bom = bool(value)
        self._remember(csv_bom=bool(value))
        self.app.render()

    def _set_section(self, name: str, value: bool) -> None:
        (self.sections.add if value else self.sections.discard)(name)
        self.app.render()

    def _set_scope(self, value: str | None) -> None:
        if value in SCOPES:
            self.scope = value
        self.app.render()

    def _set_report(self, value: bool) -> None:
        self.include_report = bool(value)
        self.app.render()

    # ------------------------------------------------------------- inputs
    def entries(self) -> list:
        s = self.app.session
        if self.context == "results" and self.scope == "selected":
            entry = s.result(s.selected_result) or (s.results[-1] if s.results else None)
            return [entry] if entry is not None else []
        if self.scope == "report" and self.context != "data":
            return s.report_entries()
        return list(s.results)

    def codebook(self):
        """The codebook of the dataset in use (cached while nothing changes)."""
        import app_identity
        import export_bundle

        app, s = self.app, self.app.session
        key = (id(s.df), s.df.shape, tuple(s.variables.items()),
               len(s.pending_transformations), app.projects.dataset_id)
        if self._cache is None or self._cache[0] != key:
            project = app.projects.project if app.projects.active else None
            book = export_bundle.codebook_for(s, project=project,
                                              dataset_id=app.projects.dataset_id,
                                              app_version=app_identity.build_info().version)
            self._cache = (key, book)
        return self._cache[1]

    def plan(self, fmt: str):
        """What the .xlsx (:func:`data_export.plan_xlsx`) or .sav
        (:func:`data_export.plan_sav`) export changes, computed once per
        version of the data (not on every render, review integration F2)."""
        import data_export as de

        book = self.codebook()
        key = self._cache[0] if self._cache else None
        if self._plans is None or self._plans[0] != key:
            self._plans = (key, {})
        plans = self._plans[1]
        if fmt not in plans:
            plans[fmt] = de.plan_xlsx(self.app.session.df) if fmt == "xlsx" else \
                de.plan_sav(self.app.session.df, book)
        return plans[fmt]

    def _stem(self) -> str:
        import export_bundle

        return export_bundle._safe_stem(self.app.session.source_name or "data")

    # -------------------------------------------------------------- build
    def build(self) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        fmt = self.format
        context = self.context
        needs_data = fmt in ("xlsx", "sav", "csv", "bundle")
        content: list[ft.Control] = []
        if needs_data and not s.has_data:
            content.append(wc.notice(ui, ui.t("export.no_data"), "neutral",
                                     data=f"export-blocked-{context}"))
        elif fmt == "results" and not s.results:
            content.append(wc.notice(ui, ui.t("export.no_results"), "neutral",
                                     data=f"export-blocked-{context}"))
        options = [(key, ui.t(f"export.format.{key}")) for key in FORMATS[context]]
        content.insert(0, ft.Row([
            wc.dropdown(ui, ui.t("export.format"), options, fmt,
                        on_select=lambda e: self._choose(e.control.value), width=320,
                        data=f"export-format-{context}"),
            wc.button(ui, ui.t(f"export.save.{fmt}"), wc.handler(self._export), kind="primary",
                      icon=ft.Icons.SAVE_ALT, data=f"export-save-{context}"),
        ], wrap=True, spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if fmt == "sav" and s.has_data:
            content += self._sav_notices()
        if s.has_data and (fmt == "bundle" or (fmt == "xlsx" and "data" in self.sections)):
            content += self._xlsx_notices(fmt)
        if fmt == "csv" and s.has_data:
            content.append(wc.caption(ui, ui.t("export.csv.note"), data="export-csv-note"))
        if fmt in ROW_LEVEL and s.has_data and (fmt != "xlsx" or "data" in self.sections):
            content += self._sensitive_notice()
        content.append(self._advanced())
        if self.feedback:
            content.append(wc.notice(ui, self.feedback[0], self.feedback[1],
                                     data=f"export-feedback-{context}"))
        return wc.card(ui, content, title=ui.t(f"export.title.{context}"),
                       description=ui.t(f"export.body.{context}"), data=f"export-{context}")

    def xlsx_lines(self) -> list[str]:
        """One line per variable and reason the .xlsx Data sheet changes."""
        t = self.app.t
        return [t(f"export.xlsx.change.{reason}", name=name, count=count)
                for name, reason, count in self.plan("xlsx")]

    def _xlsx_notices(self, fmt: str) -> list[ft.Control]:
        """Before saving: every value the .xlsx format cannot hold exactly,
        and the safe alternative (review X2, integrity F1)."""
        ui = self.app.ui
        lines = self.xlsx_lines()
        if not lines:
            return []
        count = sum(n for _, reason, n in self.plan("xlsx") if not reason.startswith("name_"))
        hint = ui.t("export.xlsx.changes_bundle" if fmt == "bundle" else
                    "export.xlsx.changes_hint")
        return [wc.notice(ui, "\n".join(lines) + "\n" + hint, "warning",
                          title=ui.t("export.xlsx.changes_title", count=count),
                          data="export-xlsx-changes")]

    def _sav_notices(self) -> list[ft.Control]:
        ui = self.app.ui
        book = self.codebook()
        plan = self.plan("sav")
        lines = [ui.t("export.sav.renamed", name=original, spss=spss)
                 for original, spss in plan.renamed.items()]
        for name, key, values in plan.changes:
            lines.append(ui.t(key, name=name or book.dataset, **values))
        notices = [wc.notice(ui, ui.t("export.sav.limits"), "neutral",
                             data="export-sav-limits")]
        if lines:
            notices.append(wc.notice(ui, "\n".join(lines), "warning",
                                     title=ui.t("export.sav.changes_title", count=len(lines)),
                                     data="export-sav-changes"))
        return notices

    def _sensitive_notice(self) -> list[ft.Control]:
        import data_export as de

        ui, s = self.app.ui, self.app.session
        try:
            found = de.sensitive_columns(s.df, levels={
                n: (v.confirmed, v.suggested) for n, v in s.variables.items()})
        except Exception:
            found = []
        if not found:
            return []
        shown = "; ".join(f"{c.name} ({ui.t('export.sensitive.' + c.reason)})"
                          for c in found[:12])
        if len(found) > 12:
            shown += " …"
        return [wc.notice(ui, ui.t("export.sensitive_body", columns=shown) + "\n"
                          + ui.t("export.not_uploaded"), "warning",
                          title=ui.t("export.sensitive_title", count=len(found)),
                          data="export-sensitive")]

    def _advanced(self) -> ft.Control:
        import data_export as de

        ui, s, fmt = self.app.ui, self.app.session, self.format
        controls: list[ft.Control] = []
        if fmt == "xlsx":
            controls.append(wc.section_label(ui, ui.t("export.sections")))
            for name in de.SECTIONS:
                if name == "results" and not s.results:
                    continue
                controls.append(wc.checkbox(ui, ui.t(f"export.section.{name}"),
                                            name in self.sections,
                                            on_change=lambda e, n=name: self._set_section(
                                                n, bool(e.control.value)),
                                            data=f"export-section-{name}"))
        if fmt == "csv":
            controls.append(wc.dropdown(
                ui, ui.t("export.csv.layout"),
                [("comma", ui.t("export.csv.layout.comma")),
                 ("semicolon", ui.t("export.csv.layout.semicolon"))], self.layout,
                on_select=lambda e: self._set_layout(e.control.value), width=420,
                data="export-csv-layout"))
            controls.append(wc.checkbox(ui, ui.t("export.csv.bom"), self.bom,
                                        on_change=lambda e: self._set_bom(bool(e.control.value)),
                                        data="export-csv-bom"))
        if fmt in ("results", "bundle") and self.context != "data":
            scopes = [("all", ui.t("export.scope.all"))]
            if self.context == "results":
                scopes.append(("selected", ui.t("export.scope.selected")))
            scopes.append(("report", ui.t("export.scope.report")))
            controls.append(wc.dropdown(ui, ui.t("export.scope"), scopes,
                                        self.scope if self.scope in dict(scopes) else "all",
                                        on_select=lambda e: self._set_scope(e.control.value),
                                        width=360, data="export-scope"))
        if fmt == "bundle":
            controls.append(wc.checkbox(ui, ui.t("export.bundle.report"), self.include_report,
                                        on_change=lambda e: self._set_report(
                                            bool(e.control.value)),
                                        data="export-bundle-report"))
        if fmt == "sav":
            controls.append(wc.caption(ui, ui.t("export.sav.names_hint")))
        if not controls:
            controls.append(wc.caption(ui, ui.t("export.advanced_none")))
        return wc.expansion(ui, wc.text(ui, ui.t("export.advanced"), tk.TYPE_LABEL,
                                        weight=ft.FontWeight.W_600),
                            [ft.Container(ft.Column(controls, spacing=tk.SPACE_2),
                                          padding=tk.SPACE_4)],
                            key=f"export-advanced-{self.context}", opened=self.opened,
                            subtitle=wc.caption(ui, ui.t("export.advanced_hint")),
                            data=f"export-advanced-{self.context}")

    # ------------------------------------------------------------- export
    def _progress(self, loop):
        """A progress callback for the worker thread (rows written)."""
        last = [0.0]

        def report(done: int, total: int) -> None:
            now = time.monotonic()
            if done < total and now - last[0] < PROGRESS_SECONDS:
                return
            last[0] = now
            text = self.app.t("export.progress", done=f"{done:,}", total=f"{total:,}")
            try:
                loop.call_soon_threadsafe(self.app.status, text, "info")
            except RuntimeError:
                pass
        return report

    async def _export(self, e=None):
        import data_export as de

        app, s, fmt = self.app, self.app.session, self.format
        if fmt in ("xlsx", "sav", "csv", "bundle") and not s.has_data:
            self.feedback = (app.t("export.no_data"), "warning")
            app.render()
            return
        if fmt == "xlsx" and not self.sections & set(de.SECTIONS):
            self.feedback = (app.t("export.nothing_selected"), "warning")
            app.render()
            return
        entries = self.entries()
        if fmt == "results" and not entries:
            self.feedback = (app.t("export.no_results"), "warning")
            app.render()
            return
        if fmt in ("results", "bundle") or (fmt == "xlsx" and "results" in self.sections):
            for entry in entries:            # restored results get their engine object back
                if entry.run.result is None and app.projects.active:
                    await app.projects.ensure_result(entry)
        formats = dict(self._preferences().get("formats") or {})
        formats[self.context] = fmt
        self._remember(formats=formats)
        writer, name = self._writer(fmt, entries, asyncio.get_running_loop())
        self._facts = {}
        outcome = await app.save_file(app.t(f"export.save.{fmt}"), name, EXTENSIONS[fmt], writer,
                                      announce=self._announce)
        self.feedback = (outcome.message, outcome.tone)
        app.render()

    def _writer(self, fmt: str, entries: list, loop):
        """(writer(path) for the worker thread, suggested file name). Everything
        the writer needs is taken from the session here, on the UI thread."""
        import app_identity
        import data_export as de
        import export_bundle
        from project_store import library_versions

        app, s = self.app, self.app.session
        stem = self._stem()
        progress = self._progress(loop)
        df = s.df.copy() if s.has_data else None
        book = self.codebook() if s.has_data else None
        if fmt == "xlsx":
            sections = set(self.sections)
            extra = export_bundle.results_sheets(entries) if "results" in sections and entries \
                else []
            rows = export_bundle.provenance_table(entries) if entries else []

            def write(path):
                self._facts = de.export_xlsx(path, df, book, sections=sections, extra=extra,
                                             provenance={"rows": rows}, progress=progress)
                return self._facts["path"]
            return write, f"{stem}.xlsx"
        if fmt == "csv":
            layout, bom = self.layout, self.bom

            def write(path):
                self._facts = de.export_csv(path, df, book, bom=bom, layout=layout,
                                            progress=progress)
                return self._facts["path"]
            return write, f"{stem}.csv"
        if fmt == "sav":
            plan = self.plan("sav")

            def write(path):
                self._facts = de.export_sav(path, df, book, plan=plan)
                return self._facts["path"]
            return write, f"{stem}.sav"
        if fmt == "results":
            def write(path):
                self._facts = export_bundle.export_results(path, entries, progress=progress)
                return self._facts["path"]
            return write, f"{stem}_results.xlsx"
        # the reproducibility bundle
        report_writer, report_name = self._report_writer() if self.include_report else (None, "")
        info = app_identity.build_info()
        project = None
        if app.projects.active:
            project_info = app.projects.info()
            project = {"title": project_info.title, "id": project_info.id}
        libraries = library_versions()

        def write(path):
            self._facts = export_bundle.write_bundle(
                path, df=df, codebook=book, entries=entries, report_writer=report_writer,
                report_name=report_name or "research_report.docx",
                app={"version": info.version, "channel": info.channel, "build": info.build,
                     "commit": info.commit}, libraries=libraries, project=project,
                progress=progress)
            return self._facts["path"]
        return write, f"{stem}_bundle.zip"

    def _report_writer(self):
        """The Word report as composed on the Reports page, or (None, "") when
        there is none to include (no entries, or outdated ones not allowed)."""
        app = self.app
        reports = app.pages.get("reports")
        if reports is None or not app.session.report_order or reports._blocked():
            return None, ""
        import app_identity
        import report_docx
        import research_report as rr

        inputs = reports.report_inputs()
        plan = rr.plan_report(inputs)
        version = app_identity.build_info().version

        def write(path):
            document = report_docx.build_research_docx(plan, version=version)
            return report_docx.save_report_docx(path, document)
        return write, report_docx.default_file_name(inputs.title or inputs.project)

    def _announce(self, path) -> str:
        facts, t = self._facts, self.app.t
        checked = facts.get("verified") or {}
        if self.format == "bundle":
            return t("export.saved_bundle", path=path, files=facts.get("files", 0),
                     rows=checked.get("rows", facts.get("rows", 0)),
                     syntax=facts.get("syntax", 0)) + self._changed_note(facts)
        if self.format == "results":
            return t("export.saved_results", path=path, sheets=len(checked.get("sheets") or ()))
        rows = checked.get("rows")
        columns = facts.get("columns") or len(facts.get("names") or ()) or \
            (self.app.session.df.shape[1] if self.app.session.has_data else 0)
        if self.format == "csv":
            from pathlib import Path

            return t("export.saved_csv", path=path, rows=rows, columns=columns,
                     codebook=Path(facts.get("codebook", "")).name,
                     signature=checked.get("signature", ""))
        if rows is None:
            return t("export.saved_results", path=path, sheets=len(checked.get("sheets") or ()))
        message = t("export.saved", path=path, rows=rows, columns=columns,
                    signature=checked.get("signature", ""))
        return message + self._changed_note(facts)

    def _changed_note(self, facts: dict) -> str:
        """After saving: the outcome never reads as an exact copy when the
        .xlsx format changed values (review X2)."""
        changes = {"bundle": facts.get("xlsx_changes"),
                   "xlsx": facts.get("changes")}.get(self.format)
        if not isinstance(changes, list) or not changes:
            return ""
        count = sum(n for _, reason, n in changes if not str(reason).startswith("name_"))
        names = list(dict.fromkeys(str(name) for name, _, _ in changes))
        shown = ", ".join(names[:6]) + (" …" if len(names) > 6 else "")
        return " " + self.app.t("export.saved_changed", count=count, columns=shown)


# ------------------------------------------- Settings → Export defaults (Stage 37)
def export_settings(page) -> list[ft.Control]:
    """The section *Export defaults* of the Settings page: the choices every
    Export card starts with, exactly those the cards remember (the settings
    file, key ``export``). A change here is a change of the cards, and the
    other way round."""
    from app_preferences import export_preferences, remember_export

    app, ui = page.app, page.app.ui
    try:
        remembered = export_preferences(settings=app.settings)
    except Exception:
        remembered = {}
    formats = remembered.get("formats") or {}

    def keep(**values) -> None:
        try:
            remember_export(values, settings=app.settings)
        except (OSError, ValueError) as error:
            app.status(ui.t("settings.not_saved", error=str(error)), "warning")
        forget_choices(app)
        app.render()

    rows: list[ft.Control] = [wc.text(ui, ui.t("settings.export_body"), tk.TYPE_BODY)]
    pickers = []
    for context in CONTEXTS:
        value = formats.get(context)
        value = value if value in FORMATS[context] else DEFAULTS[context]
        pickers.append(wc.dropdown(
            ui, ui.t(f"settings.export_format.{context}"),
            [(fmt, ui.t(f"export.format.{fmt}")) for fmt in FORMATS[context]], value,
            on_select=lambda e, c=context: keep(formats={c: e.control.value}), width=340,
            data=f"settings-export-format-{context}"))
    rows.append(ft.Row(pickers, wrap=True, spacing=tk.SPACE_3, run_spacing=tk.SPACE_3))
    layout = remembered.get("csv_layout")
    rows.append(wc.dropdown(
        ui, ui.t("export.csv.layout"),
        [(key, ui.t(f"export.csv.layout.{key}")) for key in ("comma", "semicolon")],
        layout if layout in ("comma", "semicolon") else (
            "semicolon" if app.session.language in ("lv", "ru") else "comma"),
        on_select=lambda e: keep(csv_layout=e.control.value), width=460,
        data="settings-export-csv-layout"))
    if layout not in ("comma", "semicolon"):
        rows.append(wc.caption(ui, ui.t("settings.export_layout_default"),
                               data="settings-export-csv-layout-note"))
    bom = remembered.get("csv_bom")
    rows.append(wc.checkbox(ui, ui.t("export.csv.bom"), bom if isinstance(bom, bool) else True,
                            on_change=lambda e: keep(csv_bom=bool(e.control.value)),
                            data="settings-export-csv-bom"))
    rows.append(wc.caption(ui, ui.t("settings.export_privacy"), data="settings-export-privacy"))
    return rows


def register_settings() -> None:
    """Add this module's section to the Settings page (idempotent)."""
    from workspace_settings import SettingsSection, register

    register(SettingsSection("export", "settings.section.export", 65, export_settings))


register_settings()
