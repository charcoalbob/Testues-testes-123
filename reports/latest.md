# Silver stress tracker — 2026-10-02

**Overall: ⚪ NO DATA.** Not enough market data to judge yet. Fill the gaps in data/manual.json or wait for the daily job to build history.

> Measures physical-market stress, not intent. An alert means silver is tight, not that anyone is manipulating it.

## Market context

- Silver $61.14 (2026-10-02)
- +0.0% from tracked high of $61.14 (2026-10-02)
- Gold/silver ratio 68.4

## Signals

| | Signal | Value | Detail |
|---|---|---|---|
| ⚪ | Physical vs paper premium | n/a | Add shanghai_price_cny_per_kg entries to data/manual.json. |
| 🟢 | COMEX registered inventory | 99.2M oz | As of 2026-09-29. Need 30+ days of history for the drawdown test. Covers 18.6% of open interest (2026-09-22). |
| ⚪ | Silver lease rate (1M) | n/a | Add lease_rate_1m_pct entries to data/manual.json. |
| 🟢 | Exchange rule changes | 0 in window | None in window. Last logged: 2026-02-06 margin_hike. |
| 🟢 | Commercial shorts vs inventory | 42.0% of OI | +5.1 pts since 2026-06-23; registered n/a over the same span. |
| 🟢 | State actor disclosures | 0 recent | None in window. Last logged: 2026-01-01 China. |

## Rules

- **Physical vs paper premium:** Shanghai (ex-VAT) over COMEX: watch > 5%, alert when latest and 30-day median both > 10%.
- **COMEX registered inventory:** 30-day change: watch < -10%, alert < -25%. Registered / open interest: watch < 10%, alert < 5%.
- **Silver lease rate (1M):** 1-month lease: watch > 5%, alert when latest and 30-day median both > 10% (a spike that fades is normal stress).
- **Exchange rule changes:** Alert on liquidation-only, forced cash settlement, halts, cancellations or position-limit changes in the last 90 days; watch on margin hikes in the last 30 days.
- **Commercial shorts vs inventory:** Commercial net short % of open interest rising > 5 pts (watch) / > 10 pts (alert) over ~90 days while registered stock falls > 10% / > 25%.
- **State actor disclosures:** Watch when a state or central bank discloses silver buying or export controls in the last 180 days. Disclosed buying is public, not covert, so this never escalates to alert on its own.

## Data sources

- silver_usd: ok via gold-api XAG spot (1 days) | failed: Yahoo SI=F: HTTP Error 429: Too Many Requests; Stooq xagusd: unexpected response: '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" content="no'
- gold_usd: ok via gold-api XAU spot (1 days) | failed: Yahoo GC=F: HTTP Error 429: Too Many Requests; Stooq xauusd: unexpected response: '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" content="no'
- usdcny: failed | failed: Yahoo CNY=X: HTTP Error 429: Too Many Requests; Stooq usdcny: unexpected response: '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" content="no'; FRED DEXCHUS: The read operation timed out
- CFTC COT: ok (latest 2026-09-22)
- CME silver stocks: failed: HTTP Error 403: Forbidden (use data/manual.json)
- manual comex_registered_oz: 1 entries
