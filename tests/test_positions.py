from datetime import date
from marketbot.positions import (
    Position, load_positions, save_positions, open_position, close_position,
)
from marketbot.exits import evaluate_exit


def test_open_and_persist_roundtrip(tmp_path):
    p = tmp_path / "positions.json"
    pos = {}
    assert open_position(pos, "PARAS", entry=100.0, stop=93.0,
                         day=date(2026, 6, 22), source="tv") is True
    assert open_position(pos, "PARAS", entry=999.0, stop=1.0,
                         day=date(2026, 6, 23), source="tv") is False  # already open
    save_positions(pos, p)
    loaded = load_positions(p)
    assert set(loaded) == {"PARAS"}
    assert loaded["PARAS"].entry == 100.0 and loaded["PARAS"].entry_date == "2026-06-22"


def test_close_removes_position(tmp_path):
    pos = {"X": Position("X", 10.0, 9.0, "2026-06-22", "eod")}
    close_position(pos, "X")
    assert "X" not in pos


def test_exit_fires_on_stop_hit():
    pos = Position("X", entry=100.0, stop=93.0, entry_date="2026-06-01", source="tv")
    sig = evaluate_exit(pos, exit_price=92.0, today=date(2026, 6, 22))
    assert sig is not None
    assert "stop hit" in sig.reasons
    assert round(sig.pct_move, 1) == -8.0
    assert sig.days_held == 21


def test_exit_fires_on_any_trigger_and_lists_reasons():
    pos = Position("X", entry=100.0, stop=80.0, entry_date="2026-06-20", source="eod")
    sig = evaluate_exit(pos, exit_price=110.0, today=date(2026, 6, 22),
                        chandelier_red=True, dropped_top15=True)
    assert sig is not None
    assert "Supertrend red (HA)" in sig.reasons and "left Top-15" in sig.reasons
    assert "stop hit" not in sig.reasons        # price 110 > stop 80
    assert round(sig.pct_move, 1) == 10.0


def test_no_exit_when_no_trigger():
    pos = Position("X", entry=100.0, stop=80.0, entry_date="2026-06-20", source="tv")
    assert evaluate_exit(pos, exit_price=105.0, today=date(2026, 6, 22)) is None


def test_chandelier_ha_detects_downtrend():
    import numpy as np, pandas as pd
    from marketbot.chandelier import chandelier_exit_ha
    # long uptrend then a sharp sustained drop → HA Chandelier should be short
    closes = list(range(50, 130)) + list(range(130, 60, -1))
    df = pd.DataFrame({"open": closes, "high": [c + 1 for c in closes],
                       "low": [c - 1 for c in closes], "close": closes})
    res = chandelier_exit_ha(df, length=22, mult=3.0)
    assert res.direction == -1
