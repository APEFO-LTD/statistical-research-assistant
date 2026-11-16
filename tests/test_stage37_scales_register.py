"""Stage 37 (Fable review §4 item 2): the scales register.

Acceptance (``docs/STAGE37_FABLE_NARROW_REVIEW.md`` §4, item 2):

* several scales defined in one place, items by the variable panel (name
  groups, a range typed in its search);
* scores equal a NumPy oracle exactly, and the same scale scored in Data →
  Prepare; α equals a NumPy oracle to 1e-9 and the single-scale Analyze path;
* no default for the scoring rule or the minimum answered; a reverse key is
  applied only after its own confirmation; a change of items clears the
  confirmations (K1);
* the register is kept in format-6 storage (the activity log) and comes
  back after a restart; results are normal stored results (provenance,
  Word report).

Synthetic data only: the Stage 37 master fixture (180 fictional cases).
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import flet as ft  # noqa: E402

from test_stage368_acceptance import T, label  # noqa: E402
from test_stage36_ux_baseline import CountingWorkspace  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)

import scale_register as sr  # noqa: E402

LON = [f"SYN_LON_{n:02d}" for n in range(1, 21)]
SUP = [f"SYN_SUP_{n:02d}" for n in range(1, 13)]
WELL = [f"SYN_WELL_{n:02d}" for n in range(1, 6)]
DIM1 = [f"SYN_COPE_{n:02d}" for n in range(1, 8)]
# name, items, rule, minimum answered (the fixture's own scores: LON and WELL
# are sums, SUP and the first coping dimension means)
SCALES = (("LON_SUM", LON, "sum", 20), ("SUP_AVG", SUP, "mean", 10),
          ("WELL_SUM", WELL, "sum", 5), ("COPE1_AVG", DIM1, "mean", 6))


def oracle_score(frame: pd.DataFrame, items, method: str, minimum: int) -> np.ndarray:
    values = frame[list(items)].to_numpy(dtype=float)
    answered = (~np.isnan(values)).sum(axis=1)
    if method == "sum":
        score = np.where(answered == len(items), np.nansum(values, axis=1), np.nan)
    else:
        with np.errstate(invalid="ignore", divide="ignore"):
            score = np.nansum(values, axis=1) / answered
    return np.where(answered >= minimum, score, np.nan)


def oracle_alpha(frame: pd.DataFrame, items) -> float:
    values = frame[list(items)].dropna().to_numpy(dtype=float)
    k = values.shape[1]
    return k / (k - 1) * (1 - values.var(axis=0, ddof=1).sum() / values.sum(axis=1).var(ddof=1))


def definition(name, items, method, minimum, **extra) -> sr.ScaleDefinition:
    d = sr.ScaleDefinition(name, tuple(items), method=method, min_answered=minimum)
    for key, value in extra.items():
        d = getattr(d, key)(*value)
    return d


class MasterFixture:
    folder: tempfile.TemporaryDirectory | None = None
    csv: Path

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.csv = e2e.master_fixture(Path(cls.folder.name))
        cls.frame = pd.read_csv(cls.csv)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()


# ===================================================================== logic
class RegisterLogicTests(MasterFixture, unittest.TestCase):
    def test_scores_equal_the_numpy_oracle_and_the_prepare_path_exactly(self):
        from data_preparation import score_scale

        scored = sr.score_all(self.frame, [definition(*s) for s in SCALES])
        self.assertEqual(scored.scored, [s[0] for s in SCALES])
        for name, items, method, minimum in SCALES:
            mine = scored.frame[name].to_numpy(dtype=float)
            self.assertTrue(np.array_equal(mine, oracle_score(self.frame, items, method,
                                                              minimum), equal_nan=True), name)
            single = score_scale(self.frame, items, name, method, minimum).frame[name]
            self.assertTrue(np.array_equal(mine, single.to_numpy(dtype=float),
                                           equal_nan=True), name)
        # The fixture's own scores (sum of LON, mean of SUP and of DIM1).
        self.assertTrue(np.array_equal(scored.frame["LON_SUM"], self.frame["SYN_LON_TOTAL"],
                                       equal_nan=True))
        self.assertTrue(np.allclose(scored.frame["COPE1_AVG"].where(
            self.frame[DIM1].notna().all(axis=1)), self.frame["SYN_COPE_DIM1_MEAN"],
            equal_nan=True, atol=0.006))
        # The source columns are untouched; every step is a Prepare step.
        pd.testing.assert_frame_equal(scored.frame[self.frame.columns], self.frame)
        self.assertEqual([s["type"] for s in scored.steps], ["scale"] * 4)

    def test_no_default_for_the_rule_or_the_minimum(self):
        bare = sr.ScaleDefinition("LON_SUM", tuple(LON))
        self.assertIsNone(bare.method)
        self.assertIsNone(bare.min_answered)
        keys = [key for key, _ in sr.scoring_problems(bare, self.frame.columns)]
        self.assertIn("scales.need.method", keys)
        self.assertIn("scales.need.min", keys)
        with self.assertRaises(ValueError):
            sr.score_all(self.frame, [bare])
        summed = definition("LON_SUM", LON, "sum", 15)
        self.assertIn("scales.need.sum_all",
                      [key for key, _ in sr.scoring_problems(summed, self.frame.columns)])

    def test_a_reverse_key_only_after_its_own_confirmation(self):
        d = definition("SUP_AVG", SUP, "mean", 12)
        self.assertEqual(d.reverse, ())
        self.assertEqual(d.scored_items(), SUP, "nothing is reversed by the program")
        d = d.with_reverse("SYN_SUP_03", True)
        self.assertIn("scales.need.range",
                      [key for key, _ in sr.scoring_problems(d, self.frame.columns)])
        d = d.with_range(1.0, 7.0)
        scored = sr.score_all(self.frame, [d])
        reversed_ = 8.0 - self.frame["SYN_SUP_03"]
        pd.testing.assert_series_equal(scored.frame["SYN_SUP_03_reverse"], reversed_,
                                       check_names=False)
        oracle = self.frame[SUP].copy()
        oracle["SYN_SUP_03"] = reversed_
        self.assertTrue(np.array_equal(scored.frame["SUP_AVG"],
                                       oracle_score(oracle, SUP, "mean", 12), equal_nan=True))
        self.assertEqual([s["type"] for s in scored.steps], ["reverse", "scale"])
        self.assertEqual(scored.steps[-1]["sources"][2], "SYN_SUP_03_reverse")

    def test_a_change_of_items_reverse_keys_or_range_clears_the_confirmations(self):
        d = definition("SUP_AVG", SUP, "mean", 12).confirm("one_construct", True)
        self.assertTrue(d.holds("one_construct"))
        self.assertTrue(d.with_items(SUP).holds("one_construct"), "the same items")
        self.assertFalse(d.with_items(SUP[:-1]).holds("one_construct"))
        self.assertFalse(d.with_reverse("SYN_SUP_01", True).holds("one_construct"))
        reversed_ = d.with_reverse("SYN_SUP_01", True).with_range(1, 7) \
            .confirm("one_construct", True)
        self.assertFalse(reversed_.with_range(0, 7).holds("one_construct"))
        # A confirmation copied from another scale is not one for this scale.
        other = definition("X", LON, "mean", 3)
        self.assertFalse(sr.ScaleDefinition("X", tuple(LON), confirms=d.confirms)
                         .holds("one_construct"))
        self.assertFalse(other.holds("one_construct"))

    def test_the_register_round_trips_as_json(self):
        d = definition("SUP_AVG", SUP, "mean", 12).with_reverse("SYN_SUP_02", True) \
            .with_range(1, 7).confirm("one_construct", True)
        back = sr.register_from_json(sr.register_json([d]))
        self.assertEqual(back, [d])
        self.assertTrue(back[0].holds("one_construct"))
        self.assertEqual(sr.register_from_json({"format": 99}), [])
        self.assertEqual(sr.register_from_json({"scales": [{"name": 3}, "x"]}), [])

    def test_alpha_equals_the_numpy_oracle(self):
        from analysis_runs import run_item_diagnostics

        for name, items, _, _ in SCALES:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                run = run_item_diagnostics(self.frame, items, True, resamples=0)
            self.assertAlmostEqual(run.result.alpha.value, oracle_alpha(self.frame, items),
                                   delta=1e-9, msg=name)


# ================================================================ workspace
class RegisterWorkspaceTests(MasterFixture, unittest.TestCase):
    def workspace(self, root: Path | None = None) -> CountingWorkspace:
        ws = CountingWorkspace(root=root)
        self.addCleanup(ws.close)
        return ws

    def opened(self, root: Path) -> CountingWorkspace:
        ws = self.workspace(root)
        ws.app.projects.create("Fictional master study")
        self.assertTrue(ws.run(ws.app.load_path(str(self.csv))))
        ws.check("data-accept-confirm")
        ws.click("data-accept")
        ws.click("nav-data")
        return ws

    def define(self, ws, name, items, method, minimum, *, by=None, confirm=True):
        ws.click("scales-add")
        ws.type("scales-name", name)
        if by is None:
            ws.click(f"scales-items:group:{items[0][:-2]}")
        else:
            ws.type("scales-items:search", by)
            ws.click("scales-items:select-shown")
        ws.segment("scales-method", method)
        ws.type("scales-min", str(minimum))
        if confirm:
            ws.check("scales-confirm-one_construct")

    def define_all(self, ws):
        for name, items, method, minimum in SCALES:
            self.define(ws, name, items, method, minimum,
                        by="SYN_COPE_01..SYN_COPE_07" if items is DIM1 else None)

    def test_four_scales_defined_scored_and_checked_in_one_action_each(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.opened(Path(root))
            ws.counts.clear()
            self.define_all(ws)
            card = ws.app.pages["data"].scales
            self.assertEqual([d.items for d in card.definitions],
                             [tuple(s[1]) for s in SCALES])
            self.assertEqual(label(ws, "scales-score-all"), T("scales.score_all", count=4))
            # The items are in the data: their reliability needs no score
            # (a reversed item needs its reversed column, made by scoring).
            self.assertEqual(label(ws, "scales-check-all"), T("scales.check_all", count=4))
            ws.click("scales-score-all")
            session = ws.app.session
            for name, items, method, minimum in SCALES:
                self.assertTrue(np.array_equal(session.df[name].to_numpy(dtype=float),
                                               oracle_score(self.frame, items, method, minimum),
                                               equal_nan=True), name)
                self.assertEqual(session.level(name), "unknown",
                                 "a new score waits for its level confirmation")
            ws.click("scales-levels")
            self.assertEqual({session.level(s[0]) for s in SCALES}, {"scale"})
            before = len(session.results)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ws.click("scales-check-all")
            results = session.results[before:]
            self.assertEqual([e.roles["items"] for e in results], [s[1] for s in SCALES])
            self.assertEqual({e.method for e in results}, {"item_diagnostics"})
            for entry, (name, items, _, _) in zip(results, SCALES):
                self.assertAlmostEqual(entry.run.result.alpha.value,
                                       oracle_alpha(self.frame, items), delta=1e-9)
                self.assertEqual(entry.confirms, {"one_construct": True})
                self.assertIn("I checked that the items are meant to measure one construct",
                              entry.confirmations)
                self.assertTrue(ws.has_text(T("scales.state.checked",
                                              alpha=entry.run.result.alpha.text(),
                                              omega=entry.run.result.omega.text(),
                                              n=entry.run.result.n_complete)))
            # Counted: 4 or 5 per scale, then score, levels and check.
            self.assertLessEqual(ws.total, 21)
            self.assertEqual(ws.app.route, "data", "no page change")
            # Normal stored results: in the project, with their provenance.
            project = ws.app.projects.project
            runs = [r for r in project.runs() if r.method == "item_diagnostics"]
            self.assertEqual(len(runs), 4)
            ws.click("scales-report-all")
            self.assertTrue(all(e.in_report for e in results))
            self.assertEqual(sum(r.method == "item_diagnostics" for r in project.report_runs()),
                             4, "the four results are in the Word report")
            for entry in results:
                self.assertIn("variables", entry.provenance)
                self.assertEqual(entry.provenance["variables"], entry.roles["items"])
            history = project.transformations(ws.app.projects.dataset_id) or []
            self.assertIn("score_scale", {step["kind"] for step in history}
                          | {step["kind"] for d in project.datasets()
                             for step in project.transformations(d.id)})
            project_id = ws.app.projects.info().id
            ws.close()
            again = self.workspace(Path(root))
            again.click(f"project-open-{project_id}")
            again.click("nav-data")
            reloaded = again.app.pages["data"].scales
            self.assertEqual([d.name for d in reloaded.definitions], [s[0] for s in SCALES])
            self.assertTrue(all(d.holds("one_construct") for d in reloaded.definitions))
            self.assertTrue(again.find_all("scales-result-LON_SUM"))

    def test_check_waits_for_the_one_construct_confirmation(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.opened(Path(root))
            self.define(ws, "WELL_SUM", WELL, "sum", 5, confirm=False)
            ws.click("scales-score-all")
            ws.click("scales-levels")
            check = ws.find("scales-check-all")
            self.assertTrue(check.disabled)
            self.assertEqual(check.tooltip, T("scales.check_none"))
            ws.click("scales-edit-0")
            self.assertTrue(ws.has_text(T("scales.need.one_construct")))
            ws.check("scales-confirm-one_construct")
            self.assertFalse(ws.find("scales-check-all").disabled)

    def test_nothing_is_reversed_or_chosen_by_the_program(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.opened(Path(root))
            ws.click("scales-add")
            ws.click("scales-items:group:SYN_SUP_")
            boxes = [c for c in ws.find_all("scales-reverse-") if isinstance(c, ft.Checkbox)]
            self.assertEqual(len(boxes), 12)
            self.assertFalse(any(box.value for box in boxes))
            self.assertIsNone(ws.find("scales-min").value or None)
            method = ws.find("scales-method")
            weights = [c.style.text_style.weight for c in ws.controls(method)
                       if isinstance(c, ft.Button)]
            self.assertNotIn(ft.FontWeight.W_600, weights, "no rule is preselected")
            ws.check("scales-reverse-SYN_SUP_04")
            self.assertTrue(ws.find("scales-low"))
            ws.type("scales-low", "1")
            ws.type("scales-high", "7")
            d = ws.app.pages["data"].scales.definitions[0]
            self.assertEqual((d.reverse, d.low, d.high), (("SYN_SUP_04",), 1.0, 7.0))


class TextTests(unittest.TestCase):
    def test_every_scales_text_has_three_languages(self):
        import workspace_text as wt

        keys = [key for key in wt.T if key.startswith("scales.")]
        self.assertGreater(len(keys), 40)
        for key in keys:
            self.assertEqual(len(wt.T[key]), 3, key)
            self.assertTrue(all(wt.T[key]), key)


if __name__ == "__main__":
    unittest.main()
