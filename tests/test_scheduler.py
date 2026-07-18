from datetime import datetime, timedelta

from tellme.calendars.base import Event
from tellme.scheduler import AnnouncementTracker, seconds_to_next_interval


def dt(h, m, s=0):
    return datetime(2026, 7, 18, h, m, s)


def test_seconds_to_next_hour():
    assert seconds_to_next_interval(dt(9, 0, 0), 60) == 3600
    assert seconds_to_next_interval(dt(9, 30, 0), 60) == 1800
    assert seconds_to_next_interval(dt(9, 59, 30), 60) == 30


def test_seconds_to_next_half_hour():
    assert seconds_to_next_interval(dt(9, 10, 0), 30) == 1200
    assert seconds_to_next_interval(dt(9, 45, 0), 30) == 900


def test_seconds_to_next_minute():
    assert seconds_to_next_interval(dt(9, 10, 20), 1) == 40


def ev(uid, start, all_day=False):
    return Event(uid=uid, title=f"Event {uid}", start=start, all_day=all_day)


def test_lead_then_start(tmp_path):
    tracker = AnnouncementTracker(tmp_path / "a.json")
    event = ev("e1", dt(9, 5))

    # 5 minutes before: lead reminder fires once.
    due = tracker.due([event], now=dt(9, 0), lead_minutes=5)
    assert len(due) == 1 and due[0].phase == "lead" and due[0].minutes_until == 5

    # A minute later: no repeat.
    assert tracker.due([event], now=dt(9, 1), lead_minutes=5) == []

    # At start: start announcement fires once.
    due = tracker.due([event], now=dt(9, 5), lead_minutes=5)
    assert len(due) == 1 and due[0].phase == "start"

    # After start: nothing.
    assert tracker.due([event], now=dt(9, 6), lead_minutes=5) == []


def test_start_supersedes_lead_when_app_starts_late(tmp_path):
    tracker = AnnouncementTracker(tmp_path / "a.json")
    event = ev("e2", dt(9, 0))
    # App wakes up exactly at start — should announce start, never lead afterwards.
    due = tracker.due([event], now=dt(9, 0), lead_minutes=5)
    assert len(due) == 1 and due[0].phase == "start"
    assert tracker.due([event], now=dt(9, 0, 30), lead_minutes=5) == []


def test_missed_event_outside_grace_is_skipped(tmp_path):
    tracker = AnnouncementTracker(tmp_path / "a.json")
    event = ev("e3", dt(9, 0))
    # 10 minutes late — outside the grace window, no announcement.
    assert tracker.due([event], now=dt(9, 10), lead_minutes=5) == []


def test_all_day_events_ignored(tmp_path):
    tracker = AnnouncementTracker(tmp_path / "a.json")
    event = ev("e4", dt(9, 0), all_day=True)
    assert tracker.due([event], now=dt(9, 0), lead_minutes=5) == []


def test_persistence_survives_restart(tmp_path):
    path = tmp_path / "a.json"
    event = ev("e5", dt(9, 5))
    t1 = AnnouncementTracker(path)
    t1.due([event], now=dt(9, 0), lead_minutes=5)  # marks lead
    # New tracker loading same file should remember the lead already fired.
    t2 = AnnouncementTracker(path)
    assert t2.has("e5", "lead")
    assert t2.due([event], now=dt(9, 1), lead_minutes=5) == []


def test_day_rollover_resets(tmp_path):
    tracker = AnnouncementTracker(tmp_path / "a.json")
    tracker.mark("old", "start")
    assert tracker.has("old", "start")
    # A due() call on the next day clears prior markers.
    tracker.due([], now=datetime(2026, 7, 19, 0, 1), lead_minutes=5)
    assert not tracker.has("old", "start")
