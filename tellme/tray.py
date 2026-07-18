"""System-tray indicator (AppIndicator) with quick actions.

Constructed lazily by :meth:`tellme.app.TellmeApp.run`. If the AppIndicator
typelib isn't present the constructor raises and the app runs headless.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

log = logging.getLogger(__name__)


def _load_appindicator():
    """Return an AppIndicator module (Ayatana preferred), or raise ImportError."""
    for version, module in (
        ("0.1", "AyatanaAppIndicator3"),
        ("0.1", "AppIndicator3"),
    ):
        try:
            gi.require_version(module, version)
            return getattr(__import__("gi.repository", fromlist=[module]), module)
        except (ValueError, ImportError, AttributeError):
            continue
    raise ImportError("No AppIndicator typelib found")


class TrayIcon:
    def __init__(self, app) -> None:
        self.app = app
        AppIndicator3 = _load_appindicator()

        self.indicator = AppIndicator3.Indicator.new(
            "tellme",
            "alarm-symbolic",  # a themed clock/alarm icon present in most icon themes
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("tellme")
        self.indicator.set_menu(self._build_menu())

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        speak = Gtk.MenuItem(label="Speak time now")
        speak.connect("activate", lambda _w: self.app.speak_time_now())
        menu.append(speak)

        nxt = Gtk.MenuItem(label="Next event")
        nxt.connect("activate", lambda _w: self.app.announce_next_event())
        menu.append(nxt)

        menu.append(Gtk.SeparatorMenuItem())

        mute = Gtk.CheckMenuItem(label="Mute")
        mute.set_active(self.app.config.mute)
        mute.connect("toggled", lambda w: self.app.set_mute(w.get_active()))
        menu.append(mute)

        prefs = Gtk.MenuItem(label="Preferences…")
        prefs.connect("activate", lambda _w: self._open_preferences())
        menu.append(prefs)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _w: self.app.quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _open_preferences(self) -> None:
        from .prefs import PreferencesDialog

        dialog = PreferencesDialog(self.app)
        dialog.run()
        dialog.destroy()
