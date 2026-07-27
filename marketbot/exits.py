"""Exit-signal evaluation for held positions (strategy doc, Step 4 + Step 6 stop).

Pure logic: each surface (EOD brief / intraday scan) computes the trigger booleans
from its own data and calls ``evaluate_exit``. SELL fires when ANY trigger is true.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from .positions import Position


@dataclass
class ExitSignal:
    symbol: str
    entry: float
    exit_price: float
    pct_move: float
    days_held: int
    reasons: list[str] = field(default_factory=list)
    source: str = ""


def evaluate_exit(position: Position, exit_price: float, today: date, *,
                  chandelier_red: bool = False, below_poc: bool = False,
                  dropped_top15: bool = False) -> ExitSignal | None:
    """Return an ExitSignal if any exit trigger fires for ``position``, else None."""
    reasons: list[str] = []
    if exit_price <= position.stop:
        reasons.append("stop hit")
    if chandelier_red:
        reasons.append("Supertrend red (HA)")
    if below_poc:
        reasons.append("close < POC")
    if dropped_top15:
        reasons.append("left Top-15")
    if not reasons:
        return None

    entry = position.entry
    pct = (exit_price - entry) / entry * 100.0 if entry else 0.0
    try:
        held = (today - date.fromisoformat(position.entry_date)).days
    except ValueError:
        held = 0
    return ExitSignal(symbol=position.symbol, entry=entry, exit_price=exit_price,
                      pct_move=pct, days_held=held, reasons=reasons, source=position.source)
