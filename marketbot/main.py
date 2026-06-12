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
from .history import append_day, load_history, DEFAULT_HISTORY_PATH
from .screen import build_report
from .market_overview import build_overview, MarketOverview
from .brief import render_brief, render_unavailable
from .telegram_bot import send_message


def run(run_date: date, cfg: Config,
        fetch_bhavcopy_fn: Callable[[date], pd.DataFrame],
        send_fn: Callable[[str], None],
        universe_df: pd.DataFrame,
        history_path: Path,
        dry_run: bool,
        fallback_fn: Callable[[date, list[str]], pd.DataFrame] | None = None) -> str:
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
    text = render_brief(report, overview)

    if dry_run:
        print(text)
    else:
        send_fn(text)
    return "sent"


def _default_send(cfg: Config) -> Callable[[str], None]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_IDS"].split(",") if c.strip()]
    return lambda text: send_message(token, chat_ids, text, parse_mode=None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily NSE market brief Telegram bot")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--date", help="run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    cfg = load_config()
    run_date = date.fromisoformat(args.date) if args.date else date.today()
    universe_df = load_universe()
    send_fn = (lambda text: print(text)) if args.dry_run else _default_send(cfg)

    status = run(
        run_date=run_date, cfg=cfg,
        fetch_bhavcopy_fn=fetch_bhavcopy,
        send_fn=send_fn,
        universe_df=universe_df,
        history_path=DEFAULT_HISTORY_PATH,
        dry_run=args.dry_run,
        fallback_fn=fetch_eod_yfinance,
    )
    print(f"[marketbot] status={status} date={run_date}")


if __name__ == "__main__":
    main()
