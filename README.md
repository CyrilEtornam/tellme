# tellme

A premium **talking clock for Ubuntu**. It speaks the current time on the hour and
announces your upcoming calendar events by name — *"In 5 minutes: Meeting with the
President"* — with a natural, fully-offline neural voice. Think of the classic macOS
talking clock, but for GNOME/Ubuntu and calendar-aware.

## Features

- 🕰️ **Hourly time announcements** in natural language
  (*"It's quarter past four in the afternoon"*). Interval is configurable.
- 📅 **Calendar event announcements** at start time **and** as a lead-time reminder.
- 🗣️ **Premium neural voice** via [Piper](https://github.com/rhasspy/piper) — runs
  **fully offline**, no cloud, no API keys.
- 🔌 **Both local and Google calendars.** Reads everything through Evolution Data
  Server; add your Google account in *Settings → Online Accounts* and its events flow
  in automatically. A direct Google Calendar API provider is available as a fallback.
- 🔕 **System-tray control** — speak the time now, hear your next event, mute, and a
  small preferences panel.
- 🚀 **Starts at login** via a systemd user service.

## Offline behaviour

Offline-first is a core design goal:

| Feature | Works offline? |
|---|---|
| Neural voice (Piper) | ✅ Always — the voice model lives on disk. |
| Hourly time announcements | ✅ Always. |
| Local calendars (EDS) | ✅ Reads Evolution's on-disk cache. |
| Google events via GNOME Online Accounts | ✅ *fire* offline; the cache only refreshes while online. |
| Direct Google Calendar API (optional) | ❌ Needs live network at fetch time. |

If a calendar source fails (network down, token expired), tellme logs it and keeps
announcing everything else — time and local events never depend on the network.

## Install

```bash
git clone https://github.com/CyrilEtornam/tellme
cd tellme
./packaging/install.sh
```

This installs the system dependencies, the Python package, a default voice
(`en_US-lessac-medium`, ~63 MB), and a systemd user service that starts tellme at login.

### Manual steps

```bash
# System libraries
sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1 \
    gir1.2-edataserver-1.2 gir1.2-ecal-2.0 pulseaudio-utils

# The package + a voice
pip install --user .
./scripts/get-voice.sh en_US-lessac-medium

# Try it
tellme --speak-now
```

## Usage

```bash
tellme                 # run the background app (tray + announcements)
tellme --speak-now     # speak the current time and exit
tellme --say "hello"   # speak arbitrary text and exit
tellme --next-event    # print and speak your next upcoming event
```

Manage the background service:

```bash
systemctl --user status tellme
systemctl --user restart tellme
journalctl --user -u tellme -f
```

## Configuration

Config lives at `~/.config/tellme/config.toml` and can also be edited from the tray's
**Preferences…** panel. Defaults:

```toml
mute = false

[time]
enabled = true
interval_minutes = 60      # set to 30 for half-hour, 15 for quarters

[events]
enabled = true
lead_minutes = 5           # reminder this many minutes before an event
lookahead_hours = 24
poll_minutes = 5           # how often to refresh calendars

[voice]
model = "en_US-lessac-medium"

[calendars]
use_eds = true             # local + Google-via-GNOME-Online-Accounts
use_google_api = false     # direct Google Calendar API (optional)
```

### Choosing a voice

Any Piper voice works. Download another and point the config at it:

```bash
./scripts/get-voice.sh en_GB-alba-medium
```

Browse voices at <https://huggingface.co/rhasspy/piper-voices>. `low` models are
~20 MB, `medium` ~63 MB, `high` ~110 MB.

### Google Calendar without GNOME Online Accounts (optional)

Prefer the GNOME Online Accounts route above — it needs no setup. If you can't use it,
enable the direct API:

1. `pip install --user ".[google]"`
2. Create an **OAuth desktop client** in the Google Cloud Console and save it to
   `~/.config/tellme/google_client_secret.json`.
3. Set `use_google_api = true` in the config. First run opens a browser for consent;
   the token is cached at `~/.config/tellme/google_token.json`.

## Architecture

Single-process GTK app on one GLib main loop:

- `speaker.py` — Piper wrapper; lazy-loads the model, serializes utterances through a
  worker thread, plays via `paplay`/`aplay`.
- `phrases.py` — natural-language time and event phrasing (dependency-free).
- `scheduler.py` — when to announce (hourly boundary, event lead/start), with on-disk
  de-duplication so nothing repeats.
- `calendars/` — `EDSProvider` (local + Google via GOA), optional `GoogleCalendarProvider`,
  and an `aggregator` that merges, de-dups, and degrades gracefully.
- `app.py` — wires it together; `tray.py` / `prefs.py` provide the UI.

## Development

```bash
pip install pytest
python -m pytest          # runs the phrasing/config/scheduler/aggregator tests
```

## License

MIT
