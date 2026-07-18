"""GTK preferences dialog.

Edits the on-disk config and asks the running app to reload it. Kept simple: a
handful of switches and spin buttons in a single grid.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import config as cfg_mod  # noqa: E402


class PreferencesDialog(Gtk.Dialog):
    def __init__(self, app) -> None:
        super().__init__(title="tellme Preferences", flags=0)
        self.app = app
        self.set_default_size(380, -1)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        )

        cfg = app.config
        grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin=16)
        row = 0

        self._speak_time = self._add_switch(grid, row, "Announce the time", cfg.time.enabled)
        row += 1
        self._interval = self._add_spin(
            grid, row, "Time interval (minutes)", cfg.time.interval_minutes, 1, 720
        )
        row += 1
        self._speak_events = self._add_switch(
            grid, row, "Announce calendar events", cfg.events.enabled
        )
        row += 1
        self._lead = self._add_spin(
            grid, row, "Reminder lead time (minutes)", cfg.events.lead_minutes, 0, 120
        )
        row += 1
        self._mute = self._add_switch(grid, row, "Mute", cfg.mute)
        row += 1
        self._voice = self._add_entry(grid, row, "Voice model", cfg.voice.model)
        row += 1
        self._use_eds = self._add_switch(
            grid, row, "Read local / GNOME calendars (EDS)", cfg.calendars.use_eds
        )
        row += 1
        self._use_google = self._add_switch(
            grid, row, "Use direct Google Calendar API", cfg.calendars.use_google_api
        )
        row += 1

        box = self.get_content_area()
        box.add(grid)
        self.show_all()

    # --- widget helpers ----------------------------------------------------
    def _add_switch(self, grid, row, label, active) -> Gtk.Switch:
        grid.attach(_label(label), 0, row, 1, 1)
        switch = Gtk.Switch()
        switch.set_active(active)
        switch.set_halign(Gtk.Align.START)
        grid.attach(switch, 1, row, 1, 1)
        return switch

    def _add_spin(self, grid, row, label, value, lo, hi) -> Gtk.SpinButton:
        grid.attach(_label(label), 0, row, 1, 1)
        spin = Gtk.SpinButton.new_with_range(lo, hi, 1)
        spin.set_value(value)
        grid.attach(spin, 1, row, 1, 1)
        return spin

    def _add_entry(self, grid, row, label, value) -> Gtk.Entry:
        grid.attach(_label(label), 0, row, 1, 1)
        entry = Gtk.Entry()
        entry.set_text(value)
        grid.attach(entry, 1, row, 1, 1)
        return entry

    # --- save --------------------------------------------------------------
    def run(self) -> int:
        response = super().run()
        if response == Gtk.ResponseType.OK:
            self._save()
        return response

    def _save(self) -> None:
        cfg = self.app.config
        cfg.time.enabled = self._speak_time.get_active()
        cfg.time.interval_minutes = int(self._interval.get_value())
        cfg.events.enabled = self._speak_events.get_active()
        cfg.events.lead_minutes = int(self._lead.get_value())
        cfg.mute = self._mute.get_active()
        cfg.voice.model = self._voice.get_text().strip() or cfg.voice.model
        cfg.calendars.use_eds = self._use_eds.get_active()
        cfg.calendars.use_google_api = self._use_google.get_active()
        cfg_mod.save_config(cfg)
        self.app.reload_config()


def _label(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_halign(Gtk.Align.START)
    return label
