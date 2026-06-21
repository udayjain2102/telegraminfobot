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
                   out_path: Path | str = DEFAULT_UNIVERSE_PATH,
                   max_market_cap_inr: int | None = None) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(equity_csv_text))
    raw.columns = [c.strip() for c in raw.columns]
    raw = raw[raw["SERIES"].astype(str).str.strip() == "EQ"]
    rows = []
    for _, r in raw.iterrows():
        sym = str(r["SYMBOL"]).strip().upper()
        cap = market_cap_fn(sym)
        if cap is None or cap < min_market_cap_inr:
            continue
        if max_market_cap_inr is not None and cap > max_market_cap_inr:
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
