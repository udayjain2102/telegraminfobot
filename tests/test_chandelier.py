import numpy as np
import pandas as pd
from marketbot.chandelier import chandelier_exit, ChandelierResult


def _ohlc(closes):
    closes = np.asarray(closes, float)
    return pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": np.ones(len(closes)),
    })


def test_uptrend_is_long_and_stop_below_price():
    df = _ohlc(list(range(10, 80)))  # strong uptrend
    res = chandelier_exit(df, length=22, mult=3.0)
    assert res.direction == 1
    assert res.line < df["close"].iloc[-1]


def test_downtrend_is_short():
    df = _ohlc(list(range(80, 10, -1)))
    res = chandelier_exit(df, length=22, mult=3.0)
    assert res.direction == -1


def test_buy_flip_detected_when_trend_turns_up():
    down = list(range(80, 30, -1))
    up = list(range(30, 70))
    df = _ohlc(down + up)
    res = chandelier_exit(df, length=22, mult=3.0)
    # latest direction is long; somewhere a buy flip occurred
    assert res.direction == 1
    assert res.last_buy_index is not None


def test_buy_flag_true_on_exact_flip_bar():
    down = list(range(80, 40, -1))
    up = list(range(40, 90))
    df = _ohlc(down + up)
    # Truncate so the final bar IS the flip bar
    res_full = chandelier_exit(df, length=22, mult=3.0)
    flip_i = res_full.last_buy_index
    df_trunc = df.iloc[: flip_i + 1].reset_index(drop=True)
    res = chandelier_exit(df_trunc, length=22, mult=3.0)
    assert res.buy_flip is True
    assert res.sell_flip is False
