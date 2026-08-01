# delta-lab

A safe sandbox for exploring the **Delta Exchange India** API (futures & options).
Starts read-only: public market data first, then read-only account info.
**No order-placing code is included yet** — we add that deliberately, later.

## Setup

```bash
cd delta-lab
python3 -m pip install -r requirements.txt
cp .env.example .env        # then paste your keys into .env
```

## What you can run (in order)

| Script | Needs keys? | What it shows |
|--------|-------------|---------------|
| `explore/01_products.py` | No  | Every tradable instrument, counted by type, with examples |
| `explore/02_ticker.py`   | No  | Live price snapshot for a symbol (`python 02_ticker.py BTCUSD`) |
| `explore/03_candles.py`  | No  | Historical OHLCV candles (`python 03_candles.py BTCUSD 1h 48`) |
| `explore/04_account.py`  | Yes | Your balances, positions, open orders (READ-ONLY) |

Run from inside the `explore/` folder, e.g.:

```bash
cd explore
python3 01_products.py
```

## How it's organized

- `delta/client.py` — the API client. Handles HMAC-SHA256 signing for private calls.
- `delta/__init__.py` — `make_client()` loads keys from `.env` and builds a client.
- `explore/` — small, single-purpose scripts you can read and tweak.

## Safety notes

- `.env` is gitignored. Your keys never leave your machine.
- Set `DELTA_ENV=testnet` in `.env` to practice against the demo exchange (fake funds).
- For real trading later: use an API key scoped to only the permissions you need,
  and whitelist your IP in the Delta dashboard.

## API reference

- Docs: https://docs.delta.exchange/
- India base URL: `https://api.india.delta.exchange`
- Testnet (India): `https://cdn-ind.testnet.deltaex.org`
