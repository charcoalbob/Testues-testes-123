# Silver stress tracker

Tracks the public signals that would separate a real physical silver squeeze, or a
freeze on paper contracts, from ordinary price volatility. It runs daily on GitHub
Actions and writes:

- `reports/latest.md`: a readable summary
- `reports/index.html`: a dashboard (download it, or serve it with GitHub Pages)
- `data/history.csv`: one row per date, for your own analysis

**What it measures:** stress in the physical market. **What it can't measure:** intent.
An alert means silver is tight, not that anyone is suppressing the price.

## Signals

| Signal | Source | Watch | Alert |
|---|---|---|---|
| Physical vs paper premium | Shanghai SGE Ag(T+D), ex-13% VAT, vs COMEX (manual) | > 5% | latest and 30-day median > 10% |
| COMEX registered inventory | CME `Silver_stocks.xls`, manual fallback | 30-day draw > 10%, or < 10% of open interest | draw > 25%, or < 5% of open interest |
| Lease rate (1M) | manual | > 5% | latest and 30-day median > 10% |
| Exchange rule changes | manual event log | margin hike in last 30 days | liquidation-only, forced cash settlement, halt, trade cancellation, position-limit change or delivery default in last 90 days |
| Commercial shorts vs inventory | CFTC Disaggregated COT | commercial net short up > 5 pts of OI over 90 days while registered falls > 10% | up > 10 pts while registered falls > 25% |
| State actor disclosures | manual event log | disclosure in last 180 days | never (disclosed buying is public, not covert) |

**Overall verdict:** ALERT needs at least two of the hard signals (premium, inventory,
lease, exchange) at alert at the same time. One spike on its own is normal market
stress. If fewer than two market signals have data, the verdict is NO DATA rather than
a false all-clear.

Every threshold is a heuristic and lives in `tracker/config.py`.

## Automatic vs manual data

Fetched automatically: silver, gold and USD/CNY prices (Yahoo Finance), CFTC
Commitments of Traders, and COMEX warehouse stocks. CME often blocks automated
downloads; when it does, the report says so and uses `data/manual.json` instead.

No free API exists for these, so you add them to `data/manual.json`:

- `lease_rate_1m_pct`: one-month lease rate
- `shanghai_price_cny_per_kg`: SGE Ag(T+D) price, entered as quoted
- `exchange_events`: margin changes, liquidation-only orders, settlement changes
- `state_actions`: central bank purchases, reserve programs, export controls
- `comex_registered_oz`: only when the CME fetch fails

Add an entry, commit, and the workflow reruns on push.

## Running locally

```sh
pip install -r requirements.txt   # optional, for the binary CME file
python -m tracker                 # fetch, update history, write reports
python -m tracker --offline       # rebuild reports from history + manual.json only
python -m unittest -v
```

Needs Python 3.10+. The only dependency is xlrd, and it is optional.
