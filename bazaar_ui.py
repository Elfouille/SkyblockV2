from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from ui.tab_items import BazaarItemListTab
from ui.tab_craft_tracker import BazaarCraftTrackerTab
from ui.tab_crafts import CraftsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Skyblock Hypixel Trading — JSON Core (no SQLite)")
        self.resize(1450, 860)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_craft_tracker = BazaarCraftTrackerTab(self)
        self.tab_items = BazaarItemListTab(self)
        self.tab_crafts = CraftsTab(self)

        self.tabs.addTab(self.tab_craft_tracker, "Tracker")
        self.tabs.addTab(self.tab_items, "Bazaar Items")
        self.tabs.addTab(self.tab_crafts, "Crafts")

        self.statusBar().showMessage("Ready")

        # auto refresh bazaar for items/crafts
        self.tab_items.refresh()
        self.tab_crafts.refresh_prices()


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
