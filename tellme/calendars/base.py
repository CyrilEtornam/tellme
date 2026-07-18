"""Calendar provider interface and the shared Event type."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Event:
    uid: str
    title: str
    start: datetime  # timezone-aware, in local time
    end: datetime | None = None
    calendar_name: str = ""
    all_day: bool = False


class CalendarProvider:
    """Base class for calendar sources.

    Implementations must be resilient: :meth:`upcoming` should raise on hard
    failure so the aggregator can log-and-skip, but should never block the UI
    thread (providers are called from a worker thread).
    """

    name: str = "calendar"

    def upcoming(self, within: timedelta, now: datetime | None = None) -> list[Event]:
        """Return events starting between ``now`` and ``now + within``."""
        raise NotImplementedError

    def available(self) -> bool:
        """Whether this provider can be used in the current environment."""
        return True
