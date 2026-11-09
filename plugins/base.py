"""MenuPlugin: the abstract class every plugin extends."""
from abc import ABC, abstractmethod


class MenuPlugin(ABC):
    order = 100   # smaller numbers appear first in the menu

    @abstractmethod
    def menu_entries(self, cli):
        """Return a list of MenuEntry objects. `cli` exposes community, user,
        ask(), say() and show_table()."""

    def on_tick(self, now):
        """Optional: called before every menu (e.g. to expire old requests)."""
