# Deploy: free 24/7 alerts via GitHub Actions

The live alerts run on **GitHub Actions cron** instead of a laptop or a VM.
No server, no credit card. Public repo => unlimited free Actions minutes.

## How it works

- `.github/workflows/eth-alerts.yml` runs `python alerts.py ETHUSD --once`
  every 5 minutes.
- `--once` does a single poll cycle (fetch candles -> detect level touches +
  candlestick patterns -> push to Telegram), then exits.
- Hysteresis state (which levels already fired, last candle seen) is persisted
  between runs in `.watch_state.json` via the Actions cache, so the same touch
  isn't re-alerted every 5 minutes.
- A monthly empty commit keeps the schedule from being auto-disabled after
  60 days of repo inactivity.

15-minute candles don't need per-second polling, so every 5 minutes is plenty.

## One-time setup

1. Create a **public** GitHub repo and push this project (the `gh` CLI does
   repo-create + push in one step).
2. Add two repository secrets (Settings -> Secrets and variables -> Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   These come from your local `.env`. The `.env` file itself is gitignored and
   never leaves your machine.
3. That's it. The workflow starts on the next 5-minute tick. Use the **Actions**
   tab -> "Run workflow" to trigger a test run immediately.

## Notes

- Only public *candle* data is used, so no Delta API key/secret is needed.
- `alerts.py` (snapshot / `--watch`) still works locally exactly as before;
  `--once` is just the cron-friendly entry point.
- To change the symbol or cadence, edit `eth-alerts.yml`.
