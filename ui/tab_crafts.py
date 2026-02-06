from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox
)

from common import CACHE_DIR, fmt_num, norm_item_id, load_json
from recipes_store import RecipesStore, Recipe
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


def _craft_cost_buy_from_bazaar(ingredients: List[Tuple[str, float]], prices: Dict[str, BazaarPrice]) -> float:
    # cost = sum(qty * sellPrice) (tu achètes au bazaar -> sellPrice)
    total = 0.0
    for iid, q in ingredients:
        p = prices.get(iid)
        if not p:
            return -1.0
        total += float(q) * float(p.sell)
    return total


def _craft_revenue_sell_to_bazaar(output: str, out_qty: float, prices: Dict[str, BazaarPrice]) -> float:
    # revenue = out_qty * buyPrice (tu vends au bazaar -> buyPrice)
    p = prices.get(output)
    if not p:
        return -1.0
    return float(out_qty) * float(p.buy)


class CraftsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.pool = QThreadPool.globalInstance()

        self.client = HypixelClient()
        self.prices: Dict[str, BazaarPrice] = {}

        self.store = RecipesStore(CACHE_DIR / "recipes.json")
        self.store.load()
        if not self.store.all():
            # si vide: essaie d'importer recipes_clean.json si présent dans le dossier projet
            fallback = Path(__file__).resolve().parent.parent / "recipes_clean.json"
            if fallback.exists():
                try:
                    data = json.loads(fallback.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        self.store.import_list(data)
                        self.store.save()
                except Exception:
                    pass

        root = QVBoxLayout(self)

        # Top bar
        top = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Bazaar")
        self.btn_import = QPushButton("Import recipes.json")
        self.btn_export = QPushButton("Export recipes.json")
        self.btn_clear = QPushButton("CLEAR ALL RECIPES")
        self.btn_clear.setStyleSheet("font-weight: 700;")
        self.lbl_status = QLabel("—")
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_import)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_clear)
        top.addWidget(self.lbl_status, 1)
        root.addLayout(top)

        # Search
        search = QHBoxLayout()
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText("Filter output item id… (ex: ENCHANTED_SUGAR)")
        search.addWidget(QLabel("Filter:"))
        search.addWidget(self.ed_filter, 1)
        root.addLayout(search)

        # Tree (Outputs -> variants -> ingredients)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Output", "OutQty", "Cost (buy)", "Revenue (sell)", "Profit", "Notes"])
        root.addWidget(self.tree, 1)

        # wire
        self.btn_refresh.clicked.connect(self.refresh_prices)
        self.btn_import.clicked.connect(self.import_recipes)
        self.btn_export.clicked.connect(self.export_recipes)
        self.btn_clear.clicked.connect(self.clear_all)
        self.ed_filter.textChanged.connect(self.rebuild_tree)

        self.rebuild_tree()

    def refresh_prices(self) -> None:
        self.lbl_status.setText("Fetching…")
        task = _FetchBazaarTask(self.client)
        task.signals.done.connect(self._on_prices)
        self.pool.start(task)

    def _on_prices(self, prices: dict, fresh: bool, err: str) -> None:
        if err:
            self.lbl_status.setText("Error")
            QMessageBox.critical(self, "Hypixel API", err)
            return
        self.prices = prices
        self.lbl_status.setText("OK (API)" if fresh else "OK (cache)")
        self.rebuild_tree()

    def rebuild_tree(self) -> None:
        flt = norm_item_id(self.ed_filter.text())
        self.tree.clear()

        outputs = sorted({r.output for r in self.store.all()})
        for out in outputs:
            if flt and flt not in out:
                continue

            variants = self.store.variants(out)
            if not variants:
                continue

            out_item = QTreeWidgetItem([out, "", "", "", "", f"{len(variants)} variant(s)"])
            self.tree.addTopLevelItem(out_item)

            for r in variants:
                cost = _craft_cost_buy_from_bazaar(r.ingredients, self.prices) if self.prices else -1.0
                rev = _craft_revenue_sell_to_bazaar(r.output, r.output_qty, self.prices) if self.prices else -1.0
                profit = (rev - cost) if (cost >= 0 and rev >= 0) else -1.0

                cost_s = "—" if cost < 0 else fmt_num(cost)
                rev_s = "—" if rev < 0 else fmt_num(rev)
                prof_s = "—" if profit < 0 else fmt_num(profit)

                v_item = QTreeWidgetItem([r.output, str(r.output_qty), cost_s, rev_s, prof_s, ""])
                v_item.setData(0, Qt.UserRole, r.signature())
                out_item.addChild(v_item)

                # ingredients children
                for iid, q in r.ingredients:
                    p = self.prices.get(iid)
                    unit = p.sell if p else 0.0
                    line = (float(q) * float(unit)) if p else 0.0
                    ing = QTreeWidgetItem([f"  ↳ {iid}", str(q), fmt_num(line) if p else "—", "", "", "ingredient"])
                    v_item.addChild(ing)

            out_item.setExpanded(True)

    def import_recipes(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(self, "Import recipes JSON", str(Path.cwd()), "JSON (*.json);;All (*.*)")
        if not fn:
            return
        try:
            data = json.loads(Path(fn).read_text(encoding="utf-8"))
            if isinstance(data, dict) and "recipes" in data:
                data = data["recipes"]
            if not isinstance(data, list):
                raise ValueError("JSON must be a list (or {recipes:[...]})")
            n = self.store.import_list(data)
            self.store.save()
            self.lbl_status.setText(f"Imported: {n}")
            self.rebuild_tree()
        except Exception as e:
            QMessageBox.critical(self, "Import error", str(e))

    def export_recipes(self) -> None:
        fn, _ = QFileDialog.getSaveFileName(self, "Export recipes JSON", str(Path.cwd() / "recipes_export.json"), "JSON (*.json)")
        if not fn:
            return
        try:
            payload = {"version": 1, "recipes": [r.to_dict() for r in self.store.all()]}
            Path(fn).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.lbl_status.setText("Exported.")
        except Exception as e:
            QMessageBox.critical(self, "Export error", str(e))

    def clear_all(self) -> None:
        # pas de confirmation “infinie” : 1 seule box
        ok = QMessageBox.question(self, "Clear all", "Supprimer TOUTES les recettes ? (irréversible)")
        if ok != QMessageBox.StandardButton.Yes:
            return
        self.store.clear()
        self.store.save()
        self.lbl_status.setText("All recipes cleared.")
        self.rebuild_tree()
