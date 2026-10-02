"""Thresholds and constants. Every threshold is a heuristic; tune to taste."""

TROY_OZ_PER_KG = 32.1507466
COMEX_CONTRACT_OZ = 5000

# The SGE Ag(T+D) quote includes China's 13% VAT, so strip it before comparing
# with COMEX or a "premium" of ~13% would show up even in a calm market.
CHINA_VAT = 0.13

# Physical premium of Shanghai (ex-VAT) over COMEX, in percent.
PREMIUM_WATCH_PCT = 5.0
PREMIUM_ALERT_PCT = 10.0  # alert only when the 30-day median also exceeds this

# COMEX registered (deliverable) inventory change over ~30 days, in percent.
REGISTERED_DRAW_WATCH_PCT = -10.0
REGISTERED_DRAW_ALERT_PCT = -25.0

# Registered ounces as a share of open interest (in ounces), in percent.
COVERAGE_WATCH_PCT = 10.0
COVERAGE_ALERT_PCT = 5.0

# One-month silver lease rate, in percent.
LEASE_WATCH_PCT = 5.0
LEASE_ALERT_PCT = 10.0  # alert only when the 30-day median also exceeds this

# Commercial (producer/merchant + swap dealer) net short, as % of open interest,
# rising over ~90 days while registered inventory falls.
COMMERCIAL_SHORT_RISE_WATCH_PTS = 5.0
COMMERCIAL_SHORT_RISE_ALERT_PTS = 10.0

# Exchange events and how far back they count.
SEVERE_EXCHANGE_EVENTS = {
    "liquidation_only",
    "forced_cash_settlement",
    "trade_cancellation",
    "trading_halt",
    "position_limit_change",
    "delivery_default",
}
SEVERE_EVENT_WINDOW_DAYS = 90
MARGIN_EVENT_WINDOW_DAYS = 30
STATE_ACTION_WINDOW_DAYS = 180
