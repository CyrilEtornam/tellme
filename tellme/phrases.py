"""Natural-language phrasing for time and calendar events.

Kept dependency-free: numbers are spelled out with a small lookup table rather
than pulling in ``num2words``. The goal is macOS-style phrasing, e.g.
``"It's quarter past four in the afternoon"``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# Whole numbers 0-59, enough for minutes and 12-hour clock hours.
_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]


def spell_number(n: int) -> str:
    """Spell an integer 0-59 in words (e.g. 42 -> 'forty two')."""
    if n < 0 or n > 59:
        return str(n)
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} {_ONES[ones]}"


def _daypart(hour24: int) -> str:
    """Return the spoken time-of-day qualifier for a 24-hour hour value."""
    if 5 <= hour24 < 12:
        return "in the morning"
    if 12 <= hour24 < 17:
        return "in the afternoon"
    if 17 <= hour24 < 21:
        return "in the evening"
    return "at night"


def time_phrase(now: datetime | None = None) -> str:
    """Return a natural spoken phrase for the current wall-clock time.

    Examples:
        3:00  -> "It's three o'clock in the afternoon"
        4:15  -> "It's quarter past four in the afternoon"
        2:30  -> "It's half past two in the afternoon"
        6:45  -> "It's quarter to seven in the evening"
        9:07  -> "It's seven minutes past nine in the morning"
        0:00  -> "It's midnight"
        12:00 -> "It's noon"
    """
    now = now or datetime.now()
    hour24 = now.hour
    minute = now.minute

    if minute == 0 and hour24 == 0:
        return "It's midnight"
    if minute == 0 and hour24 == 12:
        return "It's noon"

    hour12 = hour24 % 12 or 12
    hour_word = _ONES[hour12]
    daypart = _daypart(hour24)

    if minute == 0:
        return f"It's {hour_word} o'clock {daypart}"
    if minute == 15:
        return f"It's quarter past {hour_word} {daypart}"
    if minute == 30:
        return f"It's half past {hour_word} {daypart}"
    if minute == 45:
        next_hour24 = (hour24 + 1) % 24
        next_hour12 = next_hour24 % 12 or 12
        return f"It's quarter to {_ONES[next_hour12]} {_daypart(next_hour24)}"

    unit = "minute" if minute == 1 else "minutes"
    return f"It's {spell_number(minute)} {unit} past {hour_word} {daypart}"


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U0000FE00-\U0000FE0F]"
)
_URL_RE = re.compile(r"https?://\S+")


def clean_title(title: str) -> str:
    """Strip URLs, emojis, and excess whitespace from an event title so it
    reads cleanly when spoken."""
    if not title:
        return "your event"
    text = _URL_RE.sub("", title)
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—:·|")
    return text.strip() or "your event"


def humanize_minutes(minutes: int) -> str:
    """Turn a minute count into a spoken lead-in, e.g. 5 -> 'In 5 minutes'."""
    if minutes <= 0:
        return "Now"
    if minutes == 60:
        return "In one hour"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"In {hours} hours"
    if minutes == 1:
        return "In one minute"
    return f"In {minutes} minutes"


def event_lead_phrase(title: str, minutes_until: int) -> str:
    """Lead-time reminder, e.g. 'In 5 minutes: Meeting with the President'."""
    return f"{humanize_minutes(minutes_until)}: {clean_title(title)}"


def event_start_phrase(title: str) -> str:
    """Start-time announcement, e.g. "It's time for Meeting with the President"."""
    return f"It's time for {clean_title(title)}"


def next_event_phrase(title: str, start: datetime, now: datetime | None = None) -> str:
    """Describe the next upcoming event conversationally."""
    now = now or datetime.now()
    clean = clean_title(title)
    delta = start - now
    if delta <= timedelta(0):
        return f"{clean} is happening now"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{humanize_minutes(minutes)}: {clean}"
    if start.date() == now.date():
        return f"Next up at {start.strftime('%-I:%M %p').lower()}: {clean}"
    if start.date() == (now.date() + timedelta(days=1)):
        return f"Tomorrow at {start.strftime('%-I:%M %p').lower()}: {clean}"
    return f"On {start.strftime('%A')} at {start.strftime('%-I:%M %p').lower()}: {clean}"
