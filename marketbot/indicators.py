from __future__ import annotations
import numpy as np
import pandas as pd


def wilder_rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing (RMA), seeded with the SMA of the first `length` values."""
    arr = series.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    if len(arr) < length:
        return pd.Series(out, index=series.index)
    seed = arr[:length].mean()
    out[length - 1] = seed
    prev = seed
    for i in range(length, len(arr)):
        prev = (prev * (length - 1) + arr[i]) / length
        out[i] = prev
    return pd.Series(out, index=series.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = wilder_rma(gain.fillna(0.0), period)
    avg_loss = wilder_rma(loss.fillna(0.0), period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss != 0.0, 100.0)   # no losses → 100
    out = out.where(avg_gain != 0.0, 0.0)      # no gains → 0
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 22) -> pd.Series:
    return wilder_rma(true_range(df), length)


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def crossed_above(fast: pd.Series, slow: pd.Series) -> bool:
    if len(fast) < 2:
        return False
    return bool(fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1])


def crossed_below(fast: pd.Series, slow: pd.Series) -> bool:
    if len(fast) < 2:
        return False
    return bool(fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1])


def relative_volume(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    avg = df["volume"].shift(1).rolling(lookback).mean()
    return df["volume"] / avg


def turnover(df: pd.DataFrame) -> pd.Series:
    return df["close"] * df["volume"]


def pct_from_high(df: pd.DataFrame, lookback: int = 252) -> pd.Series:
    roll_high = df["high"].rolling(lookback, min_periods=1).max()
    return (df["close"] - roll_high) / roll_high * 100.0


def pct_from_low(df: pd.DataFrame, lookback: int = 252) -> pd.Series:
    roll_low = df["low"].rolling(lookback, min_periods=1).min()
    return (df["close"] - roll_low) / roll_low * 100.0
