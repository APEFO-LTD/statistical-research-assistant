"""Stage 37 research methods: fixes of the confirmed findings of the methods
verification (``verify-stage37-methods.json``, reviewed ``074dfbc``):
S37-INT-1/2 (suppression wording only with a conclusive interval), S37-INT-3
(the HC3 Wald F shown when HC3 is chosen), integration F1 (design
confirmations bound to the model) and integration F2 (restored single
Spearman correlations still verify). Each test was run red on ``074dfbc``
before its fix. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from process_models import ProcessSpec, fit_process  # noqa: E402
import process_reporting  # noqa: E402
from process_reporting import process_interpretation  # noqa: E402
from test_process_workspace import stage37_fixture  # noqa: E402

COV = ("age_years", "SYN_SEX_1", "SYN_SEX_2", "employed_code")
LABEL = {"en": "inconsistent mediation", "lv": "nekonsekventa mediācija",
         "ru": "несогласованная медиация"}

_FRAME = None


def acceptance_frame() -> pd.DataFrame:
    """The acceptance H4/H7/H8 frame from the v1 fixture (as the review ran it)."""
    global _FRAME
    if _FRAME is None:
        frame = stage37_fixture()
        avoid = [f"SYN_COPE_{i:02d}" for i in (*range(15, 22), *range(35, 41))]
        frame["SYN_COPE_AVOID_LIKE"] = frame[avoid].mean(axis=1, skipna=False)
        frame["SYN_SEX_1"] = (frame["sex_code"] == 1).astype(float)
        frame["SYN_SEX_2"] = (frame["sex_code"] == 2).astype(float)
        _FRAME = frame
    return _FRAME


class S37Int1SuppressionModel4Tests(unittest.TestCase):
    """S37-INT-1: a specific indirect effect whose interval includes zero is
    never called inconsistent mediation; its sign difference is said to be
    inconclusive."""

    @classmethod
    def setUpClass(cls):
        cls.result = fit_process(acceptance_frame(), ProcessSpec(
            "4", "SYN_LON_TOTAL", "SYN_WELL_0_100", ("SYN_COPE_DIM1_MEAN", "SYN_COPE_AVOID_LIKE"),
            covariates=COV))

    def test_an_inconclusive_indirect_effect_is_not_labelled_suppression(self):
        r = self.result
        open_ones = [e for e in r.indirect if e.key.startswith("indirect:") and not e.excludes_zero]
        self.assertEqual(len(open_ones), 2, "both specific intervals include zero here")
        for language in ("en", "lv", "ru"):
            lines = process_interpretation(r, language)
            for e in open_ones:
                path = process_reporting._t(language, "path.via", m=e.mediator)
                labelled = [l for l in lines if l.startswith(path + ":") and LABEL[language] in l
                            and "(" + LABEL[language].split()[0] not in l]
                said = [l for l in lines if l.startswith(path + ":")
                        and process_reporting.num(e.value) in l and "c′" in l]
                with self.subTest(language=language, mediator=e.mediator):
                    self.assertTrue(said, "the sign difference is still described")
                    for line in said:
                        self.assertNotRegex(line, LABEL[language] + r" \(",
                                            "labelled although its interval includes zero")
                    del labelled

    def test_the_total_indirect_effect_that_excludes_zero_keeps_the_label(self):
        r = self.result
        total = next(e for e in r.indirect if e.key == "indirect_total")
        self.assertTrue(total.excludes_zero)
        self.assertTrue(r.estimate("direct").excludes_zero)
        text = "\n".join(process_interpretation(r, "en"))
        self.assertIn("inconsistent mediation (suppression", text)

    def test_an_inconclusive_direct_effect_gives_no_label(self):
        from dataclasses import replace

        r = self.result
        direct = r.estimate("direct")
        wide = replace(direct, ci_low=-1.0, ci_high=0.5, p=0.4)
        changed = replace(r, effects=tuple(wide if e.key == "direct" else e
                                           for e in r.effects))
        total = changed.estimate("total")
        if total.excludes_zero:      # only c′ is opposite and inconclusive: test it alone
            changed = replace(changed, effects=tuple(
                replace(e, ci_low=-1.0, ci_high=0.5) if e.key == "total" else e
                for e in changed.effects))
        text = "\n".join(process_interpretation(changed, "en"))
        self.assertNotIn("inconsistent mediation (suppression", text)


class S37Int2SuppressionConditionalTests(unittest.TestCase):
    """S37-INT-2: Models 7 and 14 list as inconsistent mediation only the
    values of W whose conditional indirect effect interval excludes zero."""

    def check(self, model: str):
        r = fit_process(acceptance_frame(), ProcessSpec(
            model, "SYN_LON_TOTAL", "SYN_WELL_0_100", ("SYN_COPE_DIM1_MEAN",), w="SYN_SUP_MEAN",
            covariates=COV))
        opposite_open = [e for e in r.indirect if e.key.startswith("cond_indirect:")
                         and not e.excludes_zero
                         and np.sign(e.value) == -np.sign(r.estimate("direct").value)]
        self.assertTrue(opposite_open, "the fixture has such values of W")
        for language in ("en", "lv", "ru"):
            lines = [l for l in process_interpretation(r, language) if LABEL[language] in l]
            for line in lines:
                head = line.split(":")[0]
                for e in opposite_open:
                    with self.subTest(model=model, language=language, w=e.w):
                        self.assertNotIn(process_reporting.num(e.w), head)

    def test_model_7(self):
        self.check("7")

    def test_model_14(self):
        self.check("14")


class S37Int3HC3Tests(unittest.TestCase):
    """S37-INT-3: with HC3 chosen, the HC3 Wald F and p that are computed are
    shown, and the wording says so truthfully."""

    @staticmethod
    def frame():
        rng = np.random.default_rng(5)
        n = 90
        x = rng.normal(size=n)
        g = rng.choice([1, 2, 3], size=n, p=(.45, .45, .10))
        y = 0.3 * x + 0.55 * (g == 3) + rng.normal(size=n) * np.where(g == 3, 4.0, 0.7)
        return pd.DataFrame({"y": y, "x": x, "group": g})

    def test_the_linear_model_report_shows_the_hc3_wald_f(self):
        from linear_model import LinearSpec, fit_linear_model, format_linear_report, linear_tables

        r = fit_linear_model(self.frame(), LinearSpec("y", ("x",), ("group",), hc3=True))
        block = r.blocks[0]
        self.assertIsNotNone(block.robust_f)
        report = format_linear_report(r)
        self.assertIn(f"{block.robust_f:.2f}", report)
        cells = [c for t in linear_tables(r) for row in t.rows for c in row]
        self.assertIn(f"{block.robust_f:.2f}", cells)
        self.assertTrue(any("HC3 Wald F" in w and "shown" in w for w in r.warnings))
        from linear_model import structured_result

        keys = [q.key for q in structured_result(r).quantities]
        self.assertIn(f"hc3_f:{block.name}", keys)

    def test_the_path_model_interaction_test_shows_the_hc3_wald_f(self):
        from process_reporting import process_tables

        r = fit_process(acceptance_frame(), ProcessSpec(
            "1", "SYN_LON_TOTAL", "SYN_WELL_0_100", w="SYN_SUP_MEAN", covariates=COV, hc3=True))
        tests = [t for t in r.interactions if t.robust_f is not None]
        self.assertTrue(tests)
        for language in ("en", "lv", "ru"):
            cells = [c for t in process_tables(r, language) for row in t.rows for c in row]
            for test in tests:
                self.assertIn(f"{test.robust_f:.2f}", cells, language)
            note = process_reporting._t(language, "warn.hc3")
            self.assertIn("HC3", note)


class F1ModelBoundConfirmationTests(unittest.TestCase):
    """Integration F1: the Model 7 / Model 14 design confirmations hold only
    for the model they name (K1 scope), so a switch invalidates them on every
    path (guided run, form, Run again, clone, Ctrl+Enter all settle the
    confirmations with the same scope function)."""

    def test_a_model_7_confirmation_does_not_hold_for_model_14(self):
        from test_process_workspace import ROLES, session_for, synthetic
        from workspace_methods import (METHODS, confirmation_scope, default_options,
                                       holding_confirmations, settle_confirmations)

        session = session_for(synthetic())
        roles = ROLES["conditional_process"]
        spec = METHODS["conditional_process"]
        seven = {**default_options(spec), "method": "7"}
        fourteen = {**default_options(spec), "method": "14"}
        c7 = next(c for c in spec.confirmations if c.key == "model7_path")
        scopes = {"model7_path": confirmation_scope(c7, "conditional_process", roles, seven,
                                                    session)}
        holding, kept = settle_confirmations("conditional_process", roles, fourteen,
                                             {"model7_path": True}, scopes, session)
        self.assertNotIn("model7_path", holding)
        self.assertNotIn("model7_path", kept)
        self.assertIn("model7_path", holding_confirmations(
            "conditional_process", roles, seven, {"model7_path": True}, scopes, session))

    def test_a_guided_model_14_run_records_no_model_7_sentence(self):
        import tempfile

        from test_process_workspace import LEVELS, synthetic
        from workspace_harness import Workspace

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_process.csv"
            synthetic().to_csv(path, index=False)
            ws = Workspace(root=Path(folder) / "data")
            try:
                ws.app.projects.create("Fictional conditional process")
                self.assertTrue(ws.run(ws.app.load_path(str(path))))
                for name, level in LEVELS.items():
                    ws.app.session.confirm_level(name, level)
                ws.click("nav-analyze")
                ws.click("goal-process")
                ws.choose("role-x", "x")
                ws.choose("role-y", "y")
                ws.check("role-mediators-m1")
                ws.choose("role-w", "w")
                ws.click("alt-conditional_process-7")
                for key in ("mediators_a_priori", "model7_path", "cross_sectional",
                            "assumptions"):
                    ws.check(f"design-confirm-{key}")
                ws.click("alt-conditional_process-14")
                self.assertTrue(ws.find("guided-run").disabled or
                                ws.find_all("design-confirm-model14_path"))
                for key in ("model14_path", "assumptions"):
                    if ws.find_all(f"design-confirm-{key}"):
                        ws.check(f"design-confirm-{key}")
                ws.click("guided-run")
                entry = ws.app.session.results[-1]
                self.assertEqual(entry.run.result.spec.model, "14")
                self.assertFalse([c for c in entry.confirmations if "Model 7" in c],
                                 entry.confirmations)
                # Back to Model 7: its path confirmation is asked again.
                if ws.app.route != "analyze":
                    ws.click("nav-analyze")
                if not ws.find_all("alt-conditional_process-7"):
                    ws.click("task-change-variables")
                ws.click("alt-conditional_process-7")
                self.assertTrue(ws.find_all("design-confirm-model7_path"))
                box = ws.find("design-confirm-model7_path")
                self.assertFalse(box.value, "the Model 7 attestation is asked for again")
            finally:
                ws.close()


class F2RestoredSpearmanTests(unittest.TestCase):
    """Integration F2: the S10 note added to a single Spearman correlation at
    the permutation floor does not make a result saved by the previous
    version count as "recalculated report differs"."""

    def test_a_report_saved_before_the_s10_note_still_verifies(self):
        import hashlib
        from types import SimpleNamespace

        import project_session
        from workspace_methods import run_method
        from workspace_state import ResearchSession

        rng = np.random.default_rng(42)
        x = rng.normal(0, 1, 120)
        y = x + rng.normal(0, .5, 120)
        session = ResearchSession()
        session.set_dataset(pd.DataFrame({"x": x, "y": y}), "fictional.csv")
        session.confirm_level("x", "scale")
        session.confirm_level("y", "scale")
        now = run_method("correlation", session, {"x": "x", "y": "y"}, {"method": "spearman"},
                         {"pearson": False})
        self.assertIn("This p (.001) is the smallest", now.report)
        saved = "\n".join(line for line in now.report.split("\n")
                          if not line.startswith("This p (.001) is the smallest"))
        self.assertTrue(hashlib.sha256(saved.encode()).hexdigest().startswith(
            "08d80a0b7d464955"), "the report the previous version (2f9af71) saved")
        self.assertTrue(project_session.same_report(SimpleNamespace(report=saved), now))
        other = saved.replace("ρ", "r", 1)
        self.assertFalse(project_session.same_report(SimpleNamespace(report=other), now),
                         "any other difference is still found")


if __name__ == "__main__":
    unittest.main()
