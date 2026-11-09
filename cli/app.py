"""The menu-driven CLI. Input/output are injected so tests can script it."""
from models.enums import (Capability, Condition, ConflictSeverity, ItemStatus, LoanStatus,
                          parse_enum)
from models.errors import BorrowMateError, NotFoundError, ValidationError
from models.item import ItemFactory
from cli.inputs import parse_number, parse_when
from cli.menu import MenuEntry
from cli.tables import render_table
from plugins.loader import discover_plugins
from services.timefmt import countdown, fmt_dt

V, B, L, M = Capability.VIEW, Capability.BORROW, Capability.LEND, Capability.MODERATE


class CLI:
    def __init__(self, community, input_fn=input, output_fn=print, plugins=None):
        self.community = community
        self.user = None
        self._input = input_fn
        self._output = output_fn
        self._plugins = discover_plugins() if plugins is None else list(plugins)

    # ------------------------------------------------ API used by plugins
    def say(self, text=""):
        self._output(text)

    def ask(self, prompt):
        return str(self._input(prompt)).strip()

    def show_table(self, headers, rows, title=None):
        if title:
            self.say(f"\n{title}")
        self.say(render_table(headers, rows))

    # ------------------------------------------------------------ main loop
    def run(self):
        self.say("=== BorrowMate: borrow what you need from students near you ===")
        try:
            while True:
                if self.user is None and not self._login():
                    break
                self._tick()
                entries = self._visible_entries()
                self._show_menu(entries)
                choice = self.ask("Choose> ").lower()
                if not choice:
                    continue
                entry = self._find(entries, choice)
                if entry is None:
                    self.say(f"! Unknown choice '{choice}'. Type a number or a key from the menu.")
                    continue
                if entry.key == "quit":
                    break
                self._safely(entry.handler)
        except EOFError:
            pass
        self.say("Goodbye!")

    def _safely(self, action):
        try:
            action()
        except (BorrowMateError, ValueError) as exc:
            self.say(f"! {exc}")
        except EOFError:
            raise
        except Exception as exc:   # last line of defence: never crash the app
            self.say(f"! Something unexpected went wrong: {exc}")

    def _tick(self):
        self._safely(self.community.tick)
        now = self.community.clock.now()
        for plugin in self._plugins:
            self._safely(lambda p=plugin: p.on_tick(now))

    def _login(self):
        self.say("\nWho are you? Pick a user id:")
        self.show_table(["ID", "Name", "Role", "Hostel"],
                        [[u.id, u.name, u.role(), u.hostel.name] for u in self.community.users.all()])
        while self.user is None:
            uid = self.ask("User id (q to quit): ")
            if uid.lower() in ("q", "quit"):
                return False
            try:
                self.user = self.community.users.get(uid.upper())
            except BorrowMateError as exc:
                self.say(f"! {exc}")
        self.say(f"Welcome, {self.user.name}!")
        return True

    # ----------------------------------------------------------------- menu
    def _visible_entries(self):
        entries = list(self._core_entries())
        for plugin in self._plugins:
            try:
                entries.extend(plugin.menu_entries(self))
            except Exception as exc:
                self.say(f"! A plugin menu failed: {exc}")
        allowed = self.user.capabilities()
        shown = [e for e in entries if e.capability in allowed]
        return sorted(shown, key=lambda e: e.section == "Account")   # Account/Quit stay last

    def _show_menu(self, entries):
        now = self.community.clock.now()
        unread = self.community.notifier.unread_count(self.user.id)
        self.say(f"\n== {self.user.name} ({self.user.role()}, {self.user.hostel.name}) "
                 f"| {fmt_dt(now)} | {unread} unread ==")
        section = None
        for number, entry in enumerate(entries, 1):
            if entry.section != section:
                section = entry.section
                self.say(f" {section}")
            self.say(f"  {number:>2}) {entry.label}  [{entry.key}]")

    @staticmethod
    def _find(entries, choice):
        if choice.isdigit():
            index = int(choice) - 1
            return entries[index] if 0 <= index < len(entries) else None
        return next((e for e in entries if e.key == choice), None)

    def _core_entries(self):
        E = MenuEntry
        return [
            E("items", "All listed items", self.view_items, V, "Look around"),
            E("near", "Available items near me", self.view_near, V, "Look around"),
            E("taken", "Taken items and return times", self.view_taken, V, "Look around"),
            E("conflicts", "Booking conflicts", self.view_conflicts, V, "Look around"),
            E("overdue", "Overdue items", self.view_overdue, V, "Look around"),
            E("search", "Search items", self.search, V, "Look around"),
            E("request", "Request an item", self.act_request, B, "Borrow"),
            E("cancel", "Cancel one of my requests", self.act_cancel, B, "Borrow"),
            E("report", "Report a problem (dispute)", self.act_report, B, "Borrow"),
            E("mine", "My loans and profile", self.view_mine, B, "Borrow"),
            E("approve", "Approve a request for my item", self.act_approve, L, "Lend"),
            E("decline", "Decline a request for my item", self.act_decline, L, "Lend"),
            E("handover", "Hand over an item", self.act_handover, L, "Lend"),
            E("return", "Confirm a return", self.act_return, L, "Lend"),
            E("list", "List a new item", self.act_list, L, "Lend"),
            E("pause", "Pause / resume one of my items", self.act_pause, L, "Lend"),
            E("disputes", "View disputes", self.view_disputes, M, "Admin"),
            E("suspend", "Suspend a user", self.act_suspend, M, "Admin"),
            E("restore", "Restore a user", self.act_restore, M, "Admin"),
            E("inbox", "Notifications", self.view_inbox, V, "Account"),
            E("clock", "Move the demo clock forward", self.act_clock, V, "Account"),
            E("switch", "Switch user", self.act_switch, V, "Account"),
            E("quit", "Quit", lambda: None, V, "Account"),
        ]

    # --------------------------------------------------------------- helpers
    def _now(self):
        return self.community.clock.now()

    def _pick_item(self, prompt="Item id: "):
        return self.community.items.get(self.ask(prompt).upper())

    def _choose_loan(self, candidates, prompt="Loan id: "):
        if not candidates:
            self.say("Nothing to choose from right now.")
            return None
        self._loan_table(candidates)
        loan = self.community.loans.get(self.ask(prompt).upper())
        if loan.id not in [c.id for c in candidates]:
            raise ValidationError("That loan is not one of the loans listed above.")
        return loan

    def _loan_table(self, loans, title=None):
        self.show_table(["Loan", "Item", "Borrower", "Owner", "From", "Due", "Status"],
                        [[l.id, l.item.title, l.borrower.name, l.owner.name, fmt_dt(l.start),
                          fmt_dt(l.due), l.status.value] for l in loans], title)

    def _loans_where(self, predicate):
        return [l for l in self.community.loans.all_loans() if predicate(l)]

    def _ask_condition(self, prompt, default=None):
        text = self.ask(prompt)
        if not text and default is not None:
            return default
        return parse_enum(Condition, text)

    # ------------------------------------------------------------------ views
    def view_items(self):
        rows = []
        for item in self.community.items.all():
            loan = self.community.loans.current_loan(item)
            rows.append([item.id, item.title, item.category(), item.owner.name,
                         item.owner.hostel.name, item.status.value,
                         loan.borrower.name if loan else "-",
                         fmt_dt(loan.due) if loan else "-"])
        self.show_table(["ID", "Title", "Category", "Owner", "Hostel", "Status", "Held by", "Due back"],
                        rows, "All listed items")

    def view_near(self):
        text = self.ask("Radius in km (blank = any distance): ")
        radius = parse_number(text, "a radius in km") if text else None
        rows = []
        for r in self.community.items_near(self.user, radius):
            booked = "; ".join(f"{fmt_dt(l.start)}-{fmt_dt(l.due)}" for l in r.upcoming) or "-"
            allowed = "Yes" if r.problem is None else f"No: {r.problem}"
            rows.append([r.item.id, r.item.title, r.item.owner.name, r.item.owner.hostel.name,
                         f"{r.distance_km:.2f}", r.item.value_tier().name, booked, allowed])
        self.show_table(["ID", "Title", "Owner", "Hostel", "km", "Value", "Booked", "Can I borrow?"],
                        rows, "Available items near me (closest first)")

    def view_taken(self):
        now = self._now()
        out = self._loans_where(lambda l: l.is_holding)
        self.show_table(["Item", "Borrower", "Owner", "Due back", "Time left"],
                        [[l.item.title, l.borrower.name, l.owner.name, fmt_dt(l.due),
                          countdown(l.due, now)] for l in out], "Taken items")
        waiting = self._loans_where(lambda l: l.status is LoanStatus.ACCEPTED)
        self.show_table(["Loan", "Item", "Borrower", "Starts", "Starts in", "Due"],
                        [[l.id, l.item.title, l.borrower.name, fmt_dt(l.start),
                          countdown(l.start, now).replace(" LATE", " ago (ready)"), fmt_dt(l.due)]
                         for l in waiting], "Confirmed bookings waiting for handover")

    def view_conflicts(self):
        rows = [[c.severity.value, c.item.title,
                 f"{c.first.id} {c.first.borrower.name} {fmt_dt(c.first.start)}-{fmt_dt(c.first.due)}",
                 f"{c.second.id} {c.second.borrower.name} {fmt_dt(c.second.start)}-{fmt_dt(c.second.due)}",
                 c.note] for c in self.community.loans.conflicts()]
        self.show_table(["Severity", "Item", "Booking A", "Booking B", "Note"], rows, "Booking conflicts")

    def view_overdue(self):
        now = self._now()
        late = self._loans_where(lambda l: l.status is LoanStatus.OVERDUE)
        self.show_table(["Loan", "Item", "Borrower", "Owner", "Was due", "Late by"],
                        [[l.id, l.item.title, l.borrower.name, l.owner.name, fmt_dt(l.due),
                          countdown(l.due, now)] for l in late], "Overdue items")

    def search(self):
        found = self.community.search(self.ask("Search for: "))
        self.show_table(["ID", "Title", "Category", "Owner", "Hostel", "Status", "Details"],
                        [[i.id, i.title, i.category(), i.owner.name, i.owner.hostel.name,
                          i.status.value, i.details()] for i in found], "Search results")

    def view_mine(self):
        u, m = self.user, self.community.loans
        self.show_table(["Name", "Hostel", "Reliability", "Completed", "Late", "Trust level",
                         "Active loans"],
                        [[u.name, u.hostel.name, f"{u.reliability:.1f}", u.completed_loans,
                          u.late_returns, u.max_value_tier().name,
                          f"{m.active_count(u)}/{u.max_active_loans()}"]], "My profile")
        self._loan_table(m.loans_of(u), "My loans (borrowed and lent)")

    def view_inbox(self):
        notes = self.community.notifier.inbox(self.user.id)
        self.say("\nNotifications (newest first)")
        if not notes:
            self.say("  (none)")
        for n in reversed(notes):
            self.say(f"  {'*' if not n.read else ' '} {fmt_dt(n.time)}  {n.message}")
        self.community.notifier.mark_all_read(self.user.id)

    def view_disputes(self):
        self._loan_table(self.community.disputes(self.user), "Disputes")
        for loan in self.community.disputes(self.user):
            self.say(f"  {loan.id}: {loan.dispute_reason}")

    # ---------------------------------------------------------------- actions
    def act_request(self):
        item = self._pick_item("Item id to borrow: ")
        start = parse_when(self.ask("Start (now, +2h, tomorrow 08:00, or YYYY-MM-DD HH:MM) [now]: "),
                           self._now())
        hours = parse_number(self.ask(f"How many hours (max {item.max_hours:g})? "), "the hours")
        loan = self.community.request_item(self.user, item, start, hours)
        self.say(f"Request {loan.id} sent to {loan.owner.name}.")
        rivals = self.community.loans.competing_with(loan)
        if rivals:
            names = ", ".join(f"{r.borrower.name} ({r.id})" for r in rivals)
            self.say(f"Note: {ConflictSeverity.COMPETING.value} - others also asked for that time: "
                     f"{names}. The owner can accept only one.")

    def act_cancel(self):
        loan = self._choose_loan(self._loans_where(
            lambda l: l.borrower.id == self.user.id and l.status in (LoanStatus.REQUESTED, LoanStatus.ACCEPTED)))
        if loan:
            self.community.cancel_request(self.user, loan)
            self.say(f"Loan {loan.id} cancelled.")

    def act_report(self):
        loan = self._choose_loan(self._loans_where(
            lambda l: l.is_holding and l.status is not LoanStatus.DISPUTED
            and self.user.id in (l.borrower.id, l.owner.id)))
        if loan:
            self.community.report_problem(self.user, loan, self.ask("Describe the problem: "))
            self.say(f"Loan {loan.id} is now disputed. Admins have been told.")

    def act_approve(self):
        loan = self._choose_loan(self._loans_where(
            lambda l: l.is_pending and l.owner.id == self.user.id))
        if loan:
            self.community.accept_request(self.user, loan)
            self.say(f"Loan {loan.id} accepted. Competing requests were declined automatically.")

    def act_decline(self):
        loan = self._choose_loan(self._loans_where(
            lambda l: l.is_pending and l.owner.id == self.user.id))
        if loan:
            self.community.decline_request(self.user, loan, self.ask("Reason (optional): "))
            self.say(f"Loan {loan.id} declined.")

    def act_handover(self):
        loan = self._choose_loan(self._loans_where(
            lambda l: l.status is LoanStatus.ACCEPTED and l.owner.id == self.user.id))
        if loan:
            cond = self._ask_condition(f"Condition now [{loan.item.condition.name.lower()}]: ",
                                       loan.item.condition)
            self.community.hand_over(self.user, loan, cond)
            self.say(f"'{loan.item.title}' handed to {loan.borrower.name}. Due {fmt_dt(loan.due)}.")

    def act_return(self):
        loan = self._choose_loan(self._loans_where(
            lambda l: l.is_holding and l.owner.id == self.user.id))
        if loan:
            cond = self._ask_condition("Condition on return (new/good/fair/damaged): ")
            self.community.confirm_return(self.user, loan, cond)
            verdict = "on time" if loan.was_on_time else "LATE"
            self.say(f"Return confirmed ({verdict}). {loan.borrower.name}'s reliability: "
                     f"{loan.borrower.reliability:.1f}")

    def act_list(self):
        kind = self.ask(f"Kind ({'/'.join(ItemFactory.kinds())}): ")
        title = self.ask("Title: ")
        cond = self._ask_condition("Condition (new/good/fair/damaged) [good]: ", Condition.GOOD)
        item = self.community.add_item(self.user, kind, title, condition=cond)
        self.say(f"Listed {item.id}: {item.title} ({item.details()}).")

    def act_pause(self):
        mine = [i for i in self.community.items.all() if i.owner.id == self.user.id]
        self.show_table(["ID", "Title", "Status"], [[i.id, i.title, i.status.value] for i in mine],
                        "My items")
        item = self._pick_item("Item id: ")
        if item.status is ItemStatus.PAUSED:
            self.community.resume_item(self.user, item)
            self.say(f"'{item.title}' is available again.")
        else:
            self.community.pause_item(self.user, item)
            self.say(f"'{item.title}' is paused.")

    def act_suspend(self):
        user = self.community.suspend_user(self.user, self.ask("User id to suspend: ").upper())
        self.say(f"{user.name} is suspended.")

    def act_restore(self):
        user = self.community.restore_user(self.user, self.ask("User id to restore: ").upper())
        self.say(f"{user.name} is restored.")

    def act_clock(self):
        self.community.advance_clock(parse_number(self.ask("Move the clock forward by how many hours? "),
                                                  "the hours"))
        self.say(f"The demo clock now shows {fmt_dt(self._now())}.")

    def act_switch(self):
        self.user = None
