import unittest

from models.enums import Condition, LoanStatus as S
from models.errors import ConflictError, PermissionDeniedError, ValidationError
from plugins.extensions import ExtensionService, ExtensionStatus, RatingBook
from .helpers import World

class ExtensionTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.svc = ExtensionService(self.w.c)
        self.loan = self.w.lend(self.w.amina, self.w.cara, self.w.iron, 0, 2)    # due 11:00

    def test_hours_must_be_1_to_24(self):
        for bad in (0, 0.5, 25, -3, True, "2"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    self.svc.request(self.w.cara, self.loan, bad)

    def test_only_borrower_asks_only_owner_decides(self):
        with self.assertRaises(PermissionDeniedError):
            self.svc.request(self.w.ben, self.loan, 2)
        req = self.svc.request(self.w.cara, self.loan, 2)
        with self.assertRaises(PermissionDeniedError):
            self.svc.decide(self.w.cara, req, True)

    def test_approval_extends_due_time_once(self):
        req = self.svc.request(self.w.cara, self.loan, 3)
        self.svc.decide(self.w.amina, req, True)
        self.assertEqual(self.loan.due, self.w.at(5))
        self.assertEqual(req.status, ExtensionStatus.APPROVED)
        with self.assertRaises(ValidationError):
            self.svc.decide(self.w.amina, req, False)      # decided only once
        with self.assertRaises(ValidationError):
            self.svc.request(self.w.cara, self.loan, 1)    # one request per loan

    def test_decline_keeps_due_time(self):
        req = self.svc.request(self.w.cara, self.loan, 3)
        self.svc.decide(self.w.amina, req, False)
        self.assertEqual(self.loan.due, self.w.at(2))
        self.assertEqual(req.status, ExtensionStatus.DECLINED)
        self.assertTrue(any("declined" in n.message for n in self.w.notifier.inbox(self.w.cara.id)))

    def test_approved_extension_clears_overdue(self):
        self.w.clock.advance(4)
        self.w.c.tick()
        self.assertEqual(self.loan.status, S.OVERDUE)
        req = self.svc.request(self.w.cara, self.loan, 2)
        self.svc.decide(self.w.amina, req, True)
        self.assertEqual(self.loan.status, S.HANDED_OVER)
        self.assertGreater(self.loan.due, self.w.clock.now())
        self.assertEqual(self.w.c.tick(), [])
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)
        self.assertTrue(self.loan.was_on_time)

    def test_extension_cannot_overlap_next_confirmed_booking(self):
        later = self.w.c.request_item(self.w.ben, self.w.iron, self.w.at(3), 2)   # 12:00-14:00
        self.w.c.accept_request(self.w.amina, later)
        req = self.svc.request(self.w.cara, self.loan, 2)    # would reach 13:00
        with self.assertRaises(ConflictError):
            self.svc.decide(self.w.amina, req, True)
        self.assertEqual(self.loan.due, self.w.at(2))
        self.assertEqual(req.status, ExtensionStatus.PENDING)   # owner may still decline
        self.svc.decide(self.w.amina, req, False)
        # an extension that ends exactly when the next booking begins is fine
        loan2 = self.w.lend(self.w.cara, self.w.dan, self.w.novel, 0, 2)
        eve = self.w.c.add_student("Eve", "North")
        nxt = self.w.c.request_item(eve, self.w.novel, self.w.at(4), 1)
        self.w.c.accept_request(self.w.cara, nxt)
        r2 = self.svc.request(self.w.dan, loan2, 2)
        self.svc.decide(self.w.cara, r2, True)
        self.assertEqual(loan2.due, self.w.at(4))

    def test_cannot_extend_a_loan_not_held(self):
        pending = self.w.c.request_item(self.w.ben, self.w.novel, self.w.at(0), 2)
        with self.assertRaises(ValidationError):
            self.svc.request(self.w.ben, pending, 2)


class RatingTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.book = RatingBook(self.w.c)
        self.loan = self.w.lend(self.w.amina, self.w.cara, self.w.iron, 0, 2)

    def test_cannot_rate_before_return(self):
        with self.assertRaises(ValidationError):
            self.book.rate(self.w.cara, self.loan, 5)

    def test_each_side_rates_once_and_average_works(self):
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)
        self.assertIsNone(self.book.average(self.w.amina))
        self.book.rate(self.w.cara, self.loan, 5)       # Cara rates Amina
        self.book.rate(self.w.amina, self.loan, 4)      # Amina rates Cara
        with self.assertRaises(ValidationError):
            self.book.rate(self.w.cara, self.loan, 1)   # only once
        self.assertEqual(self.book.average(self.w.amina), (5.0, 1))
        self.assertEqual(self.book.average(self.w.cara), (4.0, 1))

    def test_stars_validation_and_outsiders(self):
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)
        for bad in (0, 6, 2.5, True, "3"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    self.book.rate(self.w.cara, self.loan, bad)
        with self.assertRaises(PermissionDeniedError):
            self.book.rate(self.w.ben, self.loan, 3)

    def test_average_over_several_loans(self):
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)
        self.book.rate(self.w.cara, self.loan, 5)
        loan2 = self.w.c.request_item(self.w.cara, self.w.iron, self.w.at(5), 1)
        self.w.c.accept_request(self.w.amina, loan2)
        self.w.clock.advance(5)
        self.w.c.hand_over(self.w.amina, loan2)
        self.w.c.confirm_return(self.w.amina, loan2, Condition.GOOD)
        self.book.rate(self.w.cara, loan2, 2)
        self.assertEqual(self.book.average(self.w.amina), (3.5, 2))


if __name__ == "__main__":
    unittest.main()
