"""MenuEntry: one line of the menu. Shared by the core CLI and by plugins."""
from dataclasses import dataclass
from typing import Callable

from models.enums import Capability


@dataclass
class MenuEntry:
    key: str                      # stable short name, e.g. "request"
    label: str                    # text shown to the user
    handler: Callable[[], None]   # called when chosen
    capability: Capability = Capability.VIEW   # who sees it (no role strings!)
    section: str = "More"
