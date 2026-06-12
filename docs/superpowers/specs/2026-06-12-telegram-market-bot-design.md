# Daily Market Brief Telegram Bot — Design

**Date:** 2026-06-12
**Status:** Approved

## Purpose

A Telegram bot that sends a daily pre-market brief (8:30 AM IST, Mon–Fri) for the
Indian market (NSE/BSE) to the user's dad (and optionally the user). The brief
covers a market overview, watchlist movers, stocks matching the family's investing
criteria, and indicator alerts. Criteria originate from the user's TradingView
setup (watchlists, screener filters, chart indicators, Pine Script strategies) and
are encoded in a config file; the TradingView extraction happens in a later
session once the Claude for Chrome extension is installed.

## Decisions made

| Decision | Choice |
|---|---|
| Platform | Telegram (official Bot API, free) |
| Market | India — NSE/BSE |
| Delivery time | 8:30 AM IST, weekdays, skipping NSE holidays |
| Content | Market overview, watchlist movers, criteria matches, indicator alerts |
| Hosting | GitHub Actions scheduled workflow (free, serverless) |
| Architecture | Option A: stateless cron script, push-only (no interactive commands) |
| Data source | yfinance (`.NS` tickers, `^NSEI`, `^BSESN`) |
| TradingView access | Extract later via Chrome extension; config file is the interface |

## Architecture

A single GitHub repository. A GitHub Actions workflow runs `bot.py` on cron
`0 3 * * 1-5` (03:00 UTC ≈ 8:30 AM IST) plus `workflow_dispatch` for manual test
runs. Each run: fetch data → compute indicators → evaluate criteria → format
message → send via Telegram `sendMessage`. Stateless except a small cached
previous-close file committed back to the repo.

## Components

- **`watchlist.txt`** — one NSE symbol per line (e.g., `RELIANCE`, `TCS`).
  Populated from the user's TradingView watchlists.
- **`criteria.yaml`** — declarative investing criteria, e.g.
  `rsi_14: {below: 30}`, `price_above_sma: 200`, `pe_below: 25`,
  `near_52w_low_pct: 10`. TradingView screener filters and indicator conditions
  translate to these rules. Pine Script strategies that don't fit the declarative
  schema become one small Python plugin per strategy implementing a
  `matches(history: DataFrame) -> bool` interface.
- **`market_data.py`** — yfinance fetches: Nifty 50 (`^NSEI`), Sensex
  (`^BSESN`), sector indices; ~1 year of daily OHLCV per watchlist stock
  (enough for 200-day SMA and 52-week levels); basic fundamentals (P/E,
  market cap) where yfinance provides them.
- **`indicators.py`** — pandas computations: RSI(14), SMA/EMA (20/50/200),
  MA crossovers, volume vs 20-day average, distance from 52-week high/low.
- **`screener.py`** — applies `criteria.yaml` (and strategy plugins) to all
  watchlist stocks; returns criteria matches and triggered indicator alerts.
- **`message.py`** — builds the Telegram HTML message in four sections:
  📊 market overview → 📈 watchlist movers (sorted by % change, volume-spike
  flags) → 🎯 criteria matches → ⚠️ indicator alerts. Splits messages over
  Telegram's 4096-character limit.
- **`bot.py`** — entry point; orchestrates the run and sends to a list of chat
  IDs. Supports `--dry-run` (print instead of send).
- **`.github/workflows/daily-brief.yml`** — cron + manual trigger; secrets
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_IDS`.
- **`holidays.py` / `nse_holidays.txt`** — static NSE holiday list (updated
  yearly); the run exits early on holidays.

## One-time setup

1. Create the bot with @BotFather → token.
2. Dad (and user) start a chat with the bot once; capture chat IDs via
   `getUpdates`.
3. Store token and chat IDs as GitHub Actions secrets.

## Error handling

- Per-ticker fetch failures: continue, append a "data unavailable for: …"
  footer. Never fail the whole brief for one bad ticker.
- Whole-run failure: GitHub Actions failure email to the repo owner.
- Flaky index data: previous close cached in-repo so day-change still computes.
- Holidays: skip via static NSE calendar.

## Testing

- Unit tests: indicator math against known reference values; criteria
  evaluation against synthetic series designed to match/not match.
- `--dry-run` prints the formatted message locally.
- `workflow_dispatch` allows a real end-to-end test send on demand.

## Out of scope (later)

- TradingView extraction session to populate `watchlist.txt` and
  `criteria.yaml` (blocked on Chrome extension install).
- Interactive commands (`/price`, `/matches`) — would move to an always-on
  host (Option B); current module boundaries allow this lift.
- WhatsApp delivery.
