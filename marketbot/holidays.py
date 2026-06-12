from __future__ import annotations
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

DEFAULT_HOLIDAY_FILE = Path(__file__).resolve().parent.parent / "data" / "nse_holidays.txt"


@lru_cache(maxsize=8)
def _load_holidays(path: Path) -> frozenset[date]:
    lines = Path(path).read_text().splitlines()
    out = set()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(date.fromisoformat(line))
    return frozenset(out)


def is_trading_day(d: date, holiday_file: Path | str = DEFAULT_HOLIDAY_FILE) -> bool:
    if d.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return d not in _load_holidays(Path(holiday_file))


def previous_trading_day(d: date, holiday_file: Path | str = DEFAULT_HOLIDAY_FILE) -> date:
    cur = d - timedelta(days=1)
    while not is_trading_day(cur, holiday_file):
        cur -= timedelta(days=1)
    return cur
