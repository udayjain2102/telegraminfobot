from __future__ import annotations
from dataclasses import dataclass, field, fields
from pathlib import Path
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass
class Config:
    min_market_cap_inr: int = 10_000_000_000
    max_market_cap_inr: int | None = None
    top_n_unusual: int = 8
    top_n_turnover: int = 15
    top_n_levels: int = 10
    relvol_lookback_days: int = 20
    relvol_spike_threshold: float = 2.0
    new_high_lookback_days: int = 20
    buy_volume_mult: float = 1.5
    min_listing_age_days: int = 365            # exclude stocks listed within the last 12 months

    # Risk/reward for BUY signals (strategy doc, Step 6)
    atr_stop_mult: float = 1.0                 # stop = entry - atr_stop_mult x ATR(14)
    max_risk_pct: float = 0.07                 # never risk more than 7% per trade
    rr_multiples: list[float] = field(default_factory=lambda: [1.0, 2.0, 3.0])
    position_risk_pct: float = 0.02            # risk 2% of capital per trade
    hold_horizon: str = "3-8 weeks (swing)"
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
