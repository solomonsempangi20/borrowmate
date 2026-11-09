import unittest

from models.enums import Condition, ConflictSeverity, ItemStatus, LoanStatus as S
from models.errors import (ConflictError, EligibilityError, InvalidTransitionError,
                           PermissionDeniedError, ValidationError)
from .helpers import T0, World


class EligibilityTest(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def refused(self, borrower, item, start_h=0, hours=1, text=""):
        with self.assertRaises(EligibilityError) as ctx:
            self.w.c.request_item(borrower, item, self.w.at(start_h), hours)
        self.assertIn(text.lower(), str(ctx.exception).lower())

    def test_allowed_request_works(self):
        loan = self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(0), 2)
        self.assertEqual(loan.status, S.REQUESTED)

    def test_admin_cannot_borrow(self):
        self.refused(self.w.admin, self.w.iron, text="only students")

    def test_suspended_user_refused(self):
        self.w.c.suspend_user(self.w.admin, self.w.ben.id)
        self.refused(self.w.ben, self.w.iron, text="suspended")
        self.w.c.restore_user(self.w.admin, self.w.ben.id)
        self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(0), 1)

    def test_own_item_refused(self):
        self.refused(self.w.amina, self.w.iron, text="own item")

    def test_paused_item_refused(self):
        self.w.iron.pause()
        self.refused(self.w.ben, self.w.iron, text="paused")

    def test_overdue_loan_blocks_new_requests(self):
        self.w.lend(self.w.amina, self.w.cara, self.w.iron, hours=1)
        self.w.clock.advance(2)
        self.w.c.tick()
        self.refused(self.w.cara, self.w.calc, start_h=3, text="overdue")

    def test_active_loan_limit_new_student_is_one(self):
        self.w.lend(self.w.amina, self.w.ben, self.w.iron, hours=1, hand_over=False)
        self.refused(self.w.ben, self.w.novel, start_h=5, text="limit")

    def test_active_loan_limit_after_two_loans_is_three(self):
        extra = [self.w.c.add_item(self.w.amina, "book", f"B{i}") for i in range(3)]
        for item in extra:
            self.w.lend(self.w.amina, self.w.cara, item, hours=1, hand_over=False)
        self.refused(self.w.cara, self.w.iron, start_h=9, text="limit")

    def test_trust_ladder_by_value_tier(self):
        self.refused(self.w.ben, self.w.calc, text="trust level")      # MEDIUM
        self.refused(self.w.cara, self.w.laptop, text="trust level")   # HIGH
        self.w.c.request_item(self.w.cara, self.w.calc, self.w.at(0), 1)       # MEDIUM ok
        self.w.c.request_item(self.w.dan, self.w.novel, self.w.at(0), 1)       # LOW ok

    def test_start_in_the_past_refused(self):
        self.refused(self.w.ben, self.w.iron, start_h=-1, text="past")

    def test_hours_limit_per_item(self):
        self.refused(self.w.ben, self.w.iron, hours=7, text="at most 6")
        self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(0), 6)
        self.refused(self.w.dan, self.w.iron, start_h=10, hours=0, text="positive")


class ConflictTest(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_blocked_by_confirmed_booking_with_free_time(self):
        self.w.lend(self.w.amina, self.w.cara, self.w.iron, 1, 3, hand_over=False)  # 1h-4h
        with self.assertRaises(ConflictError) as ctx:
            self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(2), 2)
        self.assertEqual(ctx.exception.severity, ConflictSeverity.BLOCKED)
        self.assertIn("free from Mon 10 Mar 13:00", str(ctx.exception))
        # back-to-back is fine
        self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(4), 1)

    def test_competing_requests_allowed_and_reported(self):
        a = self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(1), 3)
        b = self.w.c.request_item(self.w.dan, self.w.iron, self.w.at(2), 3)
        self.assertEqual(self.w.c.loans.competing_with(a), [b])
        found = self.w.c.loans.conflicts()
        self.assertEqual([c.severity for c in found], [ConflictSeverity.COMPETING])

    def test_accepting_one_declines_the_competing_one(self):
        a = self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(1), 3)
        b = self.w.c.request_item(self.w.dan, self.w.iron, self.w.at(2), 3)
        c = self.w.c.request_item(self.w.cara, self.w.iron, self.w.at(8), 1)   # not overlapping
        self.w.c.accept_request(self.w.amina, a)
        self.assertEqual((a.status, b.status, c.status), (S.ACCEPTED, S.DECLINED, S.REQUESTED))
        self.assertTrue(any("declined automatically" in n.message for n in self.w.notifier.inbox(self.w.dan.id)))
        self.assertEqual(self.w.c.loans.conflicts(), [])

    def test_clash_is_impossible_but_reported_if_forced(self):
        a = self.w.lend(self.w.amina, self.w.ben, self.w.iron, 1, 3, hand_over=False)
        b = self.w.c.request_item(self.w.dan, self.w.iron, self.w.at(4), 2)
        b._start = self.w.at(2)               # force an overlap behind the rules' back
        with self.assertRaises(ConflictError):
            self.w.c.accept_request(self.w.amina, b)      # impossible through the rules
        b._status = S.ACCEPTED                              # force a CLASH state
        self.assertEqual([c.severity for c in self.w.c.loans.conflicts()], [ConflictSeverity.CLASH])


class AccountabilityTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.loan = self.w.lend(self.w.amina, self.w.cara, self.w.iron, 0, 3)

    def test_only_owner_can_accept_hand_over_and_confirm_return(self):
        pending = self.w.c.request_item(self.w.ben, self.w.novel, self.w.at(0), 2)
        with self.assertRaises(PermissionDeniedError):
            self.w.c.accept_request(self.w.ben, pending)
        with self.assertRaises(PermissionDeniedError):
            self.w.c.decline_request(self.w.ben, pending)
        self.w.c.accept_request(self.w.cara, pending)
        with self.assertRaises(PermissionDeniedError):
            self.w.c.hand_over(self.w.ben, pending)
        with self.assertRaises(PermissionDeniedError):
            self.w.c.confirm_return(self.w.cara, self.loan, Condition.GOOD)   # borrower cannot fake it

    def test_on_time_return_updates_reliability_and_item(self):
        before = self.w.cara.reliability
        self.w.clock.advance(2)
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.FAIR)
        self.assertTrue(self.loan.was_on_time)
        self.assertAlmostEqual(self.w.cara.reliability, before + 0.2)
        self.assertEqual(self.w.iron.status, ItemStatus.AVAILABLE)
        self.assertEqual(self.w.iron.condition, Condition.FAIR)
        self.assertEqual(self.loan.condition_in, Condition.FAIR)

    def test_late_return_lowers_reliability(self):
        before = self.w.cara.reliability
        self.w.clock.advance(5)
        self.w.c.tick()
        self.assertEqual(self.loan.status, S.OVERDUE)
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)
        self.assertFalse(self.loan.was_on_time)
        self.assertAlmostEqual(self.w.cara.reliability, before - 0.5)
        self.assertEqual(self.w.cara.late_returns, 1)

    def test_return_requires_a_condition(self):
        with self.assertRaises(ValidationError):
            self.w.c.confirm_return(self.w.amina, self.loan, None)

    def test_cannot_return_twice(self):
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)
        with self.assertRaises(InvalidTransitionError):
            self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)

    def test_cannot_hand_over_early(self):
        later = self.w.c.request_item(self.w.dan, self.w.novel, self.w.at(5), 2)
        self.w.c.accept_request(self.w.cara, later)
        with self.assertRaises(ValidationError):
            self.w.c.hand_over(self.w.cara, later)
        self.w.clock.advance(5)
        self.w.c.hand_over(self.w.cara, later)
        self.assertEqual(later.status, S.HANDED_OVER)

    def test_only_borrower_cancels(self):
        pending = self.w.c.request_item(self.w.ben, self.w.novel, self.w.at(0), 2)
        with self.assertRaises(PermissionDeniedError):
            self.w.c.cancel_request(self.w.cara, pending)
        self.w.c.cancel_request(self.w.ben, pending)
        self.assertEqual(pending.status, S.CANCELLED)

    def test_dispute_by_party_only_and_admin_can_view(self):
        with self.assertRaises(PermissionDeniedError):
            self.w.c.report_problem(self.w.ben, self.loan, "x")
        with self.assertRaises(ValidationError):
            self.w.c.report_problem(self.w.cara, self.loan, "  ")
        self.w.c.report_problem(self.w.cara, self.loan, "It smells of smoke")
        self.assertEqual(self.w.c.disputes(self.w.admin), [self.loan])
        with self.assertRaises(PermissionDeniedError):
            self.w.c.disputes(self.w.ben)
        self.assertTrue(any("Dispute" in n.message for n in self.w.notifier.inbox(self.w.admin.id)))


class OverdueAndNotificationsTest(unittest.TestCase):
    def test_overdue_flags_loans_and_notifies_both(self):
        w = World()
        loan = w.lend(w.amina, w.cara, w.iron, 0, 2)
        self.assertEqual(w.c.tick(), [])
        w.clock.advance(3)
        self.assertEqual(w.c.tick(), [loan])
        self.assertEqual(loan.status, S.OVERDUE)
        self.assertTrue(any("OVERDUE" in n.message for n in w.notifier.inbox(w.cara.id)))
        self.assertTrue(any("OVERDUE" in n.message for n in w.notifier.inbox(w.amina.id)))
        self.assertEqual(w.c.tick(), [])        # not flagged twice

    def test_inbox_covers_the_whole_flow(self):
        w = World()
        loan = w.lend(w.amina, w.cara, w.iron, 0, 2)
        w.c.confirm_return(w.amina, loan, Condition.GOOD)
        owner_msgs = " | ".join(n.message for n in w.notifier.inbox(w.amina.id))
        borrower_msgs = " | ".join(n.message for n in w.notifier.inbox(w.cara.id))
        self.assertIn("requested", owner_msgs)
        self.assertIn("accepted", borrower_msgs)
        self.assertIn("You now have", borrower_msgs)
        self.assertIn("confirmed", borrower_msgs)
        self.assertEqual(w.notifier.unread_count(w.cara.id), 3)
        w.notifier.mark_all_read(w.cara.id)
        self.assertEqual(w.notifier.unread_count(w.cara.id), 0)


class SearchAndDistanceTest(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_items_near_sorted_by_distance_with_radius(self):
        rows = self.w.c.items_near(self.w.ben)     # Ben lives in North
        titles = [r.item.title for r in rows]
        dists = [r.distance_km for r in rows]
        self.assertEqual(dists, sorted(dists))
        self.assertEqual(titles[:3], ["Calculator", "Iron", "Laptop"])    # Amina is in North (0 km)
        self.assertEqual(titles[3], "Novel")                              # Cara in East, ~1.1 km
        near = self.w.c.items_near(self.w.ben, radius_km=0.5)
        self.assertEqual({r.item.owner.name for r in near}, {"Amina"})
        self.assertAlmostEqual(self.w.ben.hostel.distance_to(self.w.cara.hostel), 1.07, delta=0.05)
        with self.assertRaises(ValidationError):
            self.w.c.items_near(self.w.ben, radius_km=-1)

    def test_near_shows_permission_reason_and_upcoming(self):
        self.w.lend(self.w.amina, self.w.cara, self.w.iron, 3, 2, hand_over=False)
        rows = {r.item.title: r for r in self.w.c.items_near(self.w.ben)}
        self.assertIsNotNone(rows["Laptop"].problem)
        self.assertIn("trust", rows["Calculator"].problem)
        self.assertIsNone(rows["Iron"].problem)
        self.assertEqual(len(rows["Iron"].upcoming), 1)

    def test_paused_and_own_items_hidden(self):
        self.w.iron.pause()
        titles = [r.item.title for r in self.w.c.items_near(self.w.amina)]
        self.assertNotIn("Iron", titles)
        self.assertNotIn("Calculator", titles)      # her own
        self.assertIn("Novel", titles)

    def test_search(self):
        self.assertEqual([i.title for i in self.w.c.search("lap")], ["Laptop"])
        self.assertEqual(len(self.w.c.search("amina")), 3)
        with self.assertRaises(ValidationError):
            self.w.c.search("  ")


if __name__ == "__main__":
    unittest.main()
