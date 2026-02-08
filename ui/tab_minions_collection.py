# ui/tab_minions_collection.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QMessageBox, QProgressBar,
    QGroupBox, QScrollArea, QSizePolicy
)

from common import load_json


# ============================================================
# PATHS
# ============================================================
DEFAULT_CRAFTED = Path(r"D:\Skyblock_V2\SkyblockV2\cache\crafted_minions_with_tiers.json")
DEFAULT_ACTIONS = Path(r"D:\Skyblock_V2\SkyblockV2\cache\minion_action_time_with_item_id.json")
DEFAULT_ICONS   = Path(r"D:\Skyblock_V2\SkyblockV2\cache\item_icons")


# ============================================================
# DATA
# ============================================================
@dataclass
class MinionRow:
    base: str
    name: str
    crafted: int
    max_tier: int
    icon_item_id: str
    completion: float


# ============================================================
# UTILS
# ============================================================
def _safe_int(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _norm(s: str) -> str:
    return (s or "").strip().upper()


def _split_base_tier(s: str) -> Tuple[str, Optional[int]]:
    s = (s or "").strip()
    if not s:
        return "", None
    if "_" not in s:
        return _norm(s), None
    b, t = s.rsplit("_", 1)
    try:
        return _norm(b), int(t)
    except Exception:
        return _norm(s), None


def _icon_path(dir_: Path, item_id: str) -> Optional[Path]:
    if not dir_.exists() or not item_id:
        return None
    p = dir_ / f"{item_id}.png"
    if p.exists():
        return p
    for ext in (".webp", ".jpg", ".jpeg"):
        q = dir_ / f"{item_id}{ext}"
        if q.exists():
            return q
    return None


def _extract_minions(actions_raw: Any) -> Dict[str, Any]:
    """
    Supporte:
    - direct: { "COBBLESTONE": {...}, ... }
    - wrapped: { "_meta":..., "minions": {...}, ... }
    """
    if isinstance(actions_raw, dict):
        if isinstance(actions_raw.get("minions"), dict):
            return actions_raw["minions"]
        return actions_raw
    return {}


# ============================================================
# CATEGORIES (COMPLETES + BOSS / SLAYER)
# ============================================================
CATS = {
    "Mining": {
        "COBBLESTONE","COAL","IRON","GOLD","DIAMOND","EMERALD","REDSTONE","LAPIS",
        "QUARTZ","OBSIDIAN","GLOWSTONE","GRAVEL","SAND","ICE","SNOW","END_STONE",
        "MITHRIL","HARD_STONE","CLAY","RED_SAND","MYCELIUM",
    },
    "Forest": {"OAK","SPRUCE","BIRCH","JUNGLE","ACACIA","DARK_OAK"},
    "Farm": {
        "WHEAT","CARROT","POTATO","PUMPKIN","MELON","SUGAR_CANE","NETHER_WART",
        "MUSHROOM","CACTUS","RABBIT","COCOA_BEANS",
        "CHICKEN","PIG","SHEEP","COW",
    },
    "Combat": {"ZOMBIE","SKELETON","CREEPER","SPIDER","SLIME","CAVE_SPIDER"},
    "Boss / Slayer": {"REVENANT","TARANTULA","SVEN","VOIDGLOOM","INFERNO","VAMPIRE"},
    "Ender": {"ENDERMAN","END_STONE"},
    "Nether": {"BLAZE","MAGMA_CUBE","GHAST","NETHER_WARTS","INFERNO"},
    "Fish": {"FISHING"},
}


def _category(base: str) -> str:
    b = base.upper()
    for cat, values in CATS.items():
        if b in values:
            return cat
    return "Other"


# ============================================================
# MAIN TAB
# ============================================================
class MinionsCollectionTab(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        # ---------------- Top bar
        top = QHBoxLayout()
        self.ed_crafted = QLineEdit(str(DEFAULT_CRAFTED))
        self.ed_actions = QLineEdit(str(DEFAULT_ACTIONS))
        self.ed_icons   = QLineEdit(str(DEFAULT_ICONS))
        self.btn_refresh = QPushButton("Refresh")

        self.cmb_sort = QComboBox()
        self.cmb_sort.addItems([
            "Completion ↓", "Completion ↑",
            "Crafted tier ↓", "Crafted tier ↑",
            "Name A→Z", "Name Z→A",
        ])

        top.addWidget(QLabel("crafted:"))
        top.addWidget(self.ed_crafted, 2)
        top.addWidget(QLabel("actions:"))
        top.addWidget(self.ed_actions, 2)
        top.addWidget(QLabel("icons:"))
        top.addWidget(self.ed_icons, 1)
        top.addWidget(QLabel("Sort:"))
        top.addWidget(self.cmb_sort)
        top.addWidget(self.btn_refresh)

        # ---------------- Scroll global
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.inner = QWidget()
        self.columns_row = QHBoxLayout(self.inner)
        self.columns_row.setContentsMargins(10, 10, 10, 10)
        self.columns_row.setSpacing(12)

        self.scroll.setWidget(self.inner)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.scroll)

        self.btn_refresh.clicked.connect(self.refresh)
        self.cmb_sort.currentIndexChanged.connect(lambda _: self.refresh())

        self.refresh()

    # --------------------------------------------------------
    def _make_table(self) -> QTableWidget:
        t = QTableWidget(0, 5)
        t.setHorizontalHeaderLabels(["Icon", "Minion", "Crafted", "Max", "Progress"])
        t.verticalHeader().setVisible(False)

        # ✅ icônes grosses
        t.setIconSize(QSize(64, 64))
        t.verticalHeader().setDefaultSectionSize(72)

        # ✅ pas de scroll interne
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # important: la table doit rester "Fixed" en hauteur
        t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return t

    def _fit_table_height(self, t: QTableWidget) -> None:
        t.resizeRowsToContents()
        h = t.horizontalHeader().height()
        h += sum(t.rowHeight(i) for i in range(t.rowCount()))
        h += t.frameWidth() * 2 + 6
        t.setMinimumHeight(h)
        t.setMaximumHeight(h)

    def _clear_columns(self) -> None:
        while self.columns_row.count():
            item = self.columns_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # --------------------------------------------------------
    def refresh(self):
        crafted_path = Path(self.ed_crafted.text().strip())
        actions_path = Path(self.ed_actions.text().strip())
        icons_dir = Path(self.ed_icons.text().strip())

        if not crafted_path.exists():
            QMessageBox.warning(self, "Erreur", f"Fichier manquant:\n{crafted_path}")
            return
        if not actions_path.exists():
            QMessageBox.warning(self, "Erreur", f"Fichier manquant:\n{actions_path}")
            return

        crafted_raw = load_json(crafted_path, default=[])
        actions_raw = load_json(actions_path, default={})
        actions_map = _extract_minions(actions_raw)

        if not isinstance(actions_map, dict):
            QMessageBox.warning(self, "Erreur", "minion_action_time... invalide (minions map introuvable)")
            return

        # owned tier max
        owned: Dict[str, int] = {}
        if isinstance(crafted_raw, list):
            for it in crafted_raw:
                if not isinstance(it, str):
                    continue
                b, t = _split_base_tier(it)
                if b and t is not None:
                    owned[b] = max(owned.get(b, 0), t)

        # build rows
        rows: List[MinionRow] = []
        for base, info in actions_map.items():
            base = _norm(str(base))
            if not isinstance(info, dict):
                continue

            tiers = info.get("tiers")
            if not isinstance(tiers, dict):
                tiers = {}

            # ✅ max tier EXACT
            max_tier = _safe_int(info.get("tier_max"), 0)
            if max_tier <= 0:
                max_tier = max((_safe_int(k, 0) for k in tiers.keys()), default=0)
            if max_tier <= 0:
                max_tier = max(owned.get(base, 0), 1)

            o = owned.get(base, 0)

            name = base
            t1 = tiers.get("1")
            if isinstance(t1, dict):
                name = str(t1.get("name") or base)

            icon_tier = o if o > 0 else 1
            icon_item = ""
            ticon = tiers.get(str(icon_tier))
            if isinstance(ticon, dict):
                icon_item = str(ticon.get("item_id") or "")
            if not icon_item:
                icon_item = f"{base}_GENERATOR_{icon_tier}"

            comp = (o / max_tier) if max_tier > 0 else 0.0

            rows.append(MinionRow(base, name, o, max_tier, icon_item, comp))

        # sorting
        s = self.cmb_sort.currentText()
        if s == "Completion ↓":
            rows.sort(key=lambda r: (r.completion, r.crafted, r.name), reverse=True)
        elif s == "Completion ↑":
            rows.sort(key=lambda r: (r.completion, r.crafted, r.name))
        elif s == "Crafted tier ↓":
            rows.sort(key=lambda r: (r.crafted, r.completion, r.name), reverse=True)
        elif s == "Crafted tier ↑":
            rows.sort(key=lambda r: (r.crafted, r.completion, r.name))
        elif s == "Name Z→A":
            rows.sort(key=lambda r: r.name, reverse=True)
        else:
            rows.sort(key=lambda r: r.name)

        # group by category
        cat_order = ["Mining", "Forest", "Farm", "Combat", "Boss / Slayer", "Ender", "Nether", "Fish", "Other"]
        groups: Dict[str, List[MinionRow]] = {c: [] for c in cat_order}
        for r in rows:
            groups[_category(r.base)].append(r)

        # uniform "Minion" column width
        fm = QFontMetrics(self.font())
        max_name_w = max((fm.horizontalAdvance(r.name) for r in rows), default=150) + 24

        # responsive columns: 2 or 3
        cols = 3 if self.width() >= 1400 else 2

        # rebuild columns
        self._clear_columns()

        col_widgets: List[QWidget] = []
        col_layouts: List[QVBoxLayout] = []
        col_heights: List[int] = []

        for _ in range(cols):
            cw = QWidget()
            cw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            lay = QVBoxLayout(cw)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(12)
            self.columns_row.addWidget(cw, 1)

            col_widgets.append(cw)
            col_layouts.append(lay)
            col_heights.append(0)

        # helper to choose shortest column
        def pick_col() -> int:
            best = 0
            best_h = col_heights[0]
            for i, h in enumerate(col_heights):
                if h < best_h:
                    best = i
                    best_h = h
            return best

        # create groupboxes and place in shortest column (masonry)
        for cat in cat_order:
            items = groups.get(cat) or []
            if not items:
                continue

            gb = QGroupBox(f"{cat} ({len(items)})")
            gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            lay = QVBoxLayout(gb)
            lay.setContentsMargins(8, 12, 8, 8)
            lay.setSpacing(6)

            table = self._make_table()

            for r in items:
                i = table.rowCount()
                table.insertRow(i)

                icon_cell = QTableWidgetItem("")
                icon_cell.setFlags(icon_cell.flags() & ~Qt.ItemIsEditable)

                ip = _icon_path(icons_dir, r.icon_item_id)
                if ip:
                    icon_cell.setIcon(QIcon(str(ip)))

                table.setItem(i, 0, icon_cell)
                table.setItem(i, 1, QTableWidgetItem(r.name))
                table.setItem(i, 2, QTableWidgetItem(str(r.crafted if r.crafted > 0 else "—")))
                table.setItem(i, 3, QTableWidgetItem(str(r.max_tier)))

                pb = QProgressBar()
                pb.setRange(0, max(1, r.max_tier))
                pb.setValue(min(r.crafted, r.max_tier))
                pb.setFormat(f"{min(r.crafted, r.max_tier)}/{r.max_tier} ({int(r.completion*100)}%)")
                pb.setAlignment(Qt.AlignCenter)
                table.setCellWidget(i, 4, pb)

            table.setColumnWidth(1, max_name_w)
            table.resizeColumnsToContents()
            self._fit_table_height(table)

            lay.addWidget(table)

            # place groupbox in shortest column
            c = pick_col()
            col_layouts[c].addWidget(gb)

            # estimate height for balancing
            h_est = gb.sizeHint().height()
            col_heights[c] += max(50, h_est)

        # add stretch to each column (push to top)
        for lay in col_layouts:
            lay.addStretch(1)
