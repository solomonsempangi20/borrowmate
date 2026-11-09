"""Items. Item is abstract; Electronics, Book and HouseholdItem extend it."""
from abc import ABC, abstractmethod

from models.enums import Capability, Condition, ItemStatus, ValueTier
from models.errors import InvalidTransitionError, ValidationError


class Item(ABC):
    def __init__(self, item_id, title, owner, condition=Condition.GOOD,
                 max_hours=None, tier=None):
        if not str(title).strip():
            raise ValidationError("An item needs a title.")
        if Capability.LEND not in owner.capabilities():
            raise ValidationError("Only students can own items.")
        if max_hours is not None and max_hours <= 0:
            raise ValidationError("Maximum borrowing hours must be positive.")
        self._id = str(item_id)
        self._title = str(title).strip()
        self._owner = owner
        self._condition = condition
        self._status = ItemStatus.AVAILABLE
        self._max_hours = max_hours
        self._tier = tier

    @property
    def id(self):
        return self._id

    @property
    def title(self):
        return self._title

    @property
    def owner(self):
        return self._owner

    @property
    def condition(self):
        return self._condition

    @property
    def status(self):
        return self._status

    @property
    def max_hours(self):
        return self._max_hours if self._max_hours is not None else self.default_max_hours()

    # --- polymorphic behaviour ---
    @abstractmethod
    def category(self):
        """Category name shown in tables."""

    @abstractmethod
    def value_tier(self):
        """ValueTier used by the trust ladder."""

    @abstractmethod
    def default_max_hours(self):
        """Longest allowed loan when the owner did not choose a limit."""

    @abstractmethod
    def details(self):
        """One-line description specific to the subclass."""

    def _tier_or(self, default):
        return self._tier if self._tier is not None else default

    # --- state changes: only through methods that enforce the rules ---
    def pause(self):
        if self._status is ItemStatus.ON_LOAN:
            raise InvalidTransitionError("An item on loan cannot be paused.")
        if self._status is ItemStatus.REMOVED:
            raise InvalidTransitionError("A removed item cannot be paused.")
        self._status = ItemStatus.PAUSED

    def resume(self):
        if self._status is not ItemStatus.PAUSED:
            raise InvalidTransitionError("Only a paused item can be resumed.")
        self._status = ItemStatus.AVAILABLE

    def mark_on_loan(self):
        if self._status is not ItemStatus.AVAILABLE:
            raise InvalidTransitionError(f"'{self._title}' is {self._status.value}, not available.")
        self._status = ItemStatus.ON_LOAN

    def mark_available(self):
        if self._status is not ItemStatus.ON_LOAN:
            raise InvalidTransitionError(f"'{self._title}' is not on loan.")
        self._status = ItemStatus.AVAILABLE

    def remove(self):
        if self._status is ItemStatus.ON_LOAN:
            raise InvalidTransitionError("An item on loan cannot be removed.")
        self._status = ItemStatus.REMOVED

    def set_condition(self, condition):
        if not isinstance(condition, Condition):
            raise ValidationError("Condition must be a Condition value.")
        self._condition = condition

    def __repr__(self):
        return f"{type(self).__name__}({self._id!r}, {self._title!r})"


class Electronics(Item):
    def __init__(self, item_id, title, owner, brand="", **kwargs):
        super().__init__(item_id, title, owner, **kwargs)
        self._brand = brand

    def category(self):
        return "Electronics"

    def value_tier(self):
        return self._tier_or(ValueTier.MEDIUM)

    def default_max_hours(self):
        return 24

    def details(self):
        brand = f"{self._brand}, " if self._brand else ""
        return f"Electronics: {brand}{self.value_tier().name} value, max {self.max_hours:g}h"


class Book(Item):
    def __init__(self, item_id, title, owner, author="", **kwargs):
        super().__init__(item_id, title, owner, **kwargs)
        self._author = author

    def category(self):
        return "Book"

    def value_tier(self):
        return self._tier_or(ValueTier.LOW)

    def default_max_hours(self):
        return 72

    def details(self):
        by = f" by {self._author}" if self._author else ""
        return f"Book{by}, max {self.max_hours:g}h"


class HouseholdItem(Item):
    def __init__(self, item_id, title, owner, note="", **kwargs):
        super().__init__(item_id, title, owner, **kwargs)
        self._note = note

    def category(self):
        return "Household"

    def value_tier(self):
        return self._tier_or(ValueTier.LOW)

    def default_max_hours(self):
        return 6

    def details(self):
        note = f" ({self._note})" if self._note else ""
        return f"Household item{note}, max {self.max_hours:g}h"


class ItemFactory:
    """Factory: create the right Item subclass from a short kind name."""
    _KINDS = {"electronics": Electronics, "book": Book, "household": HouseholdItem}

    @classmethod
    def kinds(cls):
        return list(cls._KINDS)

    @classmethod
    def create(cls, kind, item_id, title, owner, **kwargs):
        try:
            item_cls = cls._KINDS[str(kind).strip().lower()]
        except KeyError:
            raise ValidationError(
                f"Unknown item kind '{kind}'. Choose: {', '.join(cls._KINDS)}.") from None
        return item_cls(item_id, title, owner, **kwargs)
