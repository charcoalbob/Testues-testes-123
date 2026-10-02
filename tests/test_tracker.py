import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from tracker import report, signals, sources, store
from tracker.signals import ALERT, NODATA, OK, WATCH

FIX = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 10, 2)


def rows_from(**cols):
    """Build history rows: rows_from(comex_registered_oz=[("2026-09-01", 1e8), ...])."""
    rows = []
    for col, series in cols.items():
        for date, val in series:
            store.upsert(rows, date, {col: val})
    return rows


def daily(start: str, values):
    d0 = dt.date.fromisoformat(start)
    return [((d0 + dt.timedelta(days=i)).isoformat(), v) for i, v in enumerate(values)]


class ParserTests(unittest.TestCase):
    def test_yahoo_skips_null_closes(self):
        closes = sources.parse_yahoo_chart(json.loads((FIX / "yahoo_si.json").read_text()))
        self.assertEqual(closes, {"2026-09-25": 61.42, "2026-09-29": 60.82})

    def test_frankfurter_usdcny(self):
        payload = json.loads((FIX / "frankfurter_cny.json").read_text())
        self.assertEqual(sources.parse_frankfurter(payload),
                         {"2026-09-25": 7.1203, "2026-09-26": 7.115})

    def test_gold_api_spot(self):
        payload = json.loads((FIX / "gold_api_xag.json").read_text())
        self.assertEqual(sources.parse_gold_api(payload), {"2026-10-02": 60.91})

    def test_fred_skips_holidays(self):
        self.assertEqual(sources.parse_fred_csv((FIX / "fred_dexchus.csv").read_text()),
                         {"2026-09-24": 7.1203, "2026-09-26": 7.115})

    def test_cot_handles_double_underscore_columns(self):
        rows = sources.parse_cot_rows(json.loads((FIX / "cftc_silver.json").read_text()))
        self.assertEqual([r["date"] for r in rows], ["2026-09-15", "2026-09-22"])
        latest = rows[-1]
        self.assertEqual(latest["open_interest"], 150000)
        self.assertEqual(latest["mm_net"], 35000)
        self.assertEqual(latest["commercial_net_short"], (40000 - 10000) + (45000 - 20000))

    def test_cme_html_totals(self):
        text = (FIX / "cme_stocks.html").read_text()
        out = sources.parse_cme_stock_rows(sources._html_table_rows(text))
        self.assertEqual(out, {"registered_oz": 99_200_000, "eligible_oz": 236_700_000})


class StoreTests(unittest.TestCase):
    def test_upsert_merges_and_roundtrips(self):
        rows = []
        store.upsert(rows, "2026-09-02", {"silver_usd": 61.0})
        store.upsert(rows, "2026-09-01", {"silver_usd": 60.0})
        store.upsert(rows, "2026-09-02", {"comex_registered_oz": 99_200_000, "silver_usd": None})
        self.assertEqual([r["date"] for r in rows], ["2026-09-01", "2026-09-02"])
        self.assertEqual(rows[1]["silver_usd"], 61.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.csv"
            store.save_history(path, rows)
            back = store.load_history(path)
        self.assertEqual(back[1]["comex_registered_oz"], 99_200_000)
        self.assertIsNone(back[0]["comex_registered_oz"])


class SignalTests(unittest.TestCase):
    def test_everything_nodata_on_empty_history(self):
        sigs = signals.evaluate([], {}, TODAY)
        self.assertTrue(all(s.status in (NODATA, OK) for s in sigs))
        self.assertEqual(signals.verdict(sigs)[0], NODATA)

    def test_shanghai_premium_strips_vat(self):
        from tracker.__main__ import apply_manual
        rows = rows_from(usdcny=[("2026-09-29", 7.1)], silver_usd=[("2026-09-29", 60.0)])
        # 60 USD/oz at 7.1 CNY/USD with 13% VAT, plus a 5% premium.
        cny_kg = 60.0 * 1.05 * 7.1 * 1.13 * 32.1507466
        apply_manual(rows, {"shanghai_price_cny_per_kg": [{"date": "2026-09-30", "value": cny_kg}]})
        self.assertAlmostEqual(rows[-1]["premium_pct"], 5.0, places=6)

    def test_premium_alert_needs_sustained_level(self):
        spike = rows_from(premium_pct=daily("2026-09-20", [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 14]))
        self.assertEqual(signals.physical_premium(spike, TODAY).status, WATCH)
        sustained = rows_from(premium_pct=daily("2026-09-20", [12] * 11))
        self.assertEqual(signals.physical_premium(sustained, TODAY).status, ALERT)

    def test_registered_drawdown_and_coverage(self):
        oi = [("2026-09-22", 150000)]  # 750M oz, so 99.2M registered covers 13.2%
        rows = rows_from(comex_registered_oz=[("2026-08-29", 120e6), ("2026-09-29", 99.2e6)],
                         open_interest=oi)
        sig = signals.registered_inventory(rows, TODAY)
        self.assertEqual(sig.status, WATCH)
        self.assertIn("-17.3%", sig.detail)
        self.assertIn("13.2%", sig.detail)
        rows = rows_from(comex_registered_oz=[("2026-08-29", 140e6), ("2026-09-29", 99.2e6)],
                         open_interest=oi)
        self.assertEqual(signals.registered_inventory(rows, TODAY).status, ALERT)
        thin = rows_from(comex_registered_oz=[("2026-09-29", 30e6)], open_interest=oi)
        self.assertEqual(signals.registered_inventory(thin, TODAY).status, ALERT)

    def test_lease_spike_that_fades_is_not_alert(self):
        rows = rows_from(lease_rate_1m_pct=daily("2026-09-10", [3, 3, 3, 3, 39, 3, 3, 3]))
        self.assertEqual(signals.lease_rates(rows, TODAY).status, OK)
        rows = rows_from(lease_rate_1m_pct=daily("2026-09-20", [15] * 10))
        self.assertEqual(signals.lease_rates(rows, TODAY).status, ALERT)

    def test_exchange_event_windows(self):
        old_margin = [{"date": "2026-02-06", "type": "margin_hike"}]
        self.assertEqual(signals.exchange_rules(old_margin, TODAY).status, OK)
        recent_margin = [{"date": "2026-09-25", "type": "margin_hike"}]
        self.assertEqual(signals.exchange_rules(recent_margin, TODAY).status, WATCH)
        freeze = [{"date": "2026-08-01", "type": "liquidation_only", "venue": "CME"}]
        self.assertEqual(signals.exchange_rules(freeze, TODAY).status, ALERT)

    def test_commercial_shorts_need_inventory_drain(self):
        cot = dict(open_interest=[("2026-06-23", 150000), ("2026-09-22", 150000)],
                   commercial_net_short=[("2026-06-23", 30000), ("2026-09-22", 50000)])
        flat = rows_from(**cot, comex_registered_oz=[("2026-06-23", 100e6), ("2026-09-22", 98e6)])
        self.assertEqual(signals.commercial_shorts(flat, TODAY).status, OK)
        drained = rows_from(**cot, comex_registered_oz=[("2026-06-23", 100e6), ("2026-09-22", 85e6)])
        self.assertEqual(signals.commercial_shorts(drained, TODAY).status, WATCH)

    def test_state_actions_cap_at_watch(self):
        acts = [{"date": "2026-09-01", "actor": "X", "note": "buys"}]
        self.assertEqual(signals.state_actions(acts, TODAY).status, WATCH)

    def test_verdict_requires_two_hard_alerts(self):
        mk = lambda key, st: signals.Signal(key, key, st, "", "", "")
        one = [mk("premium", ALERT), mk("lease", OK), mk("state", WATCH)]
        self.assertEqual(signals.verdict(one)[0], WATCH)
        two = [mk("premium", ALERT), mk("lease", ALERT)]
        self.assertEqual(signals.verdict(two)[0], ALERT)
        calm = [mk("premium", OK), mk("registered", OK), mk("lease", NODATA)]
        self.assertEqual(signals.verdict(calm)[0], OK)


class ReportTests(unittest.TestCase):
    def test_renders_with_data(self):
        rows = rows_from(silver_usd=daily("2026-08-01", [60 + (i % 5) for i in range(60)]),
                         gold_usd=daily("2026-08-01", [3800] * 60))
        sigs = signals.evaluate(rows, {}, TODAY)
        ctx = signals.market_context(rows)
        md = report.markdown(sigs, signals.verdict(sigs), ctx, {"x": "ok"}, TODAY)
        page = report.dashboard(sigs, signals.verdict(sigs), ctx, {"x": "ok"}, TODAY)
        self.assertIn("Gold/silver ratio", md)
        self.assertIn("<polyline", page)


if __name__ == "__main__":
    unittest.main()
