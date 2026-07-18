"""Configuration loading and saving for tellme.

Config lives at ``~/.config/tellme/config.toml``. Reading uses the stdlib
``tomllib`` (Python 3.11+); writing uses a tiny hand-rolled serializer so we
don't need a third-party TOML writer for our small, flat schema.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


def _xdg(env: str, default: Path) -> Path:
    value = os.environ.get(env)
    return Path(value) if value else default


HOME = Path.home()
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", HOME / ".config") / "tellme"
DATA_DIR = _xdg("XDG_DATA_HOME", HOME / ".local" / "share") / "tellme"
STATE_DIR = _xdg("XDG_STATE_HOME", HOME / ".local" / "state") / "tellme"

CONFIG_PATH = CONFIG_DIR / "config.toml"
VOICES_DIR = DATA_DIR / "voices"
ANNOUNCED_PATH = STATE_DIR / "announced.json"
GOOGLE_TOKEN_PATH = CONFIG_DIR / "google_token.json"
GOOGLE_CLIENT_SECRET_PATH = CONFIG_DIR / "google_client_secret.json"

DEFAULT_VOICE = "en_US-lessac-medium"


@dataclass
class TimeConfig:
    enabled: bool = True
    interval_minutes: int = 60


@dataclass
class EventsConfig:
    enabled: bool = True
    lead_minutes: int = 5
    # How far ahead to look for events, and how often to refresh the cache.
    lookahead_hours: int = 24
    poll_minutes: int = 5


@dataclass
class VoiceConfig:
    model: str = DEFAULT_VOICE


@dataclass
class CalendarsConfig:
    use_eds: bool = True
    use_google_api: bool = False


@dataclass
class Config:
    mute: bool = False
    time: TimeConfig = field(default_factory=TimeConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    calendars: CalendarsConfig = field(default_factory=CalendarsConfig)

    # --- (de)serialization -------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Build a Config, ignoring unknown keys and filling in defaults."""
        cfg = cls()
        if "mute" in data:
            cfg.mute = bool(data["mute"])
        _apply_section(cfg.time, data.get("time"))
        _apply_section(cfg.events, data.get("events"))
        _apply_section(cfg.voice, data.get("voice"))
        _apply_section(cfg.calendars, data.get("calendars"))
        return cfg

    def to_toml(self) -> str:
        lines = [
            "# tellme configuration",
            f"mute = {_toml_value(self.mute)}",
            "",
        ]
        for name, section in (
            ("time", self.time),
            ("events", self.events),
            ("voice", self.voice),
            ("calendars", self.calendars),
        ):
            lines.append(f"[{name}]")
            for key, value in asdict(section).items():
                lines.append(f"{key} = {_toml_value(value)}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _apply_section(section: Any, data: Any) -> None:
    if not isinstance(data, dict):
        return
    valid = {f.name: f.type for f in fields(section)}
    for key, value in data.items():
        if key in valid:
            setattr(section, key, value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # Strings — escape backslashes and quotes for a basic TOML string.
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Load config from disk, returning defaults if the file is missing or invalid."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return Config()
    return Config.from_dict(data)


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    """Write config to disk, creating the config directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(cfg.to_toml(), encoding="utf-8")
    tmp.replace(path)


def ensure_dirs() -> None:
    """Create the config/data/state directories used by tellme."""
    for directory in (CONFIG_DIR, VOICES_DIR, STATE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
