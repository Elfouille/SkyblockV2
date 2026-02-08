from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import requests

from common import CACHE_DIR, load_json, save_json


# ------------------------------------------------------------
# Constants & URLs
# ------------------------------------------------------------
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BazaarUI/2.0"

# v1
HYPIXEL_BAZAAR_URL = "https://api.hypixel.net/skyblock/bazaar"
HYPIXEL_ITEMS_URL = "https://api.hypixel.net/resources/skyblock/items"
HYPIXEL_PLAYER_URL = "https://api.hypixel.net/player"

# v2 (existing)
HYPIXEL_V2_SKYBLOCK_PROFILES_URL = "https://api.hypixel.net/v2/skyblock/profiles"
HYPIXEL_V2_SKYBLOCK_MUSEUM_URL = "https://api.hypixel.net/v2/skyblock/museum"

# v2 (new)
HYPIXEL_V2_COLLECTIONS_URL = "https://api.hypixel.net/v2/resources/skyblock/collections"
HYPIXEL_V2_STATUS_URL = "https://api.hypixel.net/v2/status"
HYPIXEL_V2_SKYBLOCK_PROFILE_URL = "https://api.hypixel.net/v2/skyblock/profile"
HYPIXEL_V2_SKYBLOCK_GARDEN_URL = "https://api.hypixel.net/v2/skyblock/garden"

# cache files
KEY_FILE = CACHE_DIR / "hypixel_key.json"
BAZAAR_CACHE = CACHE_DIR / "bazaar_cache.json"
ITEMS_CACHE = CACHE_DIR / "hypixel_items_cache.json"

# v2 cache files (global)
COLLECTIONS_CACHE = CACHE_DIR / "hypixel_v2_collections_cache.json"

# v2 cache dirs (per player / per profile)
V2_STATUS_DIR = CACHE_DIR / "hypixel_v2_status"         # <uuid>.json
V2_PROFILES_DIR = CACHE_DIR / "hypixel_v2_profiles"     # <uuid>.json
V2_PROFILE_DIR = CACHE_DIR / "hypixel_v2_profile"       # <profile_id>.json
V2_GARDEN_DIR = CACHE_DIR / "hypixel_v2_garden"         # <profile_id>.json


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def load_api_key() -> str:
    raw = load_json(KEY_FILE, default={})
    if isinstance(raw, dict):
        return (raw.get("key") or "").strip()
    return ""


def _now() -> float:
    return time.time()


def _safe_key(s: str) -> str:
    return (s or "").strip()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_filename_key(s: str) -> str:
    """
    Transforme une clé (uuid/profile_id) en nom de fichier safe.
    On garde [a-zA-Z0-9_-] uniquement.
    """
    s = (s or "").strip()
    out = []
    for c in s:
        if c.isalnum() or c in ("-", "_"):
            out.append(c)
    return "".join(out) or "unknown"


def _read_cache_value(path: Path) -> Optional[dict]:
    raw = load_json(path, default={})
    if isinstance(raw, dict) and "ts" in raw and "value" in raw:
        return raw
    return None


def _write_cache_value(path: Path, ts: float, value: dict) -> None:
    save_json(path, {"ts": ts, "value": value})


# ------------------------------------------------------------
# Data models
# ------------------------------------------------------------
@dataclass
class BazaarPrice:
    buy: float   # highest buy order (sell to bazaar)
    sell: float  # lowest sell offer (buy from bazaar)


# ------------------------------------------------------------
# Client
# ------------------------------------------------------------
class HypixelClient:
    def __init__(self, key: Optional[str] = None):
        self.key = key or load_api_key()

    # ---------------- HTTP ----------------
    def _get(self, url: str, params: dict) -> dict:
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": UA},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _require_key(self) -> None:
        if not self.key:
            raise RuntimeError("No Hypixel API key. Put it in cache/hypixel_key.json")

    def _assert_success(self, data: dict) -> dict:
        if not isinstance(data, dict) or not data.get("success"):
            raise RuntimeError(f"Hypixel API error: {data}")
        return data

    # ---------------- Bazaar (v1) ----------------
    def fetch_bazaar(self) -> Dict[str, BazaarPrice]:
        self._require_key()

        data = self._assert_success(self._get(HYPIXEL_BAZAAR_URL, {"key": self.key}))
        products = data.get("products") or {}
        out: Dict[str, BazaarPrice] = {}

        for pid, p in products.items():
            qs = (p or {}).get("quick_status") or {}
            try:
                buy = float(qs.get("buyPrice") or 0.0)
                sell = float(qs.get("sellPrice") or 0.0)
            except Exception:
                buy, sell = 0.0, 0.0

            out[str(pid)] = BazaarPrice(buy=buy, sell=sell)

        return out

    # ---------------- Items (v1) ----------------
    def fetch_items_map(self) -> Dict[str, dict]:
        data = self._assert_success(self._get(HYPIXEL_ITEMS_URL, {}))
        items = data.get("items") or []
        mp: Dict[str, dict] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            iid = str(it.get("id") or "").strip()
            if iid:
                mp[iid] = it
        return mp

    # ---------------- Player (GLOBAL v1) ----------------
    def fetch_player(self, uuid: str) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(self._get(HYPIXEL_PLAYER_URL, {"key": self.key, "uuid": uuid}))

    # ---------------- SkyBlock Profiles (v2) ----------------
    def fetch_profiles(self, uuid: str) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(
            self._get(HYPIXEL_V2_SKYBLOCK_PROFILES_URL, {"key": self.key, "uuid": uuid})
        )

    # ---------------- SkyBlock Museum (v2) ----------------
    def fetch_museum(self, profile_id: str) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(
            self._get(HYPIXEL_V2_SKYBLOCK_MUSEUM_URL, {"key": self.key, "profile": profile_id})
        )

    # ---------------- NEW v2 endpoints ----------------
    def fetch_collections(self) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(self._get(HYPIXEL_V2_COLLECTIONS_URL, {"key": self.key}))

    def fetch_status(self, uuid: str) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(self._get(HYPIXEL_V2_STATUS_URL, {"key": self.key, "uuid": uuid}))

    def fetch_skyblock_profile(self, profile_id: str) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(
            self._get(HYPIXEL_V2_SKYBLOCK_PROFILE_URL, {"key": self.key, "profile": profile_id})
        )

    def fetch_garden(self, profile_id: str) -> Dict[str, Any]:
        self._require_key()
        return self._assert_success(
            self._get(HYPIXEL_V2_SKYBLOCK_GARDEN_URL, {"key": self.key, "profile": profile_id})
        )

    # ------------------------------------------------------------
    # Cache helpers (existing)
    # ------------------------------------------------------------
    def load_bazaar_cached(self, max_age_sec: int = 60) -> Tuple[Dict[str, BazaarPrice], bool]:
        now = _now()
        cached = load_json(BAZAAR_CACHE, default={})

        if isinstance(cached, dict) and "ts" in cached and "prices" in cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec:
                    return _decode_prices(cached["prices"]), False
            except Exception:
                pass

        prices = self.fetch_bazaar()
        save_json(BAZAAR_CACHE, {"ts": now, "prices": _encode_prices(prices)})
        return prices, True

    def load_items_cached(self, max_age_days: int = 7) -> Dict[str, dict]:
        now = _now()
        max_age_sec = int(max_age_days * 86400)

        cached = load_json(ITEMS_CACHE, default={})
        if isinstance(cached, dict) and "ts" in cached and "items" in cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec and isinstance(cached["items"], dict):
                    return cached["items"]
            except Exception:
                pass

        mp = self.fetch_items_map()
        save_json(ITEMS_CACHE, {"ts": now, "items": mp})
        return mp

    # ------------------------------------------------------------
    # Cache helpers (v2)
    # ------------------------------------------------------------
    def load_collections_cached(self, max_age_days: int = 7) -> Dict[str, Any]:
        now = _now()
        max_age_sec = int(max_age_days * 86400)

        cached = load_json(COLLECTIONS_CACHE, default={})
        if isinstance(cached, dict) and "ts" in cached and "value" in cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec:
                    return cached["value"]
            except Exception:
                pass

        data = self.fetch_collections()
        save_json(COLLECTIONS_CACHE, {"ts": now, "value": data})
        return data

    def load_status_cached(self, uuid: str, max_age_sec: int = 20) -> Dict[str, Any]:
        """
        Cache par joueur => cache/hypixel_v2_status/<uuid>.json
        """
        uuid = _safe_key(uuid)
        if not uuid:
            raise ValueError("uuid is empty")

        now = _now()
        _ensure_dir(V2_STATUS_DIR)
        f = V2_STATUS_DIR / f"{_safe_filename_key(uuid)}.json"

        cached = _read_cache_value(f)
        if cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec and isinstance(cached["value"], dict):
                    return cached["value"]
            except Exception:
                pass

        value = self.fetch_status(uuid)
        _write_cache_value(f, now, value)
        return value

    def load_profiles_cached(self, uuid: str, max_age_sec: int = 120) -> Dict[str, Any]:
        """
        Cache par joueur => cache/hypixel_v2_profiles/<uuid>.json
        """
        uuid = _safe_key(uuid)
        if not uuid:
            raise ValueError("uuid is empty")

        now = _now()
        _ensure_dir(V2_PROFILES_DIR)
        f = V2_PROFILES_DIR / f"{_safe_filename_key(uuid)}.json"

        cached = _read_cache_value(f)
        if cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec and isinstance(cached["value"], dict):
                    return cached["value"]
            except Exception:
                pass

        value = self.fetch_profiles(uuid)
        _write_cache_value(f, now, value)
        return value

    def load_skyblock_profile_cached(self, profile_id: str, max_age_sec: int = 120) -> Dict[str, Any]:
        """
        Cache par profil => cache/hypixel_v2_profile/<profile_id>.json
        """
        profile_id = _safe_key(profile_id)
        if not profile_id:
            raise ValueError("profile_id is empty")

        now = _now()
        _ensure_dir(V2_PROFILE_DIR)
        f = V2_PROFILE_DIR / f"{_safe_filename_key(profile_id)}.json"

        cached = _read_cache_value(f)
        if cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec and isinstance(cached["value"], dict):
                    return cached["value"]
            except Exception:
                pass

        value = self.fetch_skyblock_profile(profile_id)
        _write_cache_value(f, now, value)
        return value

    def load_garden_cached(self, profile_id: str, max_age_sec: int = 120) -> Dict[str, Any]:
        """
        Cache par profil => cache/hypixel_v2_garden/<profile_id>.json
        """
        profile_id = _safe_key(profile_id)
        if not profile_id:
            raise ValueError("profile_id is empty")

        now = _now()
        _ensure_dir(V2_GARDEN_DIR)
        f = V2_GARDEN_DIR / f"{_safe_filename_key(profile_id)}.json"

        cached = _read_cache_value(f)
        if cached:
            try:
                ts = float(cached["ts"])
                if (now - ts) <= max_age_sec and isinstance(cached["value"], dict):
                    return cached["value"]
            except Exception:
                pass

        value = self.fetch_garden(profile_id)
        _write_cache_value(f, now, value)
        return value


# ------------------------------------------------------------
# Encoding helpers
# ------------------------------------------------------------
def _encode_prices(prices: Dict[str, BazaarPrice]) -> Dict[str, dict]:
    return {k: {"buy": v.buy, "sell": v.sell} for (k, v) in prices.items()}


def _decode_prices(raw: Dict[str, dict]) -> Dict[str, BazaarPrice]:
    out: Dict[str, BazaarPrice] = {}
    if not isinstance(raw, dict):
        return out

    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        try:
            out[str(k)] = BazaarPrice(
                buy=float(v.get("buy") or 0.0),
                sell=float(v.get("sell") or 0.0),
            )
        except Exception:
            out[str(k)] = BazaarPrice(buy=0.0, sell=0.0)

    return out
