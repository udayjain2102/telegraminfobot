# Daily Market Brief Telegram Bot — Design

**Date:** 2026-06-12
**Status:** Approved

## Purpose

A Telegram bot that sends a daily pre-market brief (~8:30 AM IST, weekdays,
skipping NSE holidays) for the Indian market (NSE) to the user's dad (and
optionally the user). The brief covers a market overview, the most active /
unusual-activity stocks within the family's screened universe, the most-traded
names by turnover, and indicator alerts.

The investing criteria were extracted from the user's TradingView screener
"USE ONLY THIS" on 2026-06-12 (read via the TradingView desktop app). They are
deliberately simple — a liquidity/size screen, not a multi-factor fundamental
screen.

## Captured investing criteria (from TradingView)

| Criterion | Value |
|---|---|
| Market | India (NSE) |
| Market cap | > ₹10 billion (₹1,000 crore) — the only fundamental filter |
| Primary ranking | Price × Volume (turnover), descending |
| Key signal column | Relative volume (today's volume ÷ average volume) |
| Other fundamental filters (P/E, ROE, PEG, EPS growth, div yield, sector) | **Empty** |
| Universe size on capture day | ~1,422 stocks |

In plain terms: **liquid Indian large/mid-caps (≥ ₹1,000 cr market cap), with the
daily attention list driven by turnover and relative-volume spikes.**

## Decisions made

| Decision | Choice |
|---|---|
| Platform | Telegram (official Bot API, free) |
| Market | India — NSE |
| Delivery time | ~8:30 AM IST, weekdays, skipping NSE holidays (cron `0 3 * * 1-5` UTC) |
| Content | Market overview · unusual activity (rel-vol) · most-traded (turnover) · indicator alerts |
| Movers basis | Top movers **within the screened universe** (not a separate watchlist) |
| Hosting | GitHub Actions scheduled workflow (free, serverless) |
| Architecture | Stateless cron script, push-only (no interactive commands in v1) |
| Data source | **NSE bhavcopy** (official daily EOD, all stocks) + weekly-cached market-cap universe; yfinance as a fallback only |
| Persistence | Rolling `data/history.parquet` committed back to the repo (no database) |

## Architecture

A single GitHub repository. Two GitHub Actions workflows:

- **`daily-brief.yml`** — cron `0 3 * * 1-5` (03:00 UTC ≈ 8:30 AM IST) plus
  `workflow_dispatch` for manual test runs. Runs `main.py`.
- **`refresh-universe.yml`** — weekly cron; rebuilds `data/universe.csv`
  (market cap moves slowly, so daily refresh is unnecessary).

Each daily run: download yesterday's bhavcopy → filter to the universe → append
to the rolling history store → compute indicators, relative volume, turnover →
screen + rank → build market overview → format message → send via Telegram
`sendMessage`. The updated `history.parquet` is committed back to the repo so the
next run has a rolling window with no external database.

## Components (each independently testable)

- **`config.yaml`** — all thresholds and settings: `min_market_cap_inr:
  10_000_000_000`, `top_n_unusual`, `top_n_turnover`, RSI/MA periods,
  rel-vol spike threshold, schedule, Telegram chat IDs.
- **`universe.py`** — builds `data/universe.csv` (NSE equities with market cap
  > ₹1,000 cr: symbol, name, market cap, sector). Source: NSE equity list +
  market cap; refreshed weekly. Provides the screening universe.
- **`bhavcopy.py`** — downloads NSE's official daily EOD bhavcopy (one request,
  all stocks) and returns a clean OHLCV DataFrame. Handles "not yet published"
  with retry.
- **`history.py`** — maintains `data/history.parquet`: rolling ~1 year of daily
  OHLCV for the universe. Appends each run; powers relative volume and
  indicators without a DB. Cold start backfills ~1 year (NSE archives or a
  one-off yfinance pull).
- **`indicators.py`** — pandas computations: RSI(14), SMA/EMA (20/50/200),
  MA crossovers, 52-week high/low proximity, relative volume (today ÷ 20-day
  average), turnover (close × volume).
- **`screen.py`** — applies the criteria (market cap from universe, liquidity
  from bhavcopy), ranks by turnover, flags rel-vol spikes and indicator
  signals, selects the top N for each section.
- **`market_overview.py`** — Nifty 50 (`^NSEI`) and Sensex (`^BSESN`) close and
  % change, top sector movers.
- **`brief.py`** — builds the Telegram message (Markdown/HTML) in sections;
  splits over Telegram's 4096-char limit.
- **`telegram_bot.py`** — sends via Bot API to a list of chat IDs;
  exponential-backoff retry. Supports `--dry-run` (print instead of send).
- **`main.py`** — entry point; orchestrates the run.
- **`holidays.py` / `nse_holidays.txt`** — static NSE holiday list (updated
  yearly); the run exits early on holidays.

## Daily message layout

```
📊 Market Brief — Mon 12 Jun
─────────────────────────
NIFTY 50  24,310  ▲ +0.8%
SENSEX    79,850  ▲ +0.7%
Top sectors: IT ▲1.9% · Auto ▲1.1%

🔥 Unusual activity (rel-vol spikes)
 MTARTECH  ₹7,036  +11.6%  RV 11.8x
 NETWEB    ₹4,497  +7.3%   RV 6.8x
 …

💰 Most-traded (turnover)
 HDFCBANK · RELIANCE · ICICIBANK …

📈 Signal alerts
 RSI<30: XYZ · ABC
 52w high: LT · BSE
 50/200 DMA crossover↑: APOLLO
```

## One-time setup

1. Dad creates the bot with @BotFather → bot token.
2. Dad (and optionally the user) start a chat with the bot once; capture chat
   IDs via `getUpdates`.
3. Store `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_IDS` as GitHub Actions secrets.
4. One-time history backfill so relative volume and indicators work on day one.

## Error handling

- Bhavcopy not yet published (holiday/delay): retry with backoff, then send a
  short "markets closed / data not ready" note instead of failing silently.
- Per-ticker computation failures: continue; append a "data unavailable for: …"
  footer. Never fail the whole brief for one bad ticker.
- Telegram send failure: exponential-backoff retry; surface in the Actions log
  (and GitHub failure email to the repo owner).
- Holidays: skip via the static NSE calendar.

## Testing

- Unit tests: indicator math against known reference values; screen/ranking
  against a small synthetic universe + bhavcopy fixture; snapshot test for
  message formatting; Telegram API mocked.
- `--dry-run` prints the formatted message locally.
- `workflow_dispatch` allows a real end-to-end test send on demand.

## Out of scope (later)

- Interactive commands (`/price`, `/matches`) — would require an always-on host;
  current module boundaries allow this lift later.
- Additional fundamental/technical filters — the criteria are intentionally just
  the liquidity/size screen today; thresholds live in `config.yaml` if expanded.
- WhatsApp delivery.
