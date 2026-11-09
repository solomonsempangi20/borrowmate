"""Community: a facade that OWNS the inventory, loan manager, clock, notifier
(composition). The CLI and the plugins talk to this one class."""
from dataclasses import dataclass

from models.enums import ItemStatus, LoanStatus
from models.errors import PermissionDeniedError, ValidationError
from models.hostel import Hostel
from models.item import ItemFactory
from models.person import Admin, Student
from services.loan_manager import LoanManager
from services.repository import Repository


@dataclass
class NearbyItem:
    item: object
    distance_km: float
    upcoming: list
    problem: str


class Community:
    def __init__(self, clock, notifier):
        self._clock = clock
        self._notifier = notifier
        self._hostels = {}
        self._users = Repository(lambda u: u.id, "User")
        self._items = Repository(lambda i: i.id, "Item")
        self._loans = LoanManager(clock, notifier)

    # composition: expose the owned parts read-only
    clock = property(lambda self: self._clock)
    notifier = property(lambda self: self._notifier)
    users = property(lambda self: self._users)
    items = property(lambda self: self._items)
    loans = property(lambda self: self._loans)

    # ------------------------------------------------------------- setup
    def add_hostel(self, hostel):
        self._hostels[hostel.name.lower()] = hostel
        return hostel

    def hostel(self, name):
        if isinstance(name, Hostel):
            return name
        try:
            return self._hostels[str(name).strip().lower()]
        except KeyError:
            raise ValidationError(f"Unknown hostel '{name}'.") from None

    def hostels(self):
        return list(self._hostels.values())

    def add_student(self, name, hostel, **kwargs):
        return self._users.add(Student(self._users.next_id("S"), name, self.hostel(hostel), **kwargs))

    def add_admin(self, name, hostel):
        return self._users.add(Admin(self._users.next_id("A"), name, self.hostel(hostel)))

    def students(self):
        return self._users.find(lambda u: u.can_borrow())

    def admins(self):
        return self._users.find(lambda u: u.can_moderate())

    def add_item(self, owner, kind, title, **kwargs):
        item = ItemFactory.create(kind, self._items.next_id("I"), title, owner, **kwargs)
        return self._items.add(item)

    # -------------------------------------------------- loan facade methods
    def request_item(self, borrower, item, start, hours):
        return self._loans.request(borrower, item, start, hours)

    def accept_request(self, owner, loan):
        return self._loans.accept(owner, loan)

    def decline_request(self, owner, loan, reason=""):
        return self._loans.decline(owner, loan, reason)

    def cancel_request(self, user, loan):
        return self._loans.cancel(user, loan)

    def hand_over(self, owner, loan, condition_out=None):
        return self._loans.hand_over(owner, loan, condition_out)

    def confirm_return(self, owner, loan, condition_in):
        return self._loans.confirm_return(owner, loan, condition_in)

    def report_problem(self, user, loan, reason):
        loan = self._loans.report_problem(user, loan, reason)
        for admin in self.admins():
            self._notifier.notify(admin.id, f"Dispute on loan {loan.id} ('{loan.item.title}'): "
                                            f"{loan.dispute_reason}", self._clock.now())
        return loan

    def tick(self):
        """Run before every menu: overdue loans are flagged."""
        return self._loans.check_overdue()

    def advance_clock(self, hours):
        return self._clock.advance(hours)

    # ----------------------------------------------------------- item care
    def _require_item_owner(self, owner, item):
        if owner.id != item.owner.id:
            raise PermissionDeniedError("Only the owner can change this item.")

    def pause_item(self, owner, item):
        self._require_item_owner(owner, item)
        item.pause()

    def resume_item(self, owner, item):
        self._require_item_owner(owner, item)
        item.resume()

    # ----------------------------------------------------------- admin
    def suspend_user(self, admin, user_id):
        user = self._users.get(user_id)
        user.set_suspended(True, admin)
        self._notifier.notify(user.id, "Your account has been suspended by an admin.", self._clock.now())
        return user

    def restore_user(self, admin, user_id):
        user = self._users.get(user_id)
        user.set_suspended(False, admin)
        self._notifier.notify(user.id, "Your account has been restored.", self._clock.now())
        return user

    def disputes(self, viewer):
        if not viewer.can_moderate():
            raise PermissionDeniedError("Only an admin can view disputes.")
        return [l for l in self._loans.all_loans() if l.status is LoanStatus.DISPUTED]

    # ----------------------------------------------------------- searching
    def distance_between(self, a, b):
        return a.hostel.distance_to(b.hostel)

    def items_near(self, user, radius_km=None):
        """Available items sorted by distance from the user's hostel."""
        if radius_km is not None and radius_km <= 0:
            raise ValidationError("Radius must be a positive number of km.")
        now = self._clock.now()
        rows = []
        for item in self._items.all():
            if item.status is not ItemStatus.AVAILABLE or item.owner.id == user.id:
                continue
            dist = self.distance_between(user, item.owner)
            if radius_km is not None and dist > radius_km:
                continue
            problem = self._loans.eligibility_problem(user, item, now, min(1.0, item.max_hours))
            rows.append(NearbyItem(item, dist, self._loans.upcoming_bookings(item), problem))
        return sorted(rows, key=lambda r: (r.distance_km, r.item.title))

    def search(self, text):
        needle = str(text).strip().lower()
        if not needle:
            raise ValidationError("Type something to search for.")
        return [i for i in self._items.all()
                if needle in " ".join([i.title, i.category(), i.owner.name,
                                       i.owner.hostel.name]).lower()]
