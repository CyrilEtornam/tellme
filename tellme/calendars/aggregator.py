"""Aggregates multiple calendar providers into one upcoming-events view.

Resilience is the whole point of this layer: a provider that raises (network
down, expired token, EDS not present) is logged and skipped so it never breaks
announcements coming from the other providers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .base import CalendarProvider, Event

log = logging.getLogger(__name__)


def build_aggregator(cfg) -> "CalendarAggregator":
    """Construct an aggregator from a :class:`tellme.config.Config`.

    Providers whose typelibs/deps are missing are dropped automatically by the
    aggregator's ``available()`` filter, so this never fails on a machine that
    lacks EDS or the Google client libraries.
    """
    providers: list[CalendarProvider] = []
    if cfg.calendars.use_eds:
        from .eds import EDSProvider

        providers.append(EDSProvider())
    if cfg.calendars.use_google_api:
        from .google_api import GoogleCalendarProvider

        providers.append(GoogleCalendarProvider())
    return CalendarAggregator(providers)


class CalendarAggregator:
    def __init__(self, providers: list[CalendarProvider]) -> None:
        self.providers = [p for p in providers if p.available()]

    def upcoming(self, within: timedelta, now: datetime | None = None) -> list[Event]:
        now = now or datetime.now().astimezone()
        collected: list[Event] = []
        for provider in self.providers:
            try:
                collected.extend(provider.upcoming(within, now))
            except Exception:  # noqa: BLE001 - never let one source break the rest
                log.exception("calendar provider %r failed; skipping", provider.name)
        return _dedup_sorted(collected)


def _dedup_sorted(events: list[Event]) -> list[Event]:
    """De-duplicate by (normalized title, start) and sort by start time.

    The same Google event can surface through both EDS/GOA and the direct API;
    collapsing on title+start keeps it from being announced twice.
    """
    seen: set[tuple[str, datetime]] = set()
    unique: list[Event] = []
    for ev in sorted(events, key=lambda e: e.start):
        key = (ev.title.strip().lower(), ev.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)
    return unique
