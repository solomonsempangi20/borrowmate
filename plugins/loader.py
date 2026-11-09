"""Auto-discovery: import every module in plugins/ and instantiate every
concrete MenuPlugin subclass found there."""
import importlib
import inspect
import pkgutil
import sys

import plugins
from plugins.base import MenuPlugin


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def discover_plugins():
    for info in pkgutil.iter_modules(plugins.__path__):
        try:
            importlib.import_module(f"{plugins.__name__}.{info.name}")
        except Exception as exc:  # a broken plugin must not stop the app
            print(f"! Plugin '{info.name}' could not be loaded: {exc}", file=sys.stderr)
    found = {c for c in _all_subclasses(MenuPlugin)
             if not inspect.isabstract(c) and c.__module__.startswith(plugins.__name__ + ".")}
    return [cls() for cls in sorted(found, key=lambda c: (c.order, c.__name__))]
