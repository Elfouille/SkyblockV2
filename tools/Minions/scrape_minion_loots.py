from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag


# =========================
# PATHS / CONFIG (SkyblockV2)
# =========================
BASE = "https://wiki.hypixel.net/"
INDEX_URL = urljoin(BASE, "Minions")

# D:\Skyblock_V2\SkyblockV2\cache\minion_loot.json
ROOT = Path(__file__).resolve().parents[2]          # ...\SkyblockV2
OUT_JSON = ROOT / "cache" / "minion_loot.json"

UA = "Mozilla/5.0 MinionScraper/LOOT-ONLY"
TIMEOUT = 30
SLEEP = 0.12


# =========================
# UTILS
# =========================
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


# =========================
# MINION LINKS
# =========================
def extract_minion_links(index_html: str) -> Dict[str, str]:
    soup = BeautifulSoup(index_html, "html.parser")
    out: Dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href:
            continue

        abs_url = urljoin(BASE, href)
        if not abs_url.startswith(BASE):
            continue

        path = urlparse(abs_url).path
        if not path.endswith("_Minion"):
            continue

        slug = path.rsplit("/", 1)[-1]           # Wheat_Minion
        name = slug.replace("_Minion", "")       # Wheat
        minion_id = name.replace("-", "_").upper()

        out[minion_id] = abs_url

    return dict(sorted(out.items()))


# =========================
# FIND RESSOURCES TABLE (only)
# =========================
def find_resources_table(soup: BeautifulSoup) -> Optional[Tag]:
    # 1) By heading "RESSOURCES / RESOURCES"
    for h in soup.find_all(["h2", "h3", "h4"]):
        t = norm_key(h.get_text())
        if "ressource" in t or "resource" in t:
            nxt = h
            for _ in range(300):
                nxt = nxt.find_next()
                if nxt is None:
                    break
                if isinstance(nxt, Tag) and nxt.name == "table":
                    return nxt
            break

    # 2) Fallback: table header signature
    for tbl in soup.find_all("table"):
        headers = [norm_key(th.get_text()) for th in tbl.find_all("th")]
        joined = " ".join(headers)
        if (
            ("article" in joined or "item" in joined or "drop" in joined)
            and ("%" in joined or "chance" in joined)
            and ("recolte" in joined or "harvest" in joined or "amount" in joined)
        ):
            return tbl

    return None


# =========================
# HTML TABLE -> MATRIX (handles rowspan/colspan)
# =========================
def table_to_matrix(tbl: Tag) -> List[List[str]]:
    grid: List[List[str]] = []
    spans: Dict[tuple[int, int], tuple[str, int]] = {}

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


def _is_standard_row(row: List[str]) -> bool:
    vals = [norm_key(x) for x in row if norm(x)]
    return bool(vals) and len(set(vals)) == 1 and vals[0] == "standard"


def _find_col(headers: List[str], needles: List[str]) -> Optional[int]:
    hn = [norm_key(h) for h in headers]
    for i, h in enumerate(hn):
        for n in needles:
            if n in h:
                return i
    return None


# =========================
# PARSE LOOT ONLY
# =========================
def parse_loot_only(soup: BeautifulSoup) -> List[dict]:
    tbl = find_resources_table(soup)
    if not tbl:
        return []

    m = table_to_matrix(tbl)
    if len(m) < 2:
        return []

    # Skip first row if it's "Standard" repeated
    start = 1 if _is_standard_row(m[0]) else 0

    # Detect header style
    # - Inferno-like: header is one row "Drop | Chance"
    header0 = m[start] if start < len(m) else []
    header1 = m[start + 1] if start + 1 < len(m) else []

    h0 = " | ".join(header0)
    h1 = " | ".join(header1)

    # Default: 2 header rows (group + subheader with Amount/%)
    data_start = start + 1
    header_row = header0

    if start + 1 < len(m) and (any("%" in x for x in header1) or "amount" in norm_key(h1) or "montant" in norm_key(h1)):
        header_row = header1
        data_start = start + 2

    # Inferno: 1 header row "Drop | Chance"
    if ("drop" in norm_key(h0) or "item" in norm_key(h0)) and ("chance" in norm_key(h0) or "%" in h0):
        header_row = header0
        data_start = start + 1

    col_item = _find_col(header_row, ["item", "article", "articles", "drop"]) or 0
    col_amount = _find_col(header_row, ["amount", "montant"])
    col_chance = None
    for i, x in enumerate(header_row):
        if "%" in x:
            col_chance = i
            break
    if col_chance is None:
        col_chance = _find_col(header_row, ["chance"])

    loot: List[dict] = []
    for row in m[data_start:]:
        if col_item >= len(row):
            continue

        item = norm(row[col_item])
        if not item:
            continue

        amount = parse_float(row[col_amount]) if (col_amount is not None and col_amount < len(row)) else None
        chance = parse_float(row[col_chance]) if (col_chance is not None and col_chance < len(row)) else None

        # If both missing -> not a loot row
        if amount is None and chance is None:
            continue

        # Optional extra columns if present (common layout)
        xp_item = parse_float(row[3]) if len(row) > 3 else None
        xp_stack = parse_float(row[4]) if len(row) > 4 else None
        npc_item = parse_float(row[5]) if len(row) > 5 else None
        npc_stack = parse_float(row[6]) if len(row) > 6 else None

        loot.append(
            {
                "item": item,
                "amount": amount,
                "chance_percent": chance,
                "xp_per_item": xp_item,
                "xp_per_stack": xp_stack,
                "npc_sell_per_item": npc_item,
                "npc_sell_per_stack": npc_stack,
            }
        )

    return loot


# =========================
# MAIN
# =========================
def main() -> None:
    out = {
        "_meta": {
            "source_index": INDEX_URL,
            "generated_by": "tools/Minions/scrape_minion_loots.py",
            "unit_loot_chance": "percent",
            "note": "Only 'RESSOURCES/RESOURCES' table is parsed (no upgrades, no debug).",
        },
        "minions": {},
    }

    index_html = get(INDEX_URL)
    links = extract_minion_links(index_html)

    for minion_id, url in links.items():
        html = get(url)
        soup = BeautifulSoup(html, "html.parser")
        loot = parse_loot_only(soup)

        out["minions"][minion_id] = {
            "loot": loot,
            "wiki": url,
        }

        time.sleep(SLEEP)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -> {OUT_JSON}")


if __name__ == "__main__":
    main()
