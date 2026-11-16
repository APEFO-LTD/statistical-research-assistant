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


if __name__ == "__main__":
    unittest.main()
