from __future__ import annotations
from datetime import date
from .screen import Report, StockRow
from .market_overview import MarketOverview


def _fmt_date(d) -> str:
    return d.strftime("%a %d %b") if isinstance(d, date) else str(d)


def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def _index_line(label: str, data) -> str:
    if not data:
        return f"{label}  n/a"
    close, pct = data
    return f"{label}  {close:,.0f}  {_arrow(pct)} {pct:+.1f}%"


def _stock_line(r: StockRow) -> str:
    return f" {r.symbol}  ₹{r.close:,.2f}  {r.chg_pct:+.1f}%  RV {r.rel_vol:.1f}x"


def render_unavailable(d, reason: str) -> str:
    return f"📊 Market Brief — {_fmt_date(d)}\n—\nNo brief: {reason}."


def render_brief(report: Report, overview: MarketOverview) -> str:
    lines: list[str] = []
    lines.append(f"📊 Market Brief — {_fmt_date(report.as_of)}")
    lines.append("─────────────────────────")
    lines.append(_index_line("NIFTY 50", overview.nifty))
    lines.append(_index_line("SENSEX  ", overview.sensex))
    if overview.top_sectors:
        secs = " · ".join(f"{s} {_arrow(p)}{p:.1f}%" for s, p in overview.top_sectors)
        lines.append(f"Top sectors: {secs}")

    if report.unusual_volume:
        lines.append("\n🔥 Unusual activity (rel-vol spikes)")
        lines += [_stock_line(r) for r in report.unusual_volume]

    if report.turnover_leaders:
        lines.append("\n💰 Most-traded (turnover)")
        lines.append(" " + " · ".join(r.symbol for r in report.turnover_leaders))

    if report.high_conviction:
        lines.append("\n⭐ High-conviction (Buy flip × key AVP level)")
        for r in report.high_conviction:
            h = r.level_hits[0]
            lines.append(f" {r.symbol}  ₹{r.close:,.2f}  BUY flip @ {h.name} "
                         f"₹{h.level:,.2f} ({h.distance_pct:+.1f}%)")

    if report.chandelier_buys or report.chandelier_sells:
        lines.append("\n🟢 Chandelier Exit — flipped today")
        if report.chandelier_buys:
            lines.append(" BUY:  " + " · ".join(r.symbol for r in report.chandelier_buys))
        if report.chandelier_sells:
            lines.append(" SELL: " + " · ".join(r.symbol for r in report.chandelier_sells))

    if report.approaching_levels:
        lines.append("\n🎯 Approaching key AVP level (1-yr anchor)")
        for r in report.approaching_levels:
            h = r.level_hits[0]
            lines.append(f" {r.symbol}  ₹{r.close:,.2f} → {h.side} ₹{h.level:,.2f} "
                         f"({h.distance_pct:+.1f}%)")

    alert_bits = []
    if report.rsi_oversold:
        alert_bits.append(" RSI<30: " + " · ".join(r.symbol for r in report.rsi_oversold))
    if report.rsi_overbought:
        alert_bits.append(" RSI>70: " + " · ".join(r.symbol for r in report.rsi_overbought))
    if report.new_highs:
        alert_bits.append(" 52w high: " + " · ".join(r.symbol for r in report.new_highs))
    if report.ma_crossovers:
        alert_bits.append(" 50/200 DMA crossover↑: " + " · ".join(r.symbol for r in report.ma_crossovers))
    if alert_bits:
        lines.append("\n📈 Signal alerts")
        lines += alert_bits

    if report.errors:
        lines.append(f"\n⚠️ data unavailable for {len(report.errors)} symbol(s)")

    return "\n".join(lines)
