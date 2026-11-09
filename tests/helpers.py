"""Shared test fixtures: a small, predictable world (not the demo seed)."""
from datetime import datetime, timedelta

from models.enums import Condition, ValueTier
from models.hostel import Hostel
from services.clock import SimulatedClock
from services.community import Community
from services.notifier import InAppNotifier

T0 = datetime(2025, 3, 10, 9, 0)


class World:
    """Amina: veteran (HIGH). Cara: mid (MEDIUM). Ben & Dan: brand new (LOW)."""

    def __init__(self):
        self.clock = SimulatedClock(T0)
        self.notifier = InAppNotifier()
        self.c = Community(self.clock, self.notifier)
        self.c.add_hostel(Hostel("North", 0.3000, 32.5000))
        self.c.add_hostel(Hostel("East", 0.3000, 32.5100))    # about 1.1 km from North
        self.c.add_hostel(Hostel("Far", 0.4000, 32.6000))     # about 15 km from North
        self.amina = self.c.add_student("Amina", "North", reliability=4.5, completed_loans=6)
        self.cara = self.c.add_student("Cara", "East", reliability=3.4, completed_loans=3)
        self.ben = self.c.add_student("Ben", "North")
        self.dan = self.c.add_student("Dan", "Far")
        self.admin = self.c.add_admin("Grace", "North")
        self.laptop = self.c.add_item(self.amina, "electronics", "Laptop", tier=ValueTier.HIGH)
        self.calc = self.c.add_item(self.amina, "electronics", "Calculator")        # MEDIUM
        self.iron = self.c.add_item(self.amina, "household", "Iron")                # LOW, 6h
        self.novel = self.c.add_item(self.cara, "book", "Novel")                    # LOW, 72h

    def at(self, hours):
        return T0 + timedelta(hours=hours)

    def lend(self, owner, borrower, item, start_h=0, hours=2, hand_over=True):
        """Request + accept (+ hand over) in one call."""
        loan = self.c.request_item(borrower, item, self.at(start_h), hours)
        self.c.accept_request(owner, loan)
        if hand_over:
            self.c.hand_over(owner, loan, Condition.GOOD)
        return loan


class ScriptedIO:
    """Injected CLI input/output: feeds scripted answers, records everything shown."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.lines = []

    def input(self, prompt=""):
        if not self._answers:
            raise EOFError
        return self._answers.pop(0)

    def output(self, text=""):
        self.lines.append(str(text))

    @property
    def text(self):
        return "\n".join(self.lines)
