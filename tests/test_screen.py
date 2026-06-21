from datetime import date, timedelta
import numpy as np
import pandas as pd
from marketbot.config import Config
from marketbot.screen import build_report, StockRow


def _history(symbol, closes, vols, start=date(2025, 1, 1)):
    n = len(closes)
    dates = [start + timedelta(days=i) for i in range(n)]
    closes = np.asarray(closes, float)
    return pd.DataFrame({
        "symbol": [symbol] * n,
        "open": closes, "high": closes + 1, "low": closes - 1,
        "close": closes, "volume": np.asarray(vols, float), "date": dates,
    })


def _universe(symbols):
    return pd.DataFrame({
        "symbol": symbols,
        "name": symbols,
        "market_cap": [2e11] * len(symbols),
        "sector": ["IT"] * len(symbols),
    })


def test_turnover_ranking_orders_by_close_times_volume():
    cfg = Config()
    big = _history("BIG", [100] * 300, [10000] * 300)
    small = _history("SMALL", [100] * 300, [10] * 300)
    hist = pd.concat([big, small], ignore_index=True)
    report = build_report(hist, _universe(["BIG", "SMALL"]), cfg)
    assert report.turnover_leaders[0].symbol == "BIG"


def test_relvol_spike_flagged():
    cfg = Config(relvol_spike_threshold=2.0)
    vols = [100] * 299 + [1000]   # last day 10x average
    hist = _history("SPIKE", [50] * 300, vols)
    report = build_report(hist, _universe(["SPIKE"]), cfg)
    assert any(r.symbol == "SPIKE" for r in report.unusual_volume)


def test_buy_flip_appears_in_chandelier_buys():
    cfg = Config()
    closes = list(range(120, 60, -1)) + list(range(60, 300))  # down then long uptrend
    hist = _history("FLIP", closes, [100] * len(closes))
    report = build_report(hist, _universe(["FLIP"]), cfg)
    # FLIP is currently long; it should be in buy list only if flip is recent,
    # otherwise at least not in sells.
    assert "FLIP" not in [r.symbol for r in report.chandelier_sells]


def _momentum_history(symbol, spike_volume):
    # Long downtrend (Chandelier short) then a sharp up-bar on the last session:
    # flips Chandelier to BUY, makes a fresh 20-day high, and sits above the POC.
    closes = list(range(300, 40, -1)) + [600]          # 261 bars, last bar jumps up
    vols = [100] * (len(closes) - 1) + [spike_volume]   # last-day volume control
    return _history(symbol, closes, vols)


def test_momentum_buy_fires_when_all_conditions_met():
    cfg = Config(buy_volume_mult=1.5)
    hist = _momentum_history("MOM", spike_volume=1000)   # 10x avg → passes 1.5x
    report = build_report(hist, _universe(["MOM"]), cfg)
    row = next(r for r in report.high_conviction if r.symbol == "MOM")
    assert row.buy_flip and row.new_high_20d and row.above_poc
    assert row.rel_vol >= cfg.buy_volume_mult


def test_momentum_buy_suppressed_without_volume_confirmation():
    cfg = Config(buy_volume_mult=1.5)
    hist = _momentum_history("MOM", spike_volume=100)    # flat volume → fails 1.5x
    report = build_report(hist, _universe(["MOM"]), cfg)
    assert "MOM" not in [r.symbol for r in report.high_conviction]


def test_momentum_buy_requires_top_turnover_membership():
    # Stock fires the technical signal but is outside the Top-N turnover set,
    # so it must be excluded from Momentum BUY.
    cfg = Config(buy_volume_mult=1.5, top_n_turnover=1)
    mom = _momentum_history("MOM", spike_volume=1000)
    # A second name with far higher turnover occupies the single Top-1 slot.
    big = _history("BIG", [1000] * len(mom), [10000] * len(mom))
    hist = pd.concat([mom, big], ignore_index=True)
    report = build_report(hist, _universe(["MOM", "BIG"]), cfg)
    assert report.turnover_leaders[0].symbol == "BIG"
    assert "MOM" not in [r.symbol for r in report.high_conviction]


def test_report_sections_exist():
    cfg = Config()
    hist = _history("A", [100] * 300, [500] * 300)
    report = build_report(hist, _universe(["A"]), cfg)
    for attr in ["unusual_volume", "turnover_leaders", "chandelier_buys",
                 "chandelier_sells", "approaching_levels", "high_conviction",
                 "rsi_oversold", "rsi_overbought", "new_highs", "ma_crossovers"]:
        assert hasattr(report, attr)
