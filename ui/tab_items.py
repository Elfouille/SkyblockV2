from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem, QMessageBox

from common import fmt_num
from hypixel_client import HypixelClient, BazaarPrice


class _Signals(QObject):
    done = Signal(dict, bool, str)  # prices, fresh, err


class _FetchBazaarTask(QRunnable):
    def __init__(self, client: HypixelClient):
        super().__init__()
        self.client = client
        self.signals = _Signals()

    def run(self) -> None:
        try:
            prices, fresh = self.client.load_bazaar_cached(max_age_sec=60)
            self.signals.done.emit(prices, fresh, "")
        except Exception as e:
            self.signals.done.emit({}, False, str(e))


class BazaarItemListTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.pool = QThreadPool.globalInstance()

        self.client = HypixelClient()

        self.prices: Dict[str, BazaarPrice] = {}

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Bazaar")
        self.lbl_status = QLabel("—")
        top.addWidget(self.btn_refresh)
        top.addWidget(self.lbl_status, 1)
        root.addLayout(top)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Item ID", "Buy (sell to bazaar)", "Sell (buy from bazaar)"])
        self.table.setSortingEnabled(True)
        root.addWidget(self.table, 1)

        self.btn_refresh.clicked.connect(self.refresh)

    def refresh(self) -> None:
        self.lbl_status.setText("Fetching…")
        task = _FetchBazaarTask(self.client)
        task.signals.done.connect(self._on_done)
        self.pool.start(task)

    def _on_done(self, prices: dict, fresh: bool, err: str) -> None:
        if err:
            self.lbl_status.setText("Error")
            QMessageBox.critical(self, "Hypixel API", err)
            return

        self.prices = prices
        self.lbl_status.setText("OK (API)" if fresh else "OK (cache)")

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for item_id, p in sorted(self.prices.items()):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(item_id))
            self.table.setItem(r, 1, QTableWidgetItem(fmt_num(p.buy)))
            self.table.setItem(r, 2, QTableWidgetItem(fmt_num(p.sell)))

        self.table.setSortingEnabled(True)
