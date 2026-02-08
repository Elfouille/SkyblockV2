from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Set, Dict


# ------------------------------------------------------------
# Import depuis la racine du projet
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hypixel_client import HypixelClient  # noqa: E402


PLAYERS_JSON = ROOT / "cache" / "players.json"


# ------------------------------------------------------------
# Utils UUID
# ------------------------------------------------------------
def _looks_like_uuid(s: str) -> bool:
    s = (s or "").strip()
    if len(s) == 32:
        return all(c in "0123456789abcdefABCDEF" for c in s)
    if len(s) == 36:
        parts = s.split("-")
        if [len(p) for p in parts] != [8, 4, 4, 4, 12]:
            return False
        return all(all(c in "0123456789abcdefABCDEF" for c in p) for p in parts)
    return False


def _normalize_uuid(u: str) -> str:
    u = (u or "").strip()
    if len(u) == 32 and _looks_like_uuid(u):
        return f"{u[0:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:32]}"
    return u


# ------------------------------------------------------------
# Extraction de TOUS les UUID depuis players.json
# ------------------------------------------------------------
def extract_all_uuids(data: Any) -> Set[str]:
    found: Set[str] = set()

    def visit(obj: Any):
        if isinstance(obj, str):
            if _looks_like_uuid(obj):
                found.add(_normalize_uuid(obj))
            return

        if isinstance(obj, dict):
            for v in obj.values():
                visit(v)
            return

        if isinstance(obj, list):
            for v in obj:
                visit(v)
            return

    visit(data)
    return found


def load_all_uuids(players_path: Path) -> Set[str]:
    if not players_path.exists():
        raise FileNotFoundError(f"players.json introuvable: {players_path}")

    data = json.loads(players_path.read_text(encoding="utf-8"))
    uuids = extract_all_uuids(data)

    if not uuids:
        raise RuntimeError("Aucun UUID valide trouvé dans players.json")

    return uuids


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main() -> None:
    client = HypixelClient()

    uuids = load_all_uuids(PLAYERS_JSON)

    print("\n=== Hypixel v2 test (ALL UUIDS) ===")
    print(f"players.json: {PLAYERS_JSON}")
    print(f"UUID trouvés: {len(uuids)}\n")

    # ---------------- Collections (1 seule fois)
    print("[0] Collections (global)...")
    collections = client.load_collections_cached()
    print("  -> OK | collections:", len(collections.get("collections", {})))

    # ---------------- Loop joueurs
    for idx, uuid in enumerate(sorted(uuids), start=1):
        print(f"\n[{idx}/{len(uuids)}] UUID = {uuid}")

        # ---- Status
        try:
            status = client.load_status_cached(uuid)
            online = status.get("session", {}).get("online")
            print("  Status:", "ONLINE" if online else "offline")
        except Exception as e:
            print("  Status: ERROR ->", e)
            continue

        # ---- Profiles
        try:
            profiles = client.load_profiles_cached(uuid)
            prof_list = profiles.get("profiles") or []
            print("  Profiles:", len(prof_list))
        except Exception as e:
            print("  Profiles: ERROR ->", e)
            continue

        if not prof_list:
            continue

        # ---- Profil sélectionné / fallback
        selected = next((p for p in prof_list if p.get("selected")), prof_list[0])
        profile_id = selected.get("profile_id")
        print("  Selected profile_id:", profile_id)

        # ---- SkyBlock profile
        try:
            profile = client.load_skyblock_profile_cached(profile_id)
            members = profile.get("profile", {}).get("members", {})
            print("  Members:", len(members))
        except Exception as e:
            print("  Profile: ERROR ->", e)
            continue

        # ---- Garden
        try:
            garden = client.load_garden_cached(profile_id)
            garden_keys = list(garden.get("garden", {}).keys())
            print("  Garden keys:", garden_keys)
        except Exception as e:
            print("  Garden: ERROR ->", e)

    print("\n=== DONE ===\n")


if __name__ == "__main__":
    main()
