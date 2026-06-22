"""Open-position state for the BUY→SELL lifecycle.

A symbol is either flat or open. A BUY opens a position (recording entry, stop,
date and which surface fired it); a SELL closes it. Persisting this lets the
intraday scan and the EOD brief share one watchlist, suppress BUYs on names
already held, and fire exits against held positions.

This single store replaces the older per-day dedup: a held name is suppressed
until it actually exits, not merely until the next day.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

DEFAULT_POSITIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "positions.json"


@dataclass
class Position:
    symbol: str
    entry: float
    stop: float
    entry_date: str          # ISO date
    source: str              # "tv" (intraday) or "eod"


def load_positions(path: Path | str = DEFAULT_POSITIONS_PATH) -> dict[str, Position]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, Position] = {}
    for sym, d in raw.items():
        try:
            out[sym] = Position(symbol=sym, entry=float(d["entry"]), stop=float(d["stop"]),
                                entry_date=str(d["entry_date"]), source=str(d.get("source", "")))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def save_positions(positions: dict[str, Position],
                   path: Path | str = DEFAULT_POSITIONS_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {sym: {k: v for k, v in asdict(pos).items() if k != "symbol"}
            for sym, pos in sorted(positions.items())}
    p.write_text(json.dumps(body, indent=1))


def open_position(positions: dict[str, Position], symbol: str, entry: float,
                  stop: float, day: date, source: str) -> bool:
    """Open ``symbol`` if flat. Returns True if a new position was opened."""
    if symbol in positions:
        return False
    positions[symbol] = Position(symbol=symbol, entry=entry, stop=stop,
                                 entry_date=day.isoformat(), source=source)
    return True


def close_position(positions: dict[str, Position], symbol: str) -> None:
    positions.pop(symbol, None)
