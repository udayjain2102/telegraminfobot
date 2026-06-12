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
