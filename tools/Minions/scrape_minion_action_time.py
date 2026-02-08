from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from _wiki_common import (
    INDEX_URL,
    fetch,
    find_repo_root,
    html_to_text,
    minion_display_name_from_key,
    parse_index_minions,
    polite_sleep,
)

ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}
ROMAN_RE = r"(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)"  # never empty


def extract_action_times(page_text: str, display_name: str) -> Dict[str, Dict[str, float]]:
    """
    Extract tier -> action_time seconds.
    Pattern:
      "<Name> Minion <ROMAN> ... Time Between Actions: 48s"
    """
    tiers: Dict[str, Dict[str, float]] = {}

    pattern = re.compile(
        rf"\b{re.escape(display_name)}\s+Minion\s+{ROMAN_RE}\b.*?\bTime Between Actions:\s*([0-9]+(?:\.[0-9]+)?)\s*s\b",
        re.I | re.S,
    )

    for m in pattern.finditer(page_text):
        roman = (m.group(1) or "").upper().strip()
        sec_s = m.group(2)

        tier_num = ROMAN_MAP.get(roman)
        if tier_num is None:
            continue

        try:
            secs = float(sec_s)
        except Exception:
            continue

        tiers[str(tier_num)] = {"action_time": secs}

    return tiers


def main() -> int:
    repo = find_repo_root(Path(__file__).parent)
    cache_dir = repo / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    out_path = cache_dir / "minion_action_time.json"

    print(f"[repo]  {repo}")
    print(f"[cache] {cache_dir}")
    print(f"[out]   {out_path}")

    print(f"[1] Fetch index: {INDEX_URL}")
    index_html = fetch(INDEX_URL)
    minions = parse_index_minions(index_html)
    print(f"[2] Minions found: {len(minions)}")

    data: Dict[str, Any] = {
        "_meta": {
            "source_index": INDEX_URL,
            "generated_by": "tools/minion/scrape_minion_action_time.py",
            "unit_action_time": "seconds",
        },
        "minions": {},
        "warnings": [],
        "errors": [],
    }

    for i, (key, url) in enumerate(minions, 1):
        print(f"[{i:03d}/{len(minions):03d}] {key}")
        try:
            html = fetch(url)
            text = html_to_text(html)

            display_name = minion_display_name_from_key(key)
            tiers = extract_action_times(text, display_name)

            if not tiers:
                data["warnings"].append({"warn": "missing_action_time", "minion": key, "url": url})

            data["minions"][key] = {
                "tiers": tiers,
                "wiki": url,
            }

            polite_sleep()
        except Exception as e:
            data["errors"].append({"minion": key, "url": url, "error": repr(e)})

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
