from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from common import CACHE_DIR, load_json, save_json


SETTINGS_FILE = CACHE_DIR / "settings.json"
KEY_FILE = CACHE_DIR / "hypixel_key.json"


@dataclass
class AppSettings:
    api_key: str = ""
    bazaar_cache_seconds: int = 60
    items_cache_days: int = 7
    enable_icons: bool = True
    allow_icon_downloads: bool = False

    auto_refresh_items: bool = True
    auto_refresh_crafts: bool = True

    # ✅ NEW: Museum auto-refresh
    auto_refresh_museum: bool = False
    museum_refresh_seconds: int = 120  # interval du timer (tick)
    museum_cache_ttl_seconds: int = 120  # TTL cache (anti-spam réseau)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"1", "true", "yes", "on"}:
            return True
        if value.lower() in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        iv = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, iv))


def _load_api_key() -> str:
    raw = load_json(KEY_FILE, default={})
    if isinstance(raw, dict):
        return str(raw.get("key") or "").strip()
    return ""


def _save_api_key(key: str) -> None:
    key = (key or "").strip()
    if not key:
        return
    save_json(KEY_FILE, {"key": key})


def load_settings() -> AppSettings:
    raw = load_json(SETTINGS_FILE, default={})
    if not isinstance(raw, dict):
        raw = {}

    api_key = str(raw.get("api_key") or "").strip()
    if not api_key:
        api_key = _load_api_key()

    return AppSettings(
        api_key=api_key,
        bazaar_cache_seconds=_coerce_int(raw.get("bazaar_cache_seconds"), 60, 10, 3600),
        items_cache_days=_coerce_int(raw.get("items_cache_days"), 7, 1, 60),
        enable_icons=_coerce_bool(raw.get("enable_icons"), True),
        allow_icon_downloads=_coerce_bool(raw.get("allow_icon_downloads"), False),
        auto_refresh_items=_coerce_bool(raw.get("auto_refresh_items"), True),
        auto_refresh_crafts=_coerce_bool(raw.get("auto_refresh_crafts"), True),

        # ✅ NEW
        auto_refresh_museum=_coerce_bool(raw.get("auto_refresh_museum"), False),
        museum_refresh_seconds=_coerce_int(raw.get("museum_refresh_seconds"), 120, 10, 3600),
        museum_cache_ttl_seconds=_coerce_int(raw.get("museum_cache_ttl_seconds"), 120, 10, 3600),
    )


def save_settings(settings: AppSettings) -> None:
    data: Dict[str, Any] = {
        "api_key": settings.api_key,
        "bazaar_cache_seconds": int(settings.bazaar_cache_seconds),
        "items_cache_days": int(settings.items_cache_days),
        "enable_icons": bool(settings.enable_icons),
        "allow_icon_downloads": bool(settings.allow_icon_downloads),
        "auto_refresh_items": bool(settings.auto_refresh_items),
        "auto_refresh_crafts": bool(settings.auto_refresh_crafts),

        # ✅ NEW
        "auto_refresh_museum": bool(settings.auto_refresh_museum),
        "museum_refresh_seconds": int(settings.museum_refresh_seconds),
        "museum_cache_ttl_seconds": int(settings.museum_cache_ttl_seconds),
    }
    save_json(SETTINGS_FILE, data)
    if settings.api_key:
        _save_api_key(settings.api_key)
