"""Clock abstraction so the demo and the tests can move time forward."""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from models.errors import ValidationError


class Clock(ABC):
    @abstractmethod
    def now(self):
        """Current datetime."""

    def advance(self, hours):
        raise ValidationError("This clock cannot be moved.")


class SystemClock(Clock):
    def now(self):
        return datetime.now().replace(microsecond=0)


class SimulatedClock(Clock):
    def __init__(self, start=None):
        self._now = start or datetime(2025, 3, 10, 9, 0)

    def now(self):
        return self._now

    def advance(self, hours):
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0:
            raise ValidationError("Hours to advance must be a positive number.")
        self._now += timedelta(hours=hours)
        return self._now
