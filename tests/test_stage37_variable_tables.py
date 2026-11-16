"""Stage 37 (Fable review §4 item 5): descriptives of many variables and a
correlation matrix with CIs and adjusted p.

Acceptance: 12 variables described in ≤ 6 interactions and 1 page change;
values equal pandas and SciPy. Synthetic data only (the Stage 37 master
fixture, 180 fictional cases).
"""

from __future__ import annotations

from itertools import combinations
import math
from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from test_stage36_ux_baseline import CountingWorkspace  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402

import variable_tables as vt  # noqa: E402

TWELVE = ["age_years", "SYN_LON_TOTAL", "SYN_SUP_MEAN", "SYN_WELL_RAW", "SYN_WELL_0_100",
          "SYN_COPE_DIM1_MEAN", "SYN_LON_01", "SYN_LON_02", "SYN_SUP_01", "SYN_SUP_02",
          "SYN_WELL_01", "SYN_COPE_01"]
SCORES = ["SYN_LON_TOTAL", "SYN_SUP_MEAN", "SYN_WELL_0_100", "SYN_COPE_DIM1_MEAN", "age_years"]


class Fixture:
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.csv = e2e.master_fixture(Path(cls.folder.name))
        cls.frame = pd.read_csv(cls.csv)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()


class EngineTests(Fixture, unittest.TestCase):
    def test_descriptives_equal_pandas(self):
        result = vt.describe_many(self.frame, TWELVE)
        table = result.tables[0]
        self.assertEqual([row[0] for row in table.rows], TWELVE)
        for name in TWELVE:
            values = self.frame[name].dropna().astype(float)
            q = values.quantile([0.25, 0.5, 0.75])
            expected = {"n": len(values), "missing": int(self.frame[name].isna().sum()),
                        "mean": values.mean(), "sd": values.std(), "median": values.median(),
                        "q1": q[0.25], "q3": q[0.75], "min": values.min(), "max": values.max()}
            for key, value in expected.items():
                self.assertEqual(result.quantity(f"{name}:{key}").value, value, (name, key))

    def test_pearson_matrix_equals_scipy_with_holm_over_the_whole_table(self):
        result = vt.correlation_table(self.frame, SCORES, method="pearson", adjust="holm",
                                      pearson_confirmed=True)
        pairs = list(combinations(SCORES, 2))
        self.assertEqual(len(result.quantities), len(pairs))
        raw = []
        for (a, b), quantity in zip(pairs, result.quantities):
            both = self.frame[[a, b]].dropna()
            test = stats.pearsonr(both[a], both[b])
            ci = test.confidence_interval(0.95)
            self.assertAlmostEqual(quantity.value, test.statistic, delta=1e-12)
            self.assertAlmostEqual(quantity.ci_low, ci.low, delta=1e-12)
            self.assertAlmostEqual(quantity.ci_high, ci.high, delta=1e-12)
            raw.append(test.pvalue)
        m = len(raw)
        order = np.argsort(raw)
        holm, running = [0.0] * m, 0.0
        for rank, index in enumerate(order):
            running = max(running, min(1.0, (m - rank) * raw[index]))
            holm[index] = running
        for quantity, expected in zip(result.quantities, holm):
            self.assertAlmostEqual(quantity.p, expected, delta=1e-12)
        self.assertEqual(result.tables[0].columns[-2:], ("p", "p (adjusted)"))

    def test_spearman_matrix_p_equals_scipy(self):
        result = vt.correlation_table(self.frame, SCORES[:3], method="spearman", adjust="bh")
        raw = []
        for (a, b), quantity in zip(combinations(SCORES[:3], 2), result.quantities):
            both = self.frame[[a, b]].dropna()
            test = stats.spearmanr(both[a], both[b])
            self.assertAlmostEqual(quantity.value, test.statistic, delta=1e-12)
            self.assertTrue(quantity.ci_low < quantity.value < quantity.ci_high)
            raw.append(test.pvalue)
        m, ranked = len(raw), sorted(range(len(raw)), key=lambda i: raw[i])
        bh, smallest = [0.0] * m, 1.0
        for position in range(m - 1, -1, -1):
            index = ranked[position]
            smallest = min(smallest, raw[index] * m / (position + 1))
            bh[index] = smallest
        for quantity, expected in zip(result.quantities, bh):
            self.assertAlmostEqual(quantity.p, expected, delta=1e-12)

    def test_pearson_waits_for_its_confirmation_and_limits_hold(self):
        with self.assertRaises(ValueError):
            vt.correlation_table(self.frame, SCORES, method="pearson")
        with self.assertRaises(ValueError):
            vt.describe_many(self.frame, ["participant_code", "age_years"])
        with self.assertRaises(ValueError):
            vt.correlation_table(self.frame, [f"SYN_COPE_{n:02d}" for n in range(1, 18)],
                                 method="spearman")


class WorkspaceTests(Fixture, unittest.TestCase):
    def workspace(self):
        ws = CountingWorkspace()
        self.addCleanup(ws.close)
        ws.app.projects.create("Fictional master study")
        self.assertTrue(ws.run(ws.app.load_path(str(self.csv))))
        ws.check("data-accept-confirm")
        ws.click("data-accept")
        ws.counts.clear()
        return ws

    def test_twelve_variables_described_in_six_interactions_and_one_page(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        ws.click("method-descriptives_many")
        ws.type("form-variables:search", ", ".join(TWELVE))
        ws.click("form-variables:select-shown")
        ws.click("form-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "descriptives_many")
        self.assertEqual(sorted(entry.roles["variables"]), sorted(TWELVE))
        # nav-analyze, the "All methods" segment (not counted by the harness),
        # the method, "select shown" and Run: 5 interactions and one typed
        # field; the pages are Analyze and then Results with the table.
        self.assertLessEqual(ws.total + 1, 6)
        self.assertEqual(ws.routes, ["analyze", "results"])
        # Stored as a normal result, with the whole table.
        record = next(r for r in ws.app.projects.project.runs()
                      if r.method == "descriptives_many")
        self.assertIn("SYN_LON_TOTAL", str(record.tables))
        self.assertFalse(ws.has_text("This page could not be shown"))
        self.assertTrue(ws.find_all(f"result-detail-{entry.id}"))
        # In the Word report as any result.
        from docx import Document

        ws.app.session.toggle_report(entry.id)
        ws.click("nav-reports")
        ws.click("reports-export-docx")
        cells = " ".join(cell.text for table in Document(str(ws.saved[-1])).tables
                         for row in table.rows for cell in row.cells)
        self.assertIn("SYN_COPE_DIM1_MEAN", cells)

    def test_the_matrix_with_ci_and_adjusted_p_from_the_form(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        ws.click("method-correlation_table")
        ws.type("form-items:search", ", ".join(SCORES))
        ws.click("form-items:select-shown")
        ws.check("form-confirm-pearson")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ws.click("form-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "correlation_table")
        self.assertEqual(len(entry.run.result.quantities), math.comb(len(SCORES), 2))
        self.assertTrue(all(q.p is not None for q in entry.run.result.quantities))
        self.assertFalse(ws.has_text("This page could not be shown"))


if __name__ == "__main__":
    unittest.main()
