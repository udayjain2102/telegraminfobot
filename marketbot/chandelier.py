from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .indicators import atr, heikin_ashi


@dataclass
class ChandelierResult:
    direction: int            # 1 = long, -1 = short (latest bar)
    line: float               # active stop line value on the latest bar
    buy_flip: bool            # direction flipped -1 -> 1 on the latest bar
    sell_flip: bool           # direction flipped 1 -> -1 on the latest bar
    last_buy_index: int | None
    last_sell_index: int | None


def chandelier_exit_ha(df: pd.DataFrame, length: int = 22, mult: float = 3.0) -> ChandelierResult:
    """Chandelier Exit computed on Heikin-Ashi candles (the strategy's candle basis)."""
    ha = heikin_ashi(df)
    ha_df = pd.DataFrame({
        "high": ha["ha_high"], "low": ha["ha_low"], "close": ha["ha_close"],
    }, index=df.index)
    return chandelier_exit(ha_df, length, mult)


def chandelier_exit(df: pd.DataFrame, length: int = 22, mult: float = 3.0) -> ChandelierResult:
    n = len(df)
    close = df["close"].to_numpy(dtype=float)
    atr_arr = (mult * atr(df, length)).to_numpy(dtype=float)

    highest_close = df["close"].rolling(length).max().to_numpy(dtype=float)
    lowest_close = df["close"].rolling(length).min().to_numpy(dtype=float)

    long_stop = np.full(n, np.nan)
    short_stop = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)

    for i in range(n):
        if np.isnan(atr_arr[i]):
            long_stop[i] = highest_close[i] - atr_arr[i] if not np.isnan(highest_close[i]) else np.nan
            short_stop[i] = lowest_close[i] + atr_arr[i] if not np.isnan(lowest_close[i]) else np.nan
            direction[i] = 1
            continue

        ls = highest_close[i] - atr_arr[i]
        ss = lowest_close[i] + atr_arr[i]

        prev_ls = long_stop[i - 1] if i > 0 and not np.isnan(long_stop[i - 1]) else ls
        prev_ss = short_stop[i - 1] if i > 0 and not np.isnan(short_stop[i - 1]) else ss

        long_stop[i] = max(ls, prev_ls) if (i > 0 and close[i - 1] > prev_ls) else ls
        short_stop[i] = min(ss, prev_ss) if (i > 0 and close[i - 1] < prev_ss) else ss

        prev_dir = direction[i - 1] if i > 0 else 1
        if close[i] > prev_ss:
            direction[i] = 1
        elif close[i] < prev_ls:
            direction[i] = -1
        else:
            direction[i] = prev_dir

    buy_flips = [i for i in range(1, n) if direction[i] == 1 and direction[i - 1] == -1]
    sell_flips = [i for i in range(1, n) if direction[i] == -1 and direction[i - 1] == 1]

    last = n - 1
    return ChandelierResult(
        direction=int(direction[last]),
        line=float(long_stop[last] if direction[last] == 1 else short_stop[last]),
        buy_flip=(last in buy_flips),
        sell_flip=(last in sell_flips),
        last_buy_index=(buy_flips[-1] if buy_flips else None),
        last_sell_index=(sell_flips[-1] if sell_flips else None),
    )
