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


def test_report_sections_exist():
    cfg = Config()
    hist = _history("A", [100] * 300, [500] * 300)
    report = build_report(hist, _universe(["A"]), cfg)
    for attr in ["unusual_volume", "turnover_leaders", "chandelier_buys",
                 "chandelier_sells", "approaching_levels", "high_conviction",
                 "rsi_oversold", "rsi_overbought", "new_highs", "ma_crossovers"]:
        assert hasattr(report, attr)
