import unittest

from models.enums import ItemStatus, LoanStatus as S
from models.errors import PermissionDeniedError, ValidationError
from plugins.need_requests import NeedRequestsPlugin, NeedService, NeedStatus, OfferStatus
from .helpers import World

class NeedRequestTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.svc = NeedService(self.w.c)

    def test_post_notifies_only_students_in_range(self):
        need = self.svc.post(self.w.ben, "an iron", 2, 2)      # Ben: North. East is ~1.1 km, Far is ~15 km
        self.assertCountEqual(need.notified, [self.w.amina.id, self.w.cara.id])
        self.assertTrue(any("needs 'an iron'" in n.message for n in self.w.notifier.inbox(self.w.cara.id)))
        self.assertEqual(self.w.notifier.inbox(self.w.dan.id), [])
        self.assertEqual(self.w.notifier.inbox(self.w.ben.id), [])

    def test_validation_and_range_for_offers(self):
        for args in (("", 2, 2), ("x", 0, 2), ("x", 2, 0)):
            with self.assertRaises(ValidationError):
                self.svc.post(self.w.ben, *args)
        with self.assertRaises(PermissionDeniedError):
            self.svc.post(self.w.admin, "x", 1, 1)
        need = self.svc.post(self.w.ben, "an iron", 2, 2)
        with self.assertRaises(PermissionDeniedError):
            self.svc.offer(self.w.dan, need, kind="household", title="Iron")   # outside the radius
        with self.assertRaises(PermissionDeniedError):
            self.svc.offer(self.w.ben, need, kind="household", title="Iron")   # own request
        with self.assertRaises(PermissionDeniedError):
            self.svc.offer(self.w.cara, need, item=self.w.iron)               # not her item
        self.assertEqual(self.svc.open_needs_for(self.w.cara), [need])
        self.assertEqual(self.svc.open_needs_for(self.w.dan), [])

    def test_choosing_an_unlisted_offer_lists_the_item_and_creates_a_confirmed_loan(self):
        need = self.svc.post(self.w.ben, "a hair dryer", 2, 5)
        before = len(self.w.c.items)
        o1 = self.svc.offer(self.w.cara, need, kind="household", title="Hair dryer")
        o2 = self.svc.offer(self.w.amina, need, item=self.w.iron)
        with self.assertRaises(ValidationError):
            self.svc.offer(self.w.amina, need, item=self.w.iron)       # one offer per lender
        self.assertEqual(len(self.w.c.items), before)                  # nothing listed yet
        loan = self.svc.choose(self.w.ben, need, o1)
        self.assertEqual(loan.status, S.ACCEPTED)
        self.assertEqual(loan.borrower.id, self.w.ben.id)
        self.assertEqual(loan.owner.id, self.w.cara.id)
        self.assertEqual(len(self.w.c.items), before + 1)
        self.assertEqual(loan.item.title, "Hair dryer")
        self.assertEqual((need.status, o1.status, o2.status),
                         (NeedStatus.FULFILLED, OfferStatus.CHOSEN, OfferStatus.DECLINED))
        self.assertEqual(loan.hours, 2)

    def test_eligibility_is_checked_before_anything_is_created(self):
        need = self.svc.post(self.w.ben, "a projector", 2, 5)
        offer = self.svc.offer(self.w.amina, need, kind="electronics", title="Projector")   # MEDIUM
        items_before, loans_before = len(self.w.c.items), len(self.w.c.loans.all_loans())
        with self.assertRaises(Exception) as ctx:
            self.svc.choose(self.w.ben, need, offer)      # Ben is a new student: LOW only
        self.assertIn("trust level", str(ctx.exception))
        self.assertEqual((len(self.w.c.items), len(self.w.c.loans.all_loans())), (items_before, loans_before))
        self.assertEqual(need.status, NeedStatus.OPEN)
        self.assertEqual(offer.status, OfferStatus.PENDING)

    def test_hours_longer_than_item_maximum_refused(self):
        need = self.svc.post(self.w.ben, "an iron all day", 10, 5)
        offer = self.svc.offer(self.w.amina, need, item=self.w.iron)      # household max 6h
        with self.assertRaises(Exception) as ctx:
            self.svc.choose(self.w.ben, need, offer)
        self.assertIn("at most 6", str(ctx.exception))

    def test_only_requester_chooses_and_listed_item_must_be_available(self):
        need = self.svc.post(self.w.ben, "an iron", 2, 5)
        offer = self.svc.offer(self.w.amina, need, item=self.w.iron)
        with self.assertRaises(PermissionDeniedError):
            self.svc.choose(self.w.cara, need, offer)
        self.w.iron.pause()
        with self.assertRaises(Exception) as ctx:
            self.svc.choose(self.w.ben, need, offer)
        self.assertIn("paused", str(ctx.exception))
        self.assertEqual(self.w.iron.status, ItemStatus.PAUSED)

    def test_unanswered_requests_expire_after_24_hours(self):
        need = self.svc.post(self.w.ben, "an iron", 2, 5)
        self.w.clock.advance(23)
        self.assertEqual(self.svc.expire_old(), [])
        self.w.clock.advance(1)
        self.assertEqual(self.svc.expire_old(), [need])
        self.assertEqual(need.status, NeedStatus.EXPIRED)
        self.assertTrue(any("expired" in n.message for n in self.w.notifier.inbox(self.w.ben.id)))
        with self.assertRaises(ValidationError):
            self.svc.offer(self.w.cara, need, kind="household", title="Iron")

    def test_plugin_on_tick_expires(self):
        from .helpers import ScriptedIO
        from cli.app import CLI
        plugin = NeedRequestsPlugin()
        io = ScriptedIO([])
        cli = CLI(self.w.c, io.input, io.output, plugins=[plugin])
        plugin.menu_entries(cli)                 # binds the plugin to the community
        need = plugin.service.post(self.w.ben, "an iron", 2, 5)
        self.w.clock.advance(25)
        plugin.on_tick(self.w.clock.now())
        self.assertEqual(need.status, NeedStatus.EXPIRED)


if __name__ == "__main__":
    unittest.main()
