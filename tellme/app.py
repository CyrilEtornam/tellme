"""The tellme application: wires config, speaker, scheduler, and calendars
together on a single GLib main loop.

Design notes:
- Scheduling uses ``GLib.timeout`` callbacks (no busy-waiting).
- Speech runs on the Speaker's own worker thread, so announcements never block
  the main loop.
- Calendar fetches run on a short-lived worker thread; results are marshaled
  back to the main loop with ``GLib.idle_add`` before use.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from . import config as cfg_mod
from .calendars.aggregator import build_aggregator
from .phrases import event_lead_phrase, event_start_phrase, next_event_phrase, time_phrase
from .scheduler import AnnouncementTracker, seconds_to_next_interval
from .speaker import Speaker

log = logging.getLogger(__name__)


class TellmeApp:
    def __init__(self) -> None:
        cfg_mod.ensure_dirs()
        self.config = cfg_mod.load_config()
        self.speaker = Speaker(self.config.voice.model, mute=self.config.mute)
        self.tracker = AnnouncementTracker()
        self.aggregator = build_aggregator(self.config)

        self._events: list = []
        self._events_lock = threading.Lock()
        self._time_source_id: int | None = None
        self._tray = None
        self._GLib = None
        self._loop = None

    # --- lifecycle ---------------------------------------------------------
    def run(self) -> int:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib

        self._GLib = GLib
        self.speaker.start()

        # Try to show a tray icon; the app still works headless without it.
        try:
            from .tray import TrayIcon

            self._tray = TrayIcon(self)
        except Exception:  # noqa: BLE001
            log.warning("system tray unavailable; running without an indicator")

        self._arm_time_timer()
        GLib.timeout_add_seconds(60, self._on_event_tick)
        self._refresh_events_async()
        GLib.timeout_add_seconds(
            max(1, self.config.events.poll_minutes) * 60, self._on_calendar_poll
        )

        log.info("tellme is running")
        self._loop = GLib.MainLoop()
        try:
            self._loop.run()
        except KeyboardInterrupt:
            pass
        self.speaker.stop()
        return 0

    def quit(self, *_args) -> None:
        if self._loop is not None:
            self._loop.quit()

    # --- time announcements ------------------------------------------------
    def _arm_time_timer(self) -> None:
        if self._GLib is None:
            return
        if self._time_source_id is not None:
            self._GLib.source_remove(self._time_source_id)
            self._time_source_id = None
        if not self.config.time.enabled:
            return
        delay = int(round(seconds_to_next_interval(datetime.now(), self.config.time.interval_minutes)))
        self._time_source_id = self._GLib.timeout_add_seconds(max(1, delay), self._on_time_tick)

    def _on_time_tick(self) -> bool:
        if self.config.time.enabled:
            self.speaker.say(time_phrase(datetime.now()))
        # Re-arm for the next boundary and cancel this one-shot.
        self._time_source_id = None
        self._arm_time_timer()
        return self._GLib.SOURCE_REMOVE

    def speak_time_now(self) -> None:
        self.speaker.say(time_phrase(datetime.now()))

    # --- event announcements -----------------------------------------------
    def _on_event_tick(self) -> bool:
        if self.config.events.enabled:
            now = datetime.now().astimezone()
            with self._events_lock:
                events = list(self._events)
            for due in self.tracker.due(events, now, self.config.events.lead_minutes):
                if due.phase == "lead":
                    self.speaker.say(event_lead_phrase(due.event.title, due.minutes_until))
                else:
                    self.speaker.say(event_start_phrase(due.event.title))
        return self._GLib.SOURCE_CONTINUE

    def announce_next_event(self) -> None:
        now = datetime.now().astimezone()
        with self._events_lock:
            upcoming = [e for e in self._events if not e.all_day and e.start >= now]
        if not upcoming:
            self.speaker.say("You have no upcoming events")
            return
        nxt = min(upcoming, key=lambda e: e.start)
        self.speaker.say(next_event_phrase(nxt.title, nxt.start, now))

    # --- calendar polling --------------------------------------------------
    def _on_calendar_poll(self) -> bool:
        self._refresh_events_async()
        return self._GLib.SOURCE_CONTINUE

    def _refresh_events_async(self) -> None:
        def worker() -> None:
            try:
                within = timedelta(hours=self.config.events.lookahead_hours)
                events = self.aggregator.upcoming(within)
            except Exception:  # noqa: BLE001
                log.exception("calendar refresh failed")
                events = None
            if events is not None:
                self._GLib.idle_add(self._store_events, events)

        threading.Thread(target=worker, name="calendar-refresh", daemon=True).start()

    def _store_events(self, events: list) -> bool:
        with self._events_lock:
            self._events = events
        log.debug("refreshed %d upcoming events", len(events))
        return self._GLib.SOURCE_REMOVE

    # --- config / mute -----------------------------------------------------
    def set_mute(self, mute: bool) -> None:
        self.config.mute = mute
        self.speaker.set_mute(mute)
        cfg_mod.save_config(self.config)

    def reload_config(self) -> None:
        """Re-read config from disk and re-apply everything that can change."""
        new_cfg = cfg_mod.load_config()
        voice_changed = new_cfg.voice.model != self.config.voice.model
        calendars_changed = (
            new_cfg.calendars.use_eds != self.config.calendars.use_eds
            or new_cfg.calendars.use_google_api != self.config.calendars.use_google_api
        )
        self.config = new_cfg
        self.speaker.set_mute(new_cfg.mute)
        if voice_changed:
            self.speaker.model_name = new_cfg.voice.model
        if calendars_changed:
            self.aggregator = build_aggregator(new_cfg)
            self._refresh_events_async()
        self._arm_time_timer()
