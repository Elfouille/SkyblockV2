# ui/tab_museum.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QApplication,
    QDialog,
    QPlainTextEdit,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QDialogButtonBox,
    QHeaderView,
)

from common import CACHE_DIR, fmt_num
from hypixel_client import HypixelClient
from icon_cache import get_icon_path  # <- ta fonction (sans arg debug)


# -----------------------------
# storage players
# -----------------------------
PLAYERS_FILE = CACHE_DIR / "museum_players.json"


def _uuid_norm(u: str) -> str:
    return (u or "").replace("-", "").strip().lower()


def _uuid_norm_upper(u: str) -> str:
    return (u or "").replace("-", "").strip().upper()


def _f(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_players_default() -> List[Dict[str, str]]:
    # fallback si pas de fichier
    return [
        {"name": "Elfouile", "uuid": "26b56974e38b486cba4f0449dee370d5"},
        {"name": "jejar_", "uuid": "a329d1a57fec4d01acc7c07cacd3fc54"},
    ]


def load_players() -> List[Dict[str, str]]:
    raw = _load_json(PLAYERS_FILE, default=None)
    if isinstance(raw, list) and raw:
        out: List[Dict[str, str]] = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            uuid = str(it.get("uuid") or "").strip()
            if uuid:
                if not name:
                    name = uuid[:8]
                out.append({"name": name, "uuid": uuid})
        if out:
            return out
    return load_players_default()


def save_players(players: List[Dict[str, str]]) -> None:
    _save_json(PLAYERS_FILE, players)


# -----------------------------
# reference base from hypixel_items_cache.json
# -----------------------------
ITEMS_CACHE_JSON = CACHE_DIR / "hypixel_items_cache.json"


@dataclass(frozen=True)
class RefEntry:
    group: str        # ARMOR / WEAPON / RARITIES
    key: str          # item_id or armor_set_name
    display_name: str
    tier: str         # for name color only
    value_xp: float   # donation_xp or armor_set_donation_xp[set]
    material: str     # for icon (optional)


def _tier_color(tier: str) -> QColor:
    t = (tier or "").upper()
    # simple MC-like
    if t == "COMMON":
        return QColor(220, 220, 220)
    if t == "UNCOMMON":
        return QColor(85, 255, 85)
    if t == "RARE":
        return QColor(85, 85, 255)
    if t == "EPIC":
        return QColor(170, 0, 170)
    if t == "LEGENDARY":
        return QColor(255, 170, 0)
    if t == "MYTHIC":
        return QColor(255, 85, 255)
    if t == "DIVINE":
        return QColor(85, 255, 255)
    if t == "SPECIAL" or t == "VERY_SPECIAL":
        return QColor(255, 85, 85)
    return QColor(235, 235, 235)


def _museum_type_to_group(museum_type: str) -> Optional[str]:
    mt = (museum_type or "").upper()
    if mt == "ARMOR_SETS":
        return "ARMOR"
    if mt == "WEAPONS":
        return "WEAPON"
    if mt == "RARITIES":
        return "RARITIES"
    return None


def load_reference_entries() -> List[RefEntry]:
    cached = _load_json(ITEMS_CACHE_JSON, default={})
    items = {}
    if isinstance(cached, dict):
        items = cached.get("items") or {}
    if not isinstance(items, dict):
        return []

    out: List[RefEntry] = []
    # ARMOR_SETS: group by armor_set_donation_xp dict keys
    armor_sets_seen: set[str] = set()

    for item_id, it in items.items():
        if not isinstance(it, dict):
            continue

        museum = it.get("museum_data")
        if not isinstance(museum, dict):
            continue

        grp = _museum_type_to_group(str(museum.get("type") or ""))
        if not grp:
            continue

        name = str(it.get("name") or item_id)
        tier = str(it.get("tier") or "")
        material = str(it.get("material") or "")

        if grp in {"WEAPON", "RARITIES"}:
            v = _f(museum.get("donation_xp") or 0.0)
            if v <= 0:
                continue
            out.append(
                RefEntry(
                    group=grp,
                    key=str(item_id).upper(),
                    display_name=name,
                    tier=tier,
                    value_xp=v,
                    material=material,
                )
            )
        elif grp == "ARMOR":
            aset = museum.get("armor_set_donation_xp")
            if isinstance(aset, dict):
                for set_name, xp in aset.items():
                    sn = str(set_name).upper().strip()
                    if not sn:
                        continue
                    if sn in armor_sets_seen:
                        continue
                    armor_sets_seen.add(sn)
                    out.append(
                        RefEntry(
                            group="ARMOR",
                            key=sn,
                            display_name=sn.replace("_", " ").title(),
                            tier="RARE",  # juste pour couleur, pas grave
                            value_xp=_f(xp),
                            material="",  # set icon: on laisse vide -> pas d’icone sûre
                        )
                    )

    # tri stable
    out.sort(key=lambda e: (e.group, -e.value_xp, e.display_name))
    return out


# -----------------------------
# Museum parsing from API /skyblock/museum
# response: {"success": True, "members": {uuid: {"items": {...}, "value": int, "appraisal": bool}}}
# -----------------------------
@dataclass
class PlayerMuseumComputed:
    possessed: Dict[str, set[str]]  # group -> set(keys)
    count: Dict[str, int]           # group -> count
    value: Dict[str, float]         # group -> sum xp
    total_count: int
    total_value: float


def compute_player_museum(
    member_data: Dict[str, Any],
    ref_entries: List[RefEntry],
) -> PlayerMuseumComputed:
    items = member_data.get("items") or {}
    possessed_keys: set[str] = set()
    if isinstance(items, dict):
        for k in items.keys():
            possessed_keys.add(str(k).upper())

    # build reference maps by group
    ref_by_group: Dict[str, List[RefEntry]] = {"ARMOR": [], "WEAPON": [], "RARITIES": []}
    for e in ref_entries:
        ref_by_group[e.group].append(e)

    poss: Dict[str, set[str]] = {"ARMOR": set(), "WEAPON": set(), "RARITIES": set()}
    cnt: Dict[str, int] = {"ARMOR": 0, "WEAPON": 0, "RARITIES": 0}
    val: Dict[str, float] = {"ARMOR": 0.0, "WEAPON": 0.0, "RARITIES": 0.0}

    for grp, entries in ref_by_group.items():
        for e in entries:
            if e.key.upper() in possessed_keys:
                poss[grp].add(e.key.upper())
                cnt[grp] += 1
                val[grp] += float(e.value_xp)

    total_count = cnt["ARMOR"] + cnt["WEAPON"] + cnt["RARITIES"]
    total_value = val["ARMOR"] + val["WEAPON"] + val["RARITIES"]

    return PlayerMuseumComputed(
        possessed=poss,
        count=cnt,
        value=val,
        total_count=total_count,
        total_value=total_value,
    )


# -----------------------------
# UI helpers
# -----------------------------
class NumericItem(QTableWidgetItem):
    def __init__(self, text: str, value: float):
        super().__init__(text)
        self.setData(Qt.UserRole, float(value))

    def __lt__(self, other: QTableWidgetItem) -> bool:
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole)
        if a is None or b is None:
            return super().__lt__(other)
        return float(a) < float(b)


def _make_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _set_row_bg(table: QTableWidget, row: int, color: QColor) -> None:
    br = QBrush(color)
    for c in range(table.columnCount()):
        it = table.item(row, c)
        if it is not None:
            it.setBackground(br)


def _set_row_fg(table: QTableWidget, row: int, color: QColor) -> None:
    br = QBrush(color)
    for c in range(table.columnCount()):
        it = table.item(row, c)
        if it is not None:
            it.setForeground(br)


# -----------------------------
# Players editor dialog
# -----------------------------
class PlayersDialog(QDialog):
    """
    Lignes:
      Nom uuid
    ou:
      uuid
    """
    def __init__(self, parent: QWidget, players: List[Dict[str, str]]):
        super().__init__(parent)
        self.setWindowTitle("Joueurs (UUID)")
        self.resize(700, 450)

        root = QVBoxLayout(self)

        info = QLabel("1 ligne par joueur :\n- `Nom uuid`  (ex: Elfouile 26b5...)\n- ou juste `uuid`")
        root.addWidget(info)

        self.ed = QPlainTextEdit()
        self.ed.setPlaceholderText("Ex:\nElfouile 26b56974e38b486cba4f0449dee370d5\njejar_ a329d1a57fec4d01acc7c07cacd3fc54")
        root.addWidget(self.ed, 1)

        # fill
        lines = []
        for p in players:
            name = str(p.get("name") or "").strip()
            uuid = str(p.get("uuid") or "").strip()
            if uuid:
                if name and name != uuid[:8]:
                    lines.append(f"{name} {uuid}")
                else:
                    lines.append(uuid)
        self.ed.setPlainText("\n".join(lines))

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def parsed_players(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for raw in (self.ed.toPlainText() or "").splitlines():
            s = raw.strip()
            if not s:
                continue
            parts = s.split()
            if len(parts) == 1:
                uuid = parts[0].strip()
                if uuid:
                    out.append({"name": uuid[:8], "uuid": uuid})
            else:
                uuid = parts[-1].strip()
                name = " ".join(parts[:-1]).strip()
                if uuid:
                    out.append({"name": name or uuid[:8], "uuid": uuid})
        # dedupe
        seen = set()
        uniq: List[Dict[str, str]] = []
        for p in out:
            nu = _uuid_norm(p["uuid"])
            if not nu or nu in seen:
                continue
            seen.add(nu)
            uniq.append(p)
        return uniq


# -----------------------------
# Compare dialog
# -----------------------------
class CompareDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        players: List[Dict[str, str]],
        ref_entries: List[RefEntry],
        possessed_by_player: Dict[str, Dict[str, set[str]]],  # player_name -> group -> set(keys)
        enable_icons: bool,
        allow_downloads: bool,
    ):
        super().__init__(parent)
        self.setWindowTitle("Comparaison Museum — Armor / Weapon / Rarities")
        self.resize(1200, 760)

        self.players = players
        self.ref_entries = ref_entries
        self.possessed_by_player = possessed_by_player
        self.enable_icons = enable_icons
        self.allow_downloads = allow_downloads

        self._focus_player = players[0]["name"] if players else ""
        self._group = "TOUT"
        self._view = "TOUS"  # TOUS / MANQUANTS / POSSEDES

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.cb_group = QComboBox()
        self.cb_group.addItems(["Tout", "Armor", "Weapon", "Rarities"])
        self.cb_view = QComboBox()
        self.cb_view.addItems(["Afficher: Tous", "Afficher: Manquants", "Afficher: Possédés"])
        self.cb_focus = QComboBox()
        self.cb_focus.addItems([p["name"] for p in players])

        top.addWidget(QLabel("Groupe:"))
        top.addWidget(self.cb_group)
        top.addSpacing(10)
        top.addWidget(QLabel("Vue:"))
        top.addWidget(self.cb_view)
        top.addSpacing(10)
        top.addWidget(QLabel("Joueur (focus):"))
        top.addWidget(self.cb_focus)
        top.addStretch(1)

        self.btn_copy = QPushButton("Copier tableau (TSV)")
        top.addWidget(self.btn_copy)
        root.addLayout(top)

        self.table = QTableWidget(0, 5 + len(players))
        headers = ["Icon", "Nom", "Type", "Valeur(xp)", "ID"]
        for p in players:
            headers.append(p["name"])
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.cb_group.currentIndexChanged.connect(self._on_filters_changed)
        self.cb_view.currentIndexChanged.connect(self._on_filters_changed)
        self.cb_focus.currentIndexChanged.connect(self._on_filters_changed)
        self.btn_copy.clicked.connect(self.copy_tsv)

        self.rebuild()

    def _on_filters_changed(self) -> None:
        g = self.cb_group.currentText().strip().upper()
        if g == "TOUT":
            self._group = "TOUT"
        elif g == "ARMOR":
            self._group = "ARMOR"
        elif g == "WEAPON":
            self._group = "WEAPON"
        else:
            self._group = "RARITIES"

        v = self.cb_view.currentText().strip().upper()
        if "MANQUANTS" in v:
            self._view = "MANQUANTS"
        elif "POSSÉDÉS" in v or "POSSEDES" in v:
            self._view = "POSSEDES"
        else:
            self._view = "TOUS"

        self._focus_player = self.cb_focus.currentText().strip()
        self.rebuild()

    def _icon_for(self, e: RefEntry) -> Optional[QIcon]:
        # icon_cache.get_icon_path(item_id) -> IconResult(path, ...)
        # Pour les armor sets, on n'a pas un item_id fiable -> pas d’icone
        if e.group == "ARMOR":
            return None
        res = get_icon_path(e.key, enable_icons=self.enable_icons, allow_download=self.allow_downloads)
        if res.path and res.path.exists():
            pm = QPixmap(str(res.path))
            if not pm.isNull():
                return QIcon(pm)
        return None

    def rebuild(self) -> None:
        # color palette (lisible)
        BG_MISSING = QColor(255, 210, 210)   # rouge clair
        BG_FOCUS_HAVE = QColor(210, 255, 210)  # vert clair
        BG_OTHER_HAVE = QColor(255, 235, 200)  # orange clair
        FG_DARK = QColor(15, 15, 15)

        focus = self._focus_player
        focus_have = self.possessed_by_player.get(focus, {"ARMOR": set(), "WEAPON": set(), "RARITIES": set()})

        # rows to show from reference
        rows: List[RefEntry] = []
        for e in self.ref_entries:
            if self._group != "TOUT" and e.group != self._group:
                continue

            f_has = e.key.upper() in focus_have.get(e.group, set())

            # view filter
            if self._view == "MANQUANTS" and f_has:
                continue
            if self._view == "POSSEDES" and (not f_has):
                continue

            rows.append(e)

        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)

        for e in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # icon
            icon_item = QTableWidgetItem("")
            icon = self._icon_for(e)
            if icon:
                icon_item.setIcon(icon)
            icon_item.setFlags(icon_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, icon_item)

            # name (tier color)
            name_item = _make_item(e.display_name)
            name_item.setForeground(QBrush(_tier_color(e.tier)))
            self.table.setItem(r, 1, name_item)

            self.table.setItem(r, 2, _make_item(e.group))
            self.table.setItem(r, 3, NumericItem(fmt_num(e.value_xp), e.value_xp))
            self.table.setItem(r, 4, _make_item(e.key))

            # each player
            any_other_has = False
            for i, p in enumerate(self.players):
                pname = p["name"]
                pset = self.possessed_by_player.get(pname, {"ARMOR": set(), "WEAPON": set(), "RARITIES": set()})
                has = e.key.upper() in pset.get(e.group, set())
                it = _make_item("✅" if has else "—")
                self.table.setItem(r, 5 + i, it)
                if pname != focus and has:
                    any_other_has = True

            # row background logic:
            f_has = e.key.upper() in focus_have.get(e.group, set())
            if f_has:
                _set_row_bg(self.table, r, BG_FOCUS_HAVE)
                _set_row_fg(self.table, r, FG_DARK)
            elif any_other_has:
                _set_row_bg(self.table, r, BG_OTHER_HAVE)
                _set_row_fg(self.table, r, FG_DARK)
            else:
                _set_row_bg(self.table, r, BG_MISSING)
                _set_row_fg(self.table, r, FG_DARK)

        self.table.setSortingEnabled(True)

    def copy_tsv(self) -> None:
        # export visible rows
        cols = self.table.columnCount()
        headers = [self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else "" for i in range(cols)]
        lines = ["\t".join(headers)]
        for r in range(self.table.rowCount()):
            row = []
            for c in range(cols):
                it = self.table.item(r, c)
                row.append(it.text() if it else "")
            lines.append("\t".join(row))
        QGuiApplication.clipboard().setText("\n".join(lines))


# -----------------------------
# Background task (profiles + museum)
# -----------------------------
class _Signals(QObject):
    done = Signal(object, str)  # payload, err


class FetchMuseumTask(QRunnable):
    def __init__(
        self,
        client: HypixelClient,
        players: List[Dict[str, str]],
        cache_profiles: Dict[str, Tuple[float, Dict[str, Any]]],
        cache_museum: Dict[str, Tuple[float, Dict[str, Any]]],
        ttl_s: int,
    ):
        super().__init__()
        self.client = client
        self.players = players
        self.cache_profiles = cache_profiles
        self.cache_museum = cache_museum
        self.ttl_s = int(ttl_s)
        self.signals = _Signals()

    def _get_profiles(self, uuid: str) -> Dict[str, Any]:
        nu = _uuid_norm(uuid)
        now = time.time()
        hit = self.cache_profiles.get(nu)
        if hit:
            ts, payload = hit
            if (now - ts) <= self.ttl_s:
                return payload
        payload = self.client.fetch_profiles(uuid)
        self.cache_profiles[nu] = (now, payload)
        return payload

    def _pick_selected_profile(self, profiles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for p in profiles:
            if isinstance(p, dict) and p.get("selected") is True:
                return p
        return profiles[0] if profiles else None

    def _get_museum(self, profile_id: str) -> Dict[str, Any]:
        pid = (profile_id or "").strip()
        now = time.time()
        hit = self.cache_museum.get(pid)
        if hit:
            ts, payload = hit
            if (now - ts) <= self.ttl_s:
                return payload
        payload = self.client.fetch_museum(pid)
        self.cache_museum[pid] = (now, payload)
        return payload

    def run(self) -> None:
        try:
            result: Dict[str, Any] = {
                "players": [],
            }

            for p in self.players:
                name = str(p.get("name") or "?")
                uuid = str(p.get("uuid") or "").strip()
                nu = _uuid_norm(uuid)
                row = {
                    "name": name,
                    "uuid": uuid,
                    "profile_name": "—",
                    "profile_id": "—",
                    "museum_member": {},
                    "status": "—",
                }

                if not nu:
                    row["status"] = "UUID manquant"
                    result["players"].append(row)
                    continue

                profiles_data = self._get_profiles(uuid)
                profiles = profiles_data.get("profiles") or []
                if not isinstance(profiles, list) or not profiles:
                    row["status"] = "Aucun profil SkyBlock"
                    result["players"].append(row)
                    continue

                prof = self._pick_selected_profile([x for x in profiles if isinstance(x, dict)])
                if not isinstance(prof, dict):
                    row["status"] = "Profil invalide"
                    result["players"].append(row)
                    continue

                profile_id = str(prof.get("profile_id") or "").strip()
                row["profile_id"] = profile_id or "—"
                row["profile_name"] = str(prof.get("cute_name") or profile_id or "—")

                if not profile_id:
                    row["status"] = "profile_id manquant"
                    result["players"].append(row)
                    continue

                museum_data = self._get_museum(profile_id)
                members = museum_data.get("members") or {}
                member = {}
                # members keys are UUID without dashes (often lower)
                if isinstance(members, dict):
                    member = members.get(_uuid_norm(uuid)) or members.get(_uuid_norm_upper(uuid)) or {}

                if not isinstance(member, dict):
                    member = {}

                row["museum_member"] = member
                # statut auto: si aucune data
                items = member.get("items") or {}
                if (not isinstance(items, dict)) or (len(items) == 0):
                    row["status"] = "Museum API désactivée (réglages en jeu)"  # cas screenshot
                else:
                    row["status"] = "OK"

                result["players"].append(row)

            self.signals.done.emit(result, "")
        except Exception as exc:  # noqa: BLE001
            self.signals.done.emit({}, str(exc))


# -----------------------------
# Main tab
# -----------------------------
class MuseumTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.pool = QThreadPool.globalInstance()

        self.players: List[Dict[str, str]] = load_players()
        self.ref_entries: List[RefEntry] = load_reference_entries()

        self._cache_profiles: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._cache_museum: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._in_flight = False

        self._auto_enabled = False
        self._refresh_interval_s = 120
        self._cache_ttl_s = 120

        key = (getattr(self.main, "settings", None).api_key or "").strip() or None
        self.client = HypixelClient(key)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.timeout.connect(self._on_tick)

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.btn_refresh = QPushButton("Rafraîchir")
        self.btn_players = QPushButton("Joueurs (UUID)")
        self.btn_clear_cache = QPushButton("Vider cache")
        self.btn_compare = QPushButton("Comparer…")
        self.lbl_status = QLabel("—")

        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_players)
        top.addWidget(self.btn_clear_cache)
        top.addWidget(self.btn_compare)
        top.addWidget(self.lbl_status, 1)
        root.addLayout(top)

        self.lbl_summary = QLabel("Musée — Totaux par type (donation_xp + armor_set_donation_xp)")
        root.addWidget(self.lbl_summary)

        # Table: on enlève Entrées/Donnés/Extrait/Catégory (comme tu veux)
        # On met: Armor count/value, Weapon count/value, Rarities count/value, Total count/value
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels(
            [
                "Joueur",
                "UUID",
                "Profil",
                "Profile ID",
                "Armor (items)",
                "Armor (xp)",
                "Weapon (items)",
                "Weapon (xp)",
                "Rarities (items)",
                "Rarities (xp)",
                "Total (items)",
                "Total (xp)",
                "Appraisal",
                "Statut",
            ]
        )
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.btn_refresh.clicked.connect(lambda: self.refresh(force=True))
        self.btn_clear_cache.clicked.connect(self.clear_cache)
        self.btn_players.clicked.connect(self.edit_players)
        self.btn_compare.clicked.connect(self.open_compare)

        self.apply_settings(self.main.settings)
        self.refresh(force=True)

    # ---- settings ----
    def apply_settings(self, settings) -> None:
        key = (getattr(settings, "api_key", "") or "").strip()
        self.client = HypixelClient(key or None)

        self._auto_enabled = bool(getattr(settings, "auto_refresh_museum", False))
        self._refresh_interval_s = int(getattr(settings, "museum_refresh_seconds", 120))
        self._cache_ttl_s = int(getattr(settings, "museum_cache_ttl_seconds", 120))

        self._refresh_interval_s = max(10, min(3600, self._refresh_interval_s))
        self._cache_ttl_s = max(5, min(3600, self._cache_ttl_s))

        if self._auto_enabled:
            self._timer.start(self._refresh_interval_s * 1000)
        else:
            self._timer.stop()

    def _on_tick(self) -> None:
        if self._in_flight:
            return
        self.refresh(force=False)

    # ---- actions ----
    def clear_cache(self) -> None:
        self._cache_profiles.clear()
        self._cache_museum.clear()
        self.lbl_status.setText("Cache vidé")

    def edit_players(self) -> None:
        dlg = PlayersDialog(self, self.players)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_players = dlg.parsed_players()
        if not new_players:
            QMessageBox.warning(self, "Joueurs", "Liste vide.")
            return
        self.players = new_players
        save_players(self.players)
        self.lbl_status.setText(f"Joueurs: {len(self.players)}")
        self.refresh(force=True)

    def refresh(self, force: bool) -> None:
        if self._in_flight:
            self.lbl_status.setText("Déjà en cours…")
            return

        # respect TTL si not force
        if not force:
            now = time.time()
            if self._cache_profiles:
                oldest = min(ts for ts, _ in self._cache_profiles.values())
                if (now - oldest) <= self._cache_ttl_s:
                    rem = int(self._cache_ttl_s - (now - oldest))
                    self.lbl_status.setText(f"Cache OK (TTL) — {rem}s")
                    return

        # reload reference (si ton cache items change)
        self.ref_entries = load_reference_entries()

        self._in_flight = True
        self.btn_refresh.setEnabled(False)
        self.btn_players.setEnabled(False)
        self.btn_clear_cache.setEnabled(False)
        self.btn_compare.setEnabled(False)
        self.lbl_status.setText("Chargement…")

        task = FetchMuseumTask(
            client=self.client,
            players=self.players,
            cache_profiles=self._cache_profiles,
            cache_museum=self._cache_museum,
            ttl_s=int(self._cache_ttl_s),
        )
        task.signals.done.connect(self._on_done)
        self.pool.start(task)

    def _on_done(self, payload: Any, err: str) -> None:
        self._in_flight = False
        self.btn_refresh.setEnabled(True)
        self.btn_players.setEnabled(True)
        self.btn_clear_cache.setEnabled(True)
        self.btn_compare.setEnabled(True)

        if err:
            self.lbl_status.setText("Erreur")
            QMessageBox.critical(self, "Hypixel API", err)
            return

        rows = []
        if isinstance(payload, dict):
            rows = payload.get("players") or []
        if not isinstance(rows, list):
            rows = []

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        # compute totals using reference
        best_total = None
        best_total_xp = -1.0

        # also store possessed for compare
        self._possessed_by_player: Dict[str, Dict[str, set[str]]] = {}

        for row in rows:
            name = str(row.get("name") or "?")
            uuid = str(row.get("uuid") or "")
            profile_name = str(row.get("profile_name") or "—")
            profile_id = str(row.get("profile_id") or "—")
            status = str(row.get("status") or "—")
            member = row.get("museum_member") or {}

            # compute (even if status says disabled)
            comp = compute_player_museum(member if isinstance(member, dict) else {}, self.ref_entries)
            self._possessed_by_player[name] = comp.possessed

            appraisal = member.get("appraisal")
            appraisal_txt = "True" if appraisal is True else ("False" if appraisal is False else "—")

            r = self.table.rowCount()
            self.table.insertRow(r)

            def put(col: int, item: QTableWidgetItem) -> None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, col, item)

            put(0, _make_item(name))
            put(1, _make_item(uuid))
            put(2, _make_item(profile_name))
            put(3, _make_item(profile_id))

            put(4, NumericItem(str(comp.count["ARMOR"]), float(comp.count["ARMOR"])))
            put(5, NumericItem(fmt_num(comp.value["ARMOR"]), comp.value["ARMOR"]))

            put(6, NumericItem(str(comp.count["WEAPON"]), float(comp.count["WEAPON"])))
            put(7, NumericItem(fmt_num(comp.value["WEAPON"]), comp.value["WEAPON"]))

            put(8, NumericItem(str(comp.count["RARITIES"]), float(comp.count["RARITIES"])))
            put(9, NumericItem(fmt_num(comp.value["RARITIES"]), comp.value["RARITIES"]))

            put(10, NumericItem(str(comp.total_count), float(comp.total_count)))
            put(11, NumericItem(fmt_num(comp.total_value), comp.total_value))

            put(12, _make_item(appraisal_txt))
            put(13, _make_item(status))

            if comp.total_value > best_total_xp:
                best_total_xp = comp.total_value
                best_total = (name, profile_name, comp.total_value)

        if best_total:
            self.lbl_summary.setText(f"Meilleur total: {best_total[0]} ({best_total[1]}) — {fmt_num(best_total[2])}")
        else:
            self.lbl_summary.setText("Musée — Totaux par type (donation_xp + armor_set_donation_xp)")

        ok_count = sum(1 for r in rows if str(r.get("status") or "") == "OK")
        self.lbl_status.setText(f"OK {ok_count}/{len(rows)}")
        self.table.setSortingEnabled(True)

    def open_compare(self) -> None:
        if not hasattr(self, "_possessed_by_player"):
            QMessageBox.information(self, "Comparer", "Aucune donnée. Rafraîchis d’abord.")
            return

        # settings icons
        s = getattr(self.main, "settings", None)
        enable_icons = bool(getattr(s, "enable_icons", True))
        allow_dl = bool(getattr(s, "allow_icon_downloads", False))

        dlg = CompareDialog(
            self,
            players=self.players,
            ref_entries=self.ref_entries,
            possessed_by_player=self._possessed_by_player,
            enable_icons=enable_icons,
            allow_downloads=allow_dl,
        )
        dlg.exec()
