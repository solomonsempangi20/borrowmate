"""Loan: a state machine. Every move goes through one transition table."""
from models.enums import LoanStatus as S
from models.errors import InvalidTransitionError, ValidationError


class Loan:
    TRANSITIONS = {
        S.REQUESTED: {S.ACCEPTED, S.DECLINED, S.CANCELLED},
        S.ACCEPTED: {S.HANDED_OVER, S.CANCELLED},
        S.HANDED_OVER: {S.RETURNED, S.OVERDUE, S.DISPUTED},
        S.OVERDUE: {S.RETURNED, S.HANDED_OVER, S.DISPUTED},  # HANDED_OVER = extended
        S.DISPUTED: {S.RETURNED},
        S.RETURNED: set(),
        S.DECLINED: set(),
        S.CANCELLED: set(),
    }
    CONFIRMED_STATES = frozenset({S.ACCEPTED, S.HANDED_OVER, S.OVERDUE, S.DISPUTED})
    HOLDING_STATES = frozenset({S.HANDED_OVER, S.OVERDUE, S.DISPUTED})  # borrower has the item

    def __init__(self, loan_id, item, borrower, start, due, requested_at):
        if due <= start:
            raise ValidationError("A loan must end after it starts.")
        self._id = loan_id
        self._item = item
        self._borrower = borrower
        self._start = start
        self._due = due
        self._requested_at = requested_at
        self._status = S.REQUESTED
        self._handover_time = None
        self._return_time = None
        self._condition_out = None
        self._condition_in = None
        self._dispute_reason = None

    # --- read-only properties ---
    id = property(lambda self: self._id)
    item = property(lambda self: self._item)
    borrower = property(lambda self: self._borrower)
    owner = property(lambda self: self._item.owner)
    start = property(lambda self: self._start)
    due = property(lambda self: self._due)
    requested_at = property(lambda self: self._requested_at)
    status = property(lambda self: self._status)
    handover_time = property(lambda self: self._handover_time)
    return_time = property(lambda self: self._return_time)
    condition_out = property(lambda self: self._condition_out)
    condition_in = property(lambda self: self._condition_in)
    dispute_reason = property(lambda self: self._dispute_reason)

    @property
    def hours(self):
        return (self._due - self._start).total_seconds() / 3600

    @property
    def is_confirmed(self):
        return self._status in self.CONFIRMED_STATES

    @property
    def is_pending(self):
        return self._status is S.REQUESTED

    @property
    def is_holding(self):
        return self._status in self.HOLDING_STATES

    @property
    def was_on_time(self):
        if self._return_time is None:
            return None
        return self._return_time <= self._due

    # --- state machine ---
    def can_move_to(self, new_status):
        return new_status in self.TRANSITIONS[self._status]

    def ensure_can_move_to(self, new_status):
        if not self.can_move_to(new_status):
            raise InvalidTransitionError(
                f"Loan {self._id} cannot go from {self._status.value} to {new_status.value}.")

    def _move(self, new_status):
        self.ensure_can_move_to(new_status)
        self._status = new_status

    def accept(self):
        self._move(S.ACCEPTED)

    def decline(self):
        self._move(S.DECLINED)

    def cancel(self):
        self._move(S.CANCELLED)

    def hand_over(self, now, condition_out):
        self._move(S.HANDED_OVER)
        self._handover_time = now
        self._condition_out = condition_out

    def mark_overdue(self):
        self._move(S.OVERDUE)

    def dispute(self, reason):
        self._move(S.DISPUTED)
        self._dispute_reason = reason

    def mark_returned(self, now, condition_in):
        """Returns True when the item came back on time."""
        self._move(S.RETURNED)
        self._return_time = now
        self._condition_in = condition_in
        return self.was_on_time

    def extend_to(self, new_due):
        """Push the due time later. An overdue loan becomes HANDED_OVER again."""
        if self._status not in (S.HANDED_OVER, S.OVERDUE):
            raise InvalidTransitionError("Only a loan the borrower holds can be extended.")
        if new_due <= self._due:
            raise ValidationError("The new due time must be later than the old one.")
        if self._status is S.OVERDUE:
            self._move(S.HANDED_OVER)
        self._due = new_due

    def overlaps(self, other):
        """Same item and overlapping windows. Back-to-back is NOT an overlap."""
        return (other is not self
                and self._item.id == other.item.id
                and self._start < other.due and other.start < self._due)

    def __repr__(self):
        return f"Loan({self._id!r}, {self._item.title!r}, {self._status.value})"
