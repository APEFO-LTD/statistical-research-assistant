"""Stage 37 (Fable review §4 item 2): the scales register card of the Data page.

Several scales are defined in one place, then scored and checked in one
action each (``scale_register`` holds the logic):

* each scale's items are chosen in the variable panel (search, a pattern,
  a range ``first..last``, name groups) — the panel of the Analyze page;
* every reverse-keyed item is marked by its own box, which is the
  researcher's confirmation for that item; nothing is marked by the
  program;
* the scoring rule (mean or sum) and the minimum number of answered items
  have no default: the scale cannot be scored until both are chosen;
* the design confirmation of item diagnostics ("the items are meant to
  measure one construct") is given per scale, for its items, and a change
  of the items clears it (K1);
* **Score all** scores every complete scale with Data → Prepare's own
  functions; **Check reliability of all** runs the item diagnostics of the
  Analyze page for every scale whose confirmations hold. Each result is a
  normal stored result (provenance, Results, the Word report).

A scale that is not ready says why, in text; the actions say how many
scales they act on and are disabled, with the reason, when none is ready.
"""

from __future__ import annotations

import asyncio

import flet as ft

import scale_register as sr
import workspace_components as wc
import workspace_tokens as tk
import workspace_variables as wv

PANEL = "scales-items"


def _item_role():
    from workspace_methods import ORDERED, Role

    return Role("items", "role.items", ORDERED, multiple=True, minimum=2)


class ScalesCard:
    def __init__(self, app):
        self.app = app
        self.definitions: list[sr.ScaleDefinition] = []
        self.editing: int | None = None
        self.filters: dict[str, str] = {}
        self.messages: list[tuple[str, str]] = []
        self.running = False
        self._loaded_for = object()
        self._saved: dict | None = None

    # ------------------------------------------------------------- storage
    def _project(self):
        projects = self.app.projects
        return projects.project if projects.active else None

    def _load(self) -> None:
        """The register of the project on screen (once per opened project)."""
        projects = self.app.projects
        marker = (projects.generation, projects.info().id if projects.active else None)
        if marker == self._loaded_for:
            return
        self._loaded_for = marker
        self.editing, self.messages, self.filters = None, [], {}
        project = self._project()
        if project is None:
            self.definitions, self._saved = [], None
            return
        try:
            stored = project.scale_register()
        except Exception:
            stored = {}
        self.definitions = sr.register_from_json(stored)
        self._saved = sr.register_json(self.definitions) if stored else None

    def _save(self) -> None:
        """Keep the register in the project (only when it changed)."""
        project = self._project()
        current = sr.register_json(self.definitions)
        if project is None or current == self._saved:
            return
        try:
            project.save_scale_register(current)
            self._saved = current
        except Exception as error:      # read-only copy, locked file: said, not hidden
            self.app.status(self.app.t("scales.save_failed", error=error), "danger")

    # --------------------------------------------------------------- edits
    def _set(self, index: int, definition: sr.ScaleDefinition, *, render: bool = True,
             save: bool = True) -> None:
        self.definitions[index] = definition
        if save:
            self._save()
        if render:
            self.app.render()

    def _add(self, e=None) -> None:
        self.definitions.append(sr.ScaleDefinition(""))
        self.editing = len(self.definitions) - 1
        self.filters, self.messages = {}, []
        self._save()
        self.app.render()
        self.app.request_focus("scales-name")

    def _edit(self, index: int) -> None:
        self.editing = None if self.editing == index else index
        self.filters = {}
        self._save()
        self.app.render()

    def _remove(self, index: int) -> None:
        del self.definitions[index]
        self.editing = None
        self._save()
        self.app.render()

    def _items(self, index: int, names) -> None:
        self._set(index, self.definitions[index].with_items(names))

    def _toggle_item(self, index: int, name: str, value: bool) -> None:
        items = list(self.definitions[index].items)
        if value and name not in items:
            items.append(name)
        if not value and name in items:
            items.remove(name)
        order = list(self.app.session.variables)
        items.sort(key=lambda n: order.index(n) if n in order else len(order))
        self._items(index, items)

    def _add_items(self, index: int, names) -> None:
        self._items(index, wv.merged(list(self.definitions[index].items), names))

    def _remove_items(self, index: int, names) -> None:
        gone = set(names)
        self._items(index, [n for n in self.definitions[index].items if n not in gone])

    def _name(self, index: int, value: str) -> None:
        from dataclasses import replace

        self._set(index, replace(self.definitions[index], name=(value or "").strip()),
                  save=False)

    def _method(self, index: int, value: str) -> None:
        from dataclasses import replace

        self._set(index, replace(self.definitions[index], method=value))

    def _minimum(self, index: int, value: str) -> None:
        from dataclasses import replace

        self._set(index, replace(self.definitions[index], min_answered=sr.parse_count(value)),
                  save=False)

    def _range(self, index: int, which: str, value: str) -> None:
        d = self.definitions[index]
        number = sr.parse_number(value)
        low, high = (number, d.high) if which == "low" else (d.low, number)
        self._set(index, d.with_range(low, high), save=False)

    def _reverse(self, index: int, item: str, value: bool) -> None:
        self._set(index, self.definitions[index].with_reverse(item, value))

    def _confirm(self, index: int, key: str, value: bool) -> None:
        self._set(index, self.definitions[index].confirm(key, value))

    def _query(self, text: str) -> None:
        self.filters[PANEL] = text
        self.app.render()

    def _expand(self, value: bool) -> None:
        self.filters[f"{PANEL}:all"] = "1" if value else ""
        self.app.render()

    # ------------------------------------------------------------- actions
    def ready_to_score(self) -> list[sr.ScaleDefinition]:
        columns = list(map(str, self.app.session.df.columns))
        return [d for d in self.definitions if not sr.scoring_problems(d, columns)]

    def ready_to_check(self) -> list[sr.ScaleDefinition]:
        s = self.app.session
        return [d for d in self.definitions if not sr.reliability_problems(d, s.df, s)]

    def _score_all(self, e=None) -> None:
        app, s = self.app, self.app.session
        ready = self.ready_to_score()
        if not ready:
            return
        self._save()
        try:
            scored = sr.score_all(s.df, ready)
        except ValueError as error:
            self.messages = [(app.t("scales.score_failed", error=error), "danger")]
            app.render()
            return
        from data_preparation import history_record

        before = dict(s.variables)
        s.add_prepared_columns(scored.frame, [history_record(step) for step in scored.steps])
        # A reversed item is the item read the other way round: it keeps the
        # level confirmed for the item (it is defined by its rule). The
        # scores themselves wait for the researcher's confirmation.
        for d in ready:
            for item in d.reverse:
                target = sr.reversed_name(item)
                info = before.get(item)
                if target not in before and info is not None and info.confirmed != "unknown" \
                        and target in s.variables:
                    s.confirm_level(target, info.confirmed, where="derived")
        self.messages = [(app.t("scales.scored", count=len(scored.scored),
                                names=", ".join(scored.scored)), "success")]
        self.editing = None
        app.status(self.messages[0][0], "success")
        app.render()

    def _pending_scores(self) -> list[str]:
        s = self.app.session
        return [d.name for d in self.definitions
                if d.name in s.variables and s.variables[d.name].confirmed == "unknown"]

    def _confirm_scores(self, e=None) -> None:
        """The researcher's confirmation, named on the button, that the new
        scores are quantitative (one action for the scores listed)."""
        s = self.app.session
        for name in self._pending_scores():
            s.confirm_level(name, "scale")
        self.app.render()

    async def _check_all(self, e=None) -> None:
        app, s = self.app, self.app.session
        ready = self.ready_to_check()
        if not ready or self.running:
            return
        self._save()
        self.running = True
        app.render()
        started = (app.projects.generation, id(s.df))
        from workspace_methods import ITEMS_NOT_TOTALS, METHODS, default_options, run_method

        spec = METHODS["item_diagnostics"]
        options = default_options(spec)

        def calculate():
            out = []
            for d in ready:
                confirms = {"one_construct": True}
                if sr.totals_among(s.df, d):
                    confirms[ITEMS_NOT_TOTALS.key] = True
                roles = {"items": d.scored_items()}
                try:
                    out.append((d, roles, confirms, run_method("item_diagnostics", s, roles,
                                                               options, confirms), None))
                except Exception as error:      # one scale's failure does not stop the others
                    out.append((d, roles, confirms, None, error))
            return out

        try:
            done = await asyncio.to_thread(calculate)
        finally:
            self.running = False
        if (app.projects.generation, id(s.df)) != started:
            self.messages = [(app.t("run.discarded"), "warning")]
            app.render()
            return
        messages = []
        for d, roles, confirms, run, error in done:
            if run is None:
                messages.append((app.t("scales.check_failed", name=d.name, error=error),
                                 "danger"))
                continue
            confirmed = [c.label for c in spec.confirmations if confirms.get(c.key)]
            if confirms.get(ITEMS_NOT_TOTALS.key):
                confirmed.append(ITEMS_NOT_TOTALS.label)
            s.add_result(run, confirmed, method="item_diagnostics", roles=roles,
                         options=dict(options), confirms=dict(confirms))
        checked = len(done) - len(messages)
        if checked:
            messages.insert(0, (app.t("scales.checked", count=checked), "success"))
            app.status(messages[0][0], "success")
        self.messages = messages
        app.render()

    def latest_result(self, definition: sr.ScaleDefinition):
        """The newest item-diagnostics result of this scale's items, on the
        data on screen (or None)."""
        s = self.app.session
        items = definition.scored_items()
        for entry in reversed(s.results):
            if entry.method == "item_diagnostics" and list((entry.roles or {}).get("items")
                                                         or []) == items:
                return entry
        return None

    def _open_result(self, entry_id: int) -> None:
        self.app.session.selected_result = entry_id
        self.app.navigate("results")

    def _report_all(self, e=None) -> None:
        for d in self.definitions:
            entry = self.latest_result(d)
            if entry is not None and not entry.in_report:
                self.app.session.toggle_report(entry.id)
        self.app.render()

    # -------------------------------------------------------------- layout
    def build(self) -> ft.Control:
        self._load()
        app, ui, s = self.app, self.app.ui, self.app.session
        content: list[ft.Control] = []
        for index, definition in enumerate(self.definitions):
            content.append(self._row(index, definition))
            if index == self.editing:
                content.append(self._editor(index, definition))
        for message, tone in self.messages:
            content.append(wc.notice(ui, message, tone, data="scales-message"))
        to_score, to_check = self.ready_to_score(), self.ready_to_check()
        pending = self._pending_scores()
        actions = [wc.button(ui, ui.t("scales.add"), self._add, icon=ft.Icons.ADD,
                             data="scales-add")]
        actions.append(wc.button(ui, ui.t("scales.score_all", count=len(to_score)),
                                 self._score_all, kind="primary" if to_score else "secondary",
                                 icon=ft.Icons.FUNCTIONS, disabled=not to_score,
                                 tooltip=None if to_score else ui.t("scales.score_none"),
                                 data="scales-score-all"))
        if pending:
            actions.append(wc.button(ui, ui.t("scales.confirm_levels", count=len(pending),
                                              names=", ".join(pending)),
                                     self._confirm_scores, icon=ft.Icons.RULE,
                                     tooltip=ui.t("scales.confirm_levels_tip"),
                                     data="scales-levels"))
        actions.append(wc.button(ui, ui.t("scales.check_all", count=len(to_check)),
                                 self._check_all, kind="primary" if to_check and not to_score
                                 else "secondary", icon=ft.Icons.VERIFIED_OUTLINED,
                                 disabled=not to_check or self.running,
                                 tooltip=None if to_check else ui.t("scales.check_none"),
                                 data="scales-check-all"))
        if any(self.latest_result(d) is not None and not self.latest_result(d).in_report
               for d in self.definitions):
            actions.append(wc.button(ui, ui.t("scales.report_all"), self._report_all,
                                     kind="quiet", icon=ft.Icons.POST_ADD,
                                     data="scales-report-all"))
        if self.definitions and not to_score and not to_check:
            content.append(wc.caption(ui, ui.t("scales.nothing_ready"), data="scales-why"))
        return wc.card(ui, content, title=ui.t("scales.title"),
                       description=ui.t("scales.body"), actions=actions, data="scales-card")

    def _status(self, definition: sr.ScaleDefinition) -> tuple[str, str]:
        ui, s = self.app.ui, self.app.session
        entry = self.latest_result(definition)
        if entry is not None:
            result = entry.run.result
            return ui.t("scales.state.checked", alpha=result.alpha.text(),
                        omega=result.omega.text(), n=result.n_complete), "success"
        if definition.name and definition.name in s.df.columns:
            return ui.t("scales.state.scored"), "info"
        problems = sr.scoring_problems(definition, s.df.columns)
        if problems:
            key, values = problems[0]
            return ui.t(key, **values), "warning"
        return ui.t("scales.state.ready"), "info"

    def _row(self, index: int, d: sr.ScaleDefinition) -> ft.Control:
        ui = self.app.ui
        name = d.name or ui.t("scales.unnamed")
        rule = ui.t(f"scales.method.{d.method}") if d.method else ui.t("scales.method.none")
        minimum = str(d.min_answered) if d.min_answered is not None else "—"
        facts = ui.t("scales.facts", items=len(d.items), reverse=len(d.reverse), rule=rule,
                     minimum=minimum)
        state, tone = self._status(d)
        buttons = [wc.button(ui, ui.t("scales.close") if index == self.editing
                             else ui.t("scales.edit"),
                             lambda e, i=index: self._edit(i), kind="quiet",
                             icon=ft.Icons.EDIT_OUTLINED, data=f"scales-edit-{index}"),
                   wc.button(ui, ui.t("scales.remove"), lambda e, i=index: self._remove(i),
                             kind="quiet", icon=ft.Icons.DELETE_OUTLINE,
                             data=f"scales-remove-{index}")]
        entry = self.latest_result(d)
        if entry is not None:
            buttons.insert(0, wc.button(ui, ui.t("scales.open_result"),
                                        lambda e, i=entry.id: self._open_result(i),
                                        kind="quiet", icon=ft.Icons.OPEN_IN_NEW,
                                        data=f"scales-result-{d.name}"))
        color = {"success": ui.p.success, "warning": ui.p.warning}.get(tone, ui.p.text_secondary)
        return ft.Container(ft.Column([
            ft.Row([wc.text(ui, name, tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                    wc.caption(ui, facts)], wrap=True, spacing=tk.SPACE_3),
            wc.text(ui, state, tk.TYPE_CAPTION, color=color, data=f"scales-state-{index}"),
            ft.Row(buttons, wrap=True, spacing=tk.SPACE_1),
        ], spacing=tk.SPACE_1), padding=tk.SPACE_3, border=ft.Border.all(1, ui.p.border),
            border_radius=ui.radius("control"), data=f"scales-row-{index}",
            key=f"scales-row-{index}")

    def _editor(self, index: int, d: sr.ScaleDefinition) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        role = _item_role()
        offered, left_out = wv.offered_variables(s, role, {})
        levels = {info.name: ui.t(f"level.{info.confirmed}") for info in s.variables.values()}
        name = wc.text_field(ui, ui.t("scales.name"), d.name, width=320,
                             on_change=lambda e: self._name(index, e.control.value),
                             data="scales-name", hint=ui.t("scales.name_hint"))
        name.key = "scales-name"
        name.on_blur = wc.handler(self._save)
        parts: list[ft.Control] = [name]
        parts.append(wv.role_panel(
            ui, key=PANEL, title=ui.t("scales.items"), offered=offered, left_out=left_out,
            chosen=list(d.items), query=self.filters.get(PANEL, ""), allowed=role.levels,
            label=lambda n: f"{n} · {levels.get(n, '—')}",
            on_toggle=lambda n, v: self._toggle_item(index, n, v),
            on_add=lambda names: self._add_items(index, names),
            on_remove=lambda names: self._remove_items(index, names),
            on_query=self._query, order=list(s.variables),
            quick=[wc.button(ui, ui.t("pick.clear"), lambda e: self._items(index, []),
                             kind="quiet", icon=ft.Icons.CLEAR, data=f"{PANEL}:clear")]
            if d.items else [],
            expanded=bool(self.filters.get(f"{PANEL}:all")), on_expand=self._expand))
        if d.items:
            parts.append(wc.section_label(ui, ui.t("scales.reverse")))
            parts.append(wc.caption(ui, ui.t("scales.reverse_body")))
            boxes = [wc.checkbox(ui, ui.t("scales.reverse_item", name=item), item in d.reverse,
                                 on_change=lambda e, n=item: self._reverse(
                                     index, n, bool(e.control.value)),
                                 data=f"scales-reverse-{item}") for item in d.items]
            parts.append(ft.Row(boxes, wrap=True, spacing=tk.SPACE_4, run_spacing=0,
                                key="scales-reverse"))
            if d.reverse:
                low = wc.text_field(ui, ui.t("scales.low"), _number_text(d.low), width=150,
                                    on_change=lambda e: self._range(index, "low",
                                                                    e.control.value),
                                    data="scales-low")
                high = wc.text_field(ui, ui.t("scales.high"), _number_text(d.high), width=150,
                                     on_change=lambda e: self._range(index, "high",
                                                                     e.control.value),
                                     data="scales-high")
                low.key, high.key = "scales-low", "scales-high"
                low.on_blur = high.on_blur = wc.handler(self._save)
                parts.append(ft.Row([low, high, wc.caption(ui, ui.t("scales.range_body"))],
                                    wrap=True, spacing=tk.SPACE_3))
        parts.append(wc.section_label(ui, ui.t("scales.rule")))
        minimum = wc.text_field(ui, ui.t("scales.min"),
                                "" if d.min_answered is None else str(d.min_answered),
                                width=230, on_change=lambda e: self._minimum(index,
                                                                             e.control.value),
                                data="scales-min", hint=ui.t("scales.min_hint",
                                                             count=len(d.items)))
        minimum.key = "scales-min"
        minimum.on_blur = wc.handler(self._save)
        parts.append(ft.Row([
            wc.segmented(ui, [("mean", ui.t("scales.method.mean")),
                              ("sum", ui.t("scales.method.sum"))], d.method,
                         lambda value: self._method(index, value), data="scales-method"),
            minimum], wrap=True, spacing=tk.SPACE_4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER))
        parts.append(wc.caption(ui, ui.t("scales.rule_body")))
        parts.append(wc.section_label(ui, ui.t("scales.confirm")))
        parts.append(wc.checkbox(ui, ui.t("scales.one_construct"), d.holds("one_construct"),
                                 on_change=lambda e: self._confirm(index, "one_construct",
                                                                   bool(e.control.value)),
                                 data="scales-confirm-one_construct"))
        if s.has_data and sr.totals_among(s.df, d):
            parts.append(wc.checkbox(ui, ui.t("scales.not_totals",
                                              names=", ".join(sr.totals_among(s.df, d))),
                                     d.holds("items_not_totals"),
                                     on_change=lambda e: self._confirm(
                                         index, "items_not_totals", bool(e.control.value)),
                                     data="scales-confirm-items_not_totals"))
        problems = sr.scoring_problems(d, s.df.columns) if not (
            d.name and d.name in s.df.columns) else []
        problems += [p for p in sr.reliability_problems(d, s.df, s)
                     if p[0] in ("scales.need.one_construct", "scales.need.not_totals")]
        if problems:
            parts.append(wc.text(ui, "\n".join("• " + ui.t(k, **v) for k, v in problems),
                                 tk.TYPE_CAPTION, color=ui.p.text_secondary,
                                 data="scales-problems"))
        return ft.Container(ft.Column(parts, spacing=tk.SPACE_3,
                                      horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                            padding=tk.SPACE_4, bgcolor=ui.p.surface_alt,
                            border_radius=ui.radius("control"), data="scales-editor",
                            key=f"scales-editor-{index}")


def _number_text(value) -> str:
    if value is None:
        return ""
    return f"{value:g}"
