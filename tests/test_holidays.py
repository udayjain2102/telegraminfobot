from datetime import date
from pathlib import Path
from marketbot.holidays import is_trading_day, previous_trading_day


def _holiday_file(tmp_path) -> Path:
    p = tmp_path / "h.txt"
    p.write_text("2026-01-26\n2026-08-15\n")
    return p


def test_weekend_is_not_trading_day(tmp_path):
    hf = _holiday_file(tmp_path)
    assert is_trading_day(date(2026, 6, 13), hf) is False  # Saturday
    assert is_trading_day(date(2026, 6, 14), hf) is False  # Sunday


def test_listed_holiday_is_not_trading_day(tmp_path):
    hf = _holiday_file(tmp_path)
    assert is_trading_day(date(2026, 1, 26), hf) is False


def test_normal_weekday_is_trading_day(tmp_path):
    hf = _holiday_file(tmp_path)
    assert is_trading_day(date(2026, 6, 12), hf) is True   # Friday


def test_previous_trading_day_skips_weekend(tmp_path):
    hf = _holiday_file(tmp_path)
    # Monday 2026-06-15 → previous trading day is Friday 2026-06-12
    assert previous_trading_day(date(2026, 6, 15), hf) == date(2026, 6, 12)
