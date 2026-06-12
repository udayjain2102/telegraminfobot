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
    print(f"Backfilling {len(symbols)} symbols...")

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
        print(f"  ...{min(i + 50, len(symbols))}/{len(symbols)}")

    print("Backfill complete.")


if __name__ == "__main__":
    main()
