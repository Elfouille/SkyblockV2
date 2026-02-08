# ui/tab_minions_profit.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QComboBox,
    QCheckBox,
)

from common import load_json, fmt_num


DEFAULT_ACTIONS = Path(r"D:\Skyblock_V2\SkyblockV2\cache\minion_action_time_with_item_id.json")
DEFAULT_CRAFTED = Path(r"D:\Skyblock_V2\SkyblockV2\cache\crafted_minions_with_tiers.json")
DEFAULT_LOOT = Path(r"D:\Skyblock_V2\SkyblockV2\cache\minion_loot.json")
DEFAULT_FUEL = Path(r"D:\Skyblock_V2\SkyblockV2\cache\minion_fuel.json")
DEFAULT_UPGRADE = Path(r"D:\Skyblock_V2\SkyblockV2\cache\minion_upgrade.json")
DEFAULT_SELLAUTO = Path(r"D:\Skyblock_V2\SkyblockV2\cache\minion_sellauto.json")
DEFAULT_ICONS_DIR = Path(r"D:\Skyblock_V2\SkyblockV2\cache\item_icons")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _norm_base(s: str) -> str:
    return (s or "").strip().upper()


def _split_base_tier(s: str) -> Tuple[str, Optional[int]]:
    s = (s or "").strip()
    if not s:
        return "", None
    if "_" not in s:
        return _norm_base(s), None
    base, last = s.rsplit("_", 1)
    try:
        return _norm_base(base), int(last)
    except Exception:
        return _norm_base(s), None


def _icon_path(icons_dir: Path, item_id: str) -> Optional[Path]:
    if not icons_dir.exists() or not item_id:
        return None
    p = icons_dir / f"{item_id}.png"
    if p.exists():
        return p
    for ext in (".webp", ".jpg", ".jpeg"):
        q = icons_dir / f"{item_id}{ext}"
        if q.exists():
            return q
    return None


def _extract_actions_map(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("minions"), dict):
        raw = raw["minions"]
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[_norm_base(str(k))] = v
    return out


def _extract_loot_map(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("minions"), dict):
        return raw["minions"]
    if isinstance(raw.get("loot"), dict):
        return raw["loot"]
    return raw


def _crafted_max(raw: Any) -> Dict[str, int]:
    mp: Dict[str, int] = {}
    if isinstance(raw, list):
        for it in raw:
            if not isinstance(it, str):
                continue
            base, tier = _split_base_tier(it)
            if base and tier is not None:
                mp[base] = max(mp.get(base, 0), tier)
    elif isinstance(raw, dict):
        for k, v in raw.items():
            if not v:
                continue
            base, tier = _split_base_tier(str(k))
            if base and tier is not None:
                mp[base] = max(mp.get(base, 0), tier)
    return mp


@dataclass
class FuelOpt:
    id: str
    name: str
    speed_bonus: float


@dataclass
class UpgradeOpt:
    id: str
    name: str
    speed_bonus: float


@dataclass
class SellOpt:
    id: str
    name: str
    npc_ratio: float


def _load_fuels(raw: Any) -> List[FuelOpt]:
    out: List[FuelOpt] = [FuelOpt(id="none", name="None", speed_bonus=0.0)]
    if isinstance(raw, dict):
        arr = raw.get("fuel")
        if isinstance(arr, list):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                eff = it.get("effect") if isinstance(it.get("effect"), dict) else {}
                mult = eff.get("multipliers") if isinstance(eff.get("multipliers"), dict) else {}
                sp = _safe_float(mult.get("speed"), 0.0)
                out.append(FuelOpt(
                    id=str(it.get("id") or ""),
                    name=str(it.get("name") or it.get("id") or "fuel"),
                    speed_bonus=sp,
                ))
    return out


def _load_speed_upgrades(raw: Any) -> List[UpgradeOpt]:
    out: List[UpgradeOpt] = [UpgradeOpt(id="none", name="None", speed_bonus=0.0)]
    if isinstance(raw, dict):
        arr = raw.get("upgrades")
        if isinstance(arr, list):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                eff = it.get("effect") if isinstance(it.get("effect"), dict) else {}
                mult = eff.get("multipliers") if isinstance(eff.get("multipliers"), dict) else {}
                if "speed" not in mult:
                    continue
                sp = _safe_float(mult.get("speed"), 0.0)
                out.append(UpgradeOpt(
                    id=str(it.get("id") or ""),
                    name=str(it.get("name") or it.get("id") or "upgrade"),
                    speed_bonus=sp,
                ))
    return out


def _load_sell_opts(raw: Any) -> List[SellOpt]:
    out: List[SellOpt] = [
        SellOpt(id="custom_100", name="Custom 100% NPC", npc_ratio=1.0),
        SellOpt(id="custom_50", name="Custom 50% NPC", npc_ratio=0.50),
        SellOpt(id="custom_30", name="Custom 30% NPC", npc_ratio=0.30),
    ]
    if isinstance(raw, dict):
        arr = raw.get("automated_shipping")
        if isinstance(arr, list):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                eff = it.get("effect") if isinstance(it.get("effect"), dict) else {}
                mult = eff.get("multipliers") if isinstance(eff.get("multipliers"), dict) else {}
                ratio = _safe_float(mult.get("npc_sell_price_ratio"), 0.0)
                if ratio <= 0:
                    continue
                out.append(SellOpt(
                    id=str(it.get("id") or ""),
                    name=str(it.get("name") or it.get("id") or "sellauto"),
                    npc_ratio=ratio,
                ))
    return out


@dataclass
class LootLine:
    item_name: str
    qty_per_action: float  # expected
    npc_per_item: float


def _loot_lines_expected(loot_entry: Any) -> List[LootLine]:
    if not isinstance(loot_entry, dict):
        return []
    arr = loot_entry.get("loot")
    if not isinstance(arr, list) or not arr:
        return []

    out: List[LootLine] = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        item_name = str(it.get("item") or "").strip() or "?"
        amt = _safe_float(it.get("amount"), 0.0)
        chance = _safe_float(it.get("chance_percent"), 0.0) / 100.0
        npc = _safe_float(it.get("npc_sell_per_item"), 0.0)

        if amt <= 0:
            continue
        qty = amt * max(0.0, chance)
        if qty <= 0:
            continue
        out.append(LootLine(item_name=item_name, qty_per_action=qty, npc_per_item=npc))
    return out


@dataclass
class CellModel:
    text: str = ""
    num: Optional[float] = None
    icon_path: Optional[Path] = None
    bold: bool = False


@dataclass
class RowModel:
    cells: List[CellModel]


@dataclass
class BlockModel:
    base: str
    sort_key_total: Dict[int, float]
    sort_key_first: Dict[int, float]
    rows: List[RowModel]


def _mk_item(cell: CellModel) -> QTableWidgetItem:
    it = QTableWidgetItem(cell.text)
    if cell.num is not None:
        it.setData(Qt.UserRole, float(cell.num))
    if cell.bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    if cell.icon_path:
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        it.setIcon(QIcon(str(cell.icon_path)))
    return it


def _minion_max_tier(info: Dict[str, Any]) -> int:
    tm = _safe_int(info.get("tier_max"), 0)
    if tm > 0:
        return tm
    tiers = info.get("tiers")
    if isinstance(tiers, dict):
        mx = 0
        for k in tiers.keys():
            try:
                mx = max(mx, int(k))
            except Exception:
                pass
        return mx
    return 0


class MinionsProfitTab(QWidget):
    def __init__(self, parent: "MinionsTab"):
        super().__init__(parent)
        self.host = parent

        self._blocks: List[BlockModel] = []
        self._sort_col: int = 11
        self._sort_asc: bool = False

        top = QHBoxLayout()
        self.ed_actions = QLineEdit(str(DEFAULT_ACTIONS))
        self.ed_crafted = QLineEdit(str(DEFAULT_CRAFTED))
        self.ed_loot = QLineEdit(str(DEFAULT_LOOT))
        self.ed_icons = QLineEdit(str(DEFAULT_ICONS_DIR))
        self.btn_refresh = QPushButton("Refresh")

        top.addWidget(QLabel("actions:"))
        top.addWidget(self.ed_actions, 2)
        top.addWidget(QLabel("crafted:"))
        top.addWidget(self.ed_crafted, 2)
        top.addWidget(QLabel("loot:"))
        top.addWidget(self.ed_loot, 2)
        top.addWidget(QLabel("icons:"))
        top.addWidget(self.ed_icons, 1)
        top.addWidget(self.btn_refresh)

        boosts = QHBoxLayout()
        self.cmb_fuel = QComboBox()
        self.cmb_upgrade = QComboBox()
        self.cmb_sell = QComboBox()
        self.chk_sim_max = QCheckBox("Simulation max (Tier MAX)")

        # ✅ Catalyst multiplier
        self.cmb_catalyst = QComboBox()
        self.cmb_catalyst.addItem("None (x1)", 1.0)
        self.cmb_catalyst.addItem("Catalyst (x3)", 3.0)
        self.cmb_catalyst.addItem("Hyper Catalyst (x4)", 4.0)

        boosts.addWidget(QLabel("Fuel:"))
        boosts.addWidget(self.cmb_fuel, 2)
        boosts.addSpacing(10)
        boosts.addWidget(QLabel("Speed upgrade:"))
        boosts.addWidget(self.cmb_upgrade, 2)
        boosts.addSpacing(10)
        boosts.addWidget(QLabel("Sellauto:"))
        boosts.addWidget(self.cmb_sell, 2)
        boosts.addSpacing(10)
        boosts.addWidget(QLabel("Catalyst:"))
        boosts.addWidget(self.cmb_catalyst, 1)
        boosts.addSpacing(10)
        boosts.addWidget(self.chk_sim_max)
        boosts.addStretch(1)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels([
            "Icon",
            "Minion (tier affiché)",
            "Tier affiché",
            "Sec/action",
            "Speed bonus",
            "Sec/action (eff)",
            "Loot item",
            "Qty/action",
            "Action/h",
            "Item/h",
            "Prix unitaire NPC",
            "Profit/h (-tax)",
            "Profit/day (-tax)",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)
        self.table.setIconSize(QSize(32, 32))
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(self._sort_col, Qt.DescendingOrder)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addLayout(boosts)
        root.addWidget(self.table)

        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        self.cmb_fuel.currentIndexChanged.connect(lambda _i: self.refresh())
        self.cmb_upgrade.currentIndexChanged.connect(lambda _i: self.refresh())
        self.cmb_sell.currentIndexChanged.connect(lambda _i: self.refresh())
        self.cmb_catalyst.currentIndexChanged.connect(lambda _i: self.refresh())
        self.chk_sim_max.toggled.connect(lambda _on: self.refresh())

        self._fuels: List[FuelOpt] = []
        self._upgrades: List[UpgradeOpt] = []
        self._sells: List[SellOpt] = []

        self._reload_boost_lists()
        self.refresh()

    def _on_header_clicked(self, col: int) -> None:
        if col == self._sort_col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = False
        order = Qt.AscendingOrder if self._sort_asc else Qt.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(self._sort_col, order)
        self._sort_blocks()
        self._render()

    def _on_refresh_clicked(self) -> None:
        self._reload_boost_lists()
        self.refresh()

    def _reload_boost_lists(self) -> None:
        raw_fuel = load_json(DEFAULT_FUEL, default={}) if DEFAULT_FUEL.exists() else {}
        raw_upgrade = load_json(DEFAULT_UPGRADE, default={}) if DEFAULT_UPGRADE.exists() else {}
        raw_sell = load_json(DEFAULT_SELLAUTO, default={}) if DEFAULT_SELLAUTO.exists() else {}

        self._fuels = _load_fuels(raw_fuel)
        self._upgrades = _load_speed_upgrades(raw_upgrade)
        self._sells = _load_sell_opts(raw_sell)

        self.cmb_fuel.blockSignals(True)
        self.cmb_upgrade.blockSignals(True)
        self.cmb_sell.blockSignals(True)

        self.cmb_fuel.clear()
        for f in self._fuels:
            pct = int(round(f.speed_bonus * 100))
            self.cmb_fuel.addItem(f"{f.name} (+{pct}%)", f.id)

        self.cmb_upgrade.clear()
        for u in self._upgrades:
            pct = int(round(u.speed_bonus * 100))
            self.cmb_upgrade.addItem(f"{u.name} (+{pct}%)", u.id)

        self.cmb_sell.clear()
        for s in self._sells:
            pct = int(round(s.npc_ratio * 100))
            self.cmb_sell.addItem(f"{s.name} ({pct}% NPC)", s.id)

        self.cmb_fuel.blockSignals(False)
        self.cmb_upgrade.blockSignals(False)
        self.cmb_sell.blockSignals(False)

    def _get_fuel(self) -> FuelOpt:
        fid = str(self.cmb_fuel.currentData() or "none")
        for f in self._fuels:
            if f.id == fid:
                return f
        return FuelOpt("none", "None", 0.0)

    def _get_upgrade(self) -> UpgradeOpt:
        uid = str(self.cmb_upgrade.currentData() or "none")
        for u in self._upgrades:
            if u.id == uid:
                return u
        return UpgradeOpt("none", "None", 0.0)

    def _get_sell(self) -> SellOpt:
        sid = str(self.cmb_sell.currentData() or "custom_100")
        for s in self._sells:
            if s.id == sid:
                return s
        return SellOpt("custom_100", "Custom 100% NPC", 1.0)

    def _get_catalyst_mult(self) -> float:
        try:
            return float(self.cmb_catalyst.currentData() or 1.0)
        except Exception:
            return 1.0

    def _block_key(self, blk: BlockModel, col: int) -> float:
        if col in blk.sort_key_total:
            return float(blk.sort_key_total.get(col) or 0.0)
        if col in blk.sort_key_first:
            return float(blk.sort_key_first.get(col) or 0.0)
        return 0.0

    def _sort_blocks(self) -> None:
        col = self._sort_col
        asc = self._sort_asc
        indexed = list(enumerate(self._blocks))
        indexed.sort(
            key=lambda t: (self._block_key(t[1], col), t[0]),
            reverse=not asc,
        )
        self._blocks = [b for _, b in indexed]

    def _render(self) -> None:
        self.table.setRowCount(0)
        for blk in self._blocks:
            for row in blk.rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                for c, cell in enumerate(row.cells):
                    self.table.setItem(r, c, _mk_item(cell))
        self.table.resizeColumnsToContents()

    def refresh(self) -> None:
        actions_path = Path(self.ed_actions.text().strip())
        crafted_path = Path(self.ed_crafted.text().strip())
        loot_path = Path(self.ed_loot.text().strip())
        icons_dir = Path(self.ed_icons.text().strip())

        if not actions_path.exists():
            QMessageBox.warning(self, "Fichier manquant", f"Introuvable:\n{actions_path}")
            return
        if not crafted_path.exists():
            QMessageBox.warning(self, "Fichier manquant", f"Introuvable:\n{crafted_path}")
            return
        if not loot_path.exists():
            QMessageBox.warning(self, "Fichier manquant", f"Introuvable:\n{loot_path}")
            return

        actions = _extract_actions_map(load_json(actions_path, default={}))
        owned = _crafted_max(load_json(crafted_path, default=[]))
        loot_map = _extract_loot_map(load_json(loot_path, default={}))

        fuel = self._get_fuel()
        upg = self._get_upgrade()
        sell = self._get_sell()
        sim_max = self.chk_sim_max.isChecked()

        # ✅ catalyst on Qty/action
        catalyst_mult = max(1.0, self._get_catalyst_mult())

        speed_bonus = fuel.speed_bonus + upg.speed_bonus
        speed_factor = max(0.01, 1.0 + speed_bonus)
        npc_ratio = max(0.0, min(1.0, sell.npc_ratio))

        # hidden tax
        tax_rate = 0.0
        if npc_ratio <= 0.30 + 1e-9:
            tax_rate = 0.30
        elif npc_ratio <= 0.50 + 1e-9:
            tax_rate = 0.50

        self._blocks = []

        for base in sorted(actions.keys()):
            info = actions.get(base) or {}
            tiers = info.get("tiers")
            if not isinstance(tiers, dict) or not tiers:
                continue

            owned_tier = owned.get(base, 0)

            if sim_max:
                show_tier = _minion_max_tier(info)
                if show_tier <= 0:
                    continue
            else:
                if owned_tier <= 0:
                    continue
                show_tier = owned_tier

            tinfo = tiers.get(str(show_tier))
            if not isinstance(tinfo, dict):
                continue

            minion_name = str(tinfo.get("name") or f"{base} Minion")
            item_id = str(tinfo.get("item_id") or f"{base}_GENERATOR_{show_tier}")
            base_time = _safe_float(tinfo.get("action_time"), 0.0)
            if base_time <= 0:
                continue

            # DISPLAY always base*2
            sec_display = base_time * 2.0
            # CALC always base*2 (as requested)
            sec_calc = base_time * 2.0

            eff_sec = sec_calc / speed_factor
            actions_h = 3600.0 / eff_sec if eff_sec > 0 else 0.0

            loot_entry = loot_map.get(base) if isinstance(loot_map, dict) else None
            lines = _loot_lines_expected(loot_entry)
            if not lines:
                lines = [LootLine(item_name="—", qty_per_action=0.0, npc_per_item=0.0)]

            has_multiple = len(lines) >= 2
            iconp = _icon_path(icons_dir, item_id)

            total_qty_action = 0.0
            total_profit_h = 0.0
            total_profit_d = 0.0

            rows: List[RowModel] = []
            first_numeric: Dict[int, float] = {}
            total_numeric: Dict[int, float] = {}

            title = f"{minion_name} (T{show_tier})"
            if sim_max and owned_tier > 0 and owned_tier != show_tier:
                title = f"{minion_name} (MAX T{show_tier} | owned T{owned_tier})"

            for i, ln in enumerate(lines):
                # ✅ apply catalyst to qty/action
                qty_action = ln.qty_per_action * catalyst_mult
                qty_h = qty_action * actions_h

                unit_npc = ln.npc_per_item * npc_ratio
                coins_action = qty_action * unit_npc
                profit_h = (coins_action * actions_h) * (1.0 - tax_rate)
                profit_d = profit_h * 24.0

                total_qty_action += qty_action
                total_profit_h += profit_h
                total_profit_d += profit_d

                loot_label = ln.item_name if not has_multiple else f"↳ {ln.item_name}"

                if i == 0:
                    first_numeric[2] = float(show_tier)
                    first_numeric[3] = sec_display
                    first_numeric[5] = eff_sec
                    first_numeric[8] = actions_h
                    first_numeric[9] = qty_h
                    first_numeric[10] = unit_npc
                    first_numeric[11] = profit_h
                    first_numeric[12] = profit_d

                    rows.append(RowModel(cells=[
                        CellModel(text="", icon_path=iconp),
                        CellModel(text=title),
                        CellModel(text=str(show_tier), num=float(show_tier)),
                        CellModel(text=f"{sec_display:g}", num=sec_display),
                        CellModel(text=f"+{int(round(speed_bonus * 100))}%"),
                        CellModel(text=f"{eff_sec:g}", num=eff_sec),
                        CellModel(text=loot_label),
                        CellModel(text=f"{qty_action:.6g}", num=qty_action),
                        CellModel(text=fmt_num(actions_h), num=actions_h),
                        CellModel(text=fmt_num(qty_h), num=qty_h),
                        CellModel(text=fmt_num(unit_npc), num=unit_npc),
                        CellModel(text=fmt_num(profit_h), num=profit_h),
                        CellModel(text=fmt_num(profit_d), num=profit_d),
                    ]))
                else:
                    rows.append(RowModel(cells=[
                        CellModel(text=""),
                        CellModel(text=""),
                        CellModel(text="", num=float(show_tier)),
                        CellModel(text="", num=sec_display),
                        CellModel(text=""),
                        CellModel(text="", num=eff_sec),
                        CellModel(text=loot_label),
                        CellModel(text=f"{qty_action:.6g}", num=qty_action),
                        CellModel(text="", num=actions_h),
                        CellModel(text=fmt_num(qty_h), num=qty_h),
                        CellModel(text=fmt_num(unit_npc), num=unit_npc),
                        CellModel(text=fmt_num(profit_h), num=profit_h),
                        CellModel(text=fmt_num(profit_d), num=profit_d),
                    ]))

            if has_multiple:
                total_item_h = total_qty_action * actions_h

                total_numeric[7] = total_qty_action
                total_numeric[9] = total_item_h
                total_numeric[11] = total_profit_h
                total_numeric[12] = total_profit_d

                rows.append(RowModel(cells=[
                    CellModel(text=""),
                    CellModel(text=""),
                    CellModel(text="", num=float(show_tier)),
                    CellModel(text="", num=sec_display),
                    CellModel(text=""),
                    CellModel(text="", num=eff_sec),
                    CellModel(text="↳ TOTAL", bold=True),
                    CellModel(text=f"{total_qty_action:.6g}", num=total_qty_action, bold=True),
                    CellModel(text="", num=actions_h),
                    CellModel(text=fmt_num(total_item_h), num=total_item_h, bold=True),
                    CellModel(text=""),
                    CellModel(text=fmt_num(total_profit_h), num=total_profit_h, bold=True),
                    CellModel(text=fmt_num(total_profit_d), num=total_profit_d, bold=True),
                ]))

            self._blocks.append(BlockModel(
                base=base,
                sort_key_total=total_numeric,
                sort_key_first=first_numeric,
                rows=rows,
            ))

        self._sort_blocks()
        order = Qt.AscendingOrder if self._sort_asc else Qt.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(self._sort_col, order)
        self._render()
