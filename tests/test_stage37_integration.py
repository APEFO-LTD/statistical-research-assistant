"""Stage 37 integration: what the feature branches do together.

Each branch tests its own work; these tests check the seams between them on
the integrated tree (docs/STAGE37_INTEGRATION.md):

* 0b × methods: the confirmations of a path model (methods' scopes for the
  moderated path of Model 7 or 14) decide 0b's design step of a task, and
  the Word report holds 0b's hypothesis rows and methods' path-model results
  side by side.

Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from docx import Document  # noqa: E402

import research_report as rr  # noqa: E402
import research_workflow as rw  # noqa: E402
from test_process_workspace import ROLES, session_for, synthetic  # noqa: E402
from test_stage37_ui import H1, Case, run_correlations  # noqa: E402
from workspace_methods import (  # noqa: E402
    METHODS, confirmation_scope, default_options, required_confirmations, run_method,
)
from workspace_state import ResearchTask  # noqa: E402

MEDIATION_ROLES = {"x": "UCLA", "mediators": ["SocialJoining"], "y": "AssertiveAction",
                   "covariates": ["Age"]}


def path_task(session, model: str) -> ResearchTask:
    """A conditional-process task whose confirmations were given for ``model``."""
    roles = ROLES["conditional_process"]
    spec = METHODS["conditional_process"]
    options = {**default_options(spec), "method": model}
    needed = required_confirmations(spec, options)
    scopes = {c.key: confirmation_scope(c, "conditional_process", roles, options, session)
              for c in needed}
    return ResearchTask("t1", "Fictional path model", "process", dict(roles),
                        method="conditional_process", options=options,
                        confirms={c.key: True for c in needed},
                        state={"confirm_scopes": scopes})


class ConfirmationScopeTests(unittest.TestCase):
    """K1 of 0b (the design step counts the confirmations that hold) with the
    option-bound design confirmations of methods (review integration F1)."""

    def test_the_design_step_holds_only_for_the_model_confirmed(self):
        session = session_for(synthetic())
        task = path_task(session, "7")
        ready = rw.task_facts(task, session, method="conditional_process",
                              options={**task.options, "method": "7"})
        self.assertTrue(ready.design_ready)
        moved = rw.task_facts(task, session, method="conditional_process",
                              options={**task.options, "method": "14"})
        self.assertFalse(moved.design_ready, "Model 7's path confirmation is not Model 14's")

    def test_other_variables_clear_the_design_step(self):
        session = session_for(synthetic())
        task = path_task(session, "14")
        other = {**task.selection, "mediators": ["m2"]}
        facts = rw.task_facts(task, session, selection=other, method="conditional_process",
                              options=task.options)
        self.assertFalse(facts.design_ready, "given for m1, not for m2")


class WordReportTests(Case):
    """0b's Hypotheses section and evidence table next to methods' path model."""

    def test_the_report_holds_the_hypothesis_rows_and_the_path_model(self):
        ws, _ = self.planned()
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        session = ws.app.session
        correlation = session.results[-1]
        session.toggle_report(correlation.id)
        spec = METHODS["mediation"]
        options = {**default_options(spec), "resamples": "1000"}
        run = run_method("mediation", session, MEDIATION_ROLES, options,
                         {c.key: True for c in required_confirmations(spec, options)})
        mediation = session.add_result(run, (), method="mediation", roles=MEDIATION_ROLES,
                                       options=options)
        session.toggle_report(mediation.id)
        session.update_report(language="en")
        ws.run(ws.app.pages["reports"]._export_docx())
        document = Document(str(ws.saved[-1]))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("H1 (primary): " + H1, text)                       # 0b
        self.assertIn("result current, in this report.", text)            # 0b
        self.assertIn("Mediation (PROCESS-equivalent Model 4)", text)     # methods
        self.assertIn("not by the PROCESS macro", text)                   # methods
        tables = [[[c.text for c in row.cells] for row in table.rows] for table in document.tables]
        evidence = next(t for t in tables if tuple(t[0]) == rr.TEXT["en"]["evidence_columns"])
        self.assertEqual(len(evidence), 2, "H1 × its one result; the path model tests no H")
        cells = [c for t in tables for row in t for c in row]
        self.assertTrue(any(c.startswith("Indirect effect via SocialJoining") for c in cells),
                        "the path model's effects table")


if __name__ == "__main__":
    unittest.main()
