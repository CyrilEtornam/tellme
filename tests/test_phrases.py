from datetime import datetime

import pytest

from tellme import phrases


def dt(h, m):
    return datetime(2026, 7, 18, h, m)


@pytest.mark.parametrize(
    "h,m,expected",
    [
        (0, 0, "It's midnight"),
        (12, 0, "It's noon"),
        (15, 0, "It's three o'clock in the afternoon"),
        (3, 0, "It's three o'clock at night"),
        (9, 0, "It's nine o'clock in the morning"),
        (16, 15, "It's quarter past four in the afternoon"),
        (14, 30, "It's half past two in the afternoon"),
        (18, 45, "It's quarter to seven in the evening"),
        (23, 45, "It's quarter to twelve at night"),
        (9, 7, "It's seven minutes past nine in the morning"),
        (8, 1, "It's one minute past eight in the morning"),
        (22, 42, "It's forty two minutes past ten at night"),
    ],
)
def test_time_phrase(h, m, expected):
    assert phrases.time_phrase(dt(h, m)) == expected


def test_time_phrase_covers_all_hours_and_minutes():
    # Smoke test: never raises across a full day.
    for h in range(24):
        for m in range(60):
            assert phrases.time_phrase(dt(h, m)).startswith("It's")


def test_clean_title_strips_emoji_and_url():
    assert phrases.clean_title("📞 Standup https://meet.example/x") == "Standup"
    assert phrases.clean_title("   ") == "your event"
    assert phrases.clean_title("Meeting with the President") == "Meeting with the President"


def test_humanize_minutes():
    assert phrases.humanize_minutes(5) == "In 5 minutes"
    assert phrases.humanize_minutes(1) == "In one minute"
    assert phrases.humanize_minutes(60) == "In one hour"
    assert phrases.humanize_minutes(120) == "In 2 hours"
    assert phrases.humanize_minutes(0) == "Now"


def test_event_phrases():
    assert (
        phrases.event_lead_phrase("Meeting with the President", 5)
        == "In 5 minutes: Meeting with the President"
    )
    assert (
        phrases.event_start_phrase("Meeting with the President")
        == "It's time for Meeting with the President"
    )


def test_next_event_phrase_today():
    now = dt(9, 0)
    assert phrases.next_event_phrase("Standup", dt(9, 3), now) == "In 3 minutes: Standup"
    assert "Next up at" in phrases.next_event_phrase("Lunch", dt(13, 0), now)
