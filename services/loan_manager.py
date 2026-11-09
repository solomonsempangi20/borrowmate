"""LoanManager: all borrowing rules live here (eligibility, conflicts,
accountability, overdue handling, notifications)."""
import math
from dataclasses import dataclass
from datetime import timedelta

from models.enums import ConflictSeverity, Condition, ItemStatus, LoanStatus
from models.errors import (ConflictError, EligibilityError, PermissionDeniedError,
                           ValidationError)
from models.loan import Loan
from services.repository import Repository
from services.timefmt import fmt_dt


@dataclass
class Conflict:
    severity: ConflictSeverity
    item: object
    first: Loan
    second: Loan
    note: str


class LoanManager:
    def __init__(self, clock, notifier):
        self._clock = clock
        self._notifier = notifier
        self._loans = Repository(lambda loan: loan.id, "Loan")

    # ------------------------------------------------------------ queries
    def get(self, loan_id):
        return self._loans.get(loan_id)

    def all_loans(self):
        return self._loans.all()

    def loans_for_item(self, item):
        return self._loans.find(lambda l: l.item.id == item.id)

    def loans_of(self, person):
        return self._loans.find(lambda l: person.id in (l.borrower.id, l.owner.id))

    def confirmed_for_item(self, item, exclude=None):
        return sorted((l for l in self.loans_for_item(item)
                       if l.is_confirmed and l is not exclude), key=lambda l: l.start)

    def pending_for_item(self, item):
        return [l for l in self.loans_for_item(item) if l.is_pending]

    def current_loan(self, item):
        """The loan in which the borrower is holding the item right now."""
        for loan in self.loans_for_item(item):
            if loan.is_holding:
                return loan
        return None

    def upcoming_bookings(self, item):
        return [l for l in self.confirmed_for_item(item)
                if l.status is LoanStatus.ACCEPTED and l.due > self._clock.now()]

    def active_count(self, student):
        return len(self._loans.find(
            lambda l: l.borrower.id == student.id and l.is_confirmed))

    def has_overdue(self, student):
        return any(l.borrower.id == student.id and l.status is LoanStatus.OVERDUE
                   for l in self._loans.all())

    def competing_with(self, loan):
        """Other pending requests whose time window overlaps this pending one."""
        if not loan.is_pending:
            return []
        return [o for o in self.pending_for_item(loan.item) if loan.overlaps(o)]

    # -------------------------------------------------------- eligibility
    def eligibility_problem(self, borrower, item, start, hours):
        """Return the reason a borrower is refused, or None when allowed."""
        now = self._clock.now()
        if not borrower.can_borrow():
            return "Only students can borrow items."
        if borrower.is_suspended:
            return "Your account is suspended."
        if item.owner.id == borrower.id:
            return "You cannot borrow your own item."
        if item.status in (ItemStatus.PAUSED, ItemStatus.REMOVED):
            return f"'{item.title}' is {item.status.value.lower()} and cannot be borrowed now."
        if self.has_overdue(borrower):
            return "You have an overdue loan. Return it first."
        limit = borrower.max_active_loans()
        if self.active_count(borrower) >= limit:
            return f"You already have {limit} active loan(s), which is your limit right now."
        tier = borrower.max_value_tier()
        if item.value_tier() > tier:
            return (f"'{item.title}' is a {item.value_tier().name} value item; your trust level "
                    f"only allows up to {tier.name}.")
        if start < now:
            return "The start time is in the past."
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) \
                or not math.isfinite(hours) or hours <= 0:
            return "Hours must be a positive number."
        if hours > item.max_hours:
            return f"'{item.title}' can be borrowed for at most {item.max_hours:g} hours."
        return None

    def check_eligibility(self, borrower, item, start, hours):
        problem = self.eligibility_problem(borrower, item, start, hours)
        if problem:
            raise EligibilityError(problem)

    def free_from(self, item, start, hours):
        """Earliest time (>= start) when a window of this length is free."""
        span = timedelta(hours=hours)
        t = start
        confirmed = self.confirmed_for_item(item)
        changed = True
        while changed:
            changed = False
            for other in confirmed:
                if other.start < t + span and t < other.due:
                    t = other.due
                    changed = True
        return t

    def check_no_blocking(self, item, start, hours):
        end = start + timedelta(hours=hours)
        for other in self.confirmed_for_item(item):
            if other.start < end and start < other.due:
                free = self.free_from(item, start, hours)
                raise ConflictError(
                    f"BLOCKED: '{item.title}' is already booked for that time. "
                    f"It is free from {fmt_dt(free)}.", ConflictSeverity.BLOCKED)

    def check_request(self, borrower, item, start, hours):
        self.check_eligibility(borrower, item, start, hours)
        self.check_no_blocking(item, start, hours)

    # ------------------------------------------------------------ actions
    def _tell(self, person, message):
        self._notifier.notify(person.id, message, self._clock.now())

    @staticmethod
    def _require_owner(user, loan, action):
        if user.id != loan.owner.id:
            raise PermissionDeniedError(f"Only the item's owner can {action}.")

    def request(self, borrower, item, start, hours):
        self.check_request(borrower, item, start, hours)
        due = start + timedelta(hours=hours)
        loan = Loan(self._loans.next_id("L"), item, borrower, start, due, self._clock.now())
        self._loans.add(loan)
        self._tell(item.owner, f"{borrower.name} requested '{item.title}' "
                               f"({fmt_dt(start)} to {fmt_dt(due)}). Loan {loan.id}.")
        return loan

    def accept(self, owner, loan):
        self._require_owner(owner, loan, "accept a request")
        loan.ensure_can_move_to(LoanStatus.ACCEPTED)
        borrower = loan.borrower
        if borrower.is_suspended:
            raise EligibilityError(f"{borrower.name} is suspended and cannot borrow.")
        if self.active_count(borrower) >= borrower.max_active_loans():
            raise EligibilityError(f"{borrower.name} has reached the active-loan limit.")
        if any(loan.overlaps(o) for o in self.confirmed_for_item(loan.item, exclude=loan)):
            raise ConflictError("CLASH: this overlaps a confirmed booking.", ConflictSeverity.CLASH)
        loan.accept()
        for rival in [o for o in self.pending_for_item(loan.item) if loan.overlaps(o)]:
            rival.decline()
            self._tell(rival.borrower, f"Your request {rival.id} for '{rival.item.title}' was "
                                       f"declined automatically: the item was booked by someone else.")
        self._tell(borrower, f"{owner.name} accepted your request for '{loan.item.title}' "
                             f"({fmt_dt(loan.start)} to {fmt_dt(loan.due)}).")
        return loan

    def decline(self, owner, loan, reason=""):
        self._require_owner(owner, loan, "decline a request")
        loan.decline()
        extra = f" Reason: {reason}" if reason else ""
        self._tell(loan.borrower, f"{owner.name} declined your request for '{loan.item.title}'.{extra}")
        return loan

    def cancel(self, user, loan):
        if user.id != loan.borrower.id:
            raise PermissionDeniedError("Only the borrower can cancel a request.")
        loan.cancel()
        self._tell(loan.owner, f"{user.name} cancelled the booking for '{loan.item.title}'.")
        return loan

    def hand_over(self, owner, loan, condition_out=None):
        self._require_owner(owner, loan, "hand over the item")
        loan.ensure_can_move_to(LoanStatus.HANDED_OVER)
        now = self._clock.now()
        if now < loan.start:
            raise ValidationError(f"Too early: this booking starts at {fmt_dt(loan.start)}.")
        item = loan.item
        if item.status is not ItemStatus.AVAILABLE:
            raise ConflictError(f"'{item.title}' is {item.status.value.lower()} and cannot be handed over.")
        item.mark_on_loan()
        loan.hand_over(now, condition_out or item.condition)
        self._tell(loan.borrower, f"You now have '{item.title}'. Return it by {fmt_dt(loan.due)}.")
        return loan

    def confirm_return(self, owner, loan, condition_in):
        """Only the owner can confirm, so a borrower cannot fake a return."""
        self._require_owner(owner, loan, "confirm a return")
        if not isinstance(condition_in, Condition):
            raise ValidationError("Please state the item's condition on return.")
        loan.ensure_can_move_to(LoanStatus.RETURNED)
        on_time = loan.mark_returned(self._clock.now(), condition_in)
        loan.item.mark_available()
        loan.item.set_condition(condition_in)
        loan.borrower.record_return(on_time)
        verdict = "on time" if on_time else "LATE"
        self._tell(loan.borrower, f"Return of '{loan.item.title}' confirmed ({verdict}). "
                                  f"Your reliability is now {loan.borrower.reliability:.1f}.")
        self._tell(owner, f"You confirmed the return of '{loan.item.title}' ({verdict}).")
        return loan

    def report_problem(self, user, loan, reason):
        if user.id not in (loan.borrower.id, loan.owner.id):
            raise PermissionDeniedError("Only the borrower or the owner can report a problem.")
        if not str(reason).strip():
            raise ValidationError("Please describe the problem.")
        loan.dispute(str(reason).strip())
        other = loan.owner if user.id == loan.borrower.id else loan.borrower
        self._tell(other, f"{user.name} reported a problem with '{loan.item.title}': {loan.dispute_reason}")
        return loan

    def check_overdue(self):
        """Loans past due become Overdue; both people are told."""
        now = self._clock.now()
        found = []
        for loan in self._loans.all():
            if loan.status is LoanStatus.HANDED_OVER and loan.due < now:
                loan.mark_overdue()
                self._tell(loan.borrower, f"OVERDUE: please return '{loan.item.title}' to {loan.owner.name}.")
                self._tell(loan.owner, f"OVERDUE: {loan.borrower.name} has not returned '{loan.item.title}'.")
                found.append(loan)
        return found

    # ---------------------------------------------------------- conflicts
    def conflicts(self):
        """Report overlapping open loans with a severity."""
        report = []
        open_loans = [l for l in self._loans.all() if l.is_pending or l.is_confirmed]
        for i, a in enumerate(open_loans):
            for b in open_loans[i + 1:]:
                if not a.overlaps(b):
                    continue
                if a.is_confirmed and b.is_confirmed:
                    sev, note = ConflictSeverity.CLASH, "Two confirmed bookings overlap!"
                elif a.is_pending and b.is_pending:
                    sev, note = ConflictSeverity.COMPETING, "Owner can accept only one."
                else:
                    sev, note = ConflictSeverity.BLOCKED, "A request overlaps a confirmed booking."
                report.append(Conflict(sev, a.item, a, b, note))
        return report
