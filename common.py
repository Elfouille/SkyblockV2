from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from PySide6.QtGui import QColor, QBrush


# ----------------------------
# Paths
# ----------------------------
ROOT_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------
# UI Brushes
# ----------------------------
BR_BLUE = QBrush(QColor(0, 140, 255))
BR_GREEN = QBrush(QColor(0, 170, 0))
BR_ORANGE = QBrush(QColor(255, 140, 0))
BR_RED = QBrush(QColor(200, 0, 0))
BR_GRAY = QBrush(QColor(150, 150, 150))


def fmt_num(x: float) -> str:
    try:
        x = float(x)
    except Exception:
        return "0"
    if abs(x) >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f}b"
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:.2f}m"
    if abs(x) >= 1_000:
        return f"{x/1_000:.2f}k"
    if abs(x) >= 100:
        return f"{x:.1f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.4f}"


def norm_item_id(s: str) -> str:
    return (s or "").strip().upper()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
