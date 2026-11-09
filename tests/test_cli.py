import os
import tempfile
import unittest

from cli.app import CLI
from cli.inputs import parse_number, parse_when
from cli.tables import render_table
from models.enums import ItemStatus, LoanStatus as S
from models.errors import ValidationError
from services.seed import build_demo_community
from .helpers import T0, ScriptedIO, World


def run_cli(community, answers):
    io = ScriptedIO(answers)
    CLI(community, io.input, io.output).run()
    return io.text


class ParsingTest(unittest.TestCase):
    def test_parse_when(self):
        self.assertEqual(parse_when("now", T0), T0)
        self.assertEqual(parse_when("", T0), T0)
        self.assertEqual(parse_when("+2h", T0).hour, 11)
        self.assertEqual(parse_when("tomorrow 08:30", T0).day, 11)
        self.assertEqual(parse_when("2025-03-12 14:00", T0).day, 12)
        for bad in ("soon", "tomorrow 99:99", "2025-13-45 10:00"):
            with self.assertRaises(ValidationError):
                parse_when(bad, T0)

    def test_parse_number_and_table(self):
        self.assertEqual(parse_number("1.5"), 1.5)
        for bad in ("abc", "nan", "inf"):
            with self.assertRaises(ValidationError):
                parse_number(bad)
        self.assertEqual(render_table(["A"], []), "  (none)")
        table = render_table(["Name", "N"], [["Amina", 1], ["Bo", 22]])
        lengths = {len(line) for line in table.splitlines()}
        self.assertEqual(len(lengths), 1)    # aligned


class DemoViewsTest(unittest.TestCase):
    def setUp(self):
        self.c = build_demo_community()

    def test_every_view_shows_the_demo_scenario(self):
        out = run_cli(self.c, ["S4", "items", "taken", "conflicts", "overdue", "near", "", "search", "fan", "quit"])
        self.assertIn("Welcome, David!", out)
        self.assertIn("Held by", out)                              # all items
        self.assertIn("in 2h 30m", out)                            # iron countdown
        self.assertIn("30m LATE", out)                             # cable overdue
        self.assertIn("Confirmed bookings waiting for handover", out)
        self.assertIn("Microeconomics Textbook", out)
        self.assertIn("COMPETING", out)                            # two requests for the calculator
        self.assertIn("Paused", out)                               # desk fan
        self.assertIn("Can I borrow?", out)
        self.assertIn("No: You have an overdue loan", out)         # David is overdue -> reason shown
        self.assertIn("Search results", out)

    def test_near_with_radius(self):
        out = run_cli(self.c, ["S1", "near", "0.1", "quit"])
        self.assertIn("(closest first)", out)
        self.assertIn("Gaming Laptop", out)          # David lives in Amina's hostel (0 km)
        self.assertNotIn("Phone Charger", out)       # Brian's hostel is further than 0.1 km

    def test_inbox_marks_read(self):
        out = run_cli(self.c, ["S3", "inbox", "quit"])
        self.assertIn("Notifications (newest first)", out)
        self.assertGreater(len(self.c.notifier.inbox("S3")), 0)
        self.assertEqual(self.c.notifier.unread_count("S3"), 0)


class ErrorsNeverCrashTest(unittest.TestCase):
    def test_bad_input_shows_friendly_messages(self):
        c = build_demo_community()
        out = run_cli(c, [
            "ZZ", "S5",                       # unknown login, then valid
            "99", "nonsense",                 # bad menu choices
            "request", "I1", "yesterday",                   # bad time (stops before asking hours)
            "request", "I404",                              # unknown item
            "request", "I2", "now", "abc",                  # bad number
            "request", "I2", "now", "1",                    # the iron is out until 11:30 -> BLOCKED
            "clock", "-5",                                  # bad clock move
            "return",                                       # nothing to return
            "quit"])
        self.assertIn("! User 'ZZ' was not found", out)
        self.assertIn("! Unknown choice '99'", out)
        self.assertIn("! Unknown choice 'nonsense'", out)
        self.assertIn("! Use: now, +2h", out)
        self.assertIn("! Item 'I404' was not found", out)
        self.assertIn("! Please enter the hours", out)
        self.assertIn("BLOCKED", out)
        self.assertIn("! Hours to advance must be a positive number", out)
        self.assertIn("Nothing to choose from", out)
        self.assertTrue(out.rstrip().endswith("Goodbye!"))
        self.assertNotIn("Traceback", out)

    def test_end_of_input_exits_cleanly(self):
        out = run_cli(build_demo_community(), ["S1"])
        self.assertTrue(out.endswith("Goodbye!"))

    def test_admin_cannot_use_student_actions(self):
        out = run_cli(build_demo_community(), ["A1", "request", "quit"])
        self.assertIn("! Unknown choice 'request'", out)


class FullJourneyTest(unittest.TestCase):
    """Scripted run: Brian lends the charger to Dan, Dan returns it late, then ratings and extension."""

    def test_borrow_hand_over_return_flow(self):
        w = World()
        # Ids in the test world: S1 Amina, S2 Cara, S3 Ben, S4 Dan, A1 Grace; items I1 laptop, I2 calc, I3 iron, I4 novel
        out = run_cli(w.c, [
            "S3", "request", "I3", "now", "2", "switch",       # Ben asks Amina for the iron
            "S1", "approve", "L1", "handover", "L1", "good", "switch",
            "S3", "mine", "switch",
            "S1", "clock", "1", "return", "L1", "fair", "inbox", "switch",
            "quit"])
        loan = w.c.loans.get("L1")
        self.assertEqual(loan.status, S.RETURNED)
        self.assertTrue(loan.was_on_time)
        self.assertEqual(w.iron.status, ItemStatus.AVAILABLE)
        self.assertIn("Request L1 sent to Amina", out)
        self.assertIn("Loan L1 accepted", out)
        self.assertIn("handed to Ben", out)
        self.assertIn("Return confirmed (on time)", out)
        self.assertAlmostEqual(w.ben.reliability, 3.2)

    def test_late_return_and_borrower_cannot_confirm(self):
        w = World()
        out = run_cli(w.c, [
            "S3", "request", "I3", "now", "1", "switch",
            "S1", "approve", "L1", "handover", "L1", "", "switch",
            "S3", "return", "switch",                          # borrower has nothing to confirm
            "S1", "clock", "3", "overdue", "return", "L1", "good", "switch",
            "quit"])
        self.assertIn("Nothing to choose from", out)
        self.assertIn("Overdue items", out)
        self.assertIn("LATE", out)
        self.assertAlmostEqual(w.ben.reliability, 2.5)

    def test_dispute_flow_and_admin_actions(self):
        w = World()
        out = run_cli(w.c, [
            "S3", "request", "I3", "now", "4", "switch",
            "S1", "approve", "L1", "handover", "L1", "good", "report", "L1", "Cord is frayed", "switch",
            "A1", "disputes", "suspend", "S4", "restore", "S4", "suspend", "S99", "switch",
            "S4", "request", "I3", "+5", "1", "quit"])
        self.assertEqual(w.c.loans.get("L1").status, S.DISPUTED)
        self.assertIn("Cord is frayed", out)
        self.assertIn("Dan is suspended", out)
        self.assertIn("Dan is restored", out)
        self.assertIn("! User 'S99' was not found", out)

    def test_list_pause_and_cancel(self):
        w = World()
        out = run_cli(w.c, [
            "S3", "list", "book", "Physics 101", "new", "pause", "I5", "pause", "I5",
            "request", "I4", "now", "2", "cancel", "L1", "quit"])
        self.assertIn("Listed I5: Physics 101", out)
        self.assertIn("is paused", out)
        self.assertIn("is available again", out)
        self.assertEqual(w.c.loans.get("L1").status, S.CANCELLED)

    def test_plugin_menus_in_a_scripted_run(self):
        w = World()
        out = run_cli(w.c, [
            "S3", "need_post", "A stapler", "2", "5", "switch",
            "S1", "need_help", "N1", "", "household", "Stapler", "switch",
            "S3", "need_mine", "N1", "O1", "switch",
            "S1", "handover", "L1", "", "reports", "mine", "csv", "", "rating", "S3", "quit"])
        self.assertIn("Request N1 posted", out)
        self.assertIn("Offer O1 sent", out)
        self.assertIn("Loan L1 is confirmed with Amina", out)
        self.assertIn("handed to Ben", out)
        self.assertIn("Measure,Value", out)                 # CSV shown on screen
        self.assertIn("No ratings yet.", out)

    def test_csv_export_to_file_and_bad_path(self):
        w = World()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "health.csv")
            out = run_cli(w.c, ["S1", "reports", "health", "csv", path,
                                "reports", "health", "csv", os.path.join(folder, "nope", "x.csv"), "quit"])
            self.assertTrue(os.path.exists(path))
            self.assertIn(f"Saved {path}", out)
            self.assertIn("! Could not write the file", out)
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("Metric,Value"))

    def test_clock_moves_and_overdue_runs_before_menu(self):
        c = build_demo_community()
        out = run_cli(c, ["S2", "clock", "3", "overdue", "quit"])
        self.assertIn("The demo clock now shows Mon 10 Mar 12:00", out)
        overdue = [l for l in c.loans.all_loans() if l.status is S.OVERDUE]
        self.assertEqual(len(overdue), 2)       # cable and iron are both late now


if __name__ == "__main__":
    unittest.main()
