"""
10-point crossing alert for Delta Exchange.

Watches the live price and pings Telegram every time it crosses a multiple of
`--step` (default 10), up or down. E.g. ETH at 1867 -> crosses 1870 -> alert.

Uses the PUBLIC ticker endpoint (no API key required), reuses the delta client
and the same Telegram setup as alerts.py (.env: TELEGRAM_BOT_TOKEN / _CHAT_ID).

Run (always-on watcher):
    python cross_alert.py                 # ETHUSD, step 10, poll 20s
    python cross_alert.py BTCUSD --step 100 --interval 15
    python cross_alert.py ETHUSD --once   # single check (for cron/testing)

Anti-spam: a crossing is only confirmed once price sits at least `--deadband`
points inside the new band, so it won't flip-flop while hovering on a level.
State (last confirmed band) is saved to .cross_state.json so a restart doesn't
re-fire old crossings.
"""
import os
import sys
import json
import math
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, sys.path[0] or ".")
from delta import make_client

IST = timezone(timedelta(hours=5, minutes=30))
STATE_FILE = Path(__file__).parent / ".cross_state.json"


def load_env():
    """Load .env from the delta-lab dir into os.environ (for TELEGRAM_* etc.)."""
    f = Path(__file__).parent / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def tg_send(text):
    """Push a message to Telegram if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": text}, timeout=10)
    except Exception as e:
        print(f"[warn] telegram send failed: {str(e)[:80]}", flush=True)


def emit(text):
    """Print (for logs/journalctl) AND push to Telegram."""
    print(text, flush=True)
    tg_send(text)


def now_ist():
    return datetime.now(IST).strftime("%d-%b %H:%M:%S")


def get_price(client, symbol):
    """Live price from the public ticker. Tries mark/spot/close in order."""
    t = client.get_ticker(symbol)["result"]
    for k in ("mark_price", "spot_price", "close", "last_price"):
        v = t.get(k)
        if v not in (None, "", 0, "0"):
            return float(v)
    raise RuntimeError(f"no usable price field in ticker: {list(t)[:8]}")


# ── state ──────────────────────────────────────────────────────────────────
def load_state(symbol, step):
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            if s.get("symbol") == symbol and s.get("step") == step:
                return s.get("bucket")
        except Exception:
            pass
    return None


def save_state(symbol, step, bucket):
    try:
        STATE_FILE.write_text(json.dumps(
            {"symbol": symbol, "step": step, "bucket": bucket, "ts": time.time()}))
    except Exception as e:
        print(f"[warn] state save failed: {str(e)[:80]}", flush=True)


# ── core crossing logic ──────────────────────────────────────────────────────
def levels_between(lo_bucket, hi_bucket, step):
    """The multiples of step strictly above lo_bucket's band, up to hi_bucket."""
    return [k * step for k in range(lo_bucket + 1, hi_bucket + 1)]


def check(price, confirmed, step, deadband):
    """Given current price and last confirmed band, decide if a crossing fired.

    Returns (new_confirmed, direction, crossed_levels).
    direction is 'up' / 'down' / None. A move is only confirmed once price is
    at least `deadband` points inside the new band (hysteresis vs. boundary chop).
    """
    raw = math.floor(price / step)
    if raw > confirmed and price >= raw * step + deadband:
        return raw, "up", levels_between(confirmed, raw, step)
    if raw < confirmed and price <= (raw + 1) * step - deadband:
        # crossed downward through (raw+1)*step .. confirmed*step
        crossed = [k * step for k in range(raw + 1, confirmed + 1)]
        return raw, "down", list(reversed(crossed))
    return confirmed, None, []


def fmt(levels):
    return ", ".join(f"{int(x) if float(x).is_integer() else x}" for x in levels)


def announce(symbol, direction, crossed, price):
    arrow = "🟢 ↑" if direction == "up" else "🔴 ↓"
    word = "crossed UP through" if direction == "up" else "crossed DOWN through"
    emit(f"{arrow} {symbol} {word} {fmt(crossed)}  |  now {price:g}  ({now_ist()} IST)")


# ── runners ──────────────────────────────────────────────────────────────────
def run_once(client, symbol, step, deadband):
    """Single check — for cron / GitHub Actions / testing."""
    price = get_price(client, symbol)
    confirmed = load_state(symbol, step)
    if confirmed is None:
        confirmed = math.floor(price / step)
        save_state(symbol, step, confirmed)
        print(f"init {symbol} @ {price:g} (band {confirmed*step}-{(confirmed+1)*step})", flush=True)
        return
    new, direction, crossed = check(price, confirmed, step, deadband)
    if direction:
        announce(symbol, direction, crossed, price)
        save_state(symbol, step, new)
    else:
        print(f"{now_ist()} {symbol} {price:g} — no cross (band {confirmed*step}-{(confirmed+1)*step})", flush=True)


def watch(client, symbol, step, deadband, interval):
    """Poll forever; alert on every confirmed crossing."""
    price = get_price(client, symbol)
    confirmed = load_state(symbol, step)
    if confirmed is None:
        confirmed = math.floor(price / step)
        save_state(symbol, step, confirmed)
    emit(f"ARMED {symbol} every {interval}s | step {step} | deadband {deadband} | "
         f"price {price:g} | band {confirmed*step}-{(confirmed+1)*step} | {now_ist()} IST")
    while True:
        try:
            price = get_price(client, symbol)
            new, direction, crossed = check(price, confirmed, step, deadband)
            if direction:
                announce(symbol, direction, crossed, price)
                confirmed = new
                save_state(symbol, step, confirmed)
        except Exception as e:
            print(f"{now_ist()} [warn] {str(e)[:100]}", flush=True)
        time.sleep(interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="ETHUSD")
    ap.add_argument("--step", type=float, default=10, help="point spacing (default 10)")
    ap.add_argument("--deadband", type=float, default=2,
                    help="pts inside new band before a cross counts (anti-spam)")
    ap.add_argument("--interval", type=int, default=20, help="poll seconds (watch mode)")
    ap.add_argument("--once", action="store_true", help="single check then exit")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    load_env()
    client = make_client()
    if args.once:
        run_once(client, symbol, args.step, args.deadband)
    else:
        watch(client, symbol, args.step, args.deadband, args.interval)


if __name__ == "__main__":
    main()
