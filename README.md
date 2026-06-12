# Daily Market Brief Telegram Bot

A push-only Telegram bot that sends a pre-market NSE brief each trading morning
(~8:30 AM IST). See the design spec in
`docs/superpowers/specs/2026-06-12-telegram-market-bot-design.md`.

## What it sends
- Market overview (Nifty/Sensex + sector movers)
- 🔥 Unusual activity (relative-volume spikes)
- 💰 Most-traded (turnover leaders)
- ⭐ High-conviction (Chandelier Exit Buy flip × key AVP level)
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
python -m marketbot.main --dry-run            # prints the brief, sends nothing
python -m marketbot.main --dry-run --date 2026-06-12
```

## Tests
```bash
pytest
```

## Scheduling
- `daily-brief.yml` runs `0 3 * * 1-5` (UTC) ≈ 08:30 IST weekdays; skips NSE
  holidays via `data/nse_holidays.txt` (update yearly).
- `refresh-universe.yml` rebuilds `data/universe.csv` weekly.

## Notes / limitations
- The anchored volume profile is computed from **daily** EOD data, so its
  POC/value-area levels are close to — but not pixel-identical with — the
  TradingView intraday profile.
- Hand-drawn diagonal trendlines are **not** tracked (only horizontal AVP levels).
- If NSE blocks the Actions runner IP for bhavcopy, switch the daily fetch to the
  yfinance fallback (same OHLCV shape as `backfill_history.py`).
