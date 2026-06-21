from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from .config import Config
from . import indicators as ind
from .chandelier import chandelier_exit
from .volume_profile import volume_profile, near_levels, LevelHit
from .history import history_for


@dataclass
class StockRow:
    symbol: str
    name: str
    close: float
    chg_pct: float
    rel_vol: float
    turnover: float
    sector: str
    chandelier_dir: int
    buy_flip: bool
    sell_flip: bool
    new_high_20d: bool = False
    above_poc: bool = False
    level_hits: list[LevelHit] = field(default_factory=list)
    rsi: float = float("nan")


@dataclass
class Report:
    as_of: object = None
    unusual_volume: list[StockRow] = field(default_factory=list)
    turnover_leaders: list[StockRow] = field(default_factory=list)
    chandelier_buys: list[StockRow] = field(default_factory=list)
    chandelier_sells: list[StockRow] = field(default_factory=list)
    approaching_levels: list[StockRow] = field(default_factory=list)
    high_conviction: list[StockRow] = field(default_factory=list)
    rsi_oversold: list[StockRow] = field(default_factory=list)
    rsi_overbought: list[StockRow] = field(default_factory=list)
    new_highs: list[StockRow] = field(default_factory=list)
    ma_crossovers: list[StockRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _evaluate_symbol(df: pd.DataFrame, name: str, sector: str, cfg: Config) -> StockRow | None:
    if len(df) < max(cfg.chandelier_length + 2, cfg.relvol_lookback_days + 2):
        return None
    close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])
    chg = (close - prev_close) / prev_close * 100.0 if prev_close else 0.0
    rel_vol = float(ind.relative_volume(df, cfg.relvol_lookback_days).iloc[-1])
    turn = float(ind.turnover(df).iloc[-1])
    rsi_val = float(ind.rsi(df["close"], cfg.rsi_period).iloc[-1])

    ce = chandelier_exit(df, cfg.chandelier_length, cfg.chandelier_mult)

    prof = volume_profile(df, cfg.avp_bins, cfg.avp_lookback_days, cfg.avp_value_area_pct)
    hits = near_levels(close, {"POC": prof.poc, "VAH": prof.vah, "VAL": prof.val},
                       cfg.near_level_band_pct)

    # 1-month new high: close >= highest close of last `new_high_lookback_days` sessions
    new_high_window = float(df["close"].rolling(cfg.new_high_lookback_days).max().iloc[-1])
    new_high = close >= new_high_window if new_high_window == new_high_window else False
    above_poc = close > prof.poc if prof.poc == prof.poc else False

    return StockRow(
        symbol=df["symbol"].iloc[-1], name=name, close=close, chg_pct=chg,
        rel_vol=rel_vol if rel_vol == rel_vol else 0.0, turnover=turn, sector=sector,
        chandelier_dir=ce.direction, buy_flip=ce.buy_flip, sell_flip=ce.sell_flip,
        new_high_20d=bool(new_high), above_poc=bool(above_poc),
        level_hits=hits, rsi=rsi_val,
    )


def build_report(history: pd.DataFrame, universe: pd.DataFrame, cfg: Config) -> Report:
    report = Report()
    if not history.empty:
        report.as_of = max(history["date"])

    rows: list[StockRow] = []
    meta = {r["symbol"]: r for _, r in universe.iterrows()}
    for symbol in universe["symbol"]:
        df = history_for(history, symbol)
        if df.empty:
            continue
        try:
            row = _evaluate_symbol(df, meta[symbol]["name"], meta[symbol].get("sector", ""), cfg)
            if row is not None:
                rows.append(row)
        except Exception as e:  # noqa: BLE001
            report.errors.append(f"{symbol}: {e}")

    report.unusual_volume = sorted(
        [r for r in rows if r.rel_vol >= cfg.relvol_spike_threshold],
        key=lambda r: r.rel_vol, reverse=True)[: cfg.top_n_unusual]

    report.turnover_leaders = sorted(rows, key=lambda r: r.turnover, reverse=True)[: cfg.top_n_turnover]

    report.chandelier_buys = [r for r in rows if r.buy_flip]
    report.chandelier_sells = [r for r in rows if r.sell_flip]

    report.approaching_levels = sorted(
        [r for r in rows if r.level_hits],
        key=lambda r: abs(r.level_hits[0].distance_pct))[: cfg.top_n_levels]

    # Momentum BUY (spec) — ALL conditions must hold:
    #  [1] in Top-15 turnover set  [2] 1-month new high  [3] Chandelier/Supertrend buy flip
    #  [4] close above volume-profile POC  [5] signal-day volume >= buy_volume_mult x avg
    turnover_set = {r.symbol for r in report.turnover_leaders}
    report.high_conviction = [
        r for r in rows
        if r.symbol in turnover_set
        and r.new_high_20d
        and r.buy_flip
        and r.above_poc
        and r.rel_vol >= cfg.buy_volume_mult
    ]

    report.rsi_oversold = [r for r in rows if r.rsi <= cfg.rsi_oversold]
    report.rsi_overbought = [r for r in rows if r.rsi >= cfg.rsi_overbought]
    report.new_highs = [
        r for r in rows
        if ind.pct_from_high(history_for(history, r.symbol), cfg.high_low_lookback_days).iloc[-1] >= -0.1
    ]
    report.ma_crossovers = []
    for r in rows:
        df = history_for(history, r.symbol)
        if len(df) >= max(cfg.sma_periods) + 1:
            fast = ind.sma(df["close"], cfg.sma_periods[1])
            slow = ind.sma(df["close"], cfg.sma_periods[2])
            if ind.crossed_above(fast, slow):
                report.ma_crossovers.append(r)
    return report
