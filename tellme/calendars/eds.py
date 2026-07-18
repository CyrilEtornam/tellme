"""Evolution Data Server (EDS) calendar provider.

Reads every calendar the desktop knows about, including Google calendars added
through GNOME Online Accounts — so this single provider covers both local and
Google events with no OAuth client to register. Requires the system typelibs
``gir1.2-edataserver-1.2`` and ``gir1.2-ecal-2.0``.

The ECal API varies between releases and can't be exercised in a headless CI
box, so everything here is lazy-imported and defensively wrapped.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .base import CalendarProvider, Event

log = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 5  # seconds to wait for each calendar backend


def _load_gi():
    """Import the EDS/ECal GObject bindings, or return None if unavailable."""
    try:
        import gi

        gi.require_version("EDataServer", "1.2")
        gi.require_version("ECal", "2.0")
        gi.require_version("ICalGLib", "3.0")
        from gi.repository import ECal, EDataServer, ICalGLib

        return EDataServer, ECal, ICalGLib
    except (ImportError, ValueError):
        return None


class EDSProvider(CalendarProvider):
    name = "evolution-data-server"

    def available(self) -> bool:
        return _load_gi() is not None

    def upcoming(self, within: timedelta, now: datetime | None = None) -> list[Event]:
        gi_mods = _load_gi()
        if gi_mods is None:
            return []
        EDataServer, ECal, _ICalGLib = gi_mods
        now = now or datetime.now().astimezone()
        end = now + within

        registry = EDataServer.SourceRegistry.new_sync(None)
        sources = registry.list_sources(EDataServer.SOURCE_EXTENSION_CALENDAR)
        sexp = _time_range_sexp(now, end)

        events: list[Event] = []
        for source in sources:
            if not source.get_enabled():
                continue
            try:
                events.extend(self._read_source(ECal, source, sexp, now))
            except Exception:  # noqa: BLE001 - skip a single broken calendar
                log.exception("failed to read calendar %r", source.get_display_name())
        return events

    def _read_source(self, ECal, source, sexp, now) -> list[Event]:
        client = ECal.Client.connect_sync(
            source, ECal.ClientSourceType.EVENTS, _CONNECT_TIMEOUT, None
        )
        ok, comps = client.get_object_list_as_comps_sync(sexp, None)
        if not ok or not comps:
            return []
        cal_name = source.get_display_name() or ""
        out: list[Event] = []
        for comp in comps:
            ev = _component_to_event(comp, cal_name, now.tzinfo)
            if ev is not None:
                out.append(ev)
        return out


def _time_range_sexp(start: datetime, end: datetime) -> str:
    """Build an ECal S-expression selecting events in [start, end)."""
    s = start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    e = end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f'(occur-in-time-range? (make-time "{s}") (make-time "{e}"))'


def _component_to_event(comp, cal_name: str, tzinfo) -> Event | None:
    """Convert an ECalComponent to our Event, tolerating API differences."""
    try:
        uid = comp.get_uid() or ""
        summary = comp.get_summary()
        title = summary.get_value() if summary is not None else ""

        dtstart = comp.get_dtstart()
        if dtstart is None:
            return None
        itime = dtstart.get_value()
        if itime is None:
            return None

        all_day = bool(itime.is_date())
        start = _icaltime_to_datetime(itime, tzinfo)
        if start is None:
            return None

        end = None
        dtend = comp.get_dtend()
        if dtend is not None and dtend.get_value() is not None:
            end = _icaltime_to_datetime(dtend.get_value(), tzinfo)

        return Event(
            uid=uid or f"{title}-{start.isoformat()}",
            title=title or "your event",
            start=start,
            end=end,
            calendar_name=cal_name,
            all_day=all_day,
        )
    except Exception:  # noqa: BLE001
        log.exception("could not parse calendar component")
        return None


def _icaltime_to_datetime(itime, tzinfo) -> datetime | None:
    """Convert an ICalGLib.Time to a timezone-aware local datetime."""
    try:
        # Prefer the epoch conversion when the time carries a zone.
        as_timet = getattr(itime, "as_timet", None)
        if not itime.is_date() and as_timet is not None:
            epoch = itime.as_timet()
            if epoch:
                return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(tzinfo)

        # Fall back to field-by-field construction (all-day / floating times).
        year = itime.get_year()
        month = itime.get_month()
        day = itime.get_day()
        hour = itime.get_hour()
        minute = itime.get_minute()
        second = itime.get_second()
        naive = datetime(year, month, day, hour, minute, second)
        return naive.replace(tzinfo=tzinfo)
    except Exception:  # noqa: BLE001
        return None
