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
