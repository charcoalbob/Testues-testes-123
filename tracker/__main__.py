"""Run the tracker: python -m tracker [--offline] [--today YYYY-MM-DD]."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import config as C
from . import report, signals, sources, store

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history.csv"
MANUAL = ROOT / "data" / "manual.json"
REPORTS = ROOT / "reports"


def _nearest_before(rows: list[dict], col: str, date: str):
    best = None
    for r in rows:
        if r["date"] <= date and r.get(col) is not None:
            best = r[col]
    return best


def fetch_all(rows: list[dict], today: str) -> dict[str, str]:
    status = {}

    for col, symbol in (("silver_usd", "SI=F"), ("gold_usd", "GC=F"), ("usdcny", "CNY=X")):
        try:
            closes = sources.fetch_yahoo_closes(symbol)
            for day, close in closes.items():
                store.upsert(rows, day, {col: close})
            status[f"Yahoo {symbol}"] = f"ok ({len(closes)} days)"
        except Exception as exc:  # noqa: BLE001 - any failure just means no data today
            status[f"Yahoo {symbol}"] = f"failed: {exc}"

    try:
        cot = sources.fetch_cot()
        for rec in cot:
            store.upsert(rows, rec["date"], {k: v for k, v in rec.items() if k != "date"})
        status["CFTC COT"] = f"ok (latest {cot[-1]['date']})" if cot else "ok (no rows)"
    except Exception as exc:  # noqa: BLE001
        status["CFTC COT"] = f"failed: {exc}"

    try:
        stocks = sources.fetch_cme_stocks()
        if "registered_oz" not in stocks:
            raise ValueError("totals rows not found; sheet format may have changed")
        store.upsert(rows, today, {"comex_registered_oz": stocks["registered_oz"],
                                   "comex_eligible_oz": stocks.get("eligible_oz")})
        status["CME silver stocks"] = "ok"
    except Exception as exc:  # noqa: BLE001
        status["CME silver stocks"] = f"failed: {exc} (use data/manual.json)"

    return status


def apply_manual(rows: list[dict], manual: dict) -> dict[str, str]:
    """Merge hand-entered series. Manual values override fetched ones for the same date."""
    status = {}
    for key, col in (("comex_registered_oz", "comex_registered_oz"),
                     ("lease_rate_1m_pct", "lease_rate_1m_pct")):
        entries = manual.get(key, [])
        for ent in entries:
            store.upsert(rows, ent["date"], {col: float(ent["value"])})
        if entries:
            status[f"manual {key}"] = f"{len(entries)} entries"

    sh = manual.get("shanghai_price_cny_per_kg", [])
    used = 0
    for ent in sh:
        date = ent["date"]
        fx = _nearest_before(rows, "usdcny", date)
        px = _nearest_before(rows, "silver_usd", date)
        if not fx or not px:
            continue
        usd_oz = float(ent["value"]) / (1 + C.CHINA_VAT) / fx / C.TROY_OZ_PER_KG
        store.upsert(rows, date, {"shanghai_usd_oz": usd_oz, "premium_pct": (usd_oz / px - 1) * 100})
        used += 1
    if sh:
        status["manual shanghai_price_cny_per_kg"] = (
            f"{used}/{len(sh)} entries converted"
            + ("" if used == len(sh) else " (others lack a USD/CNY or COMEX price on or before that date)"))
    return status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="skip network fetches")
    ap.add_argument("--today", help="override the as-of date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    rows = store.load_history(HISTORY)
    manual = store.load_manual(MANUAL)
    status = {} if args.offline else fetch_all(rows, today.isoformat())
    if args.offline:
        status["network"] = "skipped (--offline)"
    status.update(apply_manual(rows, manual))
    store.save_history(HISTORY, rows)

    sigs = signals.evaluate(rows, manual, today)
    verdict = signals.verdict(sigs)
    ctx = signals.market_context(rows)

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "latest.md").write_text(report.markdown(sigs, verdict, ctx, status, today))
    (REPORTS / "index.html").write_text(report.dashboard(sigs, verdict, ctx, status, today))

    print(f"Overall: {verdict[0].upper()} - {verdict[1]}")
    for s in sigs:
        print(f"  [{s.status:>6}] {s.name}: {s.value}")
    for name, st in status.items():
        print(f"  source {name}: {st}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
