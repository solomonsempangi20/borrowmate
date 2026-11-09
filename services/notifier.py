"""Notifier abstraction + the in-app inbox implementation."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Notification:
    time: object
    message: str
    read: bool = False


class Notifier(ABC):
    @abstractmethod
    def notify(self, user_id, message, when):
        """Deliver a message to one user."""

    @abstractmethod
    def inbox(self, user_id):
        """All notifications of one user, oldest first."""

    def unread_count(self, user_id):
        return sum(1 for n in self.inbox(user_id) if not n.read)

    def mark_all_read(self, user_id):
        for note in self.inbox(user_id):
            note.read = True


class InAppNotifier(Notifier):
    def __init__(self):
        self._boxes = {}

    def notify(self, user_id, message, when):
        self._boxes.setdefault(user_id, []).append(Notification(when, message))

    def inbox(self, user_id):
        return list(self._boxes.get(user_id, []))
