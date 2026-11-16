"""Stage 37.0b: fixes of the confirmed findings of the 0b verification
(``verify-stage37-0b.json``): R1, R2, C-S16/W2, A, B, E, W1, W3 and the
small minors. Each test was run red on ``a8663ce`` before its fix.
Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import analysis_runs  # noqa: E402
import research_report as rr  # noqa: E402
import result_store  # noqa: E402
from test_stage37_ui import Case  # noqa: E402


def two_group_frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    frame = pd.DataFrame({"G": ["A"] * 30 + ["B"] * 30,
                          **{f"O{i}": rng.normal(size=60) for i in (1, 2, 3)}})
    for column, rows in (("O1", (0, 1, 31)), ("O2", (2, 3, 32, 33)),
                         ("O3", (4, 5, 6, 34, 35))):
        frame.loc[list(rows), column] = np.nan
    return frame


def entry_of(run, provenance=None):
    """A report entry as the adapter reads it (only the fields it uses)."""
    return SimpleNamespace(run=run, provenance=dict(provenance or {}))


class R1AdjustedPTests(Case):
    """R1: a batch result's line names the correction of its p (the engine's
    saved adjusted p) and labels the unadjusted one; never a bare raw p
    after "correction: Holm"."""

    def test_the_result_line_shows_the_adjusted_p_with_its_correction(self):
        from test_stage37_ui import run_correlations, write_plan

        ws = self.workspace()
        hid = write_plan(ws, direction="two-sided")
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        entry = ws.app.session.results[-1]
        ws.app.session.toggle_report(entry.id)
        family = entry.run.result
        hypothesis = ws.app.projects.project.plan()["plan"]["hypotheses"][0]
        for language in ("en", "lv", "ru"):
            with self.subTest(language=language):
                evidence = rr.hypothesis_evidence(ws.app.session, ws.app.projects.project)[hid]
                text = "\n".join(i.text or "" for i in
                                 rr.hypothesis_rows(evidence, hypothesis, language))
                from batch_correlation import p_label

                adjusted = p_label("holm", language)
                raw = p_label("none", language)
                from interpretation_wizard import _p

                cautious = next(r for r in family.rows if r.y == "CautiousAction")
                self.assertIn(f"{adjusted} {_p(cautious.p_adjusted)}", text)
                self.assertIn(f"{raw} {_p(cautious.p_raw)}", text)
                self.assertNotRegex(text, r"\], p [=<]", "an unlabelled p after the correction")

    def test_two_corrections_of_one_task_give_two_different_lines(self):
        rng = np.random.default_rng(11)
        x = rng.normal(size=60)
        frame = pd.DataFrame({"X": x, **{f"Y{i}": 0.15 * x + rng.normal(size=60)
                                         for i in range(1, 9)}})
        lines = []
        for adjust in ("holm", "bh"):
            run = analysis_runs.run_batch_correlation(frame, "X", [f"Y{i}" for i in range(1, 9)],
                                                      "pearson", adjust=adjust,
                                                      pearson_confirmed=True)
            result = rr.EvidenceResult("Pearson r", n=rr._n(entry_of(run)),
                                       estimates=rr._rows(entry_of(run)))
            lines.append(rr._estimates("en", result))
        self.assertNotEqual(lines[0], lines[1])
        self.assertIn("p (Holm) = ", lines[0])
        self.assertIn("p (Benjamini–Hochberg) = ", lines[1])


class R2EngineNTests(unittest.TestCase):
    """R2: the n of a two-group batch is the engine's n of each test, also
    after the result is restored from the project."""

    def test_the_two_group_batch_n_is_the_engines_n_per_outcome(self):
        frame = two_group_frame()
        run = analysis_runs.run_batch_groups(frame, "G", ["O1", "O2", "O3"], scale="scale",
                                             two_group_method="welch",
                                             assumptions_confirmed=True)
        ns = [sum(row.ns) for row in run.result.rows]
        self.assertEqual(ns, [57, 56, 55])
        listwise = int(frame.dropna().shape[0])
        self.assertEqual(rr._n(entry_of(run, {"complete": listwise})), "57, 56, 55")
        restored = analysis_runs.AnalysisRun(
            run.section, run.title, run.report, None,
            result=result_store.from_json(result_store.to_json(run.result)))
        self.assertEqual(rr._n(entry_of(restored)), "57, 56, 55")

    def test_without_an_engine_n_the_listwise_count_is_not_used(self):
        run = SimpleNamespace(result=None, evidence=lambda: (_ for _ in ()).throw(ValueError()))
        self.assertEqual(rr._n(entry_of(run, {"complete": 48})), "—")


class S16LegacyVersionTests(unittest.TestCase):
    """C-S16 / W2: a plan version saved before 37.0b (no stored
    ``inferential_before``) is never upgraded to confirmatory, also after the
    program's own post-hoc replacement of an earlier result."""

    def legacy(self, folder, *, methods=("omnibus",)):
        import json
        import time

        import analysis_runs as runs
        import project_store as ps

        store = ps.ProjectStore(Path(folder))
        info = store.create("Fictional")
        project = store.open(info.id)
        dataset = project.import_dataset(ROOT / "examples" / "sample_scale.csv", mode="copy")
        run = runs.run_groups(project.load_frame(dataset.id), "group", "stress_q1",
                              "mannwhitney", "ordinal", True, False)
        roles = {"group": "group", "outcome": "stress_q1"}
        old = [project.record_run(run, method=m, dataset_id=dataset.id, roles=roles, options={},
                                  confirms={}) for m in methods]
        time.sleep(1.1)
        plan = ps.normalise_plan({"hypotheses": [{"id": "bbbbbbbbbbb1",
                                                  "text": "Group B reports more stress",
                                                  "priority": "primary"}]})
        with project._write() as db:          # a version as 36.x / 37.0a saved it
            cur = db.execute("INSERT INTO plan_versions (saved_at, plan, runs_before, note)"
                             " VALUES (?, ?, ?, '')",
                             (ps.now(), json.dumps(plan, sort_keys=True), len(methods)))
            ps._log(db, "plan_saved", {"version": cur.lastrowid, "hypotheses": 1,
                                       "runs_before": len(methods)})
        return project, run, dataset, roles, old

    def test_post_hoc_tests_keep_a_legacy_hypothesis_added_after_results(self):
        import time
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as folder:
            project, run, dataset, roles, old = self.legacy(folder)
            try:
                self.assertEqual(project.hypothesis_status()["bbbbbbbbbbb1"]["standing"],
                                 "added_after_results")
                time.sleep(1.1)
                project.record_run(run, method="posthoc", dataset_id=dataset.id, roles=roles,
                                   options={}, confirms={})
                project.delete_run(old[0].id)     # what _save_results does after post-hoc tests
                status = project.hypothesis_status()["bbbbbbbbbbb1"]
                self.assertEqual(status["standing"], "added_after_results")
                self.assertFalse(status["inferential_known"])
            finally:
                project.close()

    def test_a_legacy_version_after_descriptions_only_is_not_upgraded_but_flagged(self):
        from tempfile import TemporaryDirectory

        import research_workflow as rw
        from workspace_text import t

        with TemporaryDirectory() as folder:
            project, *_ = self.legacy(folder, methods=("descriptive",))
            try:
                status = project.hypothesis_status()["bbbbbbbbbbb1"]
                self.assertEqual(status["standing"], "added_after_results",
                                 "never upgraded to confirmatory automatically")
                self.assertFalse(status["inferential_known"])
                facts = rw.plan_facts(project.plan()["plan"], project.hypothesis_status())
                self.assertFalse(facts[0].standing_known)
                for language in ("en", "lv", "ru"):
                    self.assertIn("1", t(language, "hyp.standing_facts_unknown", version=1,
                                         total=1, h=1))
            finally:
                project.close()

    def test_a_legacy_version_saved_before_any_result_stays_confirmatory(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as folder:
            project, *_ = self.legacy(folder, methods=())
            try:
                status = project.hypothesis_status()["bbbbbbbbbbb1"]
                self.assertEqual(status["standing"], "confirmatory")
                self.assertTrue(status["inferential_known"])
            finally:
                project.close()

    def test_the_report_says_the_standing_of_a_legacy_version_needs_review(self):
        plan = rr.plan_report(rr.ReportInputs(title="F", hypotheses=[{
            "id": "bbbbbbbbbbb1", "text": "Group B reports more stress", "priority": "primary",
            "standing": "added_after_results", "standing_known": False}]))
        text = "\n".join(i.text or "" for i in plan.section("hypotheses").items)
        self.assertIn(rr.text("en", "standing_unknown", number=1), text)


def project_with_result(folder, plan):
    """A project with ``plan`` saved and one inferential result recorded."""
    import analysis_runs as runs
    import project_store as ps

    store = ps.ProjectStore(Path(folder))
    project = store.open(store.create("Fictional").id)
    project.save_plan(plan)
    dataset = project.import_dataset(ROOT / "examples" / "sample_scale.csv", mode="copy")
    run = runs.run_groups(project.load_frame(dataset.id), "group", "stress_q1", "mannwhitney",
                          "ordinal", True, False)
    project.record_run(run, method="groups", dataset_id=dataset.id,
                       roles={"group": "group", "outcome": "stress_q1"}, options={}, confirms={})
    return project


TWO = {"questions": [{"id": "aaaaaaaaaaa1", "type": "relate", "text": "Q?"},
                     {"id": "aaaaaaaaaaa2", "type": "compare", "text": "Q2?"}],
       "hypotheses": [{"id": "bbbbbbbbbbb1", "text": "First", "priority": "primary",
                       "question_id": "aaaaaaaaaaa1", "method_key": "batch_correlation",
                       "method_options": {"method": "pearson"},
                       "roles": {"x": "A", "y": ["B", "C"]}},
                      {"id": "bbbbbbbbbbb2", "text": "Second", "priority": "secondary"}]}


class ARemovalAfterResultsTests(unittest.TestCase):
    """A: removing a hypothesis after results needs a reason, writes an
    append-only withdrawal record, and the hypothesis stays in the records
    and in the Word report."""

    def test_the_store_refuses_a_removal_without_a_reason_and_records_one_with_it(self):
        import copy
        from tempfile import TemporaryDirectory

        import project_store as ps

        with TemporaryDirectory() as folder:
            project = project_with_result(folder, copy.deepcopy(TWO))
            try:
                project.add_protocol_record("deviation", hypothesis_id="bbbbbbbbbbb2",
                                            detail={"what": "sample"},
                                            reason="Fictional: a smaller sample.")
                plan = project.plan()["plan"]
                without = {**plan, "hypotheses": plan["hypotheses"][:1]}
                cleared = {**plan, "hypotheses": [plan["hypotheses"][0],
                                                  {**plan["hypotheses"][1], "text": ""}]}
                for edited in (without, cleared):
                    with self.subTest(edited=len(edited["hypotheses"])), \
                            self.assertRaises(ps.DesignationReasonNeeded) as raised:
                        project.save_plan(edited)
                    self.assertEqual(raised.exception.hypotheses, ("bbbbbbbbbbb2",))
                self.assertEqual(project.plan()["version"], 1, "nothing saved")
                project.save_plan(without, reasons={"bbbbbbbbbbb2": "Fictional: out of scope."})
                record = project.protocol_records(hypothesis_id="bbbbbbbbbbb2")[-1]
                self.assertEqual(record["kind"], "withdrawal")
                self.assertIsNone(record["supersedes"])
                self.assertEqual(record["reason"], "Fictional: out of scope.")
                self.assertEqual(record["detail"]["what"], "hypothesis")
                self.assertEqual(record["detail"]["hypothesis"]["text"], "Second")
                self.assertEqual(record["detail"]["hypothesis"]["number"], 2)
                self.assertEqual(record["plan_version"], 2)
                import sqlite3

                with self.assertRaises(sqlite3.DatabaseError):    # still append-only
                    with project._write() as db:
                        db.execute("DELETE FROM protocol_records WHERE id = ?", (record["id"],))
            finally:
                project.close()

    def test_a_removal_before_any_result_needs_no_reason(self):
        import copy
        from tempfile import TemporaryDirectory

        import project_store as ps

        with TemporaryDirectory() as folder:
            store = ps.ProjectStore(Path(folder))
            with store.open(store.create("Fictional").id) as project:
                project.save_plan(copy.deepcopy(TWO))
                plan = project.plan()["plan"]
                project.save_plan({**plan, "hypotheses": plan["hypotheses"][:1]})
                self.assertEqual(project.protocol_records(), [])

    def test_the_word_report_keeps_the_removed_hypothesis_and_its_records(self):
        removed = {"id": "r9", "kind": "withdrawal", "at": "2026-01-03T03:04:00+00:00",
                   "hypothesis_id": "bbbbbbbbbbb2", "supersedes": None, "plan_version": 2,
                   "results_in_project": 1, "results_of_hypothesis": 0,
                   "reason": "Fictional: out of scope.",
                   "detail": {"what": "hypothesis", "hypothesis": {
                       "number": 2, "text": "Second", "priority": "secondary", "h0": ""}}}
        earlier = {"id": "r8", "kind": "deviation", "at": "2026-01-02T03:04:00+00:00",
                   "hypothesis_id": "bbbbbbbbbbb2", "check_key": "", "reason": "Fictional: "
                   "a smaller sample.", "results_of_hypothesis": 0,
                   "detail": {"what": "sample"}}
        for language in ("en", "lv", "ru"):
            plan = rr.plan_report(rr.ReportInputs(
                title="F", language=language,
                hypotheses=[{"id": "bbbbbbbbbbb1", "text": "First", "priority": "primary"}],
                removed=[(removed, (earlier,))]))
            text = "\n".join(i.text or "" for i in plan.section("hypotheses").items)
            with self.subTest(language=language):
                self.assertIn("Second", text)
                self.assertIn("Fictional: out of scope.", text)
                self.assertIn("Fictional: a smaller sample.", text)
                self.assertIn(rr.text(language, "removed_title"), text)


class BPlanChangedAfterResultsTests(unittest.TestCase):
    """B: after results, the planned method or its options, the planned
    variables and the question kind change only with a reason, recorded as
    a deviation (what, from, to)."""

    def changed(self, change):
        import copy
        from tempfile import TemporaryDirectory

        import project_store as ps

        with TemporaryDirectory() as folder:
            project = project_with_result(folder, copy.deepcopy(TWO))
            try:
                plan = copy.deepcopy(project.plan()["plan"])
                change(plan)
                with self.assertRaises(ps.DesignationReasonNeeded):
                    project.save_plan(plan)
                self.assertEqual(project.plan()["version"], 1, "nothing saved silently")
                project.save_plan(plan, reasons={"bbbbbbbbbbb1": "Fictional: the reason."})
                return [r["detail"] for r in project.protocol_records(
                    hypothesis_id="bbbbbbbbbbb1") if r["kind"] == "deviation"]
            finally:
                project.close()

    def test_the_planned_method_or_its_options(self):
        def method(plan):
            plan["hypotheses"][0]["method_key"] = "correlation"
            plan["hypotheses"][0].pop("method_options")
        self.assertEqual(self.changed(method), [{
            "what": "method",
            "from": {"method": "batch_correlation", "options": {"method": "pearson"}},
            "to": {"method": "correlation", "options": {}}}])

        def variant(plan):
            plan["hypotheses"][0]["method_options"] = {"method": "spearman"}
        self.assertEqual(self.changed(variant)[0]["to"],
                         {"method": "batch_correlation", "options": {"method": "spearman"}})

    def test_the_planned_variables(self):
        def roles(plan):
            plan["hypotheses"][0]["roles"] = {"x": "A", "y": ["B", "D"]}
        self.assertEqual(self.changed(roles), [{
            "what": "variables", "from": {"x": "A", "y": ["B", "C"]},
            "to": {"x": "A", "y": ["B", "D"]}}])

    def test_the_question_kind(self):
        def kind(plan):
            plan["questions"][0]["type"] = "associate"
            plan["hypotheses"][0].pop("roles")
        details = self.changed(kind)
        self.assertIn({"what": "question", "from": "relate", "to": "associate"}, details)
        self.assertIn({"what": "variables", "from": {"x": "A", "y": ["B", "C"]}, "to": {}},
                      details)

    def test_the_records_read_in_the_report(self):
        record = {"id": "r1", "kind": "deviation", "at": "2026-01-03T03:04:00+00:00",
                  "plan_version": 2, "results_in_project": 1, "reason": "Fictional.",
                  "detail": {"what": "method",
                             "from": {"method": "batch_correlation",
                                      "options": {"method": "pearson"}},
                             "to": {"method": "correlation", "options": {}}}}
        line = rr.record_lines(rr.HypothesisEvidence(1, records=(record,)), "en")[0]
        self.assertIn("(method): Pearson’s r → ", line)
        self.assertNotIn("{", line)


class PlanCardAfterResultsTests(Case):
    """A and B through the plan card's real controls."""

    def feedback(self, ws) -> str:
        return " ".join(c.value for c in ws.controls(ws.find("plan-feedback"))
                        if isinstance(getattr(c, "value", None), str))

    def test_remove_after_results_asks_the_reason_and_keeps_the_hypothesis_reported(self):
        from test_stage37_ui import H1

        ws, hid = self.analysed(direction="two-sided")
        project = ws.app.projects.project
        ws.app.navigate("project")
        ws.click("plan-h0-remove")
        self.assertTrue(ws.find_all("plan-removed-0-reason"), "the reason is asked")
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 1, "nothing saved without a reason")
        self.assertIn(ws.app.t("plan.remove_reason_needed", h=1), self.feedback(ws))
        ws.click("plan-removed-0-keep")                  # Keep puts it back
        self.assertEqual([h["id"] for h in ws.app.pages["project"].plan.draft["hypotheses"]],
                         [hid])
        ws.click("plan-h0-remove")
        ws.type("plan-removed-0-reason", "Fictional: outside the thesis.")
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 2)
        self.assertEqual(project.plan()["plan"]["hypotheses"], [])
        record = project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual((record["kind"], record["reason"], record["detail"]["hypothesis"]["text"]),
                         ("withdrawal", "Fictional: outside the thesis.", H1))
        ws.app.navigate("project")
        self.assertTrue(ws.find_all("hyp-removed-0"), "the hypothesis stays in the history")
        ws.app.session.toggle_report(ws.app.session.results[-1].id)
        plan = rr.plan_report(ws.app.pages["reports"].report_inputs())
        text = "\n".join(i.text or "" for i in plan.section("hypotheses").items)
        self.assertIn(H1, text)
        self.assertIn("Fictional: outside the thesis.", text)

    def test_clearing_h1_after_results_asks_the_reason(self):
        ws, hid = self.analysed(direction="two-sided")
        project = ws.app.projects.project
        ws.app.navigate("project")
        ws.type("plan-h0-text", "")
        ws.app.render()
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 1)
        self.assertIn(ws.app.t("plan.remove_reason_needed", h=1), self.feedback(ws))
        ws.type("plan-h0-reason", "Fictional: merged into H2.")
        ws.click("plan-save")
        self.assertEqual(project.protocol_records(hypothesis_id=hid)[-1]["kind"], "withdrawal")

    def test_a_planned_method_changed_after_results_asks_the_reason(self):
        ws, hid = self.analysed(direction="two-sided")
        project = ws.app.projects.project
        ws.app.navigate("project")
        ws.choose("plan-h0-method_key", "batch_correlation")
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 1, "nothing saved silently")
        self.assertIn(ws.app.t("plan.change_reason_needed", h=1), self.feedback(ws))
        ws.type("plan-h0-reason", "Fictional: the plan named no method.")
        ws.click("plan-save")
        record = project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual((record["kind"], record["detail"]["what"]), ("deviation", "method"))


if __name__ == "__main__":
    unittest.main()
