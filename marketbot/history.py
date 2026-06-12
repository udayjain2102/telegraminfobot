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
    combined = day_df.copy() if existing.empty else pd.concat([existing, day_df], ignore_index=True)
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
