from datetime import date
import pandas as pd
from marketbot.history import append_day, load_history, history_for


def _day_df(d, symbols):
    return pd.DataFrame({
        "symbol": symbols,
        "open": [10] * len(symbols),
        "high": [11] * len(symbols),
        "low": [9] * len(symbols),
        "close": [10.5] * len(symbols),
        "volume": [100] * len(symbols),
        "date": [d] * len(symbols),
    })


def test_append_and_load_roundtrip(tmp_path):
    p = tmp_path / "history.parquet"
    append_day(_day_df(date(2026, 6, 11), ["RELIANCE", "TCS"]), p, lookback_days=300)
    append_day(_day_df(date(2026, 6, 12), ["RELIANCE", "TCS"]), p, lookback_days=300)
    hist = load_history(p)
    assert len(hist) == 4
    assert set(hist["symbol"]) == {"RELIANCE", "TCS"}


def test_append_is_idempotent_per_date(tmp_path):
    p = tmp_path / "history.parquet"
    append_day(_day_df(date(2026, 6, 12), ["RELIANCE"]), p, lookback_days=300)
    append_day(_day_df(date(2026, 6, 12), ["RELIANCE"]), p, lookback_days=300)  # same day again
    hist = load_history(p)
    assert len(hist) == 1  # not duplicated


def test_history_for_returns_sorted_single_symbol(tmp_path):
    p = tmp_path / "history.parquet"
    append_day(_day_df(date(2026, 6, 12), ["RELIANCE", "TCS"]), p, lookback_days=300)
    append_day(_day_df(date(2026, 6, 11), ["RELIANCE", "TCS"]), p, lookback_days=300)
    rel = history_for(load_history(p), "RELIANCE")
    assert list(rel["date"]) == sorted(rel["date"])
    assert set(rel["symbol"]) == {"RELIANCE"}


def test_lookback_trims_old_rows(tmp_path):
    p = tmp_path / "history.parquet"
    for day in range(1, 6):
        append_day(_day_df(date(2026, 6, day), ["RELIANCE"]), p, lookback_days=2)
    hist = load_history(p)
    # only the 2 most recent distinct dates kept
    assert hist["date"].nunique() == 2
