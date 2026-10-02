"""CSV history (one row per date) and the hand-maintained manual inputs file."""

from __future__ import annotations

import csv
import json
from pathlib import Path

COLUMNS = [
    "date",
    "silver_usd",
    "gold_usd",
    "usdcny",
    "comex_registered_oz",
    "comex_eligible_oz",
    "open_interest",
    "mm_net",
    "commercial_net_short",
    "shanghai_usd_oz",
    "premium_pct",
    "lease_rate_1m_pct",
]


def load_history(path: Path) -> list[dict]:
    """Rows sorted by date; numeric columns as float, blanks as None."""
    if not path.exists():
        return []
    rows = []
    with path.open(newline="") as fh:
        for raw in csv.DictReader(fh):
            row = {"date": raw["date"]}
            for col in COLUMNS[1:]:
                val = (raw.get(col) or "").strip()
                row[col] = float(val) if val else None
            rows.append(row)
    rows.sort(key=lambda r: r["date"])
    return rows


def upsert(rows: list[dict], date: str, values: dict) -> None:
    """Merge non-None values into the row for date, creating it if needed."""
    for row in rows:
        if row["date"] == date:
            target = row
            break
    else:
        target = {"date": date, **{c: None for c in COLUMNS[1:]}}
        rows.append(target)
    for key, val in values.items():
        if key in COLUMNS and val is not None:
            target[key] = val
    rows.sort(key=lambda r: r["date"])


def save_history(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _fmt(row.get(c)) for c in COLUMNS})


def _fmt(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        return f"{val:.6g}" if abs(val) < 1e6 else f"{val:.0f}"
    return str(val)


def load_manual(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())
