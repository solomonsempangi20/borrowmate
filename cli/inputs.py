"""Parsing of what the user types."""
import math
import re
from datetime import datetime, timedelta

from models.errors import ValidationError


def parse_number(text, what="a number"):
    try:
        value = float(str(text).strip())
    except ValueError:
        raise ValidationError(f"Please enter {what} (for example 2 or 1.5).") from None
    if not math.isfinite(value):
        raise ValidationError(f"Please enter {what}.")
    return value


def parse_when(text, now):
    """Accepts: now | +2h | tomorrow 08:00 | YYYY-MM-DD HH:MM"""
    text = (text or "now").strip().lower()
    if text == "now":
        return now
    match = re.fullmatch(r"\+(\d+(?:\.\d+)?)h?", text)
    if match:
        return now + timedelta(hours=float(match.group(1)))
    match = re.fullmatch(r"tomorrow (\d{1,2}):(\d{2})", text)
    if match:
        day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            return day.replace(hour=int(match.group(1)), minute=int(match.group(2)))
        except ValueError:
            raise ValidationError("That time of day does not exist.") from None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValidationError("Use: now, +2h, tomorrow 08:00 or YYYY-MM-DD HH:MM.") from None
