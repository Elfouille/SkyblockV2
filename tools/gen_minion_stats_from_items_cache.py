from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from common import CACHE_DIR, load_json, save_json

ITEMS_CACHE = CACHE_DIR / "hypixel_items_cache.json"
OUT_FILE = CACHE_DIR / "minion_stats.json"

def main() -> int:
    raw = load_json(ITEMS_CACHE, default={})
    if not isinstance(raw, dict):
        print("items cache invalid")
        return 1

    # items cache format: {"ts":..., "items":{ "ID": {...}, ...}}
    items = raw.get("items")
    if not isinstance(items, dict):
        # parfois tu as déjà directement la map id->item
        items = raw if isinstance(raw, dict) else {}

    out: Dict[str, Any] = {}

    for item_id, it in items.items():
        if not isinstance(it, dict):
            continue

        # On cible les minions via generator + generator_tier
        gen = it.get("generator")
        tier = it.get("generator_tier")
        if not gen or tier is None:
            continue

        try:
            tier_i = int(tier)
        except Exception:
            continue

        gen = str(gen).strip().upper()
        if not gen:
            continue

        # bucket par minion
        entry = out.setdefault(gen, {"tiers": {}, "tier11": None})

        # stocker l'item id du tier + quelques infos (utile pour icons/labels)
        entry["tiers"][str(tier_i)] = {
            "item_id": str(it.get("id") or item_id),
            "name": str(it.get("name") or ""),
            "rarity": str(it.get("tier") or ""),
        }

        # si tier 11 existe on prépare un placeholder tier11
        if tier_i == 11 and entry.get("tier11") is None:
            entry["tier11"] = {
                "seconds_per_action": 0,
                "drops": [],  # [{"item":"...", "qty":1}]
                "notes": "AUTO from hypixel_items_cache.json: fill drops + seconds manually or via external dataset",
            }

    # tri propre
    out_sorted = dict(sorted(out.items(), key=lambda kv: kv[0]))
    save_json(OUT_FILE, out_sorted)
    print(f"OK -> {OUT_FILE} | minions: {len(out_sorted)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
