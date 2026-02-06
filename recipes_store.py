from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Optional

from common import norm_item_id, load_json, save_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_signature(output: str, out_qty: float, ingredients: List[Tuple[str, float]]) -> str:
    out = norm_item_id(output)
    oq = float(out_qty)

    norm_ings: List[Tuple[str, float]] = []
    for it, q in ingredients:
        norm_ings.append((norm_item_id(it), float(q)))
    norm_ings.sort(key=lambda x: (x[0], x[1]))

    payload = {"o": out, "oq": oq, "i": norm_ings}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


@dataclass
class Recipe:
    output: str
    output_qty: float
    ingredients: List[Tuple[str, float]]  # [(item_id, qty), ...]

    def signature(self) -> str:
        return _canonical_signature(self.output, self.output_qty, self.ingredients)

    def to_dict(self) -> dict:
        return {
            "output": norm_item_id(self.output),
            "output_qty": float(self.output_qty),
            "ingredients": [{"item": norm_item_id(i), "qty": float(q)} for (i, q) in self.ingredients],
        }

    @staticmethod
    def from_dict(d: dict) -> Optional["Recipe"]:
        if not isinstance(d, dict):
            return None
        out = norm_item_id(str(d.get("output") or ""))
        if not out:
            return None
        try:
            out_qty = float(d.get("output_qty") or 1.0)
        except Exception:
            out_qty = 1.0

        raw_ings = d.get("ingredients") or []
        if not isinstance(raw_ings, list) or not raw_ings:
            return None

        ings: List[Tuple[str, float]] = []
        for it in raw_ings:
            if not isinstance(it, dict):
                continue
            iid = norm_item_id(str(it.get("item") or ""))
            if not iid:
                continue
            try:
                q = float(it.get("qty") or 1.0)
            except Exception:
                q = 1.0
            ings.append((iid, q))

        if not ings:
            return None
        return Recipe(out, out_qty, ings)


class RecipesStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.version = 1
        self.updated_at = _now_iso()
        self._by_sig: Dict[str, Recipe] = {}
        self._by_output: Dict[str, List[Recipe]] = {}

    def clear(self) -> None:
        self._by_sig.clear()
        self._by_output.clear()
        self.updated_at = _now_iso()

    def all(self) -> List[Recipe]:
        return list(self._by_sig.values())

    def variants(self, output_item: str) -> List[Recipe]:
        return list(self._by_output.get(norm_item_id(output_item), []))

    def upsert(self, r: Recipe) -> None:
        sig = r.signature()
        old = self._by_sig.get(sig)
        if old is not None:
            outk = norm_item_id(old.output)
            self._by_output[outk] = [x for x in self._by_output.get(outk, []) if x.signature() != sig]

        self._by_sig[sig] = r
        outk = norm_item_id(r.output)
        self._by_output.setdefault(outk, []).append(r)
        self.updated_at = _now_iso()

    def delete_by_sig(self, sig: str) -> bool:
        old = self._by_sig.pop(sig, None)
        if old is None:
            return False
        outk = norm_item_id(old.output)
        self._by_output[outk] = [x for x in self._by_output.get(outk, []) if x.signature() != sig]
        if not self._by_output[outk]:
            self._by_output.pop(outk, None)
        self.updated_at = _now_iso()
        return True

    def load(self) -> None:
        self.clear()
        raw = load_json(self.path, default=None)
        if raw is None:
            return

        if isinstance(raw, list):
            recipes_list = raw
        else:
            self.version = int(raw.get("version") or 1)
            self.updated_at = str(raw.get("updated_at") or _now_iso())
            recipes_list = raw.get("recipes") or []

        if not isinstance(recipes_list, list):
            return

        for d in recipes_list:
            r = Recipe.from_dict(d)
            if r is None:
                continue
            self.upsert(r)

    def save(self) -> None:
        payload = {
            "version": int(self.version),
            "updated_at": self.updated_at,
            "recipes": [r.to_dict() for r in sorted(self.all(), key=lambda x: (x.output, x.signature()))],
        }
        save_json(self.path, payload)

    def import_list(self, recipes: Iterable[dict]) -> int:
        n = 0
        for d in recipes:
            r = Recipe.from_dict(d)
            if r is None:
                continue
            self.upsert(r)
            n += 1
        return n
