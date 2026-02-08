from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QCheckBox,
)

from common import fmt_num
from hypixel_client import HypixelClient, BazaarPrice


class _Signals(QObject):
    done = Signal(dict, bool, str)  # prices, fresh, err


class _FetchBazaarTask(QRunnable):
    def __init__(self, client: HypixelClient, max_age_sec: int):
        super().__init__()
        self.client = client
        self.max_age_sec = max_age_sec
        self.signals = _Signals()

    def run(self) -> None:
        try:
            prices, fresh = self.client.load_bazaar_cached(max_age_sec=self.max_age_sec)
            self.signals.done.emit(prices, fresh, "")
        except Exception as e:
            self.signals.done.emit({}, False, str(e))


def _num_item(value: float, text: str | None = None) -> QTableWidgetItem:
    """
    Table item that sorts numerically (Qt.UserRole) while displaying formatted text.
    """
    it = QTableWidgetItem(text if text is not None else fmt_num(value))
    it.setData(Qt.UserRole, float(value))
    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


def _safe_get(p: object, *names: str, default: float = 0.0) -> float:
    for n in names:
        if hasattr(p, n):
            v = getattr(p, n)
            try:
                return float(v)
            except Exception:
                pass
    return float(default)


class BazaarItemListTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.pool = QThreadPool.globalInstance()

        self.client = HypixelClient(self.main.settings.api_key)
        self.prices: Dict[str, BazaarPrice] = {}

        root = QVBoxLayout(self)

        # Top bar
        top = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Bazaar")
        self.lbl_status = QLabel("—")

        # Switches
        self.chk_buy_instant = QCheckBox("Buy: Instant (sinon Order)")
        self.chk_sell_instant = QCheckBox("Sell: Instant (sinon Order)")

        # Par défaut: “order” (checkbox unchecked)
        self.chk_buy_instant.setChecked(False)
        self.chk_sell_instant.setChecked(False)

        top.addWidget(self.btn_refresh)
        top.addWidget(self.chk_buy_instant)
        top.addWidget(self.chk_sell_instant)
        top.addWidget(self.lbl_status, 1)
        root.addLayout(top)

        # Table
        headers = [
            "Item ID",
            "Buy",
            "Sell",
            "Vol Buy",
            "Vol Sell",
            "Nb Buy 24h",
            "Nb Sell 24h",
            "Profit (Sell-Buy)",
            "Coef (Sell*100/Buy)",
        ]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSortingEnabled(True)
        root.addWidget(self.table, 1)

        self.btn_refresh.clicked.connect(self.refresh)
        self.chk_buy_instant.toggled.connect(self._rebuild_table)
        self.chk_sell_instant.toggled.connect(self._rebuild_table)

    def apply_settings(self, settings) -> None:
        self.client.key = settings.api_key

    def refresh(self) -> None:
        self.lbl_status.setText("Fetching…")
        max_age = int(getattr(self.main.settings, "bazaar_cache_seconds", 60))
        task = _FetchBazaarTask(self.client, max_age)
        task.signals.done.connect(self._on_done)
        self.pool.start(task)

    def _on_done(self, prices: dict, fresh: bool, err: str) -> None:
        if err:
            self.lbl_status.setText("Error")
            QMessageBox.critical(self, "Hypixel API", err)
            return

        self.prices = prices
        self.lbl_status.setText("OK (API)" if fresh else "OK (cache)")
        self._rebuild_table()

    def _pick_buy_price(self, p: BazaarPrice) -> float:
        # Hypothèses (fallbacks) selon ton client:
        # - order: buy_order / buyOrder / buy
        # - instant: buy_instant / buyInstant / buy
        if self.chk_buy_instant.isChecked():
            return _safe_get(p, "buy_instant", "buyInstant", "buy", default=0.0)
        return _safe_get(p, "buy_order", "buyOrder", "buy", default=0.0)

    def _pick_sell_price(self, p: BazaarPrice) -> float:
        # Hypothèses (fallbacks) selon ton client:
        # - order: sell_order / sellOrder / sell
        # - instant: sell_instant / sellInstant / sell
        if self.chk_sell_instant.isChecked():
            return _safe_get(p, "sell_instant", "sellInstant", "sell", default=0.0)
        return _safe_get(p, "sell_order", "sellOrder", "sell", default=0.0)

    def _rebuild_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for item_id, p in sorted(self.prices.items()):
            buy_price = self._pick_buy_price(p)
            sell_price = self._pick_sell_price(p)

            vol_buy = _safe_get(p, "buy_volume", "buyVolume", default=0.0)
            vol_sell = _safe_get(p, "sell_volume", "sellVolume", default=0.0)

            # “nombre de vente et achat sur 24h”
            # Selon ton parseur ça peut s’appeler différemment -> on met plusieurs fallbacks.
            nb_buy_24h = _safe_get(p, "buy_24h", "buy24h", "buy_count_24h", "buyCount24h", default=0.0)
            nb_sell_24h = _safe_get(p, "sell_24h", "sell24h", "sell_count_24h", "sellCount24h", default=0.0)

            profit = sell_price - buy_price
            coef = (sell_price * 100.0 / buy_price) if buy_price > 0 else 0.0

            r = self.table.rowCount()
            self.table.insertRow(r)

            # Col 0: item id (texte)
            self.table.setItem(r, 0, QTableWidgetItem(item_id))

            # Cols numériques: tri numérique + affichage formaté
            self.table.setItem(r, 1, _num_item(buy_price))
            self.table.setItem(r, 2, _num_item(sell_price))
            self.table.setItem(r, 3, _num_item(vol_buy))
            self.table.setItem(r, 4, _num_item(vol_sell))
            self.table.setItem(r, 5, _num_item(nb_buy_24h))
            self.table.setItem(r, 6, _num_item(nb_sell_24h))
            self.table.setItem(r, 7, _num_item(profit))
            self.table.setItem(r, 8, _num_item(coef, text=f"{coef:.2f}"))

        self.table.setSortingEnabled(True)
