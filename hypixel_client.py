from __future__ import annotations

import time
from dataclasses import dataclass
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

# v2 (IMPORTANT)
HYPIXEL_V2_SKYBLOCK_PROFILES_URL = "https://api.hypixel.net/v2/skyblock/profiles"
HYPIXEL_V2_SKYBLOCK_MUSEUM_URL = "https://api.hypixel.net/v2/skyblock/museum"

# cache files
KEY_FILE = CACHE_DIR / "hypixel_key.json"
BAZAAR_CACHE = CACHE_DIR / "bazaar_cache.json"
ITEMS_CACHE = CACHE_DIR / "hypixel_items_cache.json"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def load_api_key() -> str:
    raw = load_json(KEY_FILE, default={})
    if isinstance(raw, dict):
        return (raw.get("key") or "").strip()
    return ""


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

    # ---------------- Bazaar (v1) ----------------
    def fetch_bazaar(self) -> Dict[str, BazaarPrice]:
        self._require_key()

        data = self._get(HYPIXEL_BAZAAR_URL, {"key": self.key})
        if not data.get("success"):
            raise RuntimeError(f"Hypixel API error: {data}")

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
        data = self._get(HYPIXEL_ITEMS_URL, {})
        if not data.get("success"):
            raise RuntimeError(f"Hypixel API error: {data}")

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

        data = self._get(HYPIXEL_PLAYER_URL, {"key": self.key, "uuid": uuid})
        if not data.get("success"):
            raise RuntimeError(f"Hypixel API error: {data}")
        return data

    # ---------------- SkyBlock Profiles (v2) ----------------
    def fetch_profiles(self, uuid: str) -> Dict[str, Any]:
        """
        GET /v2/skyblock/profiles?uuid=<uuid>
        """
        self._require_key()

        data = self._get(
            HYPIXEL_V2_SKYBLOCK_PROFILES_URL,
            {"key": self.key, "uuid": uuid},
        )
        if not data.get("success"):
            raise RuntimeError(f"Hypixel API error: {data}")
        return data

    # ---------------- SkyBlock Museum (v2) ----------------
    def fetch_museum(self, profile_id: str) -> Dict[str, Any]:
        """
        GET /v2/skyblock/museum?profile=<profile_id>
        """
        self._require_key()

        data = self._get(
            HYPIXEL_V2_SKYBLOCK_MUSEUM_URL,
            {"key": self.key, "profile": profile_id},
        )
        if not data.get("success"):
            raise RuntimeError(f"Hypixel API error: {data}")
        return data

    # ---------------- Cache helpers ----------------
    def load_bazaar_cached(self, max_age_sec: int = 60) -> Tuple[Dict[str, BazaarPrice], bool]:
        """
        Returns (prices, fresh_from_api)
        """
        now = time.time()
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
        now = time.time()
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
