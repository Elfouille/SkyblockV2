# ui/tab_minions.py
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from ui.tab_minions_collection import MinionsCollectionTab
from ui.tab_minions_profit import MinionsProfitTab


class MinionsTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window

        self.tabs = QTabWidget()
        self.tab_collection = MinionsCollectionTab(self)
        self.tab_profit = MinionsProfitTab(self)

        self.tabs.addTab(self.tab_collection, "Minions collection")
        self.tabs.addTab(self.tab_profit, "Minion profit")

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

    def apply_settings(self, settings) -> None:
        # si tu as un settings system, tu peux relayer ici
        pass
