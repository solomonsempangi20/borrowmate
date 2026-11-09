import unittest

from plugins.base import MenuPlugin
from plugins.loader import discover_plugins

class DiscoveryTest(unittest.TestCase):
    def test_all_plugins_are_found_automatically(self):
        names = {type(p).__name__ for p in discover_plugins()}
        self.assertEqual(names, {"ExtensionsPlugin", "NeedRequestsPlugin", "ReportsPlugin"})
        self.assertTrue(all(isinstance(p, MenuPlugin) for p in discover_plugins()))


if __name__ == "__main__":
    unittest.main()
