import unittest

from cli.app import CLI
from models.enums import Capability, ValueTier
from models.item import Book, Electronics, HouseholdItem, Item, ItemFactory
from models.person import Admin, Person, Student
from models.errors import (BorrowMateError, ConflictError, EligibilityError, InvalidTransitionError,
                           NotFoundError, PermissionDeniedError, ValidationError)
from plugins.base import MenuPlugin
from plugins.reports import Report, ReportFormatter
from services.clock import Clock
from services.notifier import Notifier
from .helpers import ScriptedIO, World


class AbstractClassesTest(unittest.TestCase):
    def test_abstract_classes_cannot_be_instantiated(self):
        for cls in (Person, Item, Clock, Notifier, Report, MenuPlugin, ReportFormatter):
            with self.subTest(cls=cls.__name__):
                with self.assertRaises(TypeError):
                    cls()

    def test_every_error_extends_the_base_error(self):
        for cls in (ValidationError, NotFoundError, PermissionDeniedError, EligibilityError,
                    ConflictError, InvalidTransitionError):
            self.assertTrue(issubclass(cls, BorrowMateError))


class PolymorphismTest(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def test_people_answer_differently(self):
        s, a = self.w.ben, self.w.admin
        self.assertEqual((s.role(), a.role()), ("Student", "Admin"))
        self.assertEqual((s.can_moderate(), a.can_moderate()), (False, True))
        self.assertEqual((s.can_borrow(), a.can_borrow()), (True, False))
        self.assertEqual(a.max_active_loans(), 0)
        self.assertEqual(s.max_active_loans(), 1)
        self.assertEqual(self.w.cara.max_active_loans(), 3)
        self.assertIsNone(a.max_value_tier())

    def test_items_answer_differently(self):
        c = self.w.c
        e = c.add_item(self.w.amina, "electronics", "Cable")
        b = c.add_item(self.w.amina, "book", "Atlas")
        h = c.add_item(self.w.amina, "household", "Kettle")
        self.assertEqual([x.category() for x in (e, b, h)], ["Electronics", "Book", "Household"])
        self.assertEqual([x.default_max_hours() for x in (e, b, h)], [24, 72, 6])
        self.assertEqual([x.max_hours for x in (e, b, h)], [24, 72, 6])
        self.assertEqual((e.value_tier(), b.value_tier(), h.value_tier()),
                         (ValueTier.MEDIUM, ValueTier.LOW, ValueTier.LOW))
        self.assertEqual(len({x.details() for x in (e, b, h)}), 3)
        self.assertIsInstance(e, Electronics)
        self.assertIsInstance(b, Book)
        self.assertIsInstance(h, HouseholdItem)

    def test_factory_rejects_unknown_kind(self):
        with self.assertRaises(ValidationError):
            ItemFactory.create("spaceship", "I9", "X", self.w.amina)

    def test_menu_differs_by_capability_not_role_strings(self):
        student_io, admin_io = ScriptedIO(["S1", "quit"]), ScriptedIO(["A1", "quit"])
        CLI(self.w.c, student_io.input, student_io.output).run()
        CLI(self.w.c, admin_io.input, admin_io.output).run()
        self.assertIn("Request an item", student_io.text)
        self.assertNotIn("Suspend a user", student_io.text)
        self.assertIn("Suspend a user", admin_io.text)
        self.assertNotIn("Request an item", admin_io.text)
        self.assertIn(Capability.MODERATE, self.w.admin.capabilities())
        self.assertNotIn(Capability.BORROW, self.w.admin.capabilities())


if __name__ == "__main__":
    unittest.main()
