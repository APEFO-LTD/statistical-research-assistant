"""Stage 37 (independent review, §7 gap 1): what the "data rows" context
source may send.

Before this change the source sent the first five rows with every column,
participant codes and free-text answers included, relying only on the
researcher's statement that the project's data identify nobody
(``ai_context.preview``). Columns confirmed (or recognised) as identifiers
and free-text columns are now left out by default, and the preview says
which ones were left out. Synthetic data only; the provider is faked in
this process and no test touches the network.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd  # noqa: E402

import ai_assist  # noqa: E402
import ai_context  # noqa: E402
from test_stage368_ai_gate import GateCase, texts  # noqa: E402
from workspace_state import ResearchSession  # noqa: E402

CODES = [f"SYN-P{i:03d}" for i in range(1, 13)]
COMMENTS = [f"Synthetic free-text answer {i}: my fictional week felt calm and quite busy"
            for i in range(1, 13)]


def sensitive_frame() -> pd.DataFrame:
    """Twelve fictional rows: a participant code, a numbered respondent, two
    analysable variables and a free-text comment."""
    return pd.DataFrame({
        "participant_code": CODES,
        "respondent": list(range(101, 113)),
        "group": ["arm1", "arm2"] * 6,
        "stress": [3, 4, 2, 5, 3, 4, 1, 2, 5, 4, 3, 2],
        "comment": COMMENTS,
    })


def session_with(frame: pd.DataFrame) -> ResearchSession:
    session = ResearchSession()
    session.set_dataset(frame, "synthetic_rows.csv")
    return session


class DataRowsPreviewTests(unittest.TestCase):
    def test_identifier_and_free_text_columns_are_left_out_of_the_data_rows(self):
        session = session_with(sensitive_frame())
        session.confirm_level("participant_code", "id")
        rows = ai_context.preview("raw_data", session=session)
        header = rows.splitlines()[0]
        self.assertEqual(header, "group,stress")
        for value in (*CODES, "101", *COMMENTS):
            self.assertNotIn(value, rows)
        self.assertIn("arm1,3", rows)
        self.assertEqual(ai_context.excluded_columns(session), [
            ("participant_code", "identifier"), ("respondent", "identifier"),
            ("comment", "free_text")])

    def test_a_comment_confirmed_as_a_category_is_still_free_text(self):
        session = session_with(sensitive_frame())
        session.confirm_level("comment", "nominal")       # e.g. accepted in bulk
        self.assertIn(("comment", "free_text"), ai_context.excluded_columns(session))
        self.assertNotIn(COMMENTS[0], ai_context.preview("raw_data", session=session))

    def test_nothing_left_means_no_row_is_sent(self):
        session = session_with(sensitive_frame()[["participant_code", "comment"]])
        self.assertEqual(ai_context.preview("raw_data", session=session), "")
        self.assertEqual(ai_context.data_rows(("raw_data",), session), 0)

    def test_the_request_names_what_was_left_out(self):
        session = session_with(sensitive_frame())
        request = ai_assist.build_request("explain_table", result="Synthetic result", sources=(),
                                          session=session)
        self.assertEqual(request.excluded, ())
        from project_store import ProjectStore
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(Path(folder))
            info = store.create("Rows privacy")
            with store.open(info.id) as project:
                ai_context.state_anonymous(project, True)
                ai_context.allow(project, "raw_data", True, remote=True)
                request = ai_assist.build_request(
                    "explain_table", result="Synthetic result", sources=("raw_data",),
                    project=project, session=session)
        self.assertEqual(request.excluded, (("participant_code", "identifier"),
                                            ("respondent", "identifier"),
                                            ("comment", "free_text")))
        self.assertEqual(request.data_rows, 5)
        for value in (*CODES, *COMMENTS):
            self.assertNotIn(value, request.prompt)


STRESS = [3, 4, 2, 5, 3, 4, 1, 2, 5, 4, 3, 2]
EMAILS = [f"{n}.synthetic@example.lv" for n in ("anna", "janis", "ilze", "peteris", "marta",
                                                 "olga", "ivan", "eva", "karlis", "liga",
                                                 "maris", "zane")]
NAMES = ["Anna Ozola", "Jānis Bērziņš", "Ilze Kalniņa", "Pēteris Liepa", "Marta Zariņa",
         "Olga Petrova", "Ivan Smirnov", "Eva Krūmiņa", "Kārlis Ozols", "Līga Vītola",
         "Māris Kļaviņš", "Zane Siliņa"]


class IdentifierDetectionTests(unittest.TestCase):
    """Independent review verify-stage37-rag, privacy F1 and F2: numeric
    participant codes, phone numbers, e-mails, names and codes with a repeat
    stay out of the data rows however they are named or confirmed."""

    def left_out(self, frame, *, accept=True, confirm=None):
        session = session_with(frame)
        if accept:
            session.accept_suggestions()
        for name, level in (confirm or {}).items():
            session.confirm_level(name, level)
        return dict(ai_context.excluded_columns(session)), ai_context.preview(
            "raw_data", session=session)

    def test_numeric_participant_codes_are_left_out_whatever_their_name(self):
        frame = pd.DataFrame({"ParticipantID": range(1001, 1013),
                              "Participant": range(2001, 2013),
                              "Respondenta kods": range(501, 513),
                              "Код респондента": range(701, 713),
                              "stress": STRESS})
        for accept in (True, False):
            with self.subTest(accept=accept):
                left, rows = self.left_out(frame, accept=accept)
                for name in ("ParticipantID", "Participant", "Respondenta kods",
                             "Код респондента"):
                    self.assertEqual(left.get(name), "identifier", name)
                for value in ("1001", "2001", "501,", "701"):
                    self.assertNotIn(value, rows)
                self.assertNotIn("stress", left)

    def test_phone_numbers_are_identifiers(self):
        frame = pd.DataFrame({"Phone": [37120000000 + i for i in range(12)],
                              "contact": [f"+371 2000 {1000 + i}" for i in range(12)],
                              "stress": STRESS})
        left, rows = self.left_out(frame)
        self.assertEqual(left.get("Phone"), "identifier")
        self.assertEqual(left.get("contact"), "identifier")
        self.assertNotIn("3712000000", rows)
        self.assertNotIn("+371", rows)

    def test_e_mails_and_codes_with_a_repeat_are_identifiers_even_as_categories(self):
        codes = list(CODES)
        codes[5] = codes[4]                       # one double submission
        frame = pd.DataFrame({"Email": EMAILS, "participant_code": codes, "stress": STRESS})
        left, rows = self.left_out(frame)
        self.assertEqual(left.get("Email"), "identifier")
        self.assertEqual(left.get("participant_code"), "identifier")
        self.assertNotIn("@example.lv", rows)
        self.assertNotIn("SYN-P001", rows)

    def test_names_and_e_mails_confirmed_as_categories_stay_out(self):
        frame = pd.DataFrame({"Respondent name": NAMES, "Address": EMAILS, "stress": STRESS})
        left, rows = self.left_out(frame, confirm={"Respondent name": "nominal",
                                                   "Address": "nominal"})
        self.assertEqual(left.get("Respondent name"), "identifier")
        self.assertEqual(left.get("Address"), "identifier")
        for value in ("Anna Ozola", "Jānis", "anna.synthetic"):
            self.assertNotIn(value, rows)
        many = pd.DataFrame({"E-mail": [f"p{i}.synthetic@example.lv" for i in range(30)],
                             "stress": (STRESS * 3)[:30]})
        left, rows = self.left_out(many, confirm={"E-mail": "nominal"})
        self.assertEqual(left.get("E-mail"), "identifier")
        self.assertNotIn("@example.lv", rows)

    def test_ordinary_variables_are_still_sent(self):
        frame = pd.DataFrame({
            "group": ["arm1", "arm2"] * 6, "stress": STRESS,
            "age": [19, 22, 35, 41, 28, 30, 25, 33, 47, 52, 21, 29],
            "participant_age": [19, 22, 35, 41, 28, 30, 25, 33, 47, 52, 21, 29],
            "country": ["Latvia", "Estonia", "Lithuania"] * 4,
            "condition": ["Control Group", "Treatment Group"] * 6,
            "income": [1200, 1350, 980, 2100, 1750, 1500, 1100, 1900, 2500, 1300, 1450, 1600],
            "Subject": ["Maths", "Physics", "History"] * 4,
        })
        left, rows = self.left_out(frame)
        self.assertEqual(left, {})
        self.assertIn("arm1,3,19,19,Latvia,Control Group,1200,Maths", rows)


class DataRowsOnScreenTests(GateCase):
    """The assistant panel and Settings show what the data rows leave out;
    the request that leaves holds none of it (fake provider, no network)."""

    def test_the_preview_shows_the_columns_left_out_and_the_request_has_none(self):
        ws = self.workspace()
        self.connect(ws)
        project = self.create_project(ws, "Rows privacy on screen")
        path = self.base / "synthetic_rows.csv"
        sensitive_frame().to_csv(path, index=False)
        self.assertTrue(ws.run(ws.app.load_path(str(path))))
        session = ws.app.session
        session.confirm_level("participant_code", "id")
        session.confirm_level("stress", "ordinal")
        session.confirm_level("group", "nominal")
        entry = ws.run(ws.app.pages["analyze"]._execute(
            "groups", {"outcome": "stress", "group": "group"}, {}, {"independent": True}))
        self.assertIsNotNone(entry)
        self.allow(ws, "raw_data", anonymous=True)
        ws.app.navigate("settings")
        shown = texts(ws, "ai-excluded-raw_data")
        self.assertIn("participant_code (identifier)", shown)
        self.assertIn("comment (free text)", shown)
        ws.app.navigate("results")
        ws.check("ai-source-raw_data", True)
        excluded = texts(ws, "ai-preview-excluded")
        for fragment in ("participant_code (identifier)", "respondent (identifier)",
                         "comment (free text)"):
            self.assertIn(fragment, excluded)
        preview = ws.find("ai-preview-text").value
        self.assertIn("CONTEXT (raw_data)", preview)
        for value in (*CODES, *COMMENTS):
            self.assertNotIn(value, preview)
        self.send(ws)
        (post,) = self.providers.posts()
        self.assertEqual(post.prompt, preview)
        for value in (*CODES, *COMMENTS):
            self.assertNotIn(value, post.text)
        self.assertEqual(self.ai_events(project)[0]["sources"], ["raw_data", "result"])


if __name__ == "__main__":
    unittest.main()
