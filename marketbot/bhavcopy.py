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
