from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag


# =========================
# PATHS (✅ output in SkyblockV2/cache)
# =========================
SKYBLOCKV2_DIR = Path("SkyblockV2")
CACHE_DIR = SKYBLOCKV2_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = CACHE_DIR / "minions_action_and_loot.json"
DEBUG_DIR = CACHE_DIR / "debug_minions_tables"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

HYPIXEL_ITEMS_CACHE = CACHE_DIR / "hypixel_items_cache.json"

# =========================
# WIKI
# =========================
BASE = "https://wiki.hypixel.net/"
INDEX_URL = urljoin(BASE, "Minions")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MinionScraper/3.0"

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}


# =========================
# HELPERS
# =========================
def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def strip_parens(s: str) -> str:
    # "Egg (With Enchanted Egg Upgrade)" -> "Egg"
    return re.sub(r"\s*\(.*?\)\s*", " ", s or "").strip()


def fold_ascii(s: str) -> str:
    # remove accents + lowercase + keep letters/numbers/space
    s = strip_parens(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s_/-]+", " ", s)
    s = norm_space(s)
    return s


def parse_float(s: str) -> Optional[float]:
    if s is None:
        return None
    s = str(s)
    s = s.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9\.\-]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def http_get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def write_debug_csv(minion_id: str, matrix: List[List[str]]) -> None:
    path = DEBUG_DIR / f"{minion_id}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        for row in matrix:
            w.writerow(row)


# =========================
# HYPIXEL ITEMS CACHE -> name mapping
# =========================
def load_hypixel_item_name_map(path: Path) -> Dict[str, str]:
    """
    Returns dict: folded_display_name -> item_id
    Works with several cache shapes (list / {items:[...]} / {data:[...]}).
    """
    if not path.exists():
        print(f"[WARN] hypixel_items_cache.json not found: {path}")
        return {}

    raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))

    # try to locate list of items
    items: Any = None
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for k in ("items", "data", "results"):
            if k in raw and isinstance(raw[k], list):
                items = raw[k]
                break
        if items is None and "items" not in raw and "data" not in raw:
            # sometimes cache stores {"last_update":..., "payload":{...}}
            for v in raw.values():
                if isinstance(v, dict):
                    for k in ("items", "data"):
                        if k in v and isinstance(v[k], list):
                            items = v[k]
                            break
                if items is not None:
                    break

    if not isinstance(items, list):
        print(f"[WARN] Unrecognized hypixel_items_cache.json format: {path}")
        return {}

    name_to_id: Dict[str, str] = {}

    for it in items:
        if not isinstance(it, dict):
            continue

        item_id = (it.get("id") or it.get("item_id") or it.get("skyblock_id") or "").strip()
        display = (it.get("name") or it.get("displayname") or it.get("display_name") or "").strip()

        if not item_id or not display:
            continue

        key = fold_ascii(display)
        if key:
            # prefer first seen (usually fine)
            name_to_id.setdefault(key, item_id)

    return name_to_id


def map_item_name_to_id(item_name: str, name_to_id: Dict[str, str]) -> Optional[str]:
    key = fold_ascii(item_name)
    if not key:
        return None

    # direct hit
    if key in name_to_id:
        return name_to_id[key]

    # common synonyms / special cases
    synonyms = {
        "wheat seeds": "seeds",
        "raw chicken": "chicken",
        "raw beef": "beef",
        "raw porkchop": "pork",
        "raw cod": "raw fish",
        "nether quartz": "quartz",
        "lapis lazuli": "lapis lazuli",
    }
    if key in synonyms and synonyms[key] in name_to_id:
        return name_to_id[synonyms[key]]

    # fallback: try removing trailing words like "log/ore/dust" etc. (soft match)
    parts = key.split()
    if len(parts) >= 2:
        for cut in range(len(parts), 0, -1):
            k2 = " ".join(parts[:cut])
            if k2 in name_to_id:
                return name_to_id[k2]

    return None


# =========================
# MINION LINKS (robust relative+absolute)
# =========================
def extract_minion_links(index_html: str) -> Dict[str, str]:
    soup = BeautifulSoup(index_html, "html.parser")
    out: Dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        abs_url = urljoin(BASE, href)
        if not abs_url.startswith(BASE):
            continue

        path = urlparse(abs_url).path  # "/Wheat_Minion"
        if not path.endswith("_Minion"):
            continue

        slug = path.rsplit("/", 1)[-1]  # "Wheat_Minion"
        raw = slug.replace("_Minion", "")
        minion_id = raw.replace("-", "_").upper()

        out[minion_id] = abs_url

    return dict(sorted(out.items()))


# =========================
# RESOURCES TABLE (FR/EN)
# =========================
def find_resources_table(soup: BeautifulSoup) -> Optional[Tag]:
    # 1) by heading (Resources / Ressources)
    for h in soup.find_all(["h2", "h3", "h4"]):
        t = norm_space(h.get_text(" ", strip=True)).lower()
        if "ressource" in t or "resource" in t:
            cur = h
            while True:
                cur = cur.find_next_sibling()
                if cur is None:
                    break
                if isinstance(cur, Tag):
                    if cur.name == "table":
                        return cur
                    tbl = cur.find("table")
                    if tbl:
                        return tbl

    # 2) fallback signature match
    for tbl in soup.find_all("table"):
        headers = [norm_space(th.get_text(" ", strip=True)).lower() for th in tbl.find_all("th")]
        joined = " ".join(headers)
        if (
            ("article" in joined or "item" in joined)
            and ("%" in joined or "chance" in joined or "prob" in joined)
            and ("récolte" in joined or "recolte" in joined or "harvest" in joined or "amount" in joined)
        ):
            return tbl

    return None


def table_to_matrix(tbl: Tag) -> List[List[str]]:
    mat: List[List[str]] = []
    for tr in tbl.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        mat.append([norm_space(c.get_text(" ", strip=True)) for c in cells])
    return mat


def parse_loot_from_resources_table(soup: BeautifulSoup) -> Tuple[List[Dict[str, Any]], Optional[List[List[str]]]]:
    tbl = find_resources_table(soup)
    if not tbl:
        return [], None

    mat = table_to_matrix(tbl)
    if len(mat) < 2:
        return [], mat

    loot: List[Dict[str, Any]] = []

    # data rows are typically:
    # [Item, amount, %, xp_item, xp_stack, npc_item, npc_stack]
    # (sometimes fewer columns)
    for row in mat[1:]:
        if len(row) < 3:
            continue

        item = row[0]
        amount = parse_float(row[1])
        chance = parse_float(row[2])

        xp_item = parse_float(row[3]) if len(row) > 3 else None
        xp_stack = parse_float(row[4]) if len(row) > 4 else None
        npc_item = parse_float(row[5]) if len(row) > 5 else None
        npc_stack = parse_float(row[6]) if len(row) > 6 else None

        if not item:
            continue
        if amount is None and chance is None:
            continue

        loot.append({
            "item": item,
            "amount": amount,
            "chance_percent": chance,
            "xp_per_item": xp_item,
            "xp_per_stack": xp_stack,
            "npc_sell_per_item": npc_item,
            "npc_sell_per_stack": npc_stack,
        })

    return loot, mat


# =========================
# ACTION TIMES (restore via text regex)
# =========================
def parse_action_times_from_text(minion_name: str, soup: BeautifulSoup) -> Dict[str, Dict[str, float]]:
    """
    Extract tiers 1-12 using the *text* that contains "Time Between Actions: 33s"
    This is the method you had working before (and is why you used to get action_time).
    """
    text = soup.get_text("\n")

    # Tier name format usually includes "<Minion Name> Minion VII" etc.
    # We'll accept both "Time Between Actions" (EN) and a FR-ish fallback.
    # Seconds may be integer or decimal.
    safe_title = re.escape(f"{minion_name} Minion")

    pat = re.compile(
        rf"{safe_title}\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b"
        rf".{{0,1400}}?"
        rf"(?:Time\s+Between\s+Actions|Temps\s+(?:entre|entre\s+les)\s+actions|Temps\s+d['’]action)\s*:\s*"
        rf"([0-9]+(?:\.[0-9]+)?)\s*s",
        re.IGNORECASE | re.DOTALL,
    )

    hits: Dict[int, List[float]] = {}
    for m in pat.finditer(text):
        roman = (m.group(1) or "").upper()
        sec_s = m.group(2)
        tier = ROMAN_TO_INT.get(roman)
        if not tier:
            continue
        try:
            sec = float(sec_s)
        except Exception:
            continue
        hits.setdefault(tier, []).append(sec)

    # choose the most frequent value per tier (mode); tie -> min
    out: Dict[str, Dict[str, float]] = {}
    for tier, vals in hits.items():
        rounded = [round(v, 3) for v in vals]
        counts: Dict[float, int] = {}
        for v in rounded:
            counts[v] = counts.get(v, 0) + 1
        best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        out[str(tier)] = {"action_time": float(best)}

    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


# =========================
# MAIN
# =========================
def main() -> None:
    name_to_id = load_hypixel_item_name_map(HYPIXEL_ITEMS_CACHE)
    print(f"[items] mapping loaded: {len(name_to_id)} names from {HYPIXEL_ITEMS_CACHE}")

    print(f"[1] Fetch index: {INDEX_URL}")
    index_html = http_get(INDEX_URL)

    links = extract_minion_links(index_html)
    print(f"[2] Minions found: {len(links)}")
    if not links:
        print(index_html[:500])
        raise RuntimeError("NO MINIONS FOUND (index html not as expected)")

    result: Dict[str, Any] = {
        "_meta": {
            "source_index": INDEX_URL,
            "generated_by": "scrape_minions_wiki.py",
            "unit_action_time": "seconds",
            "unit_loot_chance": "percent",
            "hypixel_items_cache": str(HYPIXEL_ITEMS_CACHE),
        },
        "minions": {},
        "warnings": [],
        "errors": [],
    }

    # Iterate each minion page
    for i, (minion_id, url) in enumerate(links.items(), 1):
        # minion_id is like "WHEAT"; displayed minion name on wiki is usually "Wheat"
        minion_name = minion_id.title().replace("_", " ")
        print(f"[{i:03d}/{len(links):03d}] {minion_id} -> {url}")

        try:
            html = http_get(url)
            soup = BeautifulSoup(html, "html.parser")

            tiers = parse_action_times_from_text(minion_name, soup)

            loot, mat = parse_loot_from_resources_table(soup)
            if mat:
                write_debug_csv(minion_id, mat)

            # add hypixel mapping for loot items
            for row in loot:
                item_name = row.get("item") or ""
                mapped = map_item_name_to_id(item_name, name_to_id)
                row["item_id"] = mapped  # can be None if unknown

            if not tiers:
                result["warnings"].append({"minion": minion_id, "warn": "no_action_time", "url": url})
            if not loot:
                result["warnings"].append({"minion": minion_id, "warn": "no_loot", "url": url})
            else:
                # warn if mapping failed for some items
                unmapped = [r["item"] for r in loot if not r.get("item_id")]
                if unmapped:
                    result["warnings"].append({
                        "minion": minion_id,
                        "warn": "loot_mapping_missing",
                        "items": unmapped[:10],
                        "url": url
                    })

            result["minions"][minion_id] = {
                "tiers": tiers,
                "loot": loot,
                "wiki": url,
            }

            time.sleep(0.15)

        except Exception as e:
            result["errors"].append({"minion": minion_id, "url": url, "error": str(e)})

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Written: {OUT_JSON}")
    print(f"[DEBUG] CSV tables: {DEBUG_DIR}/")


if __name__ == "__main__":
    main()
