from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

INDEX_URL = "https://wiki.hypixel.net/Minions"
WIKI_BASE = "https://wiki.hypixel.net"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkyblockV2/MinionTools"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

# ----------------------------
# Repo / cache paths
# ----------------------------
def find_repo_root(start: Path) -> Path:
    """
    Find SkyblockV2 repo root by looking for 'cache' folder.
    Handles running from SkyblockV2/tools/minion.
    """
    p = start.resolve()
    for parent in [p] + list(p.parents):
        # typical: <repo>/cache
        if (parent / "cache").is_dir():
            return parent
        # sometimes: <root>/SkyblockV2/cache
        if (parent / "SkyblockV2" / "cache").is_dir():
            return parent / "SkyblockV2"
    raise RuntimeError("Impossible de trouver le repo root (dossier contenant 'cache').")


# ----------------------------
# Fetch
# ----------------------------
def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text


# ----------------------------
# Minion index parsing
# ----------------------------
MINION_LINK_RE = re.compile(r'href="(/[^"]+_Minion)"', re.I)

def parse_index_minions(html: str) -> List[Tuple[str, str]]:
    """
    Returns list of (MINION_KEY, full_url) from index page.
    MINION_KEY is uppercase with underscores.
    """
    links = sorted(set(m.group(1) for m in MINION_LINK_RE.finditer(html)))
    out: List[Tuple[str, str]] = []
    for rel in links:
        slug = rel.strip("/")
        base = slug.replace("_Minion", "")
        key = re.sub(r"[^A-Za-z0-9]+", "_", base).upper()
        url = f"{WIKI_BASE}/{slug}"
        out.append((key, url))

    seen = set()
    uniq: List[Tuple[str, str]] = []
    for k, u in out:
        if k not in seen:
            seen.add(k)
            uniq.append((k, u))
    return uniq


# ----------------------------
# HTML helpers (no lxml / bs4)
# ----------------------------
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")

def html_to_text(html: str) -> str:
    html = SCRIPT_RE.sub(" ", html)
    html = STYLE_RE.sub(" ", html)
    html = html.replace("<br", "\n<br")
    html = html.replace("</tr>", "\n</tr>")
    html = html.replace("</p>", "\n</p>")
    html = TAG_RE.sub(" ", html)
    html = unescape(html)
    html = re.sub(r"[ \t\r\f\v]+", " ", html)
    html = re.sub(r"\n{2,}", "\n", html)
    return html.strip()


class SimpleTableParser:
    TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.I | re.S)
    ROW_RE = re.compile(r"<tr\b[^>]*>.*?</tr>", re.I | re.S)
    CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)

    @staticmethod
    def extract_tables(html: str) -> List[List[List[str]]]:
        tables: List[List[List[str]]] = []
        for tmatch in SimpleTableParser.TABLE_RE.finditer(html):
            thtml = tmatch.group(0)
            rows: List[List[str]] = []
            for rmatch in SimpleTableParser.ROW_RE.finditer(thtml):
                rhtml = rmatch.group(0)
                cells: List[str] = []
                for cm in SimpleTableParser.CELL_RE.finditer(rhtml):
                    raw = cm.group(1)
                    txt = html_to_text(raw)
                    txt = re.sub(r"\s+", " ", txt).strip()
                    cells.append(txt)
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables


# ----------------------------
# Hypixel items cache mapping (name -> id)
# ----------------------------
def _clean_name(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\(.*?\)", "", s).strip()
    s = s.replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def load_items_name_to_id(items_cache_path: Path) -> Dict[str, str]:
    """
    Supports common cache shapes:
    - {"items":[{"id":"WHEAT","name":"Wheat", ...}, ...]}
    - {"items":{"WHEAT":{"name":"Wheat"}, ...}}
    - {"WHEAT":{"name":"Wheat"}, ...}
    - [{"id":"WHEAT","name":"Wheat"}, ...]
    """
    if not items_cache_path.exists():
        return {}

    raw = json.loads(items_cache_path.read_text(encoding="utf-8"))
    name_to_id: Dict[str, str] = {}

    def ingest_item(item_id: Optional[str], obj: Any) -> None:
        if not item_id:
            return
        if isinstance(obj, dict):
            n = obj.get("name") or obj.get("displayname") or obj.get("display_name")
            if isinstance(n, str) and n.strip():
                name_to_id[_clean_name(n)] = item_id
        # allow direct id lookup too
        name_to_id[_clean_name(item_id)] = item_id

    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        for obj in raw["items"]:
            if isinstance(obj, dict):
                item_id = obj.get("id") or obj.get("item_id")
                if isinstance(item_id, str):
                    ingest_item(item_id, obj)
        return name_to_id

    if isinstance(raw, dict):
        if isinstance(raw.get("items"), dict):
            raw = raw["items"]
        for k, v in raw.items():
            if isinstance(k, str):
                ingest_item(k, v)
        return name_to_id

    if isinstance(raw, list):
        for obj in raw:
            if isinstance(obj, dict):
                item_id = obj.get("id") or obj.get("item_id")
                if isinstance(item_id, str):
                    ingest_item(item_id, obj)
        return name_to_id

    return name_to_id


def map_item_name_to_id(item_name: str, name_to_id: Dict[str, str]) -> Optional[str]:
    n = _clean_name(item_name)

    if n in name_to_id:
        return name_to_id[n]

    # remove "160 " prefix etc
    n2 = re.sub(r"^\d+\s+", "", n).strip()
    if n2 in name_to_id:
        return name_to_id[n2]

    aliases = {
        "wheat seeds": "seeds",
        "raw cod": "raw fish",
        "raw salmon": "raw fish",
        "tropical fish": "raw fish",
        "pufferfish": "raw fish",
        "lapis lazuli": "ink sack",
        "cocoa beans": "ink sack",
        "gunpowder": "sulphur",
        "nether wart": "nether stalk",
    }
    if n2 in aliases and aliases[n2] in name_to_id:
        return name_to_id[aliases[n2]]

    if n2.endswith("s") and n2[:-1] in name_to_id:
        return name_to_id[n2[:-1]]

    return None


# ----------------------------
# Small parsing helpers
# ----------------------------
def parse_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^\d.\-+]", "", s)
    if not s or s in {".", "-", "+"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def looks_like_resources_table(rows: List[List[str]]) -> bool:
    header = " | ".join(rows[0]).lower()
    keywords = ["item", "article", "articles", "récolte", "harvest", "npc", "pni", "sell", "price"]
    return sum(1 for k in keywords if k in header) >= 2


def minion_display_name_from_key(key: str) -> str:
    # "CAVE_SPIDER" -> "Cave Spider"
    return " ".join(w.capitalize() for w in key.split("_"))


def polite_sleep():
    time.sleep(0.12)
