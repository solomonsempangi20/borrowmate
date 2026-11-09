"""Plugin: "I Need This" requests (owned by team member 3)."""
from datetime import timedelta
from enum import Enum

from cli.inputs import parse_number
from cli.menu import MenuEntry
from models.enums import Capability
from models.errors import (BorrowMateError, NotFoundError, PermissionDeniedError,
                           ValidationError)
from models.item import ItemFactory
from plugins.base import MenuPlugin
from services.timefmt import fmt_dt


class NeedStatus(Enum):
    OPEN = "Open"
    FULFILLED = "Fulfilled"
    EXPIRED = "Expired"


class OfferStatus(Enum):
    PENDING = "Pending"
    CHOSEN = "Chosen"
    DECLINED = "Declined"


class Offer:
    def __init__(self, offer_id, lender, item=None, kind=None, title=None):
        self.id, self.lender = offer_id, lender
        self.item, self.kind, self.title = item, kind, title   # item=None -> unlisted
        self.status = OfferStatus.PENDING

    def label(self):
        return self.item.title if self.item else f"{self.title} (not listed yet, {self.kind})"


class NeedRequest:
    LIFETIME = timedelta(hours=24)

    def __init__(self, need_id, requester, description, hours, radius_km, created_at):
        self.id, self.requester, self.description = need_id, requester, description
        self.hours, self.radius_km, self.created_at = hours, radius_km, created_at
        self.status = NeedStatus.OPEN
        self.offers = []
        self.notified = []

    @property
    def expires_at(self):
        return self.created_at + self.LIFETIME


class NeedService:
    def __init__(self, community):
        self._c = community
        self._needs = []
        self._n = 0
        self._o = 0

    def all_needs(self):
        return list(self._needs)

    def get(self, need_id):
        for need in self._needs:
            if need.id == need_id:
                return need
        raise NotFoundError(f"Request '{need_id}' was not found.")

    def _in_range(self, person, need):
        return person.hostel.distance_to(need.requester.hostel) <= need.radius_km

    def _tell(self, person, text):
        self._c.notifier.notify(person.id, text, self._c.clock.now())

    def post(self, requester, description, hours, radius_km):
        if not requester.can_borrow() or requester.is_suspended:
            raise PermissionDeniedError("Only active students can post a request.")
        if not str(description).strip():
            raise ValidationError("Say what you need.")
        if hours <= 0 or radius_km <= 0:
            raise ValidationError("Hours and radius must be positive numbers.")
        self._n += 1
        need = NeedRequest(f"N{self._n}", requester, str(description).strip(), hours, radius_km,
                           self._c.clock.now())
        self._needs.append(need)
        for person in self._c.students():
            if person.id != requester.id and not person.is_suspended and self._in_range(person, need):
                need.notified.append(person.id)
                self._tell(person, f"{requester.name} needs '{need.description}' for {hours:g}h "
                                   f"(within {radius_km:g} km). Open 'I need this' to offer help. "
                                   f"Request {need.id}.")
        return need

    def open_needs_for(self, lender):
        now = self._c.clock.now()
        return [n for n in self._needs if n.status is NeedStatus.OPEN and now < n.expires_at
                and n.requester.id != lender.id and self._in_range(lender, n)]

    def needs_of(self, requester):
        return [n for n in self._needs if n.requester.id == requester.id]

    def offer(self, lender, need, item=None, kind=None, title=None):
        if need.status is not NeedStatus.OPEN or self._c.clock.now() >= need.expires_at:
            raise ValidationError("This request is no longer open.")
        if lender.id == need.requester.id:
            raise PermissionDeniedError("You cannot offer on your own request.")
        if not lender.can_borrow() or lender.is_suspended:
            raise PermissionDeniedError("Only active students can offer items.")
        if not self._in_range(lender, need):
            raise PermissionDeniedError("You are outside this request's radius.")
        if any(o.lender.id == lender.id for o in need.offers):
            raise ValidationError("You already made an offer for this request.")
        if item is not None:
            if item.owner.id != lender.id:
                raise PermissionDeniedError("You can only offer your own items.")
            offer = Offer(self._next_offer(), lender, item=item)
        else:
            ItemFactory.create(kind, "TMP", title or "", lender)   # validates kind and title
            offer = Offer(self._next_offer(), lender, kind=kind, title=str(title).strip())
        need.offers.append(offer)
        self._tell(need.requester, f"{lender.name} offered '{offer.label()}' for your request {need.id}.")
        return offer

    def _next_offer(self):
        self._o += 1
        return f"O{self._o}"

    def choose(self, requester, need, offer):
        """Check ALL eligibility rules first, then list the item (if needed) and
        create a confirmed loan. Other offers are declined."""
        if requester.id != need.requester.id:
            raise PermissionDeniedError("Only the person who asked can choose an offer.")
        if need.status is not NeedStatus.OPEN:
            raise ValidationError("This request is no longer open.")
        if offer not in need.offers or offer.status is not OfferStatus.PENDING:
            raise ValidationError("That offer cannot be chosen.")
        c, now = self._c, self._c.clock.now()
        candidate = offer.item or ItemFactory.create(offer.kind, "TMP", offer.title, offer.lender)
        c.loans.check_request(requester, candidate, now, need.hours)        # nothing created yet
        created = offer.item is None
        item = c.add_item(offer.lender, offer.kind, offer.title) if created else offer.item
        try:
            loan = c.request_item(requester, item, now, need.hours)
            c.accept_request(offer.lender, loan)
        except BorrowMateError:
            if created:
                c.items.remove(item.id)
            raise
        offer.status = OfferStatus.CHOSEN
        need.status = NeedStatus.FULFILLED
        for other in need.offers:
            if other is not offer:
                other.status = OfferStatus.DECLINED
                self._tell(other.lender, f"Request {need.id}: {requester.name} chose another offer. Thank you!")
        return loan

    def expire_old(self):
        now = self._c.clock.now()
        expired = [n for n in self._needs if n.status is NeedStatus.OPEN and now >= n.expires_at]
        for need in expired:
            need.status = NeedStatus.EXPIRED
            self._tell(need.requester, f"Your request {need.id} ('{need.description}') expired "
                                       f"after 24 hours with no accepted offer.")
        return expired


class NeedRequestsPlugin(MenuPlugin):
    order = 20

    def __init__(self):
        self._bound = None
        self.service = None

    def _bind(self, community):
        if self._bound is not community:
            self._bound = community
            self.service = NeedService(community)

    def on_tick(self, now):
        if self.service:
            self.service.expire_old()

    def menu_entries(self, cli):
        self._bind(cli.community)
        B, L = Capability.BORROW, Capability.LEND
        return [
            MenuEntry("need_post", "Post an 'I need this' request", lambda: self._post(cli), B, "I need this"),
            MenuEntry("need_mine", "My requests: pick an offer", lambda: self._mine(cli), B, "I need this"),
            MenuEntry("need_help", "Requests near me: make an offer", lambda: self._help(cli), L, "I need this"),
        ]

    def _post(self, cli):
        text = cli.ask("What do you need? ")
        hours = parse_number(cli.ask("For how many hours? "), "the hours")
        radius = parse_number(cli.ask("Within how many km? "), "the radius")
        need = self.service.post(cli.user, text, hours, radius)
        cli.say(f"Request {need.id} posted. {len(need.notified)} student(s) in range were notified. "
                f"It expires {fmt_dt(need.expires_at)}.")

    def _help(self, cli):
        needs = self.service.open_needs_for(cli.user)
        cli.show_table(["Req", "Who", "Needs", "Hours", "Expires"],
                       [[n.id, n.requester.name, n.description, f"{n.hours:g}", fmt_dt(n.expires_at)]
                        for n in needs], "Open requests in my range")
        if not needs:
            return
        need = self.service.get(cli.ask("Request id: ").upper())
        item_id = cli.ask("Offer one of your listed items? Item id (blank = offer an unlisted item): ").upper()
        if item_id:
            offer = self.service.offer(cli.user, need, item=cli.community.items.get(item_id))
        else:
            kind = cli.ask(f"Kind ({'/'.join(ItemFactory.kinds())}): ")
            offer = self.service.offer(cli.user, need, kind=kind, title=cli.ask("Item title: "))
        cli.say(f"Offer {offer.id} sent to {need.requester.name}.")

    def _mine(self, cli):
        mine = [n for n in self.service.needs_of(cli.user)]
        cli.show_table(["Req", "Needs", "Hours", "Status", "Offers"],
                       [[n.id, n.description, f"{n.hours:g}", n.status.value, len(n.offers)] for n in mine],
                       "My requests")
        open_ones = [n for n in mine if n.status is NeedStatus.OPEN and n.offers]
        if not open_ones:
            return
        need = self.service.get(cli.ask("Request id: ").upper())
        cli.show_table(["Offer", "From", "Item", "Status"],
                       [[o.id, o.lender.name, o.label(), o.status.value] for o in need.offers], "Offers")
        wanted = cli.ask("Offer id to accept: ").upper()
        offer = next((o for o in need.offers if o.id == wanted), None)
        if offer is None:
            raise NotFoundError(f"Offer '{wanted}' was not found.")
        loan = self.service.choose(cli.user, need, offer)
        cli.say(f"Done! Loan {loan.id} is confirmed with {offer.lender.name}. "
                f"They will hand over '{loan.item.title}' (due {fmt_dt(loan.due)}).")
