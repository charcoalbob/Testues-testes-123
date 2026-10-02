"""Turn history + manual events into scored signals. Pure functions only."""

from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass, field

from . import config as C

OK, WATCH, ALERT, NODATA = "ok", "watch", "alert", "nodata"
_RANK = {NODATA: 0, OK: 1, WATCH: 2, ALERT: 3}


@dataclass
class Signal:
    key: str
    name: str
    status: str
    value: str
    detail: str
    rule: str
    series: list[tuple[str, float]] = field(default_factory=list)


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def _series(rows: list[dict], col: str) -> list[tuple[str, float]]:
    return [(r["date"], r[col]) for r in rows if r.get(col) is not None]


def _value_at_or_before(series, day: dt.date):
    best = None
    for date, val in series:
        if _d(date) <= day:
            best = (date, val)
    return best


def _window(series, today: dt.date, days: int):
    start = today - dt.timedelta(days=days)
    return [v for d, v in series if start <= _d(d) <= today]


def _worst(*statuses: str) -> str:
    return max(statuses, key=_RANK.__getitem__)


def physical_premium(rows, today) -> Signal:
    s = _series(rows, "premium_pct")
    rule = (f"Shanghai (ex-VAT) over COMEX: watch > {C.PREMIUM_WATCH_PCT:g}%, alert when "
            f"latest and 30-day median both > {C.PREMIUM_ALERT_PCT:g}%")
    name = "Physical vs paper premium"
    if not s:
        return Signal("premium", name, NODATA, "n/a",
                      "Add shanghai_price_cny_per_kg entries to data/manual.json.", rule)
    latest_date, latest = s[-1]
    recent = _window(s, today, 30)
    median = statistics.median(recent) if recent else latest
    if latest > C.PREMIUM_ALERT_PCT and median > C.PREMIUM_ALERT_PCT and len(recent) >= 5:
        status = ALERT
    elif latest > C.PREMIUM_WATCH_PCT:
        status = WATCH
    else:
        status = OK
    return Signal("premium", name, status, f"{latest:+.1f}%",
                  f"As of {latest_date}; 30-day median {median:+.1f}% over {len(recent)} obs.",
                  rule, s)


def registered_inventory(rows, today) -> Signal:
    s = _series(rows, "comex_registered_oz")
    rule = (f"30-day change: watch < {C.REGISTERED_DRAW_WATCH_PCT:g}%, alert < "
            f"{C.REGISTERED_DRAW_ALERT_PCT:g}%. Registered / open interest: watch < "
            f"{C.COVERAGE_WATCH_PCT:g}%, alert < {C.COVERAGE_ALERT_PCT:g}%")
    name = "COMEX registered inventory"
    if not s:
        return Signal("registered", name, NODATA, "n/a",
                      "No CME stocks data; add comex_registered_oz to data/manual.json.", rule)
    latest_date, latest = s[-1]
    notes, statuses = [f"As of {latest_date}."], [OK]

    prior = _value_at_or_before(s, _d(latest_date) - dt.timedelta(days=30))
    if prior:
        change = (latest / prior[1] - 1) * 100
        notes.append(f"{change:+.1f}% since {prior[0]}.")
        if change < C.REGISTERED_DRAW_ALERT_PCT:
            statuses.append(ALERT)
        elif change < C.REGISTERED_DRAW_WATCH_PCT:
            statuses.append(WATCH)
    else:
        notes.append("Need 30+ days of history for the drawdown test.")

    oi = _series(rows, "open_interest")
    if oi:
        coverage = latest / (oi[-1][1] * C.COMEX_CONTRACT_OZ) * 100
        notes.append(f"Covers {coverage:.1f}% of open interest ({oi[-1][0]}).")
        if coverage < C.COVERAGE_ALERT_PCT:
            statuses.append(ALERT)
        elif coverage < C.COVERAGE_WATCH_PCT:
            statuses.append(WATCH)

    return Signal("registered", name, _worst(*statuses), f"{latest / 1e6:.1f}M oz",
                  " ".join(notes), rule, s)


def lease_rates(rows, today) -> Signal:
    s = _series(rows, "lease_rate_1m_pct")
    rule = (f"1-month lease: watch > {C.LEASE_WATCH_PCT:g}%, alert when latest and 30-day "
            f"median both > {C.LEASE_ALERT_PCT:g}% (a spike that fades is normal stress)")
    name = "Silver lease rate (1M)"
    if not s:
        return Signal("lease", name, NODATA, "n/a",
                      "Add lease_rate_1m_pct entries to data/manual.json.", rule)
    latest_date, latest = s[-1]
    recent = _window(s, today, 30)
    median = statistics.median(recent) if recent else latest
    if latest > C.LEASE_ALERT_PCT and median > C.LEASE_ALERT_PCT:
        status = ALERT
    elif latest > C.LEASE_WATCH_PCT:
        status = WATCH
    else:
        status = OK
    return Signal("lease", name, status, f"{latest:.2f}%",
                  f"As of {latest_date}; 30-day median {median:.2f}%.", rule, s)


def exchange_rules(events, today) -> Signal:
    rule = (f"Alert on liquidation-only, forced cash settlement, halts, cancellations or "
            f"position-limit changes in the last {C.SEVERE_EVENT_WINDOW_DAYS} days; watch on "
            f"margin hikes in the last {C.MARGIN_EVENT_WINDOW_DAYS} days")
    name = "Exchange rule changes"
    severe, margin = [], []
    for ev in events:
        age = (today - _d(ev["date"])).days
        if age < 0:
            continue
        if ev.get("type") in C.SEVERE_EXCHANGE_EVENTS and age <= C.SEVERE_EVENT_WINDOW_DAYS:
            severe.append(ev)
        elif ev.get("type") == "margin_hike" and age <= C.MARGIN_EVENT_WINDOW_DAYS:
            margin.append(ev)
    if severe:
        status, hits = ALERT, severe
    elif margin:
        status, hits = WATCH, margin
    else:
        status, hits = OK, []
    if hits:
        detail = "; ".join(f"{e['date']} {e.get('venue', '')} {e['type']}: {e.get('note', '')}".strip()
                           for e in hits)
    else:
        past = sorted(events, key=lambda e: e["date"])
        detail = (f"None in window. Last logged: {past[-1]['date']} {past[-1]['type']}."
                  if past else "No events logged.")
    return Signal("exchange", name, status, f"{len(hits)} in window", detail, rule)


def commercial_shorts(rows, today) -> Signal:
    rule = (f"Commercial net short % of open interest rising > "
            f"{C.COMMERCIAL_SHORT_RISE_WATCH_PTS:g} pts (watch) / > "
            f"{C.COMMERCIAL_SHORT_RISE_ALERT_PTS:g} pts (alert) over ~90 days while registered "
            f"stock falls > {-C.REGISTERED_DRAW_WATCH_PCT:g}% / > {-C.REGISTERED_DRAW_ALERT_PCT:g}%")
    name = "Commercial shorts vs inventory"
    pct = [(r["date"], r["commercial_net_short"] / r["open_interest"] * 100) for r in rows
           if r.get("commercial_net_short") is not None and r.get("open_interest")]
    if not pct:
        return Signal("shorts", name, NODATA, "n/a", "No CFTC data yet.", rule)
    latest_date, latest = pct[-1]
    prior = _value_at_or_before(pct, _d(latest_date) - dt.timedelta(days=90))
    if not prior:
        return Signal("shorts", name, OK, f"{latest:.1f}% of OI",
                      f"As of {latest_date}; need ~90 days of history for the trend test.", rule, pct)
    rise = latest - prior[1]
    reg = _series(rows, "comex_registered_oz")
    reg_now = _value_at_or_before(reg, _d(latest_date))
    reg_then = _value_at_or_before(reg, _d(prior[0]))
    reg_change = (reg_now[1] / reg_then[1] - 1) * 100 if reg_now and reg_then else None
    status = OK
    if reg_change is not None:
        if rise > C.COMMERCIAL_SHORT_RISE_ALERT_PTS and reg_change < C.REGISTERED_DRAW_ALERT_PCT:
            status = ALERT
        elif rise > C.COMMERCIAL_SHORT_RISE_WATCH_PTS and reg_change < C.REGISTERED_DRAW_WATCH_PCT:
            status = WATCH
    reg_txt = f"registered {reg_change:+.1f}%" if reg_change is not None else "registered n/a"
    return Signal("shorts", name, status, f"{latest:.1f}% of OI",
                  f"{rise:+.1f} pts since {prior[0]}; {reg_txt} over the same span.", rule, pct)


def state_actions(actions, today) -> Signal:
    rule = (f"Watch when a state or central bank discloses silver buying or export controls in "
            f"the last {C.STATE_ACTION_WINDOW_DAYS} days. Disclosed buying is public, not covert, "
            f"so this never escalates to alert on its own")
    name = "State actor disclosures"
    recent = [a for a in actions
              if 0 <= (today - _d(a["date"])).days <= C.STATE_ACTION_WINDOW_DAYS]
    if recent:
        detail = "; ".join(f"{a['date']} {a['actor']}: {a.get('note', '')}" for a in recent)
        return Signal("state", name, WATCH, f"{len(recent)} recent", detail, rule)
    past = sorted(actions, key=lambda a: a["date"])
    detail = (f"None in window. Last logged: {past[-1]['date']} {past[-1]['actor']}."
              if past else "None logged.")
    return Signal("state", name, OK, "0 recent", detail, rule)


def market_context(rows) -> dict:
    """Informational numbers with no pass/fail."""
    silver = _series(rows, "silver_usd")
    gold = _series(rows, "gold_usd")
    ctx: dict = {"silver_series": silver}
    if not silver:
        return ctx
    ctx["silver_date"], ctx["silver"] = silver[-1]
    peak_date, peak = max(silver, key=lambda x: x[1])
    ctx["peak_date"], ctx["peak"] = peak_date, peak
    ctx["drawdown_pct"] = (silver[-1][1] / peak - 1) * 100
    gold_today = dict(gold).get(silver[-1][0])
    if gold_today:
        ctx["gold_silver_ratio"] = gold_today / silver[-1][1]
    closes = [v for _, v in silver[-31:]]
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    if len(rets) >= 10:
        ctx["vol_30d_pct"] = statistics.stdev(rets) * math.sqrt(252) * 100
    return ctx


def evaluate(rows: list[dict], manual: dict, today: dt.date) -> list[Signal]:
    return [
        physical_premium(rows, today),
        registered_inventory(rows, today),
        lease_rates(rows, today),
        exchange_rules(manual.get("exchange_events", []), today),
        commercial_shorts(rows, today),
        state_actions(manual.get("state_actions", []), today),
    ]


def verdict(signals: list[Signal]) -> tuple[str, str]:
    alerts = [s for s in signals if s.status == ALERT]
    watches = [s for s in signals if s.status == WATCH]
    hard = {"premium", "registered", "lease", "exchange"}
    measured = [s for s in signals if s.key in hard and s.key != "exchange" and s.status != NODATA]
    if len(measured) < 2 and not alerts:
        return NODATA, ("Not enough market data to judge yet. Fill the gaps in data/manual.json "
                        "or wait for the daily job to build history.")
    if len([s for s in alerts if s.key in hard]) >= 2:
        return ALERT, ("Several physical-stress signals are firing together. This is the pattern "
                       "a real squeeze or paper-market freeze would leave.")
    if alerts or len(watches) >= 3:
        return WATCH, ("Some stress, but not the combined pattern. Isolated spikes like this "
                       "usually fade.")
    return OK, ("No squeeze or freeze signature. Price moves are consistent with ordinary "
                "volatility.")
