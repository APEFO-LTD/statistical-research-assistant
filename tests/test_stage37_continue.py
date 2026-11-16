"""Stage 37: Home's Continue reopens the last project with its research task.

* One click on Continue opens the project of the last session on its page
  and, there, the research task (Analyze) or the result (Results) that was
  on screen; after a restart too (the settings file keeps it).
* Opt-in by that click: a start still shows Home and opens no project, and
  opening the project from its own card opens it as before.
* A task or result deleted meanwhile is not reopened.

Synthetic data only (the Stage 36 UCLA/SACS-shaped fixture).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from test_stage36_ux_baseline import eight_correlations, prepared_workspace  # noqa: E402
from workspace_harness import Workspace  # noqa: E402


class ContinueTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def stored(self) -> dict:
        return json.loads((self.root / "settings.json").read_text(encoding="utf-8"))

    def session_with_two_tasks(self):
        ws = prepared_workspace(self.root)
        self.addCleanup(ws.close)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            eight_correlations(ws)                  # task 1 (batch), stays in the task
            first = ws.app.pages["analyze"].task_id
            ws.click("task-new")
            ws.click("goal-scale")
            for name in ("UCLA", "AssertiveAction", "SocialJoining"):
                ws.check(f"role-items-{name}")
            second_selection = dict(ws.app.pages["analyze"].selection)
        return ws, first, second_selection

    def restart(self) -> Workspace:
        again = Workspace(root=self.root)
        self.addCleanup(again.close)
        return again

    def test_continue_reopens_the_task_that_was_on_screen(self):
        ws, first, _ = self.session_with_two_tasks()
        ws.click(f"task-{first}")
        self.assertEqual(ws.app.pages["analyze"].task_id, first)
        project = ws.app.projects.info().id
        self.assertEqual((self.stored()["last_route"], self.stored()["last_task"]),
                         ("analyze", first))
        ws.close()
        again = self.restart()
        self.assertEqual(again.app.route, "home", "a start still shows Home")
        self.assertFalse(again.app.projects.active, "and opens no project by itself")
        again.click("home-continue")
        page = again.app.pages["analyze"]
        self.assertEqual((again.app.projects.info().id, again.app.route), (project, "analyze"))
        self.assertEqual(page.task_id, first, "the task that was on screen")
        self.assertEqual(page.goal, "relate")
        self.assertEqual(page.selection["x"], "UCLA")
        self.assertEqual(again.app.section, "task-result", "at its result")

    def test_continue_reopens_the_result_that_was_read(self):
        ws, first, _ = self.session_with_two_tasks()
        entry = ws.app.session.results[-1]
        ws.click("nav-results")
        self.assertEqual(ws.app.session.selected_result, entry.id)
        record = entry.record_id
        self.assertTrue(record)
        self.assertEqual(self.stored()["last_result"], record)
        ws.close()
        again = self.restart()
        again.click("home-continue")
        self.assertEqual(again.app.route, "results")
        chosen = again.app.session.result(again.app.session.selected_result)
        self.assertEqual(chosen.record_id, record)
        self.assertTrue(again.find_all(f"result-detail-{chosen.id}"))

    def test_opening_the_project_from_its_card_is_unchanged(self):
        ws, first, _ = self.session_with_two_tasks()
        ws.click(f"task-{first}")
        project = ws.app.projects.info().id
        ws.close()
        again = self.restart()
        again.click(f"project-open-{project}")
        self.assertEqual(again.app.route, "project", "the project's own page, as before")
        self.assertIsNone(again.app.pages["analyze"].task_id)

    def test_a_deleted_task_is_not_reopened(self):
        ws, first, _ = self.session_with_two_tasks()
        ws.click(f"task-{first}")
        project_id = ws.app.projects.info().id
        self.assertEqual(self.stored()["last_task"], first)
        ws.app.projects.project.delete_task(first)     # e.g. by another copy of the program
        ws.close()
        again = self.restart()
        again.click("home-continue")
        self.assertEqual((again.app.projects.info().id, again.app.route),
                         (project_id, "analyze"))
        self.assertIsNone(again.app.pages["analyze"].task_id, "nothing that is gone")


if __name__ == "__main__":
    unittest.main()
