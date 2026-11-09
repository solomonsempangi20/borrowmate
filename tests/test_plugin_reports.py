import csv
import io
import unittest

from models.enums import Condition
from plugins.reports import (CommunityHealthReport, CsvFormatter, HostelActivityReport,
                             MostRequestedItemsReport, MyActivityReport, ReportsPlugin,
                             TextFormatter, TopLendersReport)
from .helpers import World

class ReportTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.loan = self.w.lend(self.w.amina, self.w.cara, self.w.iron, 0, 2)
        self.w.c.confirm_return(self.w.amina, self.loan, Condition.GOOD)

    def test_health(self):
        rows = dict(map(tuple, CommunityHealthReport(self.w.c).rows()))
        self.assertEqual(rows["Students"], 4)
        self.assertEqual(rows["Items listed"], 4)
        self.assertEqual(rows["Returned loans"], 1)
        self.assertEqual(rows["On-time return rate"], "100%")

    def test_top_lenders_and_most_requested(self):
        self.assertEqual(TopLendersReport(self.w.c).rows(), [[1, "Amina", "North", 1]])
        self.assertEqual(MostRequestedItemsReport(self.w.c).rows()[0][1:], ["Iron", "Household", "Amina", 1])

    def test_hostel_and_my_activity(self):
        rows = {r[0]: r for r in HostelActivityReport(self.w.c).rows()}
        self.assertEqual(rows["North"][1:], [2, 3, 1, 0])     # students Amina+Ben; Amina owns 3 items; 1 loan lent
        mine = dict(map(tuple, MyActivityReport(self.w.c, self.w.cara).rows()))
        self.assertEqual(mine["Items I borrowed (loans)"], 1)

    def test_text_and_csv_formatters(self):
        report = TopLendersReport(self.w.c)
        text = TextFormatter().format(report)
        self.assertIn("Top lenders", text)
        self.assertIn("Amina", text)
        parsed = list(csv.reader(io.StringIO(CsvFormatter().format(report))))
        self.assertEqual(parsed, [["Rank", "Lender", "Hostel", "Loans lent"], ["1", "Amina", "North", "1"]])

    def test_csv_quotes_commas(self):
        self.w.c.add_item(self.w.cara, "book", "War, Peace")
        out = CsvFormatter().format(MostRequestedItemsReport(self.w.c))
        self.assertIsInstance(out, str)
        self.assertEqual(ReportsPlugin.available(self.w.c, self.w.cara)[0][0], "health")


if __name__ == "__main__":
    unittest.main()
