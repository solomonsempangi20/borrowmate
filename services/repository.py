"""A small generic in-memory repository: Repository[T]."""
from typing import Callable, Dict, Generic, List, TypeVar

from models.errors import NotFoundError, ValidationError

T = TypeVar("T")


class Repository(Generic[T]):
    def __init__(self, key: Callable[[T], str], label: str = "Record"):
        self._key = key
        self._label = label
        self._data: Dict[str, T] = {}
        self._counters: Dict[str, int] = {}

    def add(self, obj: T) -> T:
        key = self._key(obj)
        if key in self._data:
            raise ValidationError(f"{self._label} '{key}' already exists.")
        self._data[key] = obj
        return obj

    def get(self, key: str) -> T:
        try:
            return self._data[key]
        except KeyError:
            raise NotFoundError(f"{self._label} '{key}' was not found.") from None

    def find(self, predicate: Callable[[T], bool]) -> List[T]:
        return [obj for obj in self._data.values() if predicate(obj)]

    def all(self) -> List[T]:
        return list(self._data.values())

    def remove(self, key: str) -> None:
        self.get(key)
        del self._data[key]

    def next_id(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        while f"{prefix}{n}" in self._data:
            n += 1
        self._counters[prefix] = n
        return f"{prefix}{n}"

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data
