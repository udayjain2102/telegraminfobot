from datetime import date
from pathlib import Path
import pandas as pd
from marketbot.config import Config
from marketbot import main as m


def _bhav(d, symbols):
    return pd.DataFrame({
        "symbol": symbols, "open": [100] * len(symbols), "high": [101] * len(symbols),
        "low": [99] * len(symbols), "close": [100.5] * len(symbols),
        "volume": [1000] * len(symbols), "date": [d] * len(symbols),
    })


def test_run_holiday_short_circuits(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(m, "is_trading_day", lambda d, hf=None: False)
    out = m.run(
        run_date=date(2026, 1, 26), cfg=Config(),
        fetch_bhavcopy_fn=lambda d: _bhav(d, ["A"]),
        send_fn=lambda text: sent.setdefault("text", text),
        universe_df=pd.DataFrame(columns=["symbol", "name", "market_cap", "sector"]),
        history_path=tmp_path / "h.parquet", dry_run=False,
    )
    assert out == "holiday"
    assert "text" not in sent


def test_run_unavailable_sends_note(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(m, "is_trading_day", lambda d, hf=None: True)

    def boom(d):
        from marketbot.bhavcopy import BhavcopyUnavailable
        raise BhavcopyUnavailable("not ready")

    out = m.run(
        run_date=date(2026, 6, 12), cfg=Config(),
        fetch_bhavcopy_fn=boom,
        send_fn=lambda text: sent.setdefault("text", text),
        universe_df=pd.DataFrame(columns=["symbol", "name", "market_cap", "sector"]),
        history_path=tmp_path / "h.parquet", dry_run=False,
    )
    assert out == "unavailable"
    assert "not ready" in sent["text"].lower()


def test_run_happy_path_sends_brief(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(m, "is_trading_day", lambda d, hf=None: True)
    monkeypatch.setattr(m, "build_overview",
                        lambda rows, **k: m.MarketOverview(nifty=(1, 0.1), sensex=(2, 0.2)))
    universe = pd.DataFrame({"symbol": ["A"], "name": ["A"], "market_cap": [2e11], "sector": ["IT"]})
    hist_path = tmp_path / "h.parquet"

    # Seed enough history so indicators are computable across runs.
    from marketbot.history import append_day
    for i in range(60):
        append_day(_bhav(date(2026, 3, 1) + pd.Timedelta(days=i).to_pytimedelta(), ["A"]),
                   hist_path, lookback_days=300)

    out = m.run(
        run_date=date(2026, 6, 12), cfg=Config(),
        fetch_bhavcopy_fn=lambda d: _bhav(d, ["A"]),
        send_fn=lambda text: sent.setdefault("text", text),
        universe_df=universe, history_path=hist_path, dry_run=False,
    )
    assert out == "sent"
    assert "Market Brief" in sent["text"]
