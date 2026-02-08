from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


PROFILES_DIR = Path(r"D:\Skyblock_V2\SkyblockV2\cache\hypixel_v2_profiles")
OUT_PATH = Path(r"D:\Skyblock_V2\SkyblockV2\cache\crafted_minions_with_tiers.json")


def _safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return None


def _find_crafted_generators_values(obj: Any) -> List[Any]:
    """Retourne toutes les valeurs associées à la clé 'crafted_generators' (où qu'elle soit)."""
    out: List[Any] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "crafted_generators":
                    out.append(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return out


def _has_numeric_tier(s: str) -> bool:
    # ex: COBBLESTONE_10 / NETHER_WARTS_1
    parts = s.split("_")
    return len(parts) >= 2 and parts[-1].isdigit()


def _sort_key(s: str) -> Tuple[str, int]:
    base, tier = s.rsplit("_", 1)
    return base, int(tier)


def main() -> int:
    if not PROFILES_DIR.exists():
        print(f"[ERR] Dossier introuvable: {PROFILES_DIR}")
        return 2

    files = sorted(p for p in PROFILES_DIR.rglob("*.json") if p.is_file())
    if not files:
        OUT_PATH.write_text("[]", encoding="utf-8")
        print("[WARN] Aucun JSON trouvé.")
        return 0

    ids: Set[str] = set()
    failed = 0
    crafted_blocks = 0

    for p in files:
        data = _safe_load_json(p)
        if data is None:
            failed += 1
            continue

        values = _find_crafted_generators_values(data)
        for val in values:
            crafted_blocks += 1

            # cas normal: dict {"COBBLESTONE_1": 1, ...}
            if isinstance(val, dict):
                for k in val.keys():
                    if isinstance(k, str):
                        k = k.strip()
                        if _has_numeric_tier(k):
                            ids.add(k)

            # cas rare: liste ["COBBLESTONE_1", ...]
            elif isinstance(val, list):
                for it in val:
                    if isinstance(it, str):
                        it = it.strip()
                        if _has_numeric_tier(it):
                            ids.add(it)

    out_list = sorted(ids, key=_sort_key)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out_list, indent=2, ensure_ascii=False), encoding="utf-8")

    print("[OK] crafted_minions_with_tiers.json généré")
    print(f" -> {OUT_PATH}")
    print(f"    files={len(files)} crafted_generators_blocks={crafted_blocks} count={len(out_list)} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
