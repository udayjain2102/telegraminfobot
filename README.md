# Daily Market Brief Telegram Bot

A push-only Telegram bot that sends a pre-market NSE brief each trading morning
(~8:30 AM IST). See the design spec in
`docs/superpowers/specs/2026-06-12-telegram-market-bot-design.md`.

## What it sends
- Market overview (Nifty/Sensex + sector movers)
- 🔥 Unusual activity (relative-volume spikes)
- 💰 Most-traded (turnover leaders, Top-15)
- ⭐ Momentum BUY — Top-15 turnover × 20-day new high × Supertrend/Chandelier buy flip × close > POC × volume ≥ 1.5× avg
- 🔴 SELL / EXIT — exits on held positions (HA Supertrend red, close<POC, stop hit, dropped from Top-15)
- 🟢 Chandelier Exit Buy/Sell flips
- 🎯 Approaching a key anchored-volume-profile level
- 📈 Signal alerts (RSI, 52-week highs, 50/200 DMA crossovers)

## One-time setup
1. **Create the bot:** message [@BotFather](https://t.me/BotFather) → `/newbot`
   → copy the **bot token**.
2. **Get chat IDs:** each recipient sends the bot any message, then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy each `chat.id`.
3. **Add GitHub secrets** (repo → Settings → Secrets → Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_IDS` (comma-separated, e.g. `11111111,22222222`)
4. **Build the universe:** run the `refresh-universe` workflow once (Actions tab
   → Run workflow), or locally: `python scripts/refresh_universe.py`.
5. **Backfill history:** `python scripts/backfill_history.py` (one time).

## Local run
```bash
pip install -r requirements.txt
python -m marketbot.main --dry-run            # EOD brief (NSE bhavcopy), sends nothing
python -m marketbot.main --dry-run --date 2026-06-12
python -m marketbot.main --source tradingview --dry-run   # live intraday TradingView scan
```

## Two scans
- **EOD brief** (`--source bhavcopy`, default): full screen from NSE bhavcopy/yfinance
  history — Chandelier flips, anchored volume profile, Momentum BUY, RSI, etc.
- **Intraday momentum scan** (`--source tradingview`): live TradingView screener
  realizing the strategy doc — NSE, MCap ₹10B–₹200B, **Heikin-Ashi new high**,
  Top-15 by turnover, **BUY** flag when TradingView relative volume ≥ 1.5×.
  Excludes stocks **listed within the last 12 months** (TV `first_bar_time`).
  Each BUY ships a **risk/reward matrix** (entry, 1×ATR stop capped at 7% risk,
  1R/2R/3R targets, 2%-risk position size per ₹1L) and a **time horizon** (3–8 weeks).

### BUY → SELL position lifecycle
Both scans share one **open-positions watchlist** (`data/positions.json`):
- A **BUY** fires only when a name is flat → opens a position (entry, stop, date,
  source). A held name is **not re-alerted** until it exits (this replaces the old
  per-day dedup with stronger, lifecycle-based suppression).
- A **SELL/EXIT** fires when a held position hits a trigger, then closes it:
  HA Supertrend red flip · stop hit · dropped from Top-15 turnover · (EOD only)
  close < POC. The doc's "red resistance" exit is chart-drawn and not coded.
- SELLs report entry, exit price, % move, days held, and the trigger(s).

## Tests
```bash
pytest
```

## Scheduling
- `daily-brief.yml` runs `0 3 * * 1-5` (UTC) ≈ 08:30 IST weekdays; skips NSE
  holidays via `data/nse_holidays.txt` (update yearly).
- `tv-scan.yml` runs **hourly across 11:00–14:30 IST** weekdays (UTC crons 05:30,
  06:30, 07:30, 08:30, 09:00) — the live intraday TradingView momentum scan. Uses
  the same Telegram secrets. Commits `data/positions.json` (the shared watchlist)
  back so later slots suppress held names and fire exits (needs `contents: write`).
- `refresh-universe.yml` rebuilds `data/universe.csv` weekly.

## Notes / limitations
- The anchored volume profile is computed from **daily** EOD data, so its
  POC/value-area levels are close to — but not pixel-identical with — the
  TradingView intraday profile.
- Hand-drawn diagonal trendlines are **not** tracked (only horizontal AVP levels).
- If NSE blocks the Actions runner IP (or the bhavcopy is delayed), the daily run
  **automatically falls back** to fetching that day's OHLCV for the universe via
  yfinance (`marketbot/fallback.py`). Only if both bhavcopy and the fallback fail
  does it send a "data not ready" note instead of a brief.
- The TradingView scan uses the **unofficial** `tradingview-screener` library
  (no official TV API). If the endpoint changes or is unreachable, the scan sends
  a "TradingView scan failed" note rather than crashing — it never blocks the EOD brief.
- During the session `volume` is partial, so the scan uses TradingView's
  time-of-day-normalized relative volume for the ≥1.5× check.
- Strategy fidelity (double-checked vs the doc): the intraday scan covers BUY
  conditions [1] Top-15 turnover, [2] new high, and [5] volume ≥ 1.5×, with the
  Supertrend-flip [3] and close-above-POC [4] conditions living in the EOD brief.
- **Candle basis = Heikin-Ashi.** The new-high test compares today's HA close
  (= (O+H+L+C)/4 from the live snapshot) against the highest HA close of the prior
  `new_high_lookback_days` sessions. Those prior HA closes need a daily series, so
  the scan fetches ~3 months of daily bars (via yfinance) for the turnover-ranked
  shortlist that's within 5% of its 1-month high. If that history is unavailable,
  it **falls back** to TradingView's strict 1-month `High.1M` test (conservative —
  it under-alerts rather than firing an unconfirmed signal).
- **Recency:** stocks whose first traded bar (`first_bar_time`) is within the last
  `min_listing_age_days` (365) are excluded, to avoid freshly-listed IPOs.
- The R:R matrix targets (1R/2R/3R) are planning levels; the doc's actual exit is
  "book 50% at resistance, trail the rest with Supertrend." Treat the targets as
  risk-sizing references, not hard take-profits.
