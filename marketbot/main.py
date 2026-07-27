from __future__ import annotations
import argparse
import os
from datetime import date
from pathlib import Path
from typing import Callable
import pandas as pd

from .config import Config, load_config
from .holidays import is_trading_day, previous_trading_day
from .bhavcopy import fetch_bhavcopy, BhavcopyUnavailable
from .fallback import fetch_eod_yfinance
from .universe import load_universe
from .history import append_day, load_history, history_for, DEFAULT_HISTORY_PATH
from .indicators import atr as ind_atr
from .screen import build_report, evaluate_eod_exits
from .market_overview import build_overview, MarketOverview
from .brief import render_brief, render_unavailable, render_tv_scan
from .telegram_bot import send_message
from .tradingview import scan_momentum, evaluate_tv_exits, compute_risk_reward
from .positions import (
    load_positions, save_positions, open_position, close_position, DEFAULT_POSITIONS_PATH,
)


def run(run_date: date, cfg: Config,
        fetch_bhavcopy_fn: Callable[[date], pd.DataFrame],
        send_fn: Callable[[str], None],
        universe_df: pd.DataFrame,
        history_path: Path,
        dry_run: bool,
        fallback_fn: Callable[[date, list[str]], pd.DataFrame] | None = None,
        positions_path: Path | str = DEFAULT_POSITIONS_PATH) -> str:
    if not is_trading_day(run_date):
        return "holiday"

    universe_symbols = set(universe_df["symbol"])
    data_date = previous_trading_day(run_date)  # morning brief on the prior session
    try:
        day_df = fetch_bhavcopy_fn(data_date)
    except BhavcopyUnavailable as e:
        if fallback_fn is None:
            send_fn(render_unavailable(data_date, str(e)))
            return "unavailable"
        try:
            day_df = fallback_fn(data_date, sorted(universe_symbols))
        except BhavcopyUnavailable as e2:
            send_fn(render_unavailable(data_date, f"{e}; fallback failed: {e2}"))
            return "unavailable"

    day_df = day_df[day_df["symbol"].isin(universe_symbols)].copy()
    history = append_day(day_df, history_path, cfg.history_lookback_days)

    report = build_report(history, universe_df, cfg)
    overview = build_overview([*report.turnover_leaders, *report.unusual_volume])

    # Position lifecycle: exits on held names, then open fresh Momentum BUYs.
    positions = load_positions(positions_path)
    sells = evaluate_eod_exits(positions, history, report, cfg, today=data_date)
    for s in sells:
        close_position(positions, s.symbol)
    fresh_buys = [r for r in report.high_conviction if r.symbol not in positions]
    report.high_conviction = fresh_buys
    for r in fresh_buys:
        df = history_for(history, r.symbol)
        atr = float(ind_atr(df, 14).iloc[-1]) if len(df) >= 15 else 0.0
        rr = compute_risk_reward(r.close, atr, cfg)
        open_position(positions, r.symbol, r.close, rr.stop, data_date, "eod")

    text = render_brief(report, overview, sells=sells)
    if dry_run:
        print(text)
    else:
        send_fn(text)
        save_positions(positions, positions_path)
    return "sent"


def run_tv_scan(run_date: date, cfg: Config,
                send_fn: Callable[[str], None],
                dry_run: bool,
                scan_fn: Callable[[Config], object] = scan_momentum,
                positions_path: Path | str = DEFAULT_POSITIONS_PATH,
                history_fn=None) -> str:
    """Live intraday TradingView momentum scan with the BUY→SELL lifecycle.

    BUYs are suppressed for names already held (open positions); SELLs fire when a
    held name hits an exit trigger. On a dry run nothing is persisted.
    """
    if not is_trading_day(run_date):
        return "holiday"
    try:
        scan = scan_fn(cfg)
    except Exception as e:  # noqa: BLE001 — TV is unofficial; degrade gracefully
        send_fn(render_unavailable(run_date, f"TradingView scan failed: {e}"))
        return "unavailable"

    positions = load_positions(positions_path)
    sells = evaluate_tv_exits(positions, scan, cfg, history_fn=history_fn, today=run_date)
    for s in sells:
        close_position(positions, s.symbol)

    fresh = [b for b in scan.buys if b.symbol not in positions]
    scan.buys = fresh
    scan.as_of = run_date

    text = render_tv_scan(scan, cfg=cfg, sells=sells)
    if dry_run:
        print(text)
    else:
        send_fn(text)
        for b in fresh:
            rr = compute_risk_reward(b.close, b.atr, cfg)
            open_position(positions, b.symbol, b.close, rr.stop, run_date, "tv")
        save_positions(positions, positions_path)
    return "sent"


def _default_send(cfg: Config) -> Callable[[str], None]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_IDS"].split(",") if c.strip()]
    return lambda text: send_message(token, chat_ids, text, parse_mode=None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily NSE market brief Telegram bot")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--date", help="run date YYYY-MM-DD (default: today)")
    parser.add_argument("--source", choices=["bhavcopy", "tradingview"], default="bhavcopy",
                        help="bhavcopy = EOD brief (default); tradingview = live intraday scan")
    args = parser.parse_args()

    cfg = load_config()
    run_date = date.fromisoformat(args.date) if args.date else date.today()
    send_fn = (lambda text: print(text)) if args.dry_run else _default_send(cfg)

    if args.source == "tradingview":
        status = run_tv_scan(run_date=run_date, cfg=cfg, send_fn=send_fn, dry_run=args.dry_run)
    else:
        status = run(
            run_date=run_date, cfg=cfg,
            fetch_bhavcopy_fn=fetch_bhavcopy,
            send_fn=send_fn,
            universe_df=load_universe(),
            history_path=DEFAULT_HISTORY_PATH,
            dry_run=args.dry_run,
            fallback_fn=fetch_eod_yfinance,
        )
    print(f"[marketbot] status={status} date={run_date} source={args.source}")


if __name__ == "__main__":
    main()
