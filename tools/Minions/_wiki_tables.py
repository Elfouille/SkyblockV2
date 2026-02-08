from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

UA = "Mozilla/5.0 SkyblockV2/MinionIndexScraper"
TIMEOUT = 30


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def norm_key(s: str) -> str:
    s = norm(s).lower()
    s = (
        s.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
        .replace("à", "a").replace("â", "a")
        .replace("ù", "u").replace("û", "u")
        .replace("ç", "c")
        .replace("î", "i").replace("ï", "i")
        .replace("ô", "o")
    )
    return s


def parse_float(s: str) -> Optional[float]:
    """
    Support:
      - "7.639e-05"
      - "0,7353"
      - "1 024"
      - "100 %"
      - "128 Coins"
    """
    if not s:
        return None
    s = norm(s)
    if not s:
        return None
    s = s.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?", s, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def find_table_after_anchor(soup: BeautifulSoup, anchor_id: str) -> Optional[Tag]:
    """
    Trouve le 1er <table> après un élément qui a id=anchor_id.
    (ex: Minion_Upgrades, Minion_Fuel, Automated_Shipping)
    """
    anchor = soup.find(id=anchor_id)
    if not anchor:
        return None

    cur: Any = anchor
    for _ in range(800):
        cur = cur.find_next()
        if cur is None:
            break
        if isinstance(cur, Tag) and cur.name == "table":
            return cur
    return None


def table_to_matrix(tbl: Tag) -> List[List[str]]:
    """
    HTML table -> matrice rectangulaire (gère rowspan/colspan).
    """
    grid: List[List[str]] = []
    spans: Dict[Tuple[int, int], Tuple[str, int]] = {}

    rows = tbl.find_all("tr")
    for r_i, tr in enumerate(rows):
        while len(grid) <= r_i:
            grid.append([])

        c_i = 0

        def fill_span() -> None:
            nonlocal c_i
            while True:
                key = (r_i, c_i)
                if key not in spans:
                    break
                txt, remain = spans.pop(key)
                while len(grid[r_i]) <= c_i:
                    grid[r_i].append("")
                grid[r_i][c_i] = txt
                if remain > 1:
                    spans[(r_i + 1, c_i)] = (txt, remain - 1)
                c_i += 1

        fill_span()

        for cell in tr.find_all(["th", "td"]):
            while True:
                fill_span()
                if c_i < len(grid[r_i]) and grid[r_i][c_i]:
                    c_i += 1
                    continue
                break

            txt = norm(cell.get_text(" ", strip=True))
            rowspan = int(cell.get("rowspan", 1) or 1)
            colspan = int(cell.get("colspan", 1) or 1)

            for dc in range(colspan):
                while len(grid[r_i]) <= c_i + dc:
                    grid[r_i].append("")
                grid[r_i][c_i + dc] = txt
                if rowspan > 1:
                    spans[(r_i + 1, c_i + dc)] = (txt, rowspan - 1)

            c_i += colspan

    width = max((len(r) for r in grid), default=0)
    for r in grid:
        if len(r) < width:
            r.extend([""] * (width - len(r)))
    return grid


def _is_repeated_label_row(row: List[str], label: str) -> bool:
    vals = [norm_key(x) for x in row if norm(x)]
    return bool(vals) and len(set(vals)) == 1 and vals[0] == norm_key(label)


def parse_effect(effect: str) -> Dict[str, Any]:
    """
    Normalise Effect en valeurs chiffrables.
    - speed (percent) -> effect_multiplier (ex 125% => 1.25)
    - additive storage/slots -> effect_additive (ex +5 slots => 5)
    - fallback special
    """
    raw = norm(effect)
    e = raw.lower()

    # SPEED: "125% speed", "work at 125% speed", "increases speed by 20%"
    if "speed" in e:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", e)
        if m:
            pct = float(m.group(1))
            return {"effect_type": "speed", "effect_multiplier": pct / 100.0, "effect_additive": None}

        # "increase speed by 5" (rare, but just in case)
        m = re.search(r"speed.*?(\d+(?:\.\d+)?)", e)
        if m:
            pct = float(m.group(1))
            # interpret as % if small
            if pct <= 500:
                return {"effect_type": "speed", "effect_multiplier": 1.0 + (pct / 100.0), "effect_additive": None}

    # STORAGE / SLOTS
    m = re.search(r"(\d+(?:\.\d+)?)\s*(slot|slots)", e)
    if m:
        return {"effect_type": "storage", "effect_multiplier": None, "effect_additive": float(m.group(1))}

    # DOUBLE DROPS / EXTRA ITEMS (optional heuristic)
    # ex: "2x drops", "double drops"
    if "double" in e and ("drop" in e or "drops" in e):
        return {"effect_type": "drops", "effect_multiplier": 2.0, "effect_additive": None}
    m = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(drop|drops|items|item)", e)
    if m:
        return {"effect_type": "drops", "effect_multiplier": float(m.group(1)), "effect_additive": None}

    return {"effect_type": "special", "effect_multiplier": None, "effect_additive": None}


def matrix_to_rows(matrix: List[List[str]]) -> List[Dict[str, Any]]:
    """
    Convertit matrice en liste de dict:
    - 1ère vraie ligne = headers
    - valeurs: string par défaut
    - si la valeur ressemble à un nombre (%, coins, x...), on met float
    - ajoute effect_type/effect_multiplier/effect_additive si colonne Effect
    """
    if not matrix:
        return []

    start = 0
    if _is_repeated_label_row(matrix[0], "Standard"):
        start = 1

    if start >= len(matrix):
        return []

    headers = [norm(h) for h in matrix[start]]
    data = matrix[start + 1 :]

    rows: List[Dict[str, Any]] = []
    for r in data:
        if not any(norm(x) for x in r):
            continue

        obj: Dict[str, Any] = {}
        for i, h in enumerate(headers):
            key = norm(h) or f"col_{i}"
            val = norm(r[i]) if i < len(r) else ""
            if not val:
                obj[key] = None
                continue

            num = parse_float(val)
            if num is not None:
                compact = val.replace("\u00a0", "").replace(" ", "")
                # accepte: 100, 100%, 1.25x, 128Coins, etc.
                if re.fullmatch(r"[-+0-9\.,eE%xXCoinscoins]*", compact) is not None:
                    obj[key] = num
                else:
                    obj[key] = val
            else:
                obj[key] = val

        # Effect normalization (case-insensitive key match)
        effect_key = None
        for k in obj.keys():
            if norm_key(k) == "effect":
                effect_key = k
                break

        if effect_key and obj.get(effect_key):
            eff = parse_effect(str(obj[effect_key]))
            obj.update(eff)
        else:
            obj["effect_type"] = None
            obj["effect_multiplier"] = None
            obj["effect_additive"] = None

        rows.append(obj)

    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
