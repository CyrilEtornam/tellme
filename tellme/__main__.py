"""Command-line entry point for tellme.

Running with no command starts the background app (tray + hourly + event
announcements). The one-shot flags are handy for testing and for wiring into
other tools without spinning up the GLib loop.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta

from . import __version__, config as cfg_mod
from .phrases import next_event_phrase, time_phrase


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tellme", description="A premium talking clock for Ubuntu.")
    p.add_argument("--version", action="version", version=f"tellme {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--say", metavar="TEXT", help="speak TEXT and exit")
    g.add_argument("--speak-now", action="store_true", help="speak the current time and exit")
    g.add_argument(
        "--next-event", action="store_true", help="print and speak the next upcoming event"
    )
    return p


def _make_speaker(cfg):
    from .speaker import Speaker

    return Speaker(cfg.voice.model, mute=False)


def _cmd_say(cfg, text: str) -> int:
    speaker = _make_speaker(cfg)
    if not speaker.model_available():
        print(
            f"Voice model '{cfg.voice.model}' is not installed. "
            "Run scripts/get-voice.sh to download it.",
            file=sys.stderr,
        )
        return 2
    return 0 if speaker.speak_blocking(text) else 1


def _speak_best_effort(cfg, text: str) -> None:
    """Speak if a voice model is installed; otherwise stay silent (the caller
    has already printed the information to stdout)."""
    speaker = _make_speaker(cfg)
    if speaker.model_available():
        speaker.speak_blocking(text)


def _cmd_next_event(cfg) -> int:
    from .calendars.aggregator import build_aggregator

    now = datetime.now().astimezone()
    aggregator = build_aggregator(cfg)
    events = aggregator.upcoming(timedelta(hours=cfg.events.lookahead_hours), now)
    upcoming = [e for e in events if not e.all_day and e.start >= now]
    if not upcoming:
        print("No upcoming events.")
        _speak_best_effort(cfg, "You have no upcoming events")
        return 0
    nxt = min(upcoming, key=lambda e: e.start)
    phrase = next_event_phrase(nxt.title, nxt.start, now)
    print(f"{phrase}  [{nxt.calendar_name}]")
    _speak_best_effort(cfg, phrase)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg_mod.ensure_dirs()
    cfg = cfg_mod.load_config()

    if args.say is not None:
        return _cmd_say(cfg, args.say)
    if args.speak_now:
        return _cmd_say(cfg, time_phrase(datetime.now()))
    if args.next_event:
        return _cmd_next_event(cfg)

    # Default: run the background application.
    from .app import TellmeApp

    return TellmeApp().run()


if __name__ == "__main__":
    sys.exit(main())
