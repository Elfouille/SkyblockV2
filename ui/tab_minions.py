# ui/tab_minions.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
)

from common import CACHE_DIR, load_json, save_json, fmt_num
from hypixel_client import HypixelClient


# ----------------------------
# Styles (Minecraft-ish)
# ----------------------------
BR_GREEN = QBrush(QColor(220, 255, 220))
BR_RED = QBrush(QColor(255, 220, 220))
BR_GRAY = QBrush(QColor(245, 245, 245))


# ----------------------------
# Files
# ----------------------------
MINION_STATS_FILE = CACHE_DIR / "minion_stats.json"
ITEMS_CACHE = CACHE_DIR / "hypixel_items_cache.json"


# ----------------------------
# Helpers
# ----------------------------
def _load_minion_stats() -> Dict[str, Any]:
    raw = load_json(MINION_STATS_FILE, default={})
    return raw if isinstance(raw, dict) else {}


def _norm_uuid(u: str) -> str:
    return (u or "").replace("-", "").lower().strip()


def _extract_profiles_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    profs = payload.get("profiles")
    if isinstance(profs, list):
        return [p for p in profs if isinstance(p, dict)]
    return []


def _pick_profile_by_name(profiles: List[Dict[str, Any]], cute_name: str) -> Optional[Dict[str, Any]]:
    target = (cute_name or "").strip().lower()
    for p in profiles:
        name = str(p.get("cute_name") or "").strip().lower()
        if name == target:
            return p
    return None


def _get_member(profile: Dict[str, Any], uuid: str) -> Optional[Dict[str, Any]]:
    members = profile.get("members")
    if not isinstance(members, dict):
        return None
    return members.get(_norm_uuid(uuid)) or members.get(uuid)


def _parse_crafted_generators(member: Dict[str, Any]) -> Dict[str, bool]:
    cg = member.get("crafted_generators")
    out: Dict[str, bool] = {}

    if isinstance(cg, dict):
        for k, v in cg.items():
            out[str(k)] = bool(v)
        return out

    if isinstance(cg, list):
        for k in cg:
            out[str(k)] = True
        return out

    return out


def _split_minion_key(k: str) -> Tuple[str, Optional[int]]:
    s = (k or "").strip()
    if not s:
        return "", None
    if "_" not in s:
        return s, None
    base, tier_s = s.rsplit("_", 1)
    try:
        return base, int(tier_s)
    except Exception:
        return s, None


def _aggregate_unlocked(crafted_generators: Dict[str, bool]) -> Dict[str, Dict[int, bool]]:
    mp: Dict[str, Dict[int, bool]] = {}
    for k, v in crafted_generators.items():
        base, tier = _split_minion_key(k)
        if not base or tier is None:
            continue
        mp.setdefault(base, {})
        mp[base][tier] = bool(v)
    return mp


def _tiers_summary(tiers: Dict[int, bool], max_tier: int = 11) -> str:
    parts = []
    for t in range(1, max_tier + 1):
        parts.append("✓" if tiers.get(t) else "✗")
    return " ".join(parts)


def generate_minion_stats_from_items_cache() -> Tuple[int, Path]:
    """
    Génère cache/minion_stats.json à partir de cache/hypixel_items_cache.json
    -> liste tous les minions + tiers trouvés via champs 'generator'/'generator_tier'
    -> AJOUTE un placeholder tier11 à remplir (seconds_per_action + drops)
    """
    raw = load_json(ITEMS_CACHE, default={})
    if not isinstance(raw, dict):
        raise RuntimeError("hypixel_items_cache.json invalide (pas un dict).")

    items = raw.get("items")
    if not isinstance(items, dict):
        # fallback: parfois c'est déjà la map id->item
        items = raw if isinstance(raw, dict) else {}

    out: Dict[str, Any] = {}

    for item_id, it in items.items():
        if not isinstance(it, dict):
            continue

        gen = it.get("generator")
        tier = it.get("generator_tier")
        if not gen or tier is None:
            continue

        try:
            tier_i = int(tier)
        except Exception:
            continue

        gen = str(gen).strip().upper()
        if not gen:
            continue

        entry = out.setdefault(gen, {"tiers": {}, "tier11": None})

        entry["tiers"][str(tier_i)] = {
            "item_id": str(it.get("id") or item_id),
            "name": str(it.get("name") or ""),
            "rarity": str(it.get("tier") or ""),
        }

        if tier_i == 11 and entry.get("tier11") is None:
            entry["tier11"] = {
                "seconds_per_action": 0,
                "drops": [],  # [{"item":"...", "qty":1}]
                "notes": "AUTO from hypixel_items_cache.json: fill drops + seconds manually or via external dataset",
            }

    out_sorted = dict(sorted(out.items(), key=lambda kv: kv[0]))
    save_json(MINION_STATS_FILE, out_sorted)
    return (len(out_sorted), MINION_STATS_FILE)


# ----------------------------
# Sub-tab: Minions unlocked
# ----------------------------
class MinionsUnlockedTab(QWidget):
    def __init__(self, parent: "MinionsTab"):
        super().__init__(parent)
        self.host = parent

        top = QHBoxLayout()
        self.uuid_edit = QLineEdit()
        self.uuid_edit.setPlaceholderText("UUID (avec ou sans tirets)")

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.addItem("— Profil —")

        self.btn_load_profiles = QPushButton("Charger profils")
        self.btn_refresh = QPushButton("Refresh minions")

        top.addWidget(QLabel("Joueur:"))
        top.addWidget(self.uuid_edit, 2)
        top.addWidget(self.btn_load_profiles)
        top.addSpacing(10)
        top.addWidget(QLabel("Profil:"))
        top.addWidget(self.profile_combo, 1)
        top.addWidget(self.btn_refresh)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Mignon", "Tiers (1..11)", "Tier max crafté", "Statut"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)

        self.btn_load_profiles.clicked.connect(self.load_profiles)
        self.btn_refresh.clicked.connect(self.refresh)

        self._profiles_cache: List[Dict[str, Any]] = []

    def _client(self) -> HypixelClient:
        return self.host.client

    def load_profiles(self) -> None:
        uuid = _norm_uuid(self.uuid_edit.text())
        if not uuid:
            QMessageBox.warning(self, "UUID manquant", "Entre un UUID.")
            return

        try:
            data = self._client().fetch_profiles(uuid)
        except Exception as e:
            QMessageBox.critical(self, "Erreur API", str(e))
            return

        profs = _extract_profiles_list(data)
        self._profiles_cache = profs

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("— Profil —")
        for p in profs:
            self.profile_combo.addItem(str(p.get("cute_name") or p.get("profile_id") or "???"))
        self.profile_combo.blockSignals(False)

        if profs:
            self.profile_combo.setCurrentIndex(1)
        self.refresh()

    def _get_selected_profile(self) -> Optional[Dict[str, Any]]:
        if not self._profiles_cache:
            return None
        idx = self.profile_combo.currentIndex()
        if idx <= 0:
            return self._profiles_cache[0]
        name = self.profile_combo.currentText()
        p = _pick_profile_by_name(self._profiles_cache, name)
        return p or self._profiles_cache[0]

    def refresh(self) -> None:
        uuid = _norm_uuid(self.uuid_edit.text())
        if not uuid:
            return

        profile = self._get_selected_profile()
        if not profile:
            try:
                data = self._client().fetch_profiles(uuid)
                self._profiles_cache = _extract_profiles_list(data)
                profile = self._profiles_cache[0] if self._profiles_cache else None
            except Exception:
                profile = None

        if not profile:
            QMessageBox.warning(self, "Profil introuvable", "Impossible de récupérer un profil SkyBlock.")
            return

        member = _get_member(profile, uuid)
        if not member:
            QMessageBox.warning(self, "Membre introuvable", "Ce joueur n'est pas dans ce profil.")
            return

        crafted = _parse_crafted_generators(member)
        unlocked = _aggregate_unlocked(crafted)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        all_minions = sorted(unlocked.keys())
        for base in all_minions:
            tiers = unlocked.get(base, {})
            max_tier = max([t for t, ok in tiers.items() if ok] or [0])

            row = self.table.rowCount()
            self.table.insertRow(row)

            it_name = QTableWidgetItem(base)
            it_tiers = QTableWidgetItem(_tiers_summary(tiers, 11))
            it_max = QTableWidgetItem(str(max_tier if max_tier > 0 else "—"))

            crafted_any = any(bool(v) for v in tiers.values())
            it_status = QTableWidgetItem("CRAFT" if crafted_any else "NO")
            brush = BR_GREEN if crafted_any else BR_RED
            for it in (it_name, it_tiers, it_max, it_status):
                it.setBackground(brush)

            self.table.setItem(row, 0, it_name)
            self.table.setItem(row, 1, it_tiers)
            self.table.setItem(row, 2, it_max)
            self.table.setItem(row, 3, it_status)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()


# ----------------------------
# Sub-tab: Minions profit (V1 simple globale)
# ----------------------------
class MinionsProfitTab(QWidget):
    """
    V1 globale :
    - Prix = bazaar BUY (highest buy order)
    - Paramètres globaux appliqués à tous les minions:
        speed_mult, hopper_tax, compactor_ratio
    - Compactor V1: applique juste un ratio sur la valeur (placeholder),
      parce que la vraie conversion dépend de l'item (ex: 160 cobble -> 1 enchanted cobble)
      -> on laisse OFF par défaut.
    """
    def __init__(self, parent: "MinionsTab"):
        super().__init__(parent)
        self.host = parent

        # -------- Controls row 1
        top1 = QHBoxLayout()
        self.btn_generate_stats = QPushButton("Générer minion_stats.json (depuis items cache)")
        self.btn_reload_stats = QPushButton("Reload stats (JSON)")
        self.btn_refresh = QPushButton("Refresh (prix + calcul)")

        self.note = QLabel("Prix: BUY bazaar | Stats: cache/minion_stats.json (tier11)")

        top1.addWidget(self.btn_generate_stats)
        top1.addWidget(self.btn_reload_stats)
        top1.addWidget(self.btn_refresh)
        top1.addStretch(1)
        top1.addWidget(self.note)

        # -------- Controls row 2 (global params)
        top2 = QHBoxLayout()

        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setDecimals(3)
        self.spin_speed.setRange(0.10, 10.00)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(1.00)

        self.chk_hopper = QCheckBox("Hopper")
        self.spin_hopper_tax = QDoubleSpinBox()
        self.spin_hopper_tax.setSuffix(" %")
        self.spin_hopper_tax.setDecimals(2)
        self.spin_hopper_tax.setRange(0.0, 95.0)
        self.spin_hopper_tax.setSingleStep(0.5)
        self.spin_hopper_tax.setValue(10.0)
        self.spin_hopper_tax.setEnabled(False)

        self.chk_compactor = QCheckBox("Compactor (V1)")
        self.spin_compactor_ratio = QDoubleSpinBox()
        self.spin_compactor_ratio.setDecimals(4)
        self.spin_compactor_ratio.setRange(0.0001, 1.0000)
        self.spin_compactor_ratio.setSingleStep(0.01)
        self.spin_compactor_ratio.setValue(1.0000)
        self.spin_compactor_ratio.setEnabled(False)

        top2.addWidget(QLabel("Speed x"))
        top2.addWidget(self.spin_speed)
        top2.addSpacing(12)
        top2.addWidget(self.chk_hopper)
        top2.addWidget(QLabel("Tax"))
        top2.addWidget(self.spin_hopper_tax)
        top2.addSpacing(12)
        top2.addWidget(self.chk_compactor)
        top2.addWidget(QLabel("Ratio valeur"))
        top2.addWidget(self.spin_compactor_ratio)
        top2.addStretch(1)

        # -------- Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Mignon", "sec/action", "items/action", "actions/h", "items/h", "prix (BUY)", "profit/h", "profit/j"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        lay = QVBoxLayout(self)
        lay.addLayout(top1)
        lay.addLayout(top2)
        lay.addWidget(self.table)

        # signals
        self.btn_generate_stats.clicked.connect(self.generate_stats)
        self.btn_reload_stats.clicked.connect(self.reload_stats)
        self.btn_refresh.clicked.connect(self.refresh)

        self.chk_hopper.toggled.connect(self._on_hopper_toggle)
        self.chk_compactor.toggled.connect(self._on_compactor_toggle)

        self.spin_speed.valueChanged.connect(lambda _v: self.refresh())
        self.spin_hopper_tax.valueChanged.connect(lambda _v: self.refresh())
        self.spin_compactor_ratio.valueChanged.connect(lambda _v: self.refresh())

        # data
        self._stats = _load_minion_stats()
        self._bazaar_prices: Dict[str, Tuple[float, float]] = {}  # item_id -> (buy, sell)

        self.refresh()

    def _on_hopper_toggle(self, on: bool) -> None:
        self.spin_hopper_tax.setEnabled(on)
        self.refresh()

    def _on_compactor_toggle(self, on: bool) -> None:
        self.spin_compactor_ratio.setEnabled(on)
        self.refresh()

    def generate_stats(self) -> None:
        try:
            n, path = generate_minion_stats_from_items_cache()
        except Exception as e:
            QMessageBox.critical(self, "Erreur génération", str(e))
            return

        QMessageBox.information(self, "OK", f"Généré: {path}\nMinions trouvés: {n}\n\n"
                                           f"⚠️ Il faut remplir tier11.seconds_per_action + drops pour le profit.")
        self.reload_stats()

    def reload_stats(self) -> None:
        self._stats = _load_minion_stats()
        self.refresh()

    def refresh(self) -> None:
        # ----- load bazaar prices (buy/sell)
        try:
            max_age = int(getattr(self.host.main.settings, "bazaar_cache_seconds", 60))
        except Exception:
            max_age = 60

        try:
            prices, _fresh = self.host.client.load_bazaar_cached(max_age_sec=max_age)
            self._bazaar_prices = {k: (v.buy, v.sell) for k, v in prices.items()}
        except Exception:
            self._bazaar_prices = {}

        # ----- global params
        speed_mult = float(self.spin_speed.value())
        hopper_on = self.chk_hopper.isChecked()
        hopper_tax = float(self.spin_hopper_tax.value()) / 100.0 if hopper_on else 0.0
        compactor_on = self.chk_compactor.isChecked()
        compactor_ratio = float(self.spin_compactor_ratio.value()) if compactor_on else 1.0

        # ----- compute
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        minions = sorted(self._stats.keys())
        for m in minions:
            info = self._stats.get(m) or {}
            if not isinstance(info, dict):
                self._add_missing_row(m, "bad entry")
                continue

            tier11 = info.get("tier11")
            if not isinstance(tier11, dict):
                self._add_missing_row(m, "missing tier11")
                continue

            sec = float(tier11.get("seconds_per_action") or 0.0)
            drops = tier11.get("drops")
            if sec <= 0.0 or not isinstance(drops, list) or not drops:
                self._add_missing_row(m, "missing seconds/drops")
                continue

            drops_norm: List[Tuple[str, float]] = []
            for d in drops:
                if not isinstance(d, dict):
                    continue
                item = str(d.get("item") or "").strip()
                qty = float(d.get("qty") or 0.0)
                if item and qty > 0:
                    drops_norm.append((item, qty))

            if not drops_norm:
                self._add_missing_row(m, "no drops")
                continue

            actions_h = (3600.0 / sec) * speed_mult

            items_h_total = 0.0
            profit_h = 0.0
            parts = []

            # V1: on somme la valeur de chaque drop au prix BUY
            for item_id, qty in drops_norm:
                items_h = qty * actions_h
                items_h_total += items_h
                buy, _sell = self._bazaar_prices.get(item_id, (0.0, 0.0))
                profit_h += items_h * float(buy)
                parts.append(f"{item_id}×{qty:g}")

            # V1 Compactor: ratio "valeur" (placeholder)
            profit_h *= compactor_ratio

            # Hopper: taxe sur le profit
            if hopper_on:
                profit_h *= max(0.0, (1.0 - hopper_tax))

            profit_d = profit_h * 24.0

            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(m))
            self.table.setItem(row, 1, QTableWidgetItem(f"{sec:g}"))
            self.table.setItem(row, 2, QTableWidgetItem(", ".join(parts)))
            self.table.setItem(row, 3, QTableWidgetItem(fmt_num(actions_h)))
            self.table.setItem(row, 4, QTableWidgetItem(fmt_num(items_h_total)))
            self.table.setItem(row, 5, QTableWidgetItem("BUY bazaar"))
            self.table.setItem(row, 6, QTableWidgetItem(fmt_num(profit_h)))
            self.table.setItem(row, 7, QTableWidgetItem(fmt_num(profit_d)))

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def _add_missing_row(self, minion: str, reason: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        items = [
            QTableWidgetItem(minion),
            QTableWidgetItem("—"),
            QTableWidgetItem(reason),
            QTableWidgetItem("—"),
            QTableWidgetItem("—"),
            QTableWidgetItem("—"),
            QTableWidgetItem("—"),
            QTableWidgetItem("—"),
        ]
        for it in items:
            it.setBackground(BR_GRAY)

        for c, it in enumerate(items):
            self.table.setItem(row, c, it)


# ----------------------------
# Main tab: MinionsTab (contains sub-tabs)
# ----------------------------
class MinionsTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.client = HypixelClient()

        self.tabs = QTabWidget()
        self.tab_unlocked = MinionsUnlockedTab(self)
        self.tab_profit = MinionsProfitTab(self)

        self.tabs.addTab(self.tab_unlocked, "Mignons déverrouillés")
        self.tabs.addTab(self.tab_profit, "Mignon profit")

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

    def apply_settings(self, settings) -> None:
        pass
