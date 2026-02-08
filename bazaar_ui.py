from __future__ import annotations

import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from settings import AppSettings, load_settings
from ui.tab_items import BazaarItemListTab
from ui.tab_craft_tracker import BazaarCraftTrackerTab
from ui.tab_crafts import CraftsTab
from ui.tab_settings import SettingsTab
from ui.tab_museum import MuseumTab
from ui.tab_minions import MinionsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Skyblock Hypixel Trading — JSON Core (no SQLite)")
        self.resize(1450, 860)

        self.settings = load_settings()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_settings = SettingsTab(self)
        self.tab_craft_tracker = BazaarCraftTrackerTab(self)
        self.tab_items = BazaarItemListTab(self)
        self.tab_crafts = CraftsTab(self)
        self.tab_museum = MuseumTab(self)
        self.tab_minions = MinionsTab(self)

        self.tabs.addTab(self.tab_settings, "Paramètres")
        self.tabs.addTab(self.tab_craft_tracker, "Tracker")
        self.tabs.addTab(self.tab_items, "Bazaar Items")
        self.tabs.addTab(self.tab_crafts, "Crafts")
        self.tabs.addTab(self.tab_museum, "Musée")
        self.tabs.addTab(self.tab_minions, "Mignons")

        # --- Auto-refresh timer (visuel + déclenchement items/crafts) ---
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)  # tick 1s (compteur)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)

        self._refresh_interval_sec = 60
        self._refresh_remaining_sec = 60
        self._last_tick_monotonic = time.monotonic()

        self._restart_auto_refresh_timer()

        # Auto refresh au lancement (si activé)
        if self.settings.auto_refresh_items:
            self.tab_items.refresh()
        if self.settings.auto_refresh_crafts:
            self.tab_crafts.refresh_prices()
        # Museum : géré par son propre timer via settings (apply_settings du tab)
        # -> si tu veux un refresh immédiat au lancement quand auto-refresh museum est ON :
        if getattr(self.settings, "auto_refresh_museum", False):
            self.tab_museum.refresh()

    # ----------------------------
    # Apply settings
    # ----------------------------
    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings

        # Propager aux tabs (si elles ont apply_settings)
        if getattr(self, "tab_items", None) is not None:
            self.tab_items.apply_settings(settings)
        if getattr(self, "tab_crafts", None) is not None:
            self.tab_crafts.apply_settings(settings)
        if getattr(self, "tab_museum", None) is not None:
            self.tab_museum.apply_settings(settings)

        # Recalcule l’interval + reset du compteur visuel (items/crafts)
        self._restart_auto_refresh_timer()

    # ----------------------------
    # Auto refresh timer (Items/Crafts)
    # ----------------------------
    def _restart_auto_refresh_timer(self) -> None:
        # interval en sec (fallback 60)
        try:
            interval = int(getattr(self.settings, "bazaar_cache_seconds", 60))
        except Exception:
            interval = 60

        # sécurité anti-spam
        interval = max(5, interval)

        self._refresh_interval_sec = interval
        self._refresh_remaining_sec = interval
        self._last_tick_monotonic = time.monotonic()

        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

        self._update_refresh_status()

    def _on_refresh_tick(self) -> None:
        # tick robuste (si freeze, on rattrape)
        now = time.monotonic()
        elapsed = int(now - self._last_tick_monotonic)
        if elapsed <= 0:
            elapsed = 1
        self._last_tick_monotonic = now

        self._refresh_remaining_sec -= elapsed
        if self._refresh_remaining_sec <= 0:
            # déclenche refresh selon settings
            if getattr(self.settings, "auto_refresh_items", False):
                self.tab_items.refresh()
            if getattr(self.settings, "auto_refresh_crafts", False):
                self.tab_crafts.refresh_prices()

            # reset countdown
            self._refresh_remaining_sec = self._refresh_interval_sec

        self._update_refresh_status()

    def _update_refresh_status(self) -> None:
        items_on = "ON" if getattr(self.settings, "auto_refresh_items", False) else "OFF"
        crafts_on = "ON" if getattr(self.settings, "auto_refresh_crafts", False) else "OFF"
        museum_on = "ON" if getattr(self.settings, "auto_refresh_museum", False) else "OFF"

        sec = max(0, int(self._refresh_remaining_sec))
        mm = sec // 60
        ss = sec % 60

        self.statusBar().showMessage(
            f"AutoRefresh Items:{items_on} | Crafts:{crafts_on} | Museum:{museum_on} | "
            f"Refresh items/crafts dans {mm:02d}:{ss:02d} (interval {self._refresh_interval_sec}s)"
        )


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
