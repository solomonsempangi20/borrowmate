"""Small helpers that turn datetimes into friendly text."""


def fmt_dt(dt):
    return dt.strftime("%a %d %b %H:%M")


def fmt_duration(delta):
    minutes = int(abs(delta.total_seconds()) // 60)
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def countdown(due, now):
    """'in 2h 30m' before the deadline, '30m LATE' after it."""
    delta = due - now
    if delta.total_seconds() >= 0:
        return f"in {fmt_duration(delta)}"
    return f"{fmt_duration(delta)} LATE"
