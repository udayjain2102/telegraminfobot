import numpy as np
import pandas as pd
import pytest
from marketbot import indicators as ind


def _df(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "open": closes,
        "high": closes if highs is None else np.asarray(highs, float),
        "low": closes if lows is None else np.asarray(lows, float),
        "close": closes,
        "volume": np.ones(n) if vols is None else np.asarray(vols, float),
    })


def test_rsi_all_gains_is_100():
    df = _df(list(range(1, 40)))
    assert ind.rsi(df["close"], 14).iloc[-1] == pytest.approx(100.0, abs=1e-6)


def test_rsi_all_losses_is_0():
    df = _df(list(range(40, 1, -1)))
    assert ind.rsi(df["close"], 14).iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_equal_alternating_near_50():
    closes = [10 + (1 if i % 2 == 0 else 0) for i in range(60)]  # +1,-1 alternating
    val = ind.rsi(pd.Series(closes, dtype=float), 14).iloc[-1]
    assert 45 <= val <= 55


def test_atr_constant_true_range():
    # Each bar: high-low = 2, no gaps → ATR == 2 after seeding
    highs = [11] * 30
    lows = [9] * 30
    closes = [10] * 30
    df = _df(closes, highs=highs, lows=lows)
    assert ind.atr(df, 3).iloc[-1] == pytest.approx(2.0, abs=1e-9)


def test_sma():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert ind.sma(s, 3).iloc[-1] == pytest.approx(4.0)


def test_golden_cross_detected_on_last_bar():
    # fast crosses above slow exactly on the last bar
    fast = pd.Series([1, 1, 1, 1, 10], dtype=float)
    slow = pd.Series([5, 5, 5, 5, 5], dtype=float)
    assert ind.crossed_above(fast, slow) is True


def test_relative_volume():
    vols = [100] * 20 + [300]  # avg of prior 20 = 100, today = 300
    df = _df([10] * 21, vols=vols)
    assert ind.relative_volume(df, 20).iloc[-1] == pytest.approx(3.0)


def test_turnover():
    df = _df([10, 20], vols=[5, 5])
    assert ind.turnover(df).iloc[-1] == pytest.approx(100.0)


def test_pct_from_52w_high():
    closes = list(range(1, 101))  # high=100, last close=100 → 0% from high
    df = _df(closes)
    assert ind.pct_from_high(df, 252).iloc[-1] == pytest.approx(0.0, abs=1e-9)
