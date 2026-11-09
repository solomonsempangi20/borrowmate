"""Enums: every status in BorrowMate is an Enum, never a bare string."""
from enum import Enum, IntEnum

from models.errors import ValidationError


class Condition(Enum):
    NEW = "New"
    GOOD = "Good"
    FAIR = "Fair"
    DAMAGED = "Damaged"


class ItemStatus(Enum):
    AVAILABLE = "Available"
    ON_LOAN = "On loan"
    PAUSED = "Paused"
    REMOVED = "Removed"


class LoanStatus(Enum):
    REQUESTED = "Requested"
    ACCEPTED = "Accepted"
    HANDED_OVER = "Handed over"
    RETURNED = "Returned"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"
    OVERDUE = "Overdue"
    DISPUTED = "Disputed"


class UserStatus(Enum):
    ACTIVE = "Active"
    SUSPENDED = "Suspended"


class ValueTier(IntEnum):
    """Ordered so that LOW < MEDIUM < HIGH can be compared directly."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class ConflictSeverity(Enum):
    BLOCKED = "BLOCKED"      # a new request hits a confirmed booking: refused
    COMPETING = "COMPETING"  # two pending requests overlap: allowed, reported
    CLASH = "CLASH"          # two confirmed bookings overlap: must never happen


class Capability(Enum):
    """What a person may do. The CLI menu is built from these, so it never
    needs to compare role strings."""
    VIEW = "view"
    BORROW = "borrow"
    LEND = "lend"
    MODERATE = "moderate"


def parse_enum(enum_cls, text):
    """Turn user text ('damaged', 'On loan', 'low') into an enum member."""
    wanted = str(text).strip().lower().replace(" ", "_")
    for member in enum_cls:
        names = (member.name.lower(), str(member.value).lower().replace(" ", "_"))
        if wanted in names:
            return member
    choices = ", ".join(m.name.lower() for m in enum_cls)
    raise ValidationError(f"'{text}' is not valid. Choose one of: {choices}.")
