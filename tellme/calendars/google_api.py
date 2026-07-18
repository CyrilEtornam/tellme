"""Optional direct Google Calendar API provider.

Only needed when Google events are NOT already available through GNOME Online
Accounts + Evolution Data Server. Requires the ``google`` extra:

    pip install "tellme[google]"

Setup: place an OAuth *desktop app* client secret at
``~/.config/tellme/google_client_secret.json`` (created in Google Cloud Console).
On first use a browser window completes consent and the token is cached at
``~/.config/tellme/google_token.json``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..config import GOOGLE_CLIENT_SECRET_PATH, GOOGLE_TOKEN_PATH
from .base import CalendarProvider, Event

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class GoogleCalendarProvider(CalendarProvider):
    name = "google-calendar-api"

    def __init__(self) -> None:
        self._service = None

    def available(self) -> bool:
        try:
            import google.oauth2.credentials  # noqa: F401
            import googleapiclient.discovery  # noqa: F401
        except ImportError:
            return False
        return GOOGLE_CLIENT_SECRET_PATH.exists() or GOOGLE_TOKEN_PATH.exists()

    def _get_service(self):
        if self._service is not None:
            return self._service

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if GOOGLE_TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not GOOGLE_CLIENT_SECRET_PATH.exists():
                    raise FileNotFoundError(
                        f"Missing Google OAuth client secret at {GOOGLE_CLIENT_SECRET_PATH}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(GOOGLE_CLIENT_SECRET_PATH), SCOPES
                )
                creds = flow.run_local_server(port=0)
            GOOGLE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOOGLE_TOKEN_PATH.write_text(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def upcoming(self, within: timedelta, now: datetime | None = None) -> list[Event]:
        now = now or datetime.now().astimezone()
        end = now + within
        service = self._get_service()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.astimezone(timezone.utc).isoformat(),
                timeMax=end.astimezone(timezone.utc).isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [
            ev
            for item in result.get("items", [])
            if (ev := _item_to_event(item, now.tzinfo)) is not None
        ]


def _item_to_event(item: dict, tzinfo) -> Event | None:
    start_info = item.get("start", {})
    all_day = "date" in start_info and "dateTime" not in start_info
    raw = start_info.get("dateTime") or start_info.get("date")
    if not raw:
        return None
    try:
        start = _parse_google_dt(raw, all_day, tzinfo)
    except ValueError:
        return None
    end_raw = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
    end = None
    if end_raw:
        try:
            end = _parse_google_dt(end_raw, all_day, tzinfo)
        except ValueError:
            end = None
    return Event(
        uid=item.get("id", raw),
        title=item.get("summary", "your event"),
        start=start,
        end=end,
        calendar_name="Google Calendar",
        all_day=all_day,
    )


def _parse_google_dt(raw: str, all_day: bool, tzinfo) -> datetime:
    if all_day:
        d = datetime.strptime(raw, "%Y-%m-%d")
        return d.replace(tzinfo=tzinfo)
    # RFC3339, e.g. 2026-07-18T09:00:00-04:00 or ...Z
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.astimezone(tzinfo)
