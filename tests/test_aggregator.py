from datetime import datetime, timedelta

from tellme.calendars.aggregator import CalendarAggregator
from tellme.calendars.base import CalendarProvider, Event


def dt(h, m):
    return datetime(2026, 7, 18, h, m)


class FakeProvider(CalendarProvider):
    def __init__(self, name, events, raises=False):
        self.name = name
        self._events = events
        self._raises = raises

    def upcoming(self, within, now=None):
        if self._raises:
            raise RuntimeError("boom")
        return list(self._events)


def test_merges_and_sorts():
    a = FakeProvider("a", [Event("1", "Lunch", dt(13, 0))])
    b = FakeProvider("b", [Event("2", "Standup", dt(9, 0))])
    agg = CalendarAggregator([a, b])
    events = agg.upcoming(timedelta(hours=24), now=dt(8, 0))
    assert [e.title for e in events] == ["Standup", "Lunch"]


def test_dedup_same_title_and_start():
    # Same event surfaced by two providers (EDS + Google) collapses to one.
    e1 = Event("eds-uid", "Meeting with the President", dt(15, 0))
    e2 = Event("google-uid", "meeting with the president", dt(15, 0))
    agg = CalendarAggregator([FakeProvider("a", [e1]), FakeProvider("b", [e2])])
    events = agg.upcoming(timedelta(hours=24), now=dt(8, 0))
    assert len(events) == 1


def test_failing_provider_is_skipped():
    good = FakeProvider("good", [Event("1", "Standup", dt(9, 0))])
    bad = FakeProvider("bad", [], raises=True)
    agg = CalendarAggregator([bad, good])
    events = agg.upcoming(timedelta(hours=24), now=dt(8, 0))
    assert [e.title for e in events] == ["Standup"]
