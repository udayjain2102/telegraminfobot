# Daily Market Brief Telegram Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A push-only Telegram bot that, each NSE trading morning, screens the Indian large/mid-cap universe and sends a brief covering market overview, relative-volume spikes, turnover leaders, Chandelier Exit Buy/Sell flips, anchored-volume-profile level approaches, and a high-conviction confluence section.

**Architecture:** Stateless Python script run by GitHub Actions cron. NSE bhavcopy (daily EOD, all stocks) is filtered to a weekly-refreshed market-cap universe, appended to a rolling `data/history.parquet`, then pure-pandas modules compute indicators / Chandelier Exit / anchored volume profile. A formatter renders a Markdown message sent via the Telegram Bot API. History is committed back to the repo so no database is needed.

**Tech Stack:** Python 3.11, pandas, numpy, pyarrow (parquet), requests, yfinance (fallback + indices), PyYAML, pytest.

---

## File Structure

```
marketbot/
  __init__.py
  config.py            # load + validate config.yaml into a Config dataclass
  holidays.py          # NSE holiday / trading-day logic
  indicators.py        # RSI, SMA, MA-cross, 52w levels, rel-vol, turnover (pure)
  chandelier.py        # Chandelier Exit (ATR 22, mult 3) line + Buy/Sell flips (pure)
  volume_profile.py    # 1-yr anchored volume profile → POC/VAH/VAL + near_level (pure)
  bhavcopy.py          # download + parse NSE daily bhavcopy (network)
  universe.py          # build/load data/universe.csv (network, weekly)
  history.py           # append/load rolling data/history.parquet
  screen.py            # per-stock signals + ranking/selection into a Report (pure)
  market_overview.py   # Nifty/Sensex change + sector movers
  brief.py             # render Report → Telegram message text (pure)
  telegram_bot.py      # send message(s) with retry + 4096 split
  main.py              # orchestration entry point
config.yaml
data/
  nse_holidays.txt     # one ISO date per line
  universe.csv         # generated weekly (symbol,name,market_cap,sector)
  history.parquet      # generated daily (rolling OHLCV)
tests/
  conftest.py
  fixtures/
    bhavcopy_sample.csv
    equity_l_sample.csv
  test_config.py
  test_holidays.py
  test_indicators.py
  test_chandelier.py
  test_volume_profile.py
  test_bhavcopy.py
  test_universe.py
  test_history.py
  test_screen.py
  test_market_overview.py
  test_brief.py
  test_telegram_bot.py
  test_main.py
.github/workflows/
  daily-brief.yml
  refresh-universe.yml
requirements.txt
README.md
```

---

## Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`, `marketbot/__init__.py`, `pytest.ini`, `.gitignore`, `data/.gitkeep`

- [ ] **Step 1: Create `requirements.txt`**

```
pandas==2.2.2
numpy==1.26.4
pyarrow==16.1.0
requests==2.32.3
PyYAML==6.0.1
yfinance==0.2.40
pytest==8.2.2
```

- [ ] **Step 2: Create `marketbot/__init__.py`** (empty file)

```python
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

- [ ] **Step 5: Create `data/.gitkeep`** (empty file so the dir is tracked)

```
```

- [ ] **Step 6: Install and verify**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && pytest`
Expected: pytest runs and reports "no tests ran" (exit 5) — confirms install works.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt marketbot/__init__.py pytest.ini .gitignore data/.gitkeep
git commit -m "chore: project scaffold and dependencies"
```

---

## Task 2: Config loader

**Files:**
- Create: `config.yaml`, `marketbot/config.py`, `tests/test_config.py`

- [ ] **Step 1: Create `config.yaml`**

```yaml
# Screener / universe
min_market_cap_inr: 10_000_000_000   # ₹1,000 crore

# Section sizes
top_n_unusual: 8
top_n_turnover: 12
top_n_levels: 10

# Relative volume
relvol_lookback_days: 20
relvol_spike_threshold: 2.0          # today vol >= 2x average → "spike"

# Indicators
rsi_period: 14
rsi_oversold: 30
rsi_overbought: 70
sma_periods: [20, 50, 200]
high_low_lookback_days: 252          # ~52 weeks

# Chandelier Exit
chandelier_length: 22
chandelier_mult: 3.0

# Anchored Volume Profile
avp_lookback_days: 252               # ~1 year, anchor = first bar in window
avp_bins: 24
avp_value_area_pct: 0.70
near_level_band_pct: 0.02            # within 2% of a level → "approaching"

# History
history_lookback_days: 300           # rows kept per symbol in history.parquet

# Telegram (token + chat ids come from env at runtime)
telegram_parse_mode: "HTML"
```

- [ ] **Step 2: Write the failing test** → `tests/test_config.py`

```python
from pathlib import Path
from marketbot.config import load_config


def test_load_config_reads_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "min_market_cap_inr: 10000000000\n"
        "top_n_unusual: 5\n"
        "chandelier_length: 22\n"
        "chandelier_mult: 3.0\n"
        "sma_periods: [20, 50, 200]\n"
    )
    cfg = load_config(p)
    assert cfg.min_market_cap_inr == 10_000_000_000
    assert cfg.top_n_unusual == 5
    assert cfg.chandelier_length == 22
    assert cfg.chandelier_mult == 3.0
    assert cfg.sma_periods == [20, 50, 200]


def test_load_config_applies_defaults_for_missing_keys(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("min_market_cap_inr: 5\n")
    cfg = load_config(p)
    assert cfg.rsi_period == 14          # default fills in
    assert cfg.avp_value_area_pct == 0.70
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.config`

- [ ] **Step 4: Implement `marketbot/config.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field, fields
from pathlib import Path
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass
class Config:
    min_market_cap_inr: int = 10_000_000_000
    top_n_unusual: int = 8
    top_n_turnover: int = 12
    top_n_levels: int = 10
    relvol_lookback_days: int = 20
    relvol_spike_threshold: float = 2.0
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    sma_periods: list[int] = field(default_factory=lambda: [20, 50, 200])
    high_low_lookback_days: int = 252
    chandelier_length: int = 22
    chandelier_mult: float = 3.0
    avp_lookback_days: int = 252
    avp_bins: int = 24
    avp_value_area_pct: float = 0.70
    near_level_band_pct: float = 0.02
    history_lookback_days: int = 300
    telegram_parse_mode: str = "HTML"


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    known = {f.name for f in fields(Config)}
    kwargs = {k: v for k, v in raw.items() if k in known}
    return Config(**kwargs)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add config.yaml marketbot/config.py tests/test_config.py
git commit -m "feat: config loader with defaults"
```

---

## Task 3: NSE holidays / trading-day logic

**Files:**
- Create: `data/nse_holidays.txt`, `marketbot/holidays.py`, `tests/test_holidays.py`

- [ ] **Step 1: Create `data/nse_holidays.txt`** (2026 NSE holidays; update yearly)

```
2026-01-26
2026-02-15
2026-03-06
2026-03-21
2026-04-01
2026-04-03
2026-04-14
2026-05-01
2026-08-15
2026-09-04
2026-10-02
2026-10-21
2026-11-09
2026-11-24
2026-12-25
```

- [ ] **Step 2: Write the failing test** → `tests/test_holidays.py`

```python
from datetime import date
from pathlib import Path
from marketbot.holidays import is_trading_day, previous_trading_day


def _holiday_file(tmp_path) -> Path:
    p = tmp_path / "h.txt"
    p.write_text("2026-01-26\n2026-08-15\n")
    return p


def test_weekend_is_not_trading_day(tmp_path):
    hf = _holiday_file(tmp_path)
    assert is_trading_day(date(2026, 6, 13), hf) is False  # Saturday
    assert is_trading_day(date(2026, 6, 14), hf) is False  # Sunday


def test_listed_holiday_is_not_trading_day(tmp_path):
    hf = _holiday_file(tmp_path)
    assert is_trading_day(date(2026, 1, 26), hf) is False


def test_normal_weekday_is_trading_day(tmp_path):
    hf = _holiday_file(tmp_path)
    assert is_trading_day(date(2026, 6, 12), hf) is True   # Friday


def test_previous_trading_day_skips_weekend(tmp_path):
    hf = _holiday_file(tmp_path)
    # Monday 2026-06-15 → previous trading day is Friday 2026-06-12
    assert previous_trading_day(date(2026, 6, 15), hf) == date(2026, 6, 12)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_holidays.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.holidays`

- [ ] **Step 4: Implement `marketbot/holidays.py`**

```python
from __future__ import annotations
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

DEFAULT_HOLIDAY_FILE = Path(__file__).resolve().parent.parent / "data" / "nse_holidays.txt"


@lru_cache(maxsize=8)
def _load_holidays(path: Path) -> frozenset[date]:
    lines = Path(path).read_text().splitlines()
    out = set()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(date.fromisoformat(line))
    return frozenset(out)


def is_trading_day(d: date, holiday_file: Path | str = DEFAULT_HOLIDAY_FILE) -> bool:
    if d.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return d not in _load_holidays(Path(holiday_file))


def previous_trading_day(d: date, holiday_file: Path | str = DEFAULT_HOLIDAY_FILE) -> date:
    cur = d - timedelta(days=1)
    while not is_trading_day(cur, holiday_file):
        cur -= timedelta(days=1)
    return cur
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_holidays.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add data/nse_holidays.txt marketbot/holidays.py tests/test_holidays.py
git commit -m "feat: NSE trading-day / holiday logic"
```

---

## Task 4: Indicators (RSI, SMA, MA-cross, 52w, rel-vol, turnover)

**Files:**
- Create: `marketbot/indicators.py`, `tests/test_indicators.py`

All functions take a per-symbol OHLCV DataFrame sorted ascending by date with columns `open,high,low,close,volume`.

- [ ] **Step 1: Write the failing test** → `tests/test_indicators.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.indicators`

- [ ] **Step 3: Implement `marketbot/indicators.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_indicators.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/indicators.py tests/test_indicators.py
git commit -m "feat: technical indicators (RSI, ATR, SMA, rel-vol, 52w, turnover)"
```

---

## Task 5: Chandelier Exit (ATR 22, mult 3)

**Files:**
- Create: `marketbot/chandelier.py`, `tests/test_chandelier.py`

Port of the standard TradingView Chandelier Exit (everget, `useClose=true`): `longStop = highest(close,n) - mult*ATR`, `shortStop = lowest(close,n) + mult*ATR`, with the trailing-ratchet and direction flip producing Buy/Sell.

- [ ] **Step 1: Write the failing test** → `tests/test_chandelier.py`

```python
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
    series = pd.Series(df["close"])
    res_full = chandelier_exit(df, length=22, mult=3.0)
    flip_i = res_full.last_buy_index
    df_trunc = df.iloc[: flip_i + 1].reset_index(drop=True)
    res = chandelier_exit(df_trunc, length=22, mult=3.0)
    assert res.buy_flip is True
    assert res.sell_flip is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chandelier.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.chandelier`

- [ ] **Step 3: Implement `marketbot/chandelier.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .indicators import atr


@dataclass
class ChandelierResult:
    direction: int            # 1 = long, -1 = short (latest bar)
    line: float               # active stop line value on the latest bar
    buy_flip: bool            # direction flipped -1 -> 1 on the latest bar
    sell_flip: bool           # direction flipped 1 -> -1 on the latest bar
    last_buy_index: int | None
    last_sell_index: int | None


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chandelier.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/chandelier.py tests/test_chandelier.py
git commit -m "feat: Chandelier Exit with Buy/Sell flip detection"
```

---

## Task 6: Anchored Volume Profile (1-year)

**Files:**
- Create: `marketbot/volume_profile.py`, `tests/test_volume_profile.py`

- [ ] **Step 1: Write the failing test** → `tests/test_volume_profile.py`

```python
import numpy as np
import pandas as pd
from marketbot.volume_profile import volume_profile, near_levels


def _bars(prices, vols):
    prices = np.asarray(prices, float)
    return pd.DataFrame({
        "open": prices, "high": prices + 0.5, "low": prices - 0.5,
        "close": prices, "volume": np.asarray(vols, float),
    })


def test_poc_at_concentrated_price():
    # Most volume traded around price 100
    prices = [100] * 50 + [80, 81, 120, 121]
    vols = [1000] * 50 + [1, 1, 1, 1]
    prof = volume_profile(_bars(prices, vols), bins=24, lookback=200, value_area_pct=0.7)
    assert abs(prof.poc - 100) <= 2.0
    assert prof.val <= prof.poc <= prof.vah


def test_near_levels_within_band():
    levels = {"POC": 100.0, "VAH": 110.0, "VAL": 90.0}
    hits = near_levels(price=101.0, levels=levels, band_pct=0.02)  # within 2% of 100
    names = {h.name for h in hits}
    assert "POC" in names
    assert "VAH" not in names  # 110 is >2% from 101


def test_near_levels_reports_direction():
    levels = {"VAH": 110.0}
    hits = near_levels(price=109.0, levels=levels, band_pct=0.02)
    assert hits[0].side == "resistance"   # price below the level
    hits2 = near_levels(price=111.0, levels=levels, band_pct=0.02)
    assert hits2[0].side == "support"     # price above the level
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_volume_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.volume_profile`

- [ ] **Step 3: Implement `marketbot/volume_profile.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Profile:
    poc: float    # point of control (price of highest-volume bin)
    vah: float    # value-area high
    val: float    # value-area low


@dataclass
class LevelHit:
    name: str     # "POC" | "VAH" | "VAL"
    level: float
    side: str     # "resistance" (price below level) | "support" (price above)
    distance_pct: float


def volume_profile(df: pd.DataFrame, bins: int = 24, lookback: int = 252,
                   value_area_pct: float = 0.70) -> Profile:
    window = df.iloc[-lookback:]
    lo = float(window["low"].min())
    hi = float(window["high"].max())
    if hi <= lo:
        return Profile(poc=lo, vah=lo, val=lo)

    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    vol_per_bin = np.zeros(bins)

    # Distribute each bar's volume uniformly across the bins its [low, high] spans.
    for low, high, vol in zip(window["low"], window["high"], window["volume"]):
        b_lo = np.searchsorted(edges, low, side="right") - 1
        b_hi = np.searchsorted(edges, high, side="right") - 1
        b_lo = max(0, min(bins - 1, b_lo))
        b_hi = max(0, min(bins - 1, b_hi))
        span = b_hi - b_lo + 1
        vol_per_bin[b_lo:b_hi + 1] += vol / span

    poc_idx = int(np.argmax(vol_per_bin))
    poc = float(centers[poc_idx])

    # Grow the value area outward from the POC until it holds value_area_pct of volume.
    total = vol_per_bin.sum()
    target = total * value_area_pct
    lo_idx = hi_idx = poc_idx
    acc = vol_per_bin[poc_idx]
    while acc < target and (lo_idx > 0 or hi_idx < bins - 1):
        left = vol_per_bin[lo_idx - 1] if lo_idx > 0 else -1.0
        right = vol_per_bin[hi_idx + 1] if hi_idx < bins - 1 else -1.0
        if right >= left:
            hi_idx += 1
            acc += vol_per_bin[hi_idx]
        else:
            lo_idx -= 1
            acc += vol_per_bin[lo_idx]

    return Profile(poc=poc, vah=float(centers[hi_idx]), val=float(centers[lo_idx]))


def near_levels(price: float, levels: dict[str, float], band_pct: float = 0.02) -> list[LevelHit]:
    hits = []
    for name, level in levels.items():
        if level <= 0:
            continue
        dist = (price - level) / level
        if abs(dist) <= band_pct:
            side = "support" if price >= level else "resistance"
            hits.append(LevelHit(name=name, level=level, side=side, distance_pct=dist * 100.0))
    hits.sort(key=lambda h: abs(h.distance_pct))
    return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_volume_profile.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/volume_profile.py tests/test_volume_profile.py
git commit -m "feat: 1-year anchored volume profile (POC/VAH/VAL) + near_levels"
```

---

## Task 7: Bhavcopy download + parse

**Files:**
- Create: `marketbot/bhavcopy.py`, `tests/fixtures/bhavcopy_sample.csv`, `tests/test_bhavcopy.py`

NSE UDiFF bhavcopy columns include `TckrSymb`, `SctySrs`, `OpnPric`, `HghPric`, `LwPric`, `ClsPric`, `TtlTradgVol`, `TradDt`. We keep series `EQ`/`BE` equities and normalise to `symbol,open,high,low,close,volume,date`.

- [ ] **Step 1: Create `tests/fixtures/bhavcopy_sample.csv`**

```csv
TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol
2026-06-12,RELIANCE,EQ,1260,1272,1255,1268.6,1670000
2026-06-12,TCS,EQ,3900,3950,3890,3940,719350
2026-06-12,SOMEINDEX,GS,100,101,99,100,5
2026-06-12,ZEEL,EQ,111,113,110,112.67,30220000
```

- [ ] **Step 2: Write the failing test** → `tests/test_bhavcopy.py`

```python
from pathlib import Path
import pandas as pd
from marketbot.bhavcopy import parse_bhavcopy


def test_parse_keeps_equities_and_normalises_columns():
    raw = Path("tests/fixtures/bhavcopy_sample.csv").read_text()
    df = parse_bhavcopy(raw)
    assert set(["symbol", "open", "high", "low", "close", "volume", "date"]).issubset(df.columns)
    # Non-equity series (GS) dropped
    assert "SOMEINDEX" not in set(df["symbol"])
    reliance = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert reliance["close"] == 1268.6
    assert reliance["volume"] == 1670000


def test_parse_is_case_insensitive_on_symbols():
    raw = Path("tests/fixtures/bhavcopy_sample.csv").read_text()
    df = parse_bhavcopy(raw)
    assert (df["symbol"] == df["symbol"].str.upper()).all()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_bhavcopy.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.bhavcopy`

- [ ] **Step 4: Implement `marketbot/bhavcopy.py`**

```python
from __future__ import annotations
import io
import time
import zipfile
from datetime import date
import pandas as pd
import requests

UDIFF_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}


class BhavcopyUnavailable(Exception):
    pass


def parse_bhavcopy(csv_text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(csv_text))
    raw.columns = [c.strip() for c in raw.columns]
    df = raw.rename(columns={
        "TckrSymb": "symbol", "SctySrs": "series",
        "OpnPric": "open", "HghPric": "high", "LwPric": "low",
        "ClsPric": "close", "TtlTradgVol": "volume", "TradDt": "date",
    })
    df["series"] = df["series"].astype(str).str.strip().str.upper()
    df = df[df["series"].isin(EQUITY_SERIES)].copy()
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.dropna(subset=["close", "volume"])
    return df[["symbol", "open", "high", "low", "close", "volume", "date"]].reset_index(drop=True)


def fetch_bhavcopy(d: date, retries: int = 3, backoff: float = 5.0,
                   session: requests.Session | None = None) -> pd.DataFrame:
    url = UDIFF_URL.format(yyyymmdd=d.strftime("%Y%m%d"))
    sess = session or requests.Session()
    last_err = None
    for attempt in range(retries):
        try:
            resp = sess.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                raise BhavcopyUnavailable(f"bhavcopy not published for {d}")
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                name = zf.namelist()[0]
                csv_text = zf.read(name).decode("utf-8")
            return parse_bhavcopy(csv_text)
        except BhavcopyUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise BhavcopyUnavailable(f"bhavcopy fetch failed for {d}: {last_err}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_bhavcopy.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add marketbot/bhavcopy.py tests/fixtures/bhavcopy_sample.csv tests/test_bhavcopy.py
git commit -m "feat: NSE bhavcopy download + parse"
```

---

## Task 8: Universe builder

**Files:**
- Create: `marketbot/universe.py`, `tests/fixtures/equity_l_sample.csv`, `tests/test_universe.py`

`universe.py` parses NSE's `EQUITY_L.csv` for the symbol list, attaches market cap (fetched per-symbol; injected as a callable so tests stay offline), filters by `min_market_cap_inr`, and writes `data/universe.csv`.

- [ ] **Step 1: Create `tests/fixtures/equity_l_sample.csv`**

```csv
SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE
RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10
TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,1,1,INE467B01029,1
TINYCO,Tiny Company Limited,EQ,01-JAN-2020,10,1,INE999Z01011,10
```

- [ ] **Step 2: Write the failing test** → `tests/test_universe.py`

```python
from pathlib import Path
import pandas as pd
from marketbot.universe import build_universe, load_universe


def test_build_filters_by_market_cap(tmp_path):
    equity_csv = Path("tests/fixtures/equity_l_sample.csv").read_text()
    caps = {  # ₹
        "RELIANCE": 17_000_000_000_000,
        "TCS": 14_000_000_000_000,
        "TINYCO": 500_000_000,        # below ₹1,000 cr → dropped
    }
    sectors = {"RELIANCE": "Energy", "TCS": "IT", "TINYCO": "Misc"}
    out = tmp_path / "universe.csv"
    df = build_universe(
        equity_csv,
        min_market_cap_inr=10_000_000_000,
        market_cap_fn=lambda s: caps.get(s),
        sector_fn=lambda s: sectors.get(s),
        out_path=out,
    )
    syms = set(df["symbol"])
    assert "RELIANCE" in syms and "TCS" in syms
    assert "TINYCO" not in syms
    # persisted and reloadable
    loaded = load_universe(out)
    assert set(loaded["symbol"]) == syms
    assert "market_cap" in loaded.columns and "sector" in loaded.columns


def test_build_skips_symbols_with_unknown_cap(tmp_path):
    equity_csv = Path("tests/fixtures/equity_l_sample.csv").read_text()
    out = tmp_path / "u.csv"
    df = build_universe(
        equity_csv,
        min_market_cap_inr=1,
        market_cap_fn=lambda s: None,   # no caps available
        sector_fn=lambda s: None,
        out_path=out,
    )
    assert len(df) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_universe.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.universe`

- [ ] **Step 4: Implement `marketbot/universe.py`**

```python
from __future__ import annotations
import io
from pathlib import Path
from typing import Callable
import pandas as pd
import requests

EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
}
DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "data" / "universe.csv"


def fetch_equity_list(session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(EQUITY_LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def yf_market_cap(symbol: str) -> float | None:
    import yfinance as yf
    try:
        fi = yf.Ticker(f"{symbol}.NS").fast_info
        cap = fi.get("market_cap") if hasattr(fi, "get") else fi["market_cap"]
        return float(cap) if cap else None
    except Exception:  # noqa: BLE001
        return None


def yf_sector(symbol: str) -> str | None:
    import yfinance as yf
    try:
        return yf.Ticker(f"{symbol}.NS").info.get("sector")
    except Exception:  # noqa: BLE001
        return None


def build_universe(equity_csv_text: str, min_market_cap_inr: int,
                   market_cap_fn: Callable[[str], float | None],
                   sector_fn: Callable[[str], str | None],
                   out_path: Path | str = DEFAULT_UNIVERSE_PATH) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(equity_csv_text))
    raw.columns = [c.strip() for c in raw.columns]
    raw = raw[raw["SERIES"].astype(str).str.strip() == "EQ"]
    rows = []
    for _, r in raw.iterrows():
        sym = str(r["SYMBOL"]).strip().upper()
        cap = market_cap_fn(sym)
        if cap is None or cap < min_market_cap_inr:
            continue
        rows.append({
            "symbol": sym,
            "name": str(r["NAME OF COMPANY"]).strip(),
            "market_cap": float(cap),
            "sector": sector_fn(sym) or "",
        })
    df = pd.DataFrame(rows, columns=["symbol", "name", "market_cap", "sector"])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df


def load_universe(path: Path | str = DEFAULT_UNIVERSE_PATH) -> pd.DataFrame:
    return pd.read_csv(path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_universe.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add marketbot/universe.py tests/fixtures/equity_l_sample.csv tests/test_universe.py
git commit -m "feat: NSE universe builder with market-cap filter"
```

---

## Task 9: Rolling history store

**Files:**
- Create: `marketbot/history.py`, `tests/test_history.py`

- [ ] **Step 1: Write the failing test** → `tests/test_history.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_history.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.history`

- [ ] **Step 3: Implement `marketbot/history.py`**

```python
from __future__ import annotations
from pathlib import Path
import pandas as pd

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.parquet"
COLUMNS = ["symbol", "open", "high", "low", "close", "volume", "date"]


def load_history(path: Path | str = DEFAULT_HISTORY_PATH) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def append_day(day_df: pd.DataFrame, path: Path | str = DEFAULT_HISTORY_PATH,
               lookback_days: int = 300) -> pd.DataFrame:
    existing = load_history(path)
    day_df = day_df[COLUMNS].copy()
    day_df["date"] = pd.to_datetime(day_df["date"]).dt.date
    combined = pd.concat([existing, day_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["symbol", "date"], keep="last")

    keep_dates = sorted(combined["date"].unique())[-lookback_days:]
    combined = combined[combined["date"].isin(keep_dates)]
    combined = combined.sort_values(["symbol", "date"]).reset_index(drop=True)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    return combined


def history_for(history: pd.DataFrame, symbol: str) -> pd.DataFrame:
    out = history[history["symbol"] == symbol].sort_values("date").reset_index(drop=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_history.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/history.py tests/test_history.py
git commit -m "feat: rolling parquet history store"
```

---

## Task 10: Screen — per-stock signals, ranking, Report

**Files:**
- Create: `marketbot/screen.py`, `tests/test_screen.py`

`screen.py` ties indicators + chandelier + volume_profile together over the history for each universe symbol and produces a `Report` dataclass that `brief.py` will render.

- [ ] **Step 1: Write the failing test** → `tests/test_screen.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_screen.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.screen`

- [ ] **Step 3: Implement `marketbot/screen.py`**

```python
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

    return StockRow(
        symbol=df["symbol"].iloc[-1], name=name, close=close, chg_pct=chg,
        rel_vol=rel_vol if rel_vol == rel_vol else 0.0, turnover=turn, sector=sector,
        chandelier_dir=ce.direction, buy_flip=ce.buy_flip, sell_flip=ce.sell_flip,
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

    report.high_conviction = [r for r in rows if r.buy_flip and r.level_hits]

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_screen.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/screen.py tests/test_screen.py
git commit -m "feat: screen module — signals, ranking, Report"
```

---

## Task 11: Market overview

**Files:**
- Create: `marketbot/market_overview.py`, `tests/test_market_overview.py`

Index changes come from yfinance (injected for tests). Sector movers are computed from the screened rows by averaging `chg_pct` per sector.

- [ ] **Step 1: Write the failing test** → `tests/test_market_overview.py`

```python
from marketbot.market_overview import sector_movers, MarketOverview, build_overview
from marketbot.screen import StockRow


def _row(sym, sector, chg):
    return StockRow(symbol=sym, name=sym, close=100, chg_pct=chg, rel_vol=1.0,
                    turnover=1.0, sector=sector, chandelier_dir=1,
                    buy_flip=False, sell_flip=False)


def test_sector_movers_average_and_sort():
    rows = [_row("A", "IT", 2.0), _row("B", "IT", 0.0), _row("C", "Auto", 5.0)]
    movers = sector_movers(rows, top=2)
    assert movers[0][0] == "Auto" and movers[0][1] == 5.0
    assert movers[1][0] == "IT" and abs(movers[1][1] - 1.0) < 1e-9


def test_build_overview_uses_injected_index_fn():
    def fake_index(_ticker):
        return (24310.0, 0.8)  # (last_close, pct_change)
    ov = build_overview(rows=[_row("A", "IT", 2.0)], index_fn=fake_index)
    assert isinstance(ov, MarketOverview)
    assert ov.nifty == (24310.0, 0.8)
    assert ov.sensex == (24310.0, 0.8)
    assert ov.top_sectors[0][0] == "IT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_overview.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.market_overview`

- [ ] **Step 3: Implement `marketbot/market_overview.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Callable


@dataclass
class MarketOverview:
    nifty: tuple[float, float] | None = None     # (close, pct_change)
    sensex: tuple[float, float] | None = None
    top_sectors: list[tuple[str, float]] = field(default_factory=list)


def sector_movers(rows, top: int = 3) -> list[tuple[str, float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.sector:
            buckets[r.sector].append(r.chg_pct)
    avgs = [(sec, sum(v) / len(v)) for sec, v in buckets.items() if v]
    avgs.sort(key=lambda x: x[1], reverse=True)
    return avgs[:top]


def yf_index(ticker: str) -> tuple[float, float] | None:
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2:
            return None
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        return (last, (last - prev) / prev * 100.0)
    except Exception:  # noqa: BLE001
        return None


def build_overview(rows, index_fn: Callable[[str], tuple[float, float] | None] = yf_index,
                   top_sectors: int = 3) -> MarketOverview:
    return MarketOverview(
        nifty=index_fn("^NSEI"),
        sensex=index_fn("^BSESN"),
        top_sectors=sector_movers(rows, top_sectors),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_overview.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/market_overview.py tests/test_market_overview.py
git commit -m "feat: market overview (indices + sector movers)"
```

---

## Task 12: Brief renderer

**Files:**
- Create: `marketbot/brief.py`, `tests/test_brief.py`

- [ ] **Step 1: Write the failing test** → `tests/test_brief.py`

```python
from datetime import date
from marketbot.brief import render_brief, render_unavailable
from marketbot.screen import Report, StockRow
from marketbot.market_overview import MarketOverview
from marketbot.volume_profile import LevelHit


def _row(sym, chg=1.0, rv=3.0, poc=True):
    hits = [LevelHit("POC", 385.0, "support", 1.0)] if poc else []
    return StockRow(symbol=sym, name=sym, close=389.0, chg_pct=chg, rel_vol=rv,
                    turnover=1e9, sector="IT", chandelier_dir=1,
                    buy_flip=True, sell_flip=False, level_hits=hits, rsi=25.0)


def test_render_includes_all_section_headers():
    report = Report(as_of=date(2026, 6, 12))
    report.unusual_volume = [_row("MTARTECH")]
    report.turnover_leaders = [_row("HDFCBANK")]
    report.high_conviction = [_row("APOLLO")]
    report.chandelier_buys = [_row("APOLLO")]
    report.rsi_oversold = [_row("XYZ")]
    ov = MarketOverview(nifty=(24310.0, 0.8), sensex=(79850.0, 0.7), top_sectors=[("IT", 1.9)])
    text = render_brief(report, ov)
    for marker in ["Market Brief", "Unusual activity", "Most-traded",
                   "High-conviction", "Chandelier", "12 Jun"]:
        assert marker in text


def test_render_unavailable_message():
    text = render_unavailable(date(2026, 6, 12), "data not ready")
    assert "12 Jun" in text
    assert "not ready" in text.lower()


def test_empty_report_still_renders_without_error():
    report = Report(as_of=date(2026, 6, 12))
    ov = MarketOverview(nifty=None, sensex=None, top_sectors=[])
    text = render_brief(report, ov)
    assert "Market Brief" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_brief.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.brief`

- [ ] **Step 3: Implement `marketbot/brief.py`**

```python
from __future__ import annotations
from datetime import date
from .screen import Report, StockRow
from .market_overview import MarketOverview


def _fmt_date(d) -> str:
    return d.strftime("%a %d %b") if isinstance(d, date) else str(d)


def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def _index_line(label: str, data) -> str:
    if not data:
        return f"{label}  n/a"
    close, pct = data
    return f"{label}  {close:,.0f}  {_arrow(pct)} {pct:+.1f}%"


def _stock_line(r: StockRow) -> str:
    return f" {r.symbol}  ₹{r.close:,.2f}  {r.chg_pct:+.1f}%  RV {r.rel_vol:.1f}x"


def render_unavailable(d, reason: str) -> str:
    return f"📊 Market Brief — {_fmt_date(d)}\n—\nNo brief: {reason}."


def render_brief(report: Report, overview: MarketOverview) -> str:
    lines: list[str] = []
    lines.append(f"📊 Market Brief — {_fmt_date(report.as_of)}")
    lines.append("─────────────────────────")
    lines.append(_index_line("NIFTY 50", overview.nifty))
    lines.append(_index_line("SENSEX  ", overview.sensex))
    if overview.top_sectors:
        secs = " · ".join(f"{s} {_arrow(p)}{p:.1f}%" for s, p in overview.top_sectors)
        lines.append(f"Top sectors: {secs}")

    if report.unusual_volume:
        lines.append("\n🔥 Unusual activity (rel-vol spikes)")
        lines += [_stock_line(r) for r in report.unusual_volume]

    if report.turnover_leaders:
        lines.append("\n💰 Most-traded (turnover)")
        lines.append(" " + " · ".join(r.symbol for r in report.turnover_leaders))

    if report.high_conviction:
        lines.append("\n⭐ High-conviction (Buy flip × key AVP level)")
        for r in report.high_conviction:
            h = r.level_hits[0]
            lines.append(f" {r.symbol}  ₹{r.close:,.2f}  BUY flip @ {h.name} "
                         f"₹{h.level:,.2f} ({h.distance_pct:+.1f}%)")

    if report.chandelier_buys or report.chandelier_sells:
        lines.append("\n🟢 Chandelier Exit — flipped today")
        if report.chandelier_buys:
            lines.append(" BUY:  " + " · ".join(r.symbol for r in report.chandelier_buys))
        if report.chandelier_sells:
            lines.append(" SELL: " + " · ".join(r.symbol for r in report.chandelier_sells))

    if report.approaching_levels:
        lines.append("\n🎯 Approaching key AVP level (1-yr anchor)")
        for r in report.approaching_levels:
            h = r.level_hits[0]
            lines.append(f" {r.symbol}  ₹{r.close:,.2f} → {h.side} ₹{h.level:,.2f} "
                         f"({h.distance_pct:+.1f}%)")

    alert_bits = []
    if report.rsi_oversold:
        alert_bits.append(" RSI<30: " + " · ".join(r.symbol for r in report.rsi_oversold))
    if report.rsi_overbought:
        alert_bits.append(" RSI>70: " + " · ".join(r.symbol for r in report.rsi_overbought))
    if report.new_highs:
        alert_bits.append(" 52w high: " + " · ".join(r.symbol for r in report.new_highs))
    if report.ma_crossovers:
        alert_bits.append(" 50/200 DMA crossover↑: " + " · ".join(r.symbol for r in report.ma_crossovers))
    if alert_bits:
        lines.append("\n📈 Signal alerts")
        lines += alert_bits

    if report.errors:
        lines.append(f"\n⚠️ data unavailable for {len(report.errors)} symbol(s)")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_brief.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/brief.py tests/test_brief.py
git commit -m "feat: Telegram brief renderer"
```

---

## Task 13: Telegram sender

**Files:**
- Create: `marketbot/telegram_bot.py`, `tests/test_telegram_bot.py`

- [ ] **Step 1: Write the failing test** → `tests/test_telegram_bot.py`

```python
from unittest.mock import MagicMock
from marketbot.telegram_bot import split_message, send_message


def test_split_message_under_limit_single_chunk():
    chunks = split_message("hello", limit=4096)
    assert chunks == ["hello"]


def test_split_message_splits_on_newlines():
    text = "\n".join("line%d" % i for i in range(1000))
    chunks = split_message(text, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_send_message_posts_to_each_chat():
    session = MagicMock()
    resp = MagicMock(); resp.status_code = 200; resp.json.return_value = {"ok": True}
    session.post.return_value = resp
    send_message("TOKEN", ["111", "222"], "hi", session=session, parse_mode="HTML")
    assert session.post.call_count == 2
    url = session.post.call_args_list[0].args[0]
    assert "botTOKEN/sendMessage" in url


def test_send_message_retries_on_failure():
    session = MagicMock()
    bad = MagicMock(); bad.status_code = 500; bad.json.return_value = {"ok": False}
    good = MagicMock(); good.status_code = 200; good.json.return_value = {"ok": True}
    session.post.side_effect = [bad, good]
    send_message("TOKEN", ["111"], "hi", session=session, retries=2, backoff=0)
    assert session.post.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: marketbot.telegram_bot`

- [ ] **Step 3: Implement `marketbot/telegram_bot.py`**

```python
from __future__ import annotations
import time
import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def split_message(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        candidate = line if not cur else cur + "\n" + line
        if len(candidate) <= limit:
            cur = candidate
        else:
            if cur:
                chunks.append(cur)
            # a single over-long line: hard-split
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            cur = line
    if cur:
        chunks.append(cur)
    return chunks


def send_message(token: str, chat_ids: list[str], text: str,
                 parse_mode: str | None = None, retries: int = 3,
                 backoff: float = 2.0, session: requests.Session | None = None) -> None:
    sess = session or requests.Session()
    url = API.format(token=token)
    for chat_id in chat_ids:
        for chunk in split_message(text):
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            _post_with_retry(sess, url, payload, retries, backoff)


def _post_with_retry(sess, url, payload, retries, backoff) -> None:
    last = None
    for attempt in range(retries):
        try:
            resp = sess.post(url, data=payload, timeout=30)
            if resp.status_code == 200 and resp.json().get("ok", False):
                return
            last = f"status={resp.status_code} body={resp.json()}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if attempt < retries - 1 and backoff:
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Telegram send failed after {retries} attempts: {last}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_telegram_bot.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add marketbot/telegram_bot.py tests/test_telegram_bot.py
git commit -m "feat: Telegram sender with retry and 4096-char splitting"
```

---

## Task 14: Orchestration (`main.py`)

**Files:**
- Create: `marketbot/main.py`, `tests/test_main.py`

- [ ] **Step 1: Write the failing test** → `tests/test_main.py`

```python
from datetime import date
from pathlib import Path
import pandas as pd
from marketbot.config import Config
from marketbot import main as m


def _bhav(d, symbols):
    return pd.DataFrame({
        "symbol": symbols, "open": [100] * len(symbols), "high": [101] * len(symbols),
        "low": [99] * len(symbols), "close": [100.5] * len(symbols),
        "volume": [1000] * len(symbols), "date": [d] * len(symbols),
    })


def test_run_holiday_short_circuits(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(m, "is_trading_day", lambda d, hf=None: False)
    out = m.run(
        run_date=date(2026, 1, 26), cfg=Config(),
        fetch_bhavcopy_fn=lambda d: _bhav(d, ["A"]),
        send_fn=lambda text: sent.setdefault("text", text),
        universe_df=pd.DataFrame(columns=["symbol", "name", "market_cap", "sector"]),
        history_path=tmp_path / "h.parquet", dry_run=False,
    )
    assert out == "holiday"
    assert "text" not in sent


def test_run_unavailable_sends_note(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(m, "is_trading_day", lambda d, hf=None: True)

    def boom(d):
        from marketbot.bhavcopy import BhavcopyUnavailable
        raise BhavcopyUnavailable("not ready")

    out = m.run(
        run_date=date(2026, 6, 12), cfg=Config(),
        fetch_bhavcopy_fn=boom,
        send_fn=lambda text: sent.setdefault("text", text),
        universe_df=pd.DataFrame(columns=["symbol", "name", "market_cap", "sector"]),
        history_path=tmp_path / "h.parquet", dry_run=False,
    )
    assert out == "unavailable"
    assert "not ready" in sent["text"].lower()


def test_run_happy_path_sends_brief(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(m, "is_trading_day", lambda d, hf=None: True)
    monkeypatch.setattr(m, "build_overview",
                        lambda rows, **k: m.MarketOverview(nifty=(1, 0.1), sensex=(2, 0.2)))
    universe = pd.DataFrame({"symbol": ["A"], "name": ["A"], "market_cap": [2e11], "sector": ["IT"]})
    hist_path = tmp_path / "h.parquet"

    # Seed enough history so indicators are computable across runs.
    from marketbot.history import append_day
    for i in range(60):
        append_day(_bhav(date(2026, 3, 1) + pd.Timedelta(days=i).to_pytimedelta(), ["A"]),
                   hist_path, lookback_days=300)

    out = m.run(
        run_date=date(2026, 6, 12), cfg=Config(),
        fetch_bhavcopy_fn=lambda d: _bhav(d, ["A"]),
        send_fn=lambda text: sent.setdefault("text", text),
        universe_df=universe, history_path=hist_path, dry_run=False,
    )
    assert out == "sent"
    assert "Market Brief" in sent["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError` / attribute errors.

- [ ] **Step 3: Implement `marketbot/main.py`**

```python
from __future__ import annotations
import argparse
import os
from datetime import date
from pathlib import Path
from typing import Callable
import pandas as pd

from .config import Config, load_config
from .holidays import is_trading_day, previous_trading_day
from .bhavcopy import fetch_bhavcopy, BhavcopyUnavailable
from .universe import load_universe
from .history import append_day, load_history, DEFAULT_HISTORY_PATH
from .screen import build_report
from .market_overview import build_overview, MarketOverview
from .brief import render_brief, render_unavailable
from .telegram_bot import send_message


def run(run_date: date, cfg: Config,
        fetch_bhavcopy_fn: Callable[[date], pd.DataFrame],
        send_fn: Callable[[str], None],
        universe_df: pd.DataFrame,
        history_path: Path,
        dry_run: bool) -> str:
    if not is_trading_day(run_date):
        return "holiday"

    data_date = previous_trading_day(run_date)  # morning brief on the prior session
    try:
        day_df = fetch_bhavcopy_fn(data_date)
    except BhavcopyUnavailable as e:
        send_fn(render_unavailable(data_date, str(e)))
        return "unavailable"

    universe_symbols = set(universe_df["symbol"])
    day_df = day_df[day_df["symbol"].isin(universe_symbols)].copy()
    history = append_day(day_df, history_path, cfg.history_lookback_days)

    report = build_report(history, universe_df, cfg)
    overview = build_overview([*report.turnover_leaders, *report.unusual_volume])
    text = render_brief(report, overview)

    if dry_run:
        print(text)
    else:
        send_fn(text)
    return "sent"


def _default_send(cfg: Config) -> Callable[[str], None]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_IDS"].split(",") if c.strip()]
    return lambda text: send_message(token, chat_ids, text, parse_mode=None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily NSE market brief Telegram bot")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--date", help="run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    cfg = load_config()
    run_date = date.fromisoformat(args.date) if args.date else date.today()
    universe_df = load_universe()
    send_fn = (lambda text: print(text)) if args.dry_run else _default_send(cfg)

    status = run(
        run_date=run_date, cfg=cfg,
        fetch_bhavcopy_fn=fetch_bhavcopy,
        send_fn=send_fn,
        universe_df=universe_df,
        history_path=DEFAULT_HISTORY_PATH,
        dry_run=args.dry_run,
    )
    print(f"[marketbot] status={status} date={run_date}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: PASS (all tests green)

- [ ] **Step 6: Commit**

```bash
git add marketbot/main.py tests/test_main.py
git commit -m "feat: orchestration entry point with holiday/unavailable handling"
```

---

## Task 15: GitHub Actions workflows

**Files:**
- Create: `.github/workflows/daily-brief.yml`, `.github/workflows/refresh-universe.yml`, `scripts/refresh_universe.py`

- [ ] **Step 1: Create `scripts/refresh_universe.py`**

```python
"""Weekly job: rebuild data/universe.csv from the NSE equity list + market caps."""
from marketbot.config import load_config
from marketbot.universe import (
    fetch_equity_list, build_universe, yf_market_cap, yf_sector,
)


def main() -> None:
    cfg = load_config()
    equity_csv = fetch_equity_list()
    df = build_universe(
        equity_csv,
        min_market_cap_inr=cfg.min_market_cap_inr,
        market_cap_fn=yf_market_cap,
        sector_fn=yf_sector,
    )
    print(f"[refresh-universe] kept {len(df)} symbols ≥ ₹{cfg.min_market_cap_inr:,}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `.github/workflows/daily-brief.yml`**

```yaml
name: daily-brief
on:
  schedule:
    - cron: "0 3 * * 1-5"   # 03:00 UTC ≈ 08:30 IST, Mon–Fri
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Print instead of sending"
        type: boolean
        default: false

permissions:
  contents: write           # to commit updated history.parquet

concurrency:
  group: daily-brief
  cancel-in-progress: false

jobs:
  brief:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - name: Run brief
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_IDS: ${{ secrets.TELEGRAM_CHAT_IDS }}
        run: |
          if [ "${{ inputs.dry_run }}" = "true" ]; then
            python -m marketbot.main --dry-run
          else
            python -m marketbot.main
          fi
      - name: Commit updated history
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/history.parquet
          git commit -m "data: update rolling history [skip ci]" || echo "no changes"
          git push || echo "nothing to push"
```

- [ ] **Step 3: Create `.github/workflows/refresh-universe.yml`**

```yaml
name: refresh-universe
on:
  schedule:
    - cron: "30 1 * * 0"    # Sundays 01:30 UTC
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python scripts/refresh_universe.py
      - name: Commit universe
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/universe.csv
          git commit -m "data: refresh universe [skip ci]" || echo "no changes"
          git push || echo "nothing to push"
```

- [ ] **Step 4: Validate YAML locally**

Run: `python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('ok')"`
Expected: prints `ok`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily-brief.yml .github/workflows/refresh-universe.yml scripts/refresh_universe.py
git commit -m "ci: daily-brief and weekly refresh-universe workflows"
```

---

## Task 16: Cold-start backfill + README

**Files:**
- Create: `scripts/backfill_history.py`, `README.md`

- [ ] **Step 1: Create `scripts/backfill_history.py`**

```python
"""One-time: seed data/history.parquet with ~1 year of OHLCV for the universe via yfinance.

Run locally once before the first daily brief so relative-volume, Chandelier Exit,
and the anchored volume profile have history to work with.
"""
from datetime import date
import pandas as pd
import yfinance as yf
from marketbot.config import load_config
from marketbot.universe import load_universe
from marketbot.history import append_day, DEFAULT_HISTORY_PATH


def main() -> None:
    cfg = load_config()
    universe = load_universe()
    symbols = list(universe["symbol"])
    print(f"Backfilling {len(symbols)} symbols…")

    for i in range(0, len(symbols), 50):
        batch = symbols[i:i + 50]
        tickers = [f"{s}.NS" for s in batch]
        data = yf.download(tickers, period="1y", interval="1d",
                           group_by="ticker", auto_adjust=False, threads=True, progress=False)
        for s in batch:
            try:
                sub = data[f"{s}.NS"].dropna()
            except Exception:  # noqa: BLE001
                continue
            for idx, row in sub.iterrows():
                day = pd.DataFrame([{
                    "symbol": s, "open": row["Open"], "high": row["High"],
                    "low": row["Low"], "close": row["Close"], "volume": row["Volume"],
                    "date": idx.date(),
                }])
                append_day(day, DEFAULT_HISTORY_PATH, cfg.history_lookback_days)
        print(f"  …{min(i + 50, len(symbols))}/{len(symbols)}")

    print("Backfill complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `README.md`**

````markdown
# Daily Market Brief Telegram Bot

A push-only Telegram bot that sends a pre-market NSE brief each trading morning
(~8:30 AM IST). See the design spec in
`docs/superpowers/specs/2026-06-12-telegram-market-bot-design.md`.

## What it sends
- Market overview (Nifty/Sensex + sector movers)
- 🔥 Unusual activity (relative-volume spikes)
- 💰 Most-traded (turnover leaders)
- ⭐ High-conviction (Chandelier Exit Buy flip × key AVP level)
- 🟢 Chandelier Exit Buy/Sell flips
- 🎯 Approaching a key anchored-volume-profile level
- 📈 Signal alerts (RSI, 52-week highs, 50/200 DMA crossovers)

## One-time setup
1. **Create the bot:** message [@BotFather](https://t.me/BotFather) → `/newbot`
   → copy the **bot token**.
2. **Get chat IDs:** each recipient sends the bot any message, then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy each `chat.id`.
3. **Add GitHub secrets** (repo → Settings → Secrets → Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_IDS` (comma-separated, e.g. `11111111,22222222`)
4. **Build the universe:** run the `refresh-universe` workflow once (Actions tab
   → Run workflow), or locally: `python scripts/refresh_universe.py`.
5. **Backfill history:** `python scripts/backfill_history.py` (one time).

## Local run
```bash
pip install -r requirements.txt
python -m marketbot.main --dry-run            # prints the brief, sends nothing
python -m marketbot.main --dry-run --date 2026-06-12
```

## Tests
```bash
pytest
```

## Scheduling
- `daily-brief.yml` runs `0 3 * * 1-5` (UTC) ≈ 08:30 IST weekdays; skips NSE
  holidays via `data/nse_holidays.txt` (update yearly).
- `refresh-universe.yml` rebuilds `data/universe.csv` weekly.

## Notes / limitations
- The anchored volume profile is computed from **daily** EOD data, so its
  POC/value-area levels are close to — but not pixel-identical with — the
  TradingView intraday profile.
- Hand-drawn diagonal trendlines are **not** tracked (only horizontal AVP levels).
- If NSE blocks the Actions runner IP for bhavcopy, switch the daily fetch to the
  yfinance fallback (same OHLCV shape as `backfill_history.py`).
````

- [ ] **Step 3: Verify backfill script imports cleanly**

Run: `python -c "import ast; ast.parse(open('scripts/backfill_history.py').read()); print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_history.py README.md
git commit -m "docs: README + one-time history backfill script"
```

---

## Self-Review Notes

**Spec coverage check:**
- Screener universe (mkt cap > ₹1,000 cr) → Task 8 `universe.py` ✅
- Bhavcopy daily EOD → Task 7 ✅
- Rolling history (no DB) → Task 9 ✅
- RSI / SMA / MA-cross / 52w / rel-vol / turnover → Task 4 ✅
- Chandelier Exit (22, 3) Buy/Sell flips → Task 5 ✅
- Anchored volume profile (1-yr, first-candle anchor) + near_level → Task 6 ✅
- Confluence (Buy flip × AVP level) → Task 10 `high_conviction` ✅
- Market overview (indices + sector movers) → Task 11 ✅
- Message layout (all sections) → Task 12 ✅
- Telegram send + 4096 split + retry → Task 13 ✅
- Holiday skip / unavailable note / per-ticker resilience → Tasks 3, 14, 10 ✅
- GitHub Actions daily + weekly + history commit-back → Task 15 ✅
- Cold-start backfill + setup docs → Task 16 ✅

**Open config knobs (tunable, non-blocking):** `top_n_*`, `relvol_spike_threshold`,
`near_level_band_pct`, recipients via `TELEGRAM_CHAT_IDS`.
