"""Custom exception hierarchy. Every error extends BorrowMateError, so the
CLI can catch one base class and show a friendly message instead of crashing."""


class BorrowMateError(Exception):
    """Base class for every error raised on purpose by BorrowMate."""


class ValidationError(BorrowMateError):
    """Input is malformed (empty name, negative hours, unknown option...)."""


class NotFoundError(BorrowMateError):
    """A user, item or loan id does not exist."""


class PermissionDeniedError(BorrowMateError):
    """The person is not allowed to perform this action (e.g. not the owner)."""


class EligibilityError(BorrowMateError):
    """A borrower is refused. The message always explains the reason."""


class ConflictError(BorrowMateError):
    """A booking clashes with another one. Carries a ConflictSeverity."""

    def __init__(self, message, severity=None):
        super().__init__(message)
        self.severity = severity


class InvalidTransitionError(BorrowMateError):
    """A state machine (Loan, Item) was asked to make an illegal move."""
