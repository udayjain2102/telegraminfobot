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
