"""Demo data: 3 hostels, 5 students, 1 admin, 8 items and a scenario that
makes every view interesting the moment the app starts.

Hostel coordinates are illustrative, not survey-accurate."""
from datetime import datetime, timedelta

from models.enums import Condition, ValueTier
from models.hostel import Hostel
from services.clock import SimulatedClock
from services.community import Community
from services.notifier import InAppNotifier


def build_demo_community():
    clock = SimulatedClock(datetime(2025, 3, 10, 6, 0))
    community = Community(clock, InAppNotifier())
    seed_demo(community)
    return community


def seed_demo(c):
    """Fill an empty Community. Expects a SimulatedClock starting at 06:00."""
    for name, lat, lon in [("Mitchell Hall", 0.3350, 32.5670),
                           ("Lumumba Hall", 0.3315, 32.5720),
                           ("Nkrumah Hall", 0.3380, 32.5640)]:
        c.add_hostel(Hostel(name, lat, lon))

    amina = c.add_student("Amina", "Mitchell Hall", reliability=4.2, completed_loans=6)   # S1 HIGH trust
    brian = c.add_student("Brian", "Lumumba Hall", reliability=3.4, completed_loans=3)    # S2 MEDIUM
    carol = c.add_student("Carol", "Nkrumah Hall", reliability=3.2, completed_loans=2)    # S3 MEDIUM
    david = c.add_student("David", "Mitchell Hall", reliability=3.6, completed_loans=3)   # S4 MEDIUM
    esther = c.add_student("Esther", "Lumumba Hall", reliability=4.1, completed_loans=6)  # S5 HIGH
    c.add_admin("Grace", "Mitchell Hall")                                                 # A1

    calc = c.add_item(amina, "electronics", "Scientific Calculator", brand="Casio")       # I1
    iron = c.add_item(brian, "household", "Steam Iron")                                   # I2
    cable = c.add_item(carol, "electronics", "Extension Cable", tier=ValueTier.LOW)       # I3
    book = c.add_item(david, "book", "Microeconomics Textbook", author="Mankiw")          # I4
    fan = c.add_item(esther, "household", "Desk Fan", note="USB powered")                 # I5
    c.add_item(amina, "book", "Data Structures Notes", author="Amina")                    # I6
    c.add_item(david, "electronics", "Gaming Laptop", tier=ValueTier.HIGH, brand="Asus")  # I7
    c.add_item(brian, "electronics", "Phone Charger", tier=ValueTier.LOW)                 # I8

    clock = c.clock
    now = clock.now()

    # 06:00  David borrows Carol's cable for 2.5h  -> will be 30m LATE at 09:00
    loan = c.request_item(david, cable, now, 2.5)
    c.accept_request(carol, loan)
    c.hand_over(carol, loan, Condition.GOOD)

    # 06:30  Carol borrows Brian's iron for 5h -> due back "in 2h 30m" at 09:00
    clock.advance(0.5)
    loan = c.request_item(carol, iron, clock.now(), 5)
    c.accept_request(brian, loan)
    c.hand_over(brian, loan, Condition.GOOD)

    clock.advance(2.5)   # 09:00 -> the cable is overdue
    c.tick()

    # Two COMPETING pending requests for Amina's calculator tomorrow morning
    tomorrow = datetime(2025, 3, 11, 8, 0)
    c.request_item(brian, calc, tomorrow, 2)
    c.request_item(esther, calc, tomorrow + timedelta(minutes=30), 2)

    # A confirmed FUTURE booking: Esther will borrow David's textbook tomorrow 10:00
    loan = c.request_item(esther, book, datetime(2025, 3, 11, 10, 0), 24)
    c.accept_request(david, loan)

    # A paused item
    c.pause_item(esther, fan)
    return c
