"""Plugin: reports + formatters (owned by team member 4)."""
import csv
import io
from abc import ABC, abstractmethod

from cli.menu import MenuEntry
from cli.tables import render_table
from models.enums import Capability, ItemStatus, LoanStatus
from models.errors import ValidationError
from plugins.base import MenuPlugin


class Report(ABC):
    """A report is a title, headers and rows. How it is shown is up to a formatter."""

    def __init__(self, community):
        self._c = community

    @abstractmethod
    def title(self):
        """Report title."""

    @abstractmethod
    def headers(self):
        """Column names."""

    @abstractmethod
    def rows(self):
        """List of rows (each a list of cells)."""

    def _handed_over(self):
        return [l for l in self._c.loans.all_loans() if l.handover_time is not None]


class CommunityHealthReport(Report):
    def title(self):
        return "Community health"

    def headers(self):
        return ["Metric", "Value"]

    def rows(self):
        c = self._c
        loans = c.loans.all_loans()
        returned = [l for l in loans if l.status is LoanStatus.RETURNED]
        on_time = sum(1 for l in returned if l.was_on_time)
        students = c.students()
        avg = sum(s.reliability for s in students) / len(students) if students else 0
        items = c.items.all()
        return [
            ["Students", len(students)],
            ["Items listed", len(items)],
            ["Items available", sum(1 for i in items if i.status is ItemStatus.AVAILABLE)],
            ["Items on loan", sum(1 for i in items if i.status is ItemStatus.ON_LOAN)],
            ["Overdue loans", sum(1 for l in loans if l.status is LoanStatus.OVERDUE)],
            ["Open disputes", sum(1 for l in loans if l.status is LoanStatus.DISPUTED)],
            ["Returned loans", len(returned)],
            ["On-time return rate", f"{100 * on_time / len(returned):.0f}%" if returned else "n/a"],
            ["Average reliability", f"{avg:.2f}"],
        ]


class TopLendersReport(Report):
    def title(self):
        return "Top lenders"

    def headers(self):
        return ["Rank", "Lender", "Hostel", "Loans lent"]

    def rows(self):
        counts = {}
        for loan in self._handed_over():
            counts[loan.owner.id] = counts.get(loan.owner.id, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        rows = []
        for rank, (uid, n) in enumerate(ranked, 1):
            owner = self._c.users.get(uid)
            rows.append([rank, owner.name, owner.hostel.name, n])
        return rows


class MostRequestedItemsReport(Report):
    def title(self):
        return "Most requested items"

    def headers(self):
        return ["Rank", "Item", "Category", "Owner", "Requests"]

    def rows(self):
        counts = {}
        for loan in self._c.loans.all_loans():
            counts[loan.item.id] = counts.get(loan.item.id, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        rows = []
        for rank, (iid, n) in enumerate(ranked, 1):
            item = self._c.items.get(iid)
            rows.append([rank, item.title, item.category(), item.owner.name, n])
        return rows


class HostelActivityReport(Report):
    def title(self):
        return "Hostel activity"

    def headers(self):
        return ["Hostel", "Students", "Items listed", "Loans lent", "Loans borrowed"]

    def rows(self):
        rows = []
        for hostel in self._c.hostels():
            students = [s for s in self._c.students() if s.hostel == hostel]
            items = [i for i in self._c.items.all() if i.owner.hostel == hostel]
            lent = sum(1 for l in self._handed_over() if l.owner.hostel == hostel)
            borrowed = sum(1 for l in self._handed_over() if l.borrower.hostel == hostel)
            rows.append([hostel.name, len(students), len(items), lent, borrowed])
        return rows


class MyActivityReport(Report):
    def __init__(self, community, user):
        super().__init__(community)
        self._user = user

    def title(self):
        return f"My activity ({self._user.name})"

    def headers(self):
        return ["Measure", "Value"]

    def rows(self):
        u = self._user
        mine = self._c.loans.loans_of(u)
        lent = [l for l in mine if l.owner.id == u.id and l.handover_time is not None]
        borrowed = [l for l in mine if l.borrower.id == u.id and l.handover_time is not None]
        rows = [["Items I lent out (loans)", len(lent)], ["Items I borrowed (loans)", len(borrowed)],
                ["Open or pending loans", sum(1 for l in mine if l.is_pending or l.is_confirmed)]]
        if u.can_borrow():
            rows += [["Reliability", f"{u.reliability:.1f}"], ["Late returns", u.late_returns]]
        return rows


class ReportFormatter(ABC):
    """Strategy: the same Report can be shown in different ways."""

    @abstractmethod
    def format(self, report):
        """Return the report as a string."""


class TextFormatter(ReportFormatter):
    def format(self, report):
        return f"{report.title()}\n{render_table(report.headers(), report.rows())}"


class CsvFormatter(ReportFormatter):
    def format(self, report):
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(report.headers())
        writer.writerows(report.rows())
        return buffer.getvalue()


FORMATTERS = {"text": TextFormatter, "csv": CsvFormatter}


class ReportsPlugin(MenuPlugin):
    order = 30

    def menu_entries(self, cli):
        return [MenuEntry("reports", "Reports (screen or CSV export)", lambda: self._run(cli),
                          Capability.VIEW, "Reports")]

    @staticmethod
    def available(community, user):
        return [("health", CommunityHealthReport(community)),
                ("lenders", TopLendersReport(community)),
                ("requested", MostRequestedItemsReport(community)),
                ("hostels", HostelActivityReport(community)),
                ("mine", MyActivityReport(community, user))]

    def _run(self, cli):
        reports = self.available(cli.community, cli.user)
        cli.show_table(["Key", "Report"], [[k, r.title()] for k, r in reports], "Reports")
        key = cli.ask("Report key: ").lower()
        report = dict(reports).get(key)
        if report is None:
            raise ValidationError(f"Unknown report '{key}'.")
        kind = cli.ask("Format (text/csv) [text]: ").lower() or "text"
        if kind not in FORMATTERS:
            raise ValidationError("Choose text or csv.")
        output = FORMATTERS[kind]().format(report)
        if kind == "csv":
            path = cli.ask("Save to file (blank = show here): ")
            if path:
                try:
                    with open(path, "w", newline="", encoding="utf-8") as handle:
                        handle.write(output)
                except OSError as exc:
                    raise ValidationError(f"Could not write the file: {exc}") from None
                cli.say(f"Saved {path}.")
                return
        cli.say(output)
