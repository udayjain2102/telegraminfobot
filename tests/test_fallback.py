from datetime import date
import pandas as pd
import pytest
from marketbot.fallback import fetch_eod_yfinance
from marketbot.bhavcopy import BhavcopyUnavailable


def _yf_frame(rows):
    # rows: list of (date, o, h, l, c, v); index is a DatetimeIndex like yfinance returns
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, *_ in rows])
    return pd.DataFrame(
        {
            "Open": [o for _, o, *_ in rows],
            "High": [h for _, _, h, *_ in rows],
            "Low": [l for _, _, _, l, *_ in rows],
            "Close": [c for _, _, _, _, c, _ in rows],
            "Volume": [v for *_, v in rows],
        },
        index=idx,
    )


def test_fallback_picks_latest_bar_on_or_before_date():
    data = {
        "RELIANCE.NS": _yf_frame([
            (date(2026, 6, 10), 1, 2, 0.5, 1.5, 100),
            (date(2026, 6, 11), 2, 3, 1.5, 2.5, 200),   # this is <= 2026-06-11 and latest
            (date(2026, 6, 12), 9, 9, 9, 9, 999),       # after data_date → ignored
        ]),
    }
    df = fetch_eod_yfinance(date(2026, 6, 11), ["RELIANCE"], history_fn=lambda t: data[t])
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "RELIANCE"
    assert row["close"] == 2.5
    assert row["date"] == date(2026, 6, 11)
    assert set(df.columns) == {"symbol", "open", "high", "low", "close", "volume", "date"}


def test_fallback_skips_symbols_that_error_or_empty():
    def history_fn(ticker):
        if ticker == "GOOD.NS":
            return _yf_frame([(date(2026, 6, 11), 1, 2, 0.5, 1.5, 100)])
        if ticker == "EMPTY.NS":
            return pd.DataFrame()
        raise RuntimeError("network")
    df = fetch_eod_yfinance(date(2026, 6, 11), ["GOOD", "EMPTY", "BAD"], history_fn=history_fn)
    assert list(df["symbol"]) == ["GOOD"]


def test_fallback_raises_when_no_data():
    with pytest.raises(BhavcopyUnavailable):
        fetch_eod_yfinance(date(2026, 6, 11), ["X"], history_fn=lambda t: pd.DataFrame())
