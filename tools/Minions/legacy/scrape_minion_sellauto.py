from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from _wiki_tables import get, find_table_after_anchor, table_to_matrix, matrix_to_rows, write_json

INDEX_URL = "https://wiki.hypixel.net/Minions"
ANCHOR = "Automated_Shipping"

ROOT = Path(__file__).resolve().parents[2]  # ...\SkyblockV2
OUT = ROOT / "cache" / "minion_sellauto.json"


def main() -> None:
    html = get(INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")

    tbl = find_table_after_anchor(soup, ANCHOR)
    matrix = table_to_matrix(tbl) if tbl else []
    rows = matrix_to_rows(matrix)

    out = {
        "_meta": {
            "source_index": INDEX_URL,
            "anchor": f"#{ANCHOR}",
            "generated_by": "tools/Minions/scrape_minion_sellauto.py",
            "effect_normalization": {"effect_type": True, "effect_multiplier": True, "effect_additive": True},
        },
        "sellauto": rows,
    }

    write_json(OUT, out)
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    main()
