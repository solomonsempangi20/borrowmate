import unittest

from models.enums import Condition, ItemStatus, LoanStatus as S, ValueTier
from models.errors import InvalidTransitionError, PermissionDeniedError, ValidationError
from models.hostel import Hostel
from models.loan import Loan
from .helpers import T0, World


class EncapsulationTest(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_properties_are_read_only(self):
        for obj, attr in [(self.w.ben, "reliability"), (self.w.ben, "completed_loans"),
                          (self.w.ben, "name"), (self.w.calc, "status"), (self.w.calc, "owner"),
                          (self.w.c.hostels()[0], "name")]:
            with self.subTest(attr=attr):
                with self.assertRaises(AttributeError):
                    setattr(obj, attr, 1)

    def test_reliability_changes_and_is_clamped(self):
        s = self.w.ben
        s.record_return(True)
        self.assertAlmostEqual(s.reliability, 3.2)
        s.record_return(False)
        self.assertAlmostEqual(s.reliability, 2.7)
        self.assertEqual((s.completed_loans, s.late_returns), (2, 1))
        for _ in range(20):
            s.record_return(False)
        self.assertEqual(s.reliability, 0.0)
        for _ in range(40):
            s.record_return(True)
        self.assertEqual(s.reliability, 5.0)

    def test_only_an_admin_can_suspend(self):
        with self.assertRaises(PermissionDeniedError):
            self.w.ben.set_suspended(True, self.w.dan)
        self.w.ben.set_suspended(True, self.w.admin)
        self.assertTrue(self.w.ben.is_suspended)

    def test_trust_ladder(self):
        s = self.w.c.add_student("T", "North", reliability=3.0, completed_loans=1)
        self.assertEqual(s.max_value_tier(), ValueTier.LOW)
        s2 = self.w.c.add_student("T2", "North", reliability=3.0, completed_loans=2)
        self.assertEqual(s2.max_value_tier(), ValueTier.MEDIUM)
        s3 = self.w.c.add_student("T3", "North", reliability=4.0, completed_loans=4)
        self.assertEqual(s3.max_value_tier(), ValueTier.MEDIUM)
        s4 = self.w.c.add_student("T4", "North", reliability=4.0, completed_loans=5)
        self.assertEqual(s4.max_value_tier(), ValueTier.HIGH)
        self.assertEqual(self.w.ben.max_active_loans(), 1)

    def test_admin_cannot_own_items(self):
        with self.assertRaises(ValidationError):
            self.w.c.add_item(self.w.admin, "book", "Nope")


class HostelTest(unittest.TestCase):
    def test_haversine(self):
        london, paris = Hostel("L", 51.5074, -0.1278), Hostel("P", 48.8566, 2.3522)
        self.assertAlmostEqual(london.distance_to(paris), 343.5, delta=2)
        self.assertAlmostEqual(london.distance_to(london), 0.0)
        self.assertAlmostEqual(london.distance_to(paris), paris.distance_to(london))

    def test_invalid_coordinates(self):
        with self.assertRaises(ValidationError):
            Hostel("Bad", 100, 0)


class ItemRulesTest(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_pause_resume(self):
        self.w.iron.pause()
        self.assertEqual(self.w.iron.status, ItemStatus.PAUSED)
        self.w.iron.resume()
        self.assertEqual(self.w.iron.status, ItemStatus.AVAILABLE)
        with self.assertRaises(InvalidTransitionError):
            self.w.iron.resume()

    def test_item_on_loan_cannot_be_paused(self):
        self.w.lend(self.w.amina, self.w.cara, self.w.iron)
        with self.assertRaises(InvalidTransitionError):
            self.w.iron.pause()
        with self.assertRaises(PermissionDeniedError):
            self.w.c.pause_item(self.w.cara, self.w.iron)   # not the owner


class LoanStateMachineTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.loan = Loan("L9", self.w.iron, self.w.cara, self.w.at(0), self.w.at(2), T0)

    def test_happy_path(self):
        l = self.loan
        l.accept(); self.assertEqual(l.status, S.ACCEPTED)
        l.hand_over(self.w.at(0), Condition.GOOD); self.assertEqual(l.status, S.HANDED_OVER)
        self.assertTrue(l.mark_returned(self.w.at(1), Condition.GOOD))
        self.assertEqual(l.status, S.RETURNED)

    def test_decline_and_cancel(self):
        self.loan.decline(); self.assertEqual(self.loan.status, S.DECLINED)
        other = Loan("L8", self.w.iron, self.w.cara, self.w.at(0), self.w.at(2), T0)
        other.cancel(); self.assertEqual(other.status, S.CANCELLED)
        other2 = Loan("L7", self.w.iron, self.w.cara, self.w.at(0), self.w.at(2), T0)
        other2.accept(); other2.cancel(); self.assertEqual(other2.status, S.CANCELLED)

    def test_overdue_dispute_and_extension_paths(self):
        l = self.loan
        l.accept(); l.hand_over(T0, Condition.GOOD)
        l.mark_overdue(); self.assertEqual(l.status, S.OVERDUE)
        l.extend_to(self.w.at(5)); self.assertEqual(l.status, S.HANDED_OVER)
        l.dispute("broken"); self.assertEqual(l.status, S.DISPUTED)
        self.assertFalse(l.mark_returned(self.w.at(9), Condition.DAMAGED))   # late
        self.assertEqual(l.status, S.RETURNED)

    def test_overdue_can_be_returned_late(self):
        l = self.loan
        l.accept(); l.hand_over(T0, Condition.GOOD); l.mark_overdue()
        self.assertFalse(l.mark_returned(self.w.at(3), Condition.GOOD))

    def test_every_illegal_move_raises(self):
        for source, allowed in Loan.TRANSITIONS.items():
            for target in S:
                if target in allowed:
                    continue
                with self.subTest(source=source.name, target=target.name):
                    loan = Loan("LX", self.w.iron, self.w.cara, self.w.at(0), self.w.at(2), T0)
                    loan._status = source          # put the machine in the source state
                    with self.assertRaises(InvalidTransitionError):
                        loan.ensure_can_move_to(target)

    def test_specific_illegal_calls(self):
        with self.assertRaises(InvalidTransitionError):
            self.loan.hand_over(T0, Condition.GOOD)          # not accepted yet
        with self.assertRaises(InvalidTransitionError):
            self.loan.mark_returned(T0, Condition.GOOD)
        self.loan.decline()
        with self.assertRaises(InvalidTransitionError):
            self.loan.accept()

    def test_overlap_logic(self):
        mk = lambda a, b, item=None: Loan("Lx", item or self.w.iron, self.w.cara, self.w.at(a), self.w.at(b), T0)
        base = mk(2, 4)
        self.assertTrue(base.overlaps(mk(3, 5)))
        self.assertTrue(base.overlaps(mk(0, 3)))
        self.assertTrue(base.overlaps(mk(2.5, 3.5)))     # inside
        self.assertTrue(base.overlaps(mk(1, 6)))         # contains
        self.assertFalse(base.overlaps(mk(4, 6)))        # back-to-back
        self.assertFalse(base.overlaps(mk(0, 2)))        # back-to-back
        self.assertFalse(base.overlaps(mk(3, 5, self.w.calc)))   # other item
        self.assertFalse(base.overlaps(base))

    def test_loan_must_end_after_start(self):
        with self.assertRaises(ValidationError):
            Loan("L0", self.w.iron, self.w.cara, self.w.at(2), self.w.at(2), T0)


if __name__ == "__main__":
    unittest.main()
