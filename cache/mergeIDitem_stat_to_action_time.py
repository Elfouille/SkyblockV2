import json
from pathlib import Path

stats_path = Path("minion_stats.json")
action_path = Path("minion_action_time.json")
out_path = Path("minion_action_time_with_item_id.json")

stats = json.loads(stats_path.read_text(encoding="utf-8"))
action = json.loads(action_path.read_text(encoding="utf-8"))

for minion, mdata in action["minions"].items():
    tiers_action = mdata.get("tiers", {})
    tiers_stats = stats.get(minion, {}).get("tiers", {})

    tier_numbers = []

    for tier, tdata in tiers_action.items():
        tier_numbers.append(int(tier))

        s = tiers_stats.get(str(tier), {})
        item_id = s.get("item_id")
        name = s.get("name")

        if item_id:
            tdata["item_id"] = item_id
        if name:
            tdata["name"] = name

    # ajout du tier max au niveau du minion
    if tier_numbers:
        mdata["tier_max"] = max(tier_numbers)

out_path.write_text(
    json.dumps(action, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print(f"[OK] généré → {out_path}")
