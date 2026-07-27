from __future__ import annotations
from datetime import date
from .screen import Report, StockRow
from .market_overview import MarketOverview
from .config import Config
from .tradingview import TvScan, compute_risk_reward


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


def _exit_line(s) -> str:
    held = f"{s.days_held}d" if s.days_held else "today"
    return (f" {s.symbol}  ₹{s.exit_price:,.2f}  ({s.pct_move:+.1f}% from ₹{s.entry:,.2f}, "
            f"{held})  · {', '.join(s.reasons)}")


def render_tv_scan(scan: TvScan, when: str = "11:00–14:30 IST",
                   cfg: Config | None = None, sells: list | None = None) -> str:
    """Render the live intraday TradingView momentum scan with per-BUY risk/reward."""
    cfg = cfg or Config()
    sells = sells or []
    lines: list[str] = []
    lines.append(f"📡 TradingView Momentum Scan — {_fmt_date(scan.as_of)} · {when}")
    lines.append("─────────────────────────")
    lines.append("NSE · MCap ₹10B–₹200B · Heikin-Ashi new high · Top-15 turnover · ex-IPO<12m")

    if sells:
        lines.append("\n🔴 SELL / EXIT (held positions)")
        lines += [_exit_line(s) for s in sells]

    if not scan.universe:
        if not sells:
            lines.append("\nNo stocks at a 1-month high in the universe right now.")
        return "\n".join(lines)

    if scan.buys:
        lines.append("\n🟢 BUY (volume-confirmed ≥ 1.5× rel-vol)")
        for r in scan.buys:
            rr = compute_risk_reward(r.close, r.atr, cfg)
            cap = " ·cap7%" if rr.capped else ""
            tgts = "  ".join(
                f"{t.r_multiple:.0f}R→₹{t.price:,.2f} ({t.gain_pct:+.1f}%)"
                for t in rr.targets
            )
            lines.append(f" {r.symbol}  ₹{r.close:,.2f}  {r.change_pct:+.1f}%  RV {r.rel_vol:.1f}x")
            lines.append(f"   Entry ₹{rr.entry:,.2f} · Stop ₹{rr.stop:,.2f} "
                         f"(−{rr.risk_pct*100:.1f}%{cap}) · Risk ₹{rr.risk_per_share:,.2f}/sh")
            lines.append(f"   R:R  {tgts}")
            lines.append(f"   Size {cfg.position_risk_pct*100:.0f}% risk → {rr.shares_per_lakh} sh/₹1L "
                         f"· Horizon {cfg.hold_horizon}")
    else:
        lines.append("\n🟢 BUY — none volume-confirmed yet")

    lines.append("\n⭐ Screener universe (Top-15 turnover @ HA new high)")
    fresh_buys = {id(b) for b in scan.buys}
    for i, r in enumerate(scan.universe, 1):
        if id(r) in fresh_buys:
            flag = " ✅"
        elif r.buy:
            flag = " ·sent"          # volume-confirmed but already alerted earlier today
        else:
            flag = ""
        lines.append(f" {i:>2}. {r.symbol}  ₹{r.close:,.2f}  {r.change_pct:+.1f}%  "
                     f"RV {r.rel_vol:.1f}x{flag}")

    lines.append("\nℹ️ Intraday snapshot; trend/POC confirmation in the EOD brief.")
    return "\n".join(lines)


def render_brief(report: Report, overview: MarketOverview, sells: list | None = None) -> str:
    lines: list[str] = []
    sells = sells or []
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
        lines.append("\n⭐ Momentum BUY (20d high × Supertrend flip × >POC × vol)")
        for r in report.high_conviction:
            lines.append(f" {r.symbol}  ₹{r.close:,.2f}  {r.chg_pct:+.1f}%  "
                         f"RV {r.rel_vol:.1f}x  · 20d high · BUY flip · >POC")

    if sells:
        lines.append("\n🔴 SELL / EXIT (held positions)")
        lines += [_exit_line(s) for s in sells]

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
