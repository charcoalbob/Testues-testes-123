"""Render signals to Markdown (reports/latest.md) and a static HTML dashboard."""

from __future__ import annotations

import datetime as dt
import html

from .signals import ALERT, NODATA, OK, WATCH, Signal

LABEL = {OK: "OK", WATCH: "WATCH", ALERT: "ALERT", NODATA: "NO DATA"}
EMOJI = {OK: "🟢", WATCH: "🟡", ALERT: "🔴", NODATA: "⚪"}


def _ctx_lines(ctx: dict) -> list[str]:
    if "silver" not in ctx:
        return ["No price data yet."]
    lines = [f"Silver ${ctx['silver']:.2f} ({ctx['silver_date']})",
             f"{ctx['drawdown_pct']:+.1f}% from tracked high of ${ctx['peak']:.2f} ({ctx['peak_date']})"]
    if "gold_silver_ratio" in ctx:
        lines.append(f"Gold/silver ratio {ctx['gold_silver_ratio']:.1f}")
    if "vol_30d_pct" in ctx:
        lines.append(f"30-day annualised volatility {ctx['vol_30d_pct']:.0f}%")
    return lines


def markdown(signals: list[Signal], verdict: tuple[str, str], ctx: dict,
             source_status: dict[str, str], today: dt.date) -> str:
    v_status, v_text = verdict
    out = [f"# Silver stress tracker — {today.isoformat()}", "",
           f"**Overall: {EMOJI[v_status]} {LABEL[v_status]}.** {v_text}", "",
           "> Measures physical-market stress, not intent. An alert means silver is tight, "
           "not that anyone is manipulating it.", "",
           "## Market context", ""]
    out += [f"- {line}" for line in _ctx_lines(ctx)]
    out += ["", "## Signals", "", "| | Signal | Value | Detail |", "|---|---|---|---|"]
    for s in signals:
        out.append(f"| {EMOJI[s.status]} | {s.name} | {s.value} | {s.detail} |")
    out += ["", "## Rules", ""]
    out += [f"- **{s.name}:** {s.rule}." for s in signals]
    out += ["", "## Data sources", ""]
    out += [f"- {name}: {status}" for name, status in source_status.items()]
    return "\n".join(out) + "\n"


def _spark(series: list[tuple[str, float]], width: int = 220, height: int = 44) -> str:
    pts = [v for _, v in series][-180:]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    step = width / (len(pts) - 1)
    coords = " ".join(f"{i * step:.1f},{height - 3 - (v - lo) / span * (height - 6):.1f}"
                      for i, v in enumerate(pts))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
            f'aria-hidden="true"><polyline points="{coords}"/></svg>')


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#6b6b66;--line:#e3e3de;
--ok:#2f7d4f;--watch:#b07a00;--alert:#c0392b;--nodata:#8a8a85;--accent:#5b6b7a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151514;--card:#1f1f1d;
--text:#ecece8;--muted:#a3a39d;--line:#33332f;--ok:#5cc28a;--watch:#e0b23c;--alert:#ee6b5e;
--nodata:#8a8a85;--accent:#9fb3c6}}
:root[data-theme="dark"]{--bg:#151514;--card:#1f1f1d;--text:#ecece8;--muted:#a3a39d;--line:#33332f;
--ok:#5cc28a;--watch:#e0b23c;--alert:#ee6b5e;--nodata:#8a8a85;--accent:#9fb3c6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.05rem;margin:32px 0 12px}
.muted{color:var(--muted)}
.verdict{border-left:4px solid var(--c);background:var(--card);padding:14px 16px;border-radius:6px;margin:16px 0}
.ctx{display:flex;flex-wrap:wrap;gap:8px 24px;padding:0;list-style:none;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;
border-top:3px solid var(--c)}
.card h3{font-size:.95rem;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px}
.pill{font-size:.7rem;font-weight:600;letter-spacing:.04em;color:var(--c)}
.value{font-size:1.4rem;font-weight:600;margin:2px 0}
.detail{font-size:.85rem;color:var(--muted);margin:4px 0 0}
.spark{width:100%;height:44px;margin-top:8px}.spark polyline{fill:none;stroke:var(--accent);stroke-width:1.5}
details{margin-top:8px;font-size:.8rem;color:var(--muted)}
.ok{--c:var(--ok)}.watch{--c:var(--watch)}.alert{--c:var(--alert)}.nodata{--c:var(--nodata)}
ul.src{font-size:.85rem;color:var(--muted)}
"""


def dashboard(signals: list[Signal], verdict: tuple[str, str], ctx: dict,
              source_status: dict[str, str], today: dt.date) -> str:
    e = html.escape
    v_status, v_text = verdict
    cards = []
    for s in signals:
        cards.append(
            f'<article class="card {s.status}"><h3>{e(s.name)}'
            f'<span class="pill">{LABEL[s.status]}</span></h3>'
            f'<div class="value">{e(s.value)}</div><p class="detail">{e(s.detail)}</p>'
            f'{_spark(s.series)}<details><summary>Rule</summary>{e(s.rule)}.</details></article>')
    ctx_items = "".join(f"<li>{e(line)}</li>" for line in _ctx_lines(ctx))
    sources = "".join(f"<li>{e(k)}: {e(v)}</li>" for k, v in source_status.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Silver Stress Tracker</title><style>{CSS}</style></head>
<body><main>
<h1>Silver stress tracker</h1>
<div class="muted">Updated {today.isoformat()}. Measures physical-market stress, not intent.</div>
<div class="verdict {v_status}"><strong>Overall: {LABEL[v_status]}.</strong> {e(v_text)}</div>
<ul class="ctx">{ctx_items}</ul>
{_spark(ctx.get("silver_series", []), 940, 70).replace('class="spark"', 'class="spark" style="height:70px"')}
<h2>Signals</h2>
<div class="grid">{''.join(cards)}</div>
<h2>Data sources</h2><ul class="src">{sources}</ul>
</main></body></html>
"""
