"""Scheduling logic: when to announce the time and calendar events.

This module is intentionally free of any GUI/GLib dependency so it can be
unit-tested in isolation. :mod:`tellme.app` drives it with real timers.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .calendars.base import Event
from .config import ANNOUNCED_PATH

log = logging.getLogger(__name__)

# Catch-up window: if the app was asleep/just started, still announce an event
# whose moment passed within this many seconds (avoids spamming stale events).
DEFAULT_GRACE_SECONDS = 120


def seconds_to_next_interval(now: datetime, interval_minutes: int) -> float:
    """Seconds from ``now`` until the next interval boundary aligned to midnight.

    With ``interval_minutes=60`` this is the top of the next hour; with 30 it is
    the next :00/:30; with 15 the next quarter hour.
    """
    interval_minutes = max(1, interval_minutes)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (now - midnight).total_seconds()
    step = interval_minutes * 60
    next_boundary = (math.floor(elapsed / step) + 1) * step
    return next_boundary - elapsed


@dataclass
class DueAnnouncement:
    event: Event
    phase: str  # "lead" or "start"
    minutes_until: int


class AnnouncementTracker:
    """Remembers which (event, phase) announcements have already fired today.

    Persisted to disk so a restart doesn't repeat announcements already spoken.
    The record resets automatically when the date rolls over.
    """

    def __init__(self, path: Path = ANNOUNCED_PATH) -> None:
        self.path = path
        # No day is current until a real ``now`` (via due()/_load()) sets one;
        # this guarantees the first due() call always establishes it correctly
        # rather than relying on the wall clock at construction time.
        self._day: str = ""
        self._seen: set[str] = set()
        self._load()

    def _key(self, uid: str, phase: str) -> str:
        return f"{uid}|{phase}"

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        self._day = data.get("day", self._day)
        self._seen = set(data.get("seen", []))

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"day": self._day, "seen": sorted(self._seen)}))
        except OSError:
            log.warning("could not persist announcement state to %s", self.path)

    def _roll_day_if_needed(self, now: datetime) -> None:
        today = now.date().isoformat()
        if today != self._day:
            self._day = today
            self._seen.clear()
            self._save()

    def has(self, uid: str, phase: str) -> bool:
        return self._key(uid, phase) in self._seen

    def mark(self, uid: str, phase: str) -> None:
        self._seen.add(self._key(uid, phase))
        self._save()

    def due(
        self,
        events: list[Event],
        now: datetime,
        lead_minutes: int,
        grace_seconds: int = DEFAULT_GRACE_SECONDS,
    ) -> list[DueAnnouncement]:
        """Return announcements that should fire at ``now`` and mark them seen.

        For each event two moments matter: ``start - lead_minutes`` (a reminder)
        and ``start`` itself. A "start" announcement supersedes a pending "lead"
        one so a just-started event isn't announced twice.
        """
        self._roll_day_if_needed(now)
        lead_window = lead_minutes * 60
        out: list[DueAnnouncement] = []

        for ev in events:
            if ev.all_day:
                continue
            delta = (ev.start - now).total_seconds()

            # Start phase: at or just past the start time.
            if -grace_seconds <= delta <= 0:
                if not self.has(ev.uid, "start"):
                    self.mark(ev.uid, "start")
                    self.mark(ev.uid, "lead")  # start supersedes the reminder
                    out.append(DueAnnouncement(ev, "start", 0))
                continue

            # Lead phase: inside the reminder window, before the start.
            if 0 < delta <= lead_window:
                if not self.has(ev.uid, "lead") and not self.has(ev.uid, "start"):
                    self.mark(ev.uid, "lead")
                    minutes = max(1, math.ceil(delta / 60))
                    out.append(DueAnnouncement(ev, "lead", minutes))

        return out
