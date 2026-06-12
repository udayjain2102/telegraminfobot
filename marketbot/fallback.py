"""yfinance fallback for the daily EOD fetch.

Used when the NSE bhavcopy is unavailable (e.g. the Actions runner IP is blocked
or the file is delayed). Returns the same shape as ``bhavcopy.parse_bhavcopy``:
columns ``symbol, open, high, low, close, volume, date``.
"""
from __future__ import annotations
from datetime import date
from typing import Callable
import pandas as pd
from .bhavcopy import BhavcopyUnavailable


def _default_history_fn(ticker: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.Ticker(ticker).history(period="7d", interval="1d", auto_adjust=False)


def fetch_eod_yfinance(data_date: date, symbols: list[str],
                       history_fn: Callable[[str], pd.DataFrame] | None = None) -> pd.DataFrame:
    """Fetch one day's OHLCV for ``symbols`` via yfinance.

    For each symbol, picks the most recent bar on or before ``data_date``.
    Raises ``BhavcopyUnavailable`` if no symbol yields data.
    """
    history_fn = history_fn or _default_history_fn
    records = []
    for s in symbols:
        try:
            h = history_fn(f"{s}.NS")
        except Exception:  # noqa: BLE001
            continue
        if h is None or len(h) == 0:
            continue
        rows = []
        for ts, row in h.iterrows():
            d = ts.date() if hasattr(ts, "date") else ts
            if d <= data_date:
                rows.append((d, row))
        if not rows:
            continue
        d, row = max(rows, key=lambda x: x[0])
        try:
            records.append({
                "symbol": s,
                "open": float(row["Open"]), "high": float(row["High"]),
                "low": float(row["Low"]), "close": float(row["Close"]),
                "volume": float(row["Volume"]), "date": d,
            })
        except (KeyError, TypeError, ValueError):
            continue

    df = pd.DataFrame(records, columns=["symbol", "open", "high", "low", "close", "volume", "date"])
    if df.empty:
        raise BhavcopyUnavailable(f"yfinance fallback returned no data for {data_date}")
    return df
