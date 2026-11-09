"""People. Person is abstract; Student and Admin give different answers to the
same questions (polymorphism)."""
from abc import ABC, abstractmethod

from models.enums import Capability, UserStatus, ValueTier
from models.errors import PermissionDeniedError, ValidationError


class Person(ABC):
    def __init__(self, user_id, name, hostel):
        if not str(user_id).strip() or not str(name).strip():
            raise ValidationError("A person needs an id and a name.")
        self._id = str(user_id).strip()
        self._name = str(name).strip()
        self._hostel = hostel
        self._status = UserStatus.ACTIVE

    # --- read-only properties (encapsulation) ---
    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def hostel(self):
        return self._hostel

    @property
    def status(self):
        return self._status

    @property
    def is_suspended(self):
        return self._status is UserStatus.SUSPENDED

    # --- the only way to change status ---
    def set_suspended(self, suspended, by):
        if not by.can_moderate():
            raise PermissionDeniedError("Only an admin can suspend or restore users.")
        self._status = UserStatus.SUSPENDED if suspended else UserStatus.ACTIVE

    # --- polymorphic behaviour every subclass must define ---
    @abstractmethod
    def role(self):
        """Human readable role name."""

    @abstractmethod
    def can_moderate(self):
        """May this person view disputes and suspend users?"""

    @abstractmethod
    def can_borrow(self):
        """May this person borrow items at all?"""

    @abstractmethod
    def max_active_loans(self):
        """How many loans may be active at once."""

    @abstractmethod
    def max_value_tier(self):
        """Highest ValueTier this person may borrow (None = cannot borrow)."""

    @abstractmethod
    def capabilities(self):
        """Set of Capability values; the CLI builds its menu from these."""

    def __repr__(self):
        return f"{type(self).__name__}({self._id!r}, {self._name!r})"


class Student(Person):
    START_SCORE = 3.0

    def __init__(self, user_id, name, hostel, reliability=START_SCORE,
                 completed_loans=0, late_returns=0):
        super().__init__(user_id, name, hostel)
        self._reliability = self._clamp(reliability)
        self._completed_loans = int(completed_loans)
        self._late_returns = int(late_returns)

    @staticmethod
    def _clamp(value):
        return round(max(0.0, min(5.0, float(value))), 2)

    @property
    def reliability(self):
        return self._reliability

    @property
    def completed_loans(self):
        return self._completed_loans

    @property
    def late_returns(self):
        return self._late_returns

    def record_return(self, on_time):
        """+0.2 for an on-time return, -0.5 for a late one (clamped 0-5)."""
        self._completed_loans += 1
        if on_time:
            self._reliability = self._clamp(self._reliability + 0.2)
        else:
            self._late_returns += 1
            self._reliability = self._clamp(self._reliability - 0.5)

    # --- polymorphic answers ---
    def role(self):
        return "Student"

    def can_moderate(self):
        return False

    def can_borrow(self):
        return True

    def max_active_loans(self):
        return 3 if self._completed_loans >= 2 else 1

    def max_value_tier(self):
        """Trust ladder: LOW -> MEDIUM -> HIGH."""
        if self._reliability >= 4.0 and self._completed_loans >= 5:
            return ValueTier.HIGH
        if self._reliability >= 3.0 and self._completed_loans >= 2:
            return ValueTier.MEDIUM
        return ValueTier.LOW

    def capabilities(self):
        return frozenset({Capability.VIEW, Capability.BORROW, Capability.LEND})


class Admin(Person):
    def role(self):
        return "Admin"

    def can_moderate(self):
        return True

    def can_borrow(self):
        return False

    def max_active_loans(self):
        return 0

    def max_value_tier(self):
        return None

    def capabilities(self):
        return frozenset({Capability.VIEW, Capability.MODERATE})
