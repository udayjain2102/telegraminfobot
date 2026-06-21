"""Per-day dedup state for the intraday TradingView scan.

The scan runs several times during the session (11:00–14:30 IST). Without state
each run would re-alert the same BUY. We persist the set of symbols already
alerted *today* in a small JSON file; symbols already sent are suppressed from
later runs. The state resets automatically when the date rolls over.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

DEFAULT_ALERTS_PATH = Path(__file__).resolve().parent.parent / "data" / "tv_alerts.json"


def _read(path: Path | str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def load_alerted(path: Path | str, day: date) -> set[str]:
    """Symbols already alerted on ``day`` (empty if the file is from another day)."""
    data = _read(path)
    if data.get("date") != day.isoformat():
        return set()
    return set(data.get("symbols", []))


def record_alerted(path: Path | str, day: date, symbols: list[str]) -> None:
    """Merge ``symbols`` into ``day``'s alerted set, resetting on a new day."""
    current = load_alerted(path, day)
    current.update(symbols)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"date": day.isoformat(), "symbols": sorted(current)}, indent=0))
