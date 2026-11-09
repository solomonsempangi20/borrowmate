"""Plugin: loan extensions and ratings (owned by team member 2)."""
from enum import Enum

from cli.inputs import parse_number
from cli.menu import MenuEntry
from models.enums import Capability, LoanStatus
from models.errors import (ConflictError, NotFoundError, PermissionDeniedError,
                           ValidationError)
from plugins.base import MenuPlugin
from services.timefmt import fmt_dt
from datetime import timedelta


class ExtensionStatus(Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    DECLINED = "Declined"


class ExtensionRequest:
    def __init__(self, ext_id, loan, hours, requested_at):
        self._id, self._loan, self._hours = ext_id, loan, hours
        self._requested_at = requested_at
        self._status = ExtensionStatus.PENDING

    id = property(lambda self: self._id)
    loan = property(lambda self: self._loan)
    hours = property(lambda self: self._hours)
    requested_at = property(lambda self: self._requested_at)
    status = property(lambda self: self._status)

    def decide(self, approved):
        """A request can be decided exactly once."""
        if self._status is not ExtensionStatus.PENDING:
            raise ValidationError("This extension request was already decided.")
        self._status = ExtensionStatus.APPROVED if approved else ExtensionStatus.DECLINED


class ExtensionService:
    MIN_HOURS, MAX_HOURS = 1, 24

    def __init__(self, community):
        self._c = community
        self._requests = []
        self._counter = 0

    def all_requests(self):
        return list(self._requests)

    def get(self, ext_id):
        for req in self._requests:
            if req.id == ext_id:
                return req
        raise NotFoundError(f"Extension request '{ext_id}' was not found.")

    def pending_for(self, owner):
        return [r for r in self._requests
                if r.status is ExtensionStatus.PENDING and r.loan.owner.id == owner.id]

    def request(self, borrower, loan, hours):
        if borrower.id != loan.borrower.id:
            raise PermissionDeniedError("Only the borrower can ask for an extension.")
        if loan.status not in (LoanStatus.HANDED_OVER, LoanStatus.OVERDUE):
            raise ValidationError("You can only extend a loan you are currently holding.")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) \
                or not self.MIN_HOURS <= hours <= self.MAX_HOURS:
            raise ValidationError(f"Ask for between {self.MIN_HOURS} and {self.MAX_HOURS} extra hours.")
        if any(r.loan.id == loan.id for r in self._requests):
            raise ValidationError("This loan already had an extension request (one per loan).")
        self._counter += 1
        req = ExtensionRequest(f"E{self._counter}", loan, hours, self._c.clock.now())
        self._requests.append(req)
        self._c.notifier.notify(loan.owner.id, f"{borrower.name} asks for {hours:g} more hour(s) on "
                                f"'{loan.item.title}'. Extension {req.id}.", self._c.clock.now())
        return req

    def decide(self, owner, req, approve):
        loan = req.loan
        if owner.id != loan.owner.id:
            raise PermissionDeniedError("Only the item's owner can decide on an extension.")
        if req.status is not ExtensionStatus.PENDING:
            raise ValidationError("This extension request was already decided.")
        now = self._c.clock.now()
        if approve:
            new_due = max(loan.due, now) + timedelta(hours=req.hours)
            for other in self._c.loans.confirmed_for_item(loan.item, exclude=loan):
                if other.start < new_due and other.due > loan.due:
                    raise ConflictError(f"Cannot extend: the next booking starts {fmt_dt(other.start)}.")
            loan.extend_to(new_due)   # also clears Overdue
            req.decide(True)
            msg = f"Extension approved. New due time: {fmt_dt(new_due)}."
        else:
            req.decide(False)
            msg = "Extension declined. The original due time stands."
        self._c.notifier.notify(loan.borrower.id, f"'{loan.item.title}': {msg}", now)
        return req


class RatingBook:
    """Each side may rate the other once per returned loan (1-5 stars)."""

    def __init__(self, community):
        self._c = community
        self._ratings = {}   # (loan_id, rater_id) -> (ratee_id, stars)

    def rate(self, rater, loan, stars):
        if loan.status is not LoanStatus.RETURNED:
            raise ValidationError("You can rate only after the item has been returned.")
        if rater.id == loan.borrower.id:
            ratee = loan.owner
        elif rater.id == loan.owner.id:
            ratee = loan.borrower
        else:
            raise PermissionDeniedError("Only the two people in the loan can rate each other.")
        if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
            raise ValidationError("Stars must be a whole number from 1 to 5.")
        key = (loan.id, rater.id)
        if key in self._ratings:
            raise ValidationError("You already rated this loan.")
        self._ratings[key] = (ratee.id, stars)
        self._c.notifier.notify(ratee.id, f"{rater.name} gave you {stars} star(s) for '{loan.item.title}'.",
                                self._c.clock.now())

    def average(self, user):
        """(average, count) or None when the user has no ratings yet."""
        stars = [s for (ratee, s) in self._ratings.values() if ratee == user.id]
        return (sum(stars) / len(stars), len(stars)) if stars else None


class ExtensionsPlugin(MenuPlugin):
    order = 10

    def __init__(self):
        self._bound = None
        self.extensions = None
        self.ratings = None

    def _bind(self, community):
        if self._bound is not community:
            self._bound = community
            self.extensions = ExtensionService(community)
            self.ratings = RatingBook(community)

    def menu_entries(self, cli):
        self._bind(cli.community)
        B, L, V = Capability.BORROW, Capability.LEND, Capability.VIEW
        return [
            MenuEntry("ext_ask", "Ask for extra time on a loan", lambda: self._ask(cli), B, "Extensions & ratings"),
            MenuEntry("ext_decide", "Approve / decline an extension", lambda: self._decide(cli), L, "Extensions & ratings"),
            MenuEntry("rate", "Rate someone after a return", lambda: self._rate(cli), B, "Extensions & ratings"),
            MenuEntry("rating", "View a user's average rating", lambda: self._view(cli), V, "Extensions & ratings"),
        ]

    def _ask(self, cli):
        mine = [l for l in cli.community.loans.all_loans()
                if l.borrower.id == cli.user.id and l.is_holding]
        cli.show_table(["Loan", "Item", "Due", "Status"],
                       [[l.id, l.item.title, fmt_dt(l.due), l.status.value] for l in mine], "Loans I hold")
        if not mine:
            return
        loan = cli.community.loans.get(cli.ask("Loan id: ").upper())
        hours = parse_number(cli.ask("Extra hours (1-24): "), "the extra hours")
        req = self.extensions.request(cli.user, loan, hours)
        cli.say(f"Extension {req.id} sent to {loan.owner.name}.")

    def _decide(self, cli):
        pending = self.extensions.pending_for(cli.user)
        cli.show_table(["Ext", "Loan", "Item", "Borrower", "Extra hours"],
                       [[r.id, r.loan.id, r.loan.item.title, r.loan.borrower.name, f"{r.hours:g}"]
                        for r in pending], "Extension requests for my items")
        if not pending:
            return
        req = self.extensions.get(cli.ask("Extension id: ").upper())
        answer = cli.ask("Approve? (y/n): ").lower()
        if answer not in ("y", "n"):
            raise ValidationError("Please answer y or n.")
        self.extensions.decide(cli.user, req, answer == "y")
        cli.say(f"Extension {req.id} {req.status.value.lower()}.")

    def _rate(self, cli):
        done = [l for l in cli.community.loans.loans_of(cli.user) if l.status is LoanStatus.RETURNED]
        cli.show_table(["Loan", "Item", "Borrower", "Owner"],
                       [[l.id, l.item.title, l.borrower.name, l.owner.name] for l in done], "Returned loans")
        if not done:
            return
        loan = cli.community.loans.get(cli.ask("Loan id: ").upper())
        stars = cli.ask("Stars (1-5): ")
        if not stars.isdigit():
            raise ValidationError("Stars must be a whole number from 1 to 5.")
        self.ratings.rate(cli.user, loan, int(stars))
        cli.say("Thanks for your rating!")

    def _view(self, cli):
        user = cli.community.users.get(cli.ask("User id: ").upper())
        result = self.ratings.average(user)
        cli.say("No ratings yet." if result is None
                else f"{user.name}: {result[0]:.1f} stars from {result[1]} rating(s).")
