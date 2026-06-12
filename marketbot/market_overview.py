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
