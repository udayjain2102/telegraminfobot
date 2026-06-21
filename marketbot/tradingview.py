"""Live intraday momentum scan sourced from TradingView's stock screener.

Realizes the strategy doc's TradingView screener: NSE equities in the
₹10B–₹200B market-cap band that are at a 1-month new high, ranked by turnover,
with a volume-confirmation flag for BUY candidates. Uses TradingView's
time-of-day-normalized relative volume so the volume check is meaningful
mid-session (unlike a naive today-vs-20d-average).

The TradingView call is isolated behind `query_fn` so the scan logic is
testable without the network, and so a TV outage can be handled by the caller.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import pandas as pd
from .config import Config
from .indicators import heikin_ashi


@dataclass
class TvRow:
    symbol: str
    name: str
    close: float
    change_pct: float
    volume: float
    turnover: float
    market_cap: float
    month_high: float
    rel_vol: float
    new_high: bool
    buy: bool = False
    atr: float = 0.0
    ha_close: float = 0.0          # today's Heikin-Ashi close = (O+H+L+C)/4
    new_high_basis: str = "HA"     # "HA" or "1M" (fallback when daily history unavailable)


@dataclass
class Target:
    r_multiple: float
    price: float
    gain_pct: float


@dataclass
class RiskReward:
    entry: float
    stop: float
    risk_per_share: float
    risk_pct: float
    capped: bool                 # True if ATR stop exceeded max_risk_pct and was capped
    targets: list[Target]
    shares_per_lakh: int         # shares for a ₹1,00,000 account at position_risk_pct


@dataclass
class TvScan:
    as_of: object = None
    universe: list[TvRow] = field(default_factory=list)   # Top-N turnover @ 1M new high
    buys: list[TvRow] = field(default_factory=list)       # universe ∧ volume confirmed


# Scanner columns we depend on (must match tradingview-screener field names).
_SELECT = [
    "name", "open", "high", "low", "close", "change", "volume", "market_cap_basic",
    "High.1M", "relative_volume_10d_calc", "ATR", "first_bar_time",
]


def compute_risk_reward(entry: float, atr: float, cfg: Config) -> RiskReward:
    """Per-trade risk/reward from the strategy doc (Step 6).

    Stop = entry - atr_stop_mult x ATR(14), but never risking more than
    max_risk_pct of entry. If ATR is missing/zero, fall back to the max-risk stop.
    Targets are placed at the configured R multiples (reward = n x risk).
    """
    cap_risk = cfg.max_risk_pct * entry
    atr_risk = cfg.atr_stop_mult * atr
    if atr_risk <= 0:
        risk_per_share, capped = cap_risk, False
    elif atr_risk > cap_risk:
        risk_per_share, capped = cap_risk, True
    else:
        risk_per_share, capped = atr_risk, False

    stop = entry - risk_per_share
    targets = [
        Target(r_multiple=m,
               price=entry + m * risk_per_share,
               gain_pct=(m * risk_per_share / entry) * 100.0)
        for m in cfg.rr_multiples
    ]
    budget = cfg.position_risk_pct * 100_000.0
    shares = int(budget // risk_per_share) if risk_per_share > 0 else 0
    return RiskReward(
        entry=entry, stop=stop, risk_per_share=risk_per_share,
        risk_pct=risk_per_share / entry, capped=capped,
        targets=targets, shares_per_lakh=shares,
    )


def _default_query_fn(min_cap: int, max_cap: int | None, limit: int) -> pd.DataFrame:
    """Run the real TradingView screener query for NSE equities."""
    from tradingview_screener import Query, col

    where = [col("exchange") == "NSE", col("market_cap_basic") >= min_cap]
    if max_cap is not None:
        where.append(col("market_cap_basic") <= max_cap)
    _, df = (Query()
             .set_markets("india")
             .select(*_SELECT)
             .where(*where)
             .order_by("volume", ascending=False)
             .limit(limit)
             .get_scanner_data())
    return df


def _default_history_fn(symbol: str) -> pd.DataFrame | None:
    """Recent daily OHLC for an NSE symbol (settled bars), for HA + new-high."""
    import yfinance as yf
    h = yf.Ticker(f"{symbol}.NS").history(period="3mo", interval="1d", auto_adjust=False)
    if h is None or len(h) == 0:
        return None
    return h.rename(columns={"Open": "open", "High": "high",
                             "Low": "low", "Close": "close"})[["open", "high", "low", "close"]]


def _is_ha_new_high(row: TvRow, history_fn, cfg: Config) -> bool:
    """True if today's HA close makes a new high over the last N HA closes.

    Uses settled daily history (through the prior session) to build the prior HA
    closes; today's HA close comes from the live snapshot. Falls back to the TV
    1-month high when daily history is unavailable/too short.
    """
    try:
        h = history_fn(row.symbol)
    except Exception:  # noqa: BLE001
        h = None
    if h is None or len(h) < cfg.new_high_lookback_days:
        row.new_high_basis = "1M"
        return row.month_high > 0 and row.close >= row.month_high * 0.999

    ha_close = heikin_ashi(h)["ha_close"]
    prior_max = float(ha_close.tail(cfg.new_high_lookback_days).max())
    row.new_high_basis = "HA"
    return prior_max > 0 and row.ha_close >= prior_max * 0.999


def scan_momentum(cfg: Config, query_fn=None, history_fn=None, now=None,
                  fetch_limit: int = 400, ha_fetch_cap: int = 50,
                  near_high_band: float = 0.05) -> TvScan:
    """Build the intraday momentum scan from a TradingView screener snapshot.

    Pipeline (strategy doc):
      1. NSE + MCap band + **not listed within the last `min_listing_age_days`**
      2. cheap pre-filter to names within `near_high_band` of the TV 1-month high
         (bounds how many daily-history fetches we do)
      3. **Heikin-Ashi new-high confirmation** over `new_high_lookback_days`
         (falls back to the strict TV 1-month high when daily history is missing)
      4. rank survivors by turnover, take top-N
      5. flag BUY when relative volume ≥ `buy_volume_mult`
    """
    query_fn = query_fn or _default_query_fn
    history_fn = history_fn or _default_history_fn
    now = now or datetime.now(timezone.utc)
    cutoff_ts = (now - timedelta(days=cfg.min_listing_age_days)).timestamp()

    df = query_fn(cfg.min_market_cap_inr, cfg.max_market_cap_inr, fetch_limit)
    scan = TvScan()
    if df is None or df.empty:
        return scan

    # 1+2) market-cap band, recency, and a cheap "near the 1-month high" pre-filter
    cand: list[TvRow] = []
    for _, r in df.iterrows():
        cap = float(r.get("market_cap_basic") or 0.0)
        if cap < cfg.min_market_cap_inr:
            continue
        if cfg.max_market_cap_inr is not None and cap > cfg.max_market_cap_inr:
            continue
        fbt = r.get("first_bar_time")
        if fbt is not None and not pd.isna(fbt) and float(fbt) > cutoff_ts:
            continue  # trading started within the last 12 months → skip
        close = float(r["close"])
        month_high = float(r.get("High.1M") or 0.0)
        if not (month_high > 0 and close >= month_high * (1.0 - near_high_band)):
            continue  # not near a 1-month high → can't be a fresh breakout
        o = float(r.get("open") or 0.0)
        hi = float(r.get("high") or 0.0)
        lo = float(r.get("low") or 0.0)
        vol = float(r.get("volume") or 0.0)
        cand.append(TvRow(
            symbol=str(r.get("name") or str(r.get("ticker", "")).split(":")[-1]),
            name=str(r.get("name") or ""),
            close=close,
            change_pct=float(r.get("change") or 0.0),
            volume=vol,
            turnover=close * vol,
            market_cap=cap,
            month_high=month_high,
            rel_vol=float(r.get("relative_volume_10d_calc") or 0.0),
            new_high=False,
            atr=float(r.get("ATR") or 0.0),
            ha_close=(o + hi + lo + close) / 4.0 if (o and hi and lo) else close,
        ))

    # 3) Heikin-Ashi new-high confirmation (bounded number of history fetches)
    confirmed: list[TvRow] = []
    for examined, row in enumerate(sorted(cand, key=lambda x: x.turnover, reverse=True)):
        if examined >= ha_fetch_cap:
            break
        if _is_ha_new_high(row, history_fn, cfg):
            row.new_high = True
            confirmed.append(row)

    # 4) rank by turnover, take top-N
    confirmed.sort(key=lambda x: x.turnover, reverse=True)
    universe = confirmed[: cfg.top_n_turnover]

    # 5) BUY = volume-confirmed
    for r in universe:
        r.buy = r.rel_vol >= cfg.buy_volume_mult

    scan.universe = universe
    scan.buys = [r for r in universe if r.buy]
    return scan
