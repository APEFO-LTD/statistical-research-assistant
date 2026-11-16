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


if __name__ == "__main__":
    unittest.main()
