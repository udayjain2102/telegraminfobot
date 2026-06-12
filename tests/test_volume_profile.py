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
