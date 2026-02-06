from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Tuple

import requests

from common import CACHE_DIR

ICONS_DIR = CACHE_DIR / "item_icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

ITEMS_CACHE_JSON = CACHE_DIR / "hypixel_items_cache.json"
HYPIXEL_ITEMS_URL = "https://api.hypixel.net/resources/skyblock/items"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BazaarUI/2.0"


@dataclass
class IconResult:
    path: Optional[Path]
    source: str
    reason: str


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_hypixel_items() -> dict:
    r = requests.get(HYPIXEL_ITEMS_URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def load_hypixel_items_map(max_age_days: int = 7) -> Dict[str, dict]:
    now = time.time()
    max_age_sec = max(1, int(max_age_days * 86400))

    cached = _load_json(ITEMS_CACHE_JSON)
    if isinstance(cached, dict) and "ts" in cached and "items" in cached:
        try:
            ts = float(cached["ts"])
            if (now - ts) <= max_age_sec and isinstance(cached["items"], dict):
                return {str(k): v for (k, v) in cached["items"].items()}
        except Exception:
            pass

    try:
        data = _fetch_hypixel_items()
        items_list = data.get("items") or []
        mp: Dict[str, dict] = {}
        for it in items_list:
            if not isinstance(it, dict):
                continue
            iid = str(it.get("id") or "").strip()
            if iid:
                mp[iid] = it
        _save_json(ITEMS_CACHE_JSON, {"ts": now, "items": mp})
        return mp
    except Exception:
        if isinstance(cached, dict) and isinstance(cached.get("items"), dict):
            return {str(k): v for (k, v) in cached["items"].items()}
        return {}


def _extract_texture_url_from_skin_b64(skin_b64: str) -> Optional[str]:
    if not skin_b64:
        return None
    try:
        raw = base64.b64decode(skin_b64).decode("utf-8", errors="replace")
        j = json.loads(raw)
        url = j.get("textures", {}).get("SKIN", {}).get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url.replace("http://", "https://", 1)
    except Exception:
        return None
    return None


def _download_to(path: Path, url: str) -> Tuple[bool, str]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return False, f"http {r.status_code}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def get_icon_path(item_id: str, *, enable_icons: bool = True, allow_download: bool = False) -> IconResult:
    item_id = (item_id or "").strip().upper()
    if not enable_icons or not item_id:
        return IconResult(None, "none", "disabled or empty")

    out_path = ICONS_DIR / f"{item_id}.png"
    if out_path.exists() and out_path.stat().st_size > 0:
        return IconResult(out_path, "cache", "ok")

    if not allow_download:
        return IconResult(None, "none", "missing (download disabled)")

    mp = load_hypixel_items_map()
    it = mp.get(item_id)
    if not it:
        return IconResult(None, "none", "not found in items map")

    skin = it.get("skin")
    if not isinstance(skin, str) or not skin.strip():
        return IconResult(None, "none", "no skin")

    url = _extract_texture_url_from_skin_b64(skin.strip())
    if not url:
        return IconResult(None, "none", "skin decode failed")

    ok, reason = _download_to(out_path, url)
    if not ok:
        return IconResult(None, "none", f"download failed: {reason}")
    return IconResult(out_path, "download", "ok")
