"""
Level + candlestick alert engine for Delta Exchange (15m candles).

One-shot snapshot:
    python alerts.py ETHUSD
    python alerts.py BTCUSD --step 500

Builds three kinds of levels:
  1. Auto support/resistance from swing pivots (clustered, with touch-strength)
  2. Round/even levels at a fixed step (e.g. 1620,1640,1660 for ETH)
  3. Recent session high/low
Detects candlestick patterns on the latest closed candle, then reports
price proximity to every level (TOUCH / NEAR) and a plain-English read.

Used both as a snapshot and as the brain for the live --watch loop.
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import requests

sys.path.insert(0, sys.path[0] or ".")
from delta import make_client

IST = timezone(timedelta(hours=5, minutes=30))


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
    except Exception:
        pass


def emit(text):
    """Print (for the monitor) AND push to Telegram."""
    print(text, flush=True)
    tg_send(text)
RES_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}

# default round-level step per symbol family
DEFAULT_STEP = {"ETHUSD": 20, "BTCUSD": 500}


def ist(t):
    return datetime.fromtimestamp(t, IST).strftime("%d-%b %H:%M")


def fetch(client, symbol, res, bars):
    step = RES_SECONDS[res]
    end = int(time.time())
    rows = client.get_candles(symbol, res, end - step * bars, end)["result"]
    return sorted(rows, key=lambda c: c["time"])


# ── levels ───────────────────────────────────────────────────────────────────
def pivots(h, l, w=5):
    res, sup = [], []
    for i in range(w, len(h) - w):
        if h[i] == max(h[i - w:i + w + 1]):
            res.append(h[i])
        if l[i] == min(l[i - w:i + w + 1]):
            sup.append(l[i])
    return res, sup


def cluster(levels, tol=0.0025):
    """Merge levels within tol; strength = how many pivots formed it."""
    if not levels:
        return []
    levels = sorted(levels)
    groups, cur = [], [levels[0]]
    for x in levels[1:]:
        if x <= cur[-1] * (1 + tol):
            cur.append(x)
        else:
            groups.append(cur); cur = [x]
    groups.append(cur)
    return [(round(float(np.mean(g)), 1), len(g)) for g in groups]


def round_levels(price, step, band=0.04):
    lo, hi = price * (1 - band), price * (1 + band)
    x = (int(lo // step)) * step
    out = []
    while x <= hi:
        if x >= lo:
            out.append((float(x), "round100" if x % (step * 5) == 0 else "round"))
        x += step
    return out


# ── candlestick patterns (latest closed candle) ──────────────────────────────
def patterns(c):
    p, q = c[-1], c[-2]
    o, h, lo, cl = p["open"], p["high"], p["low"], p["close"]
    body = abs(cl - o); rng = (h - lo) or 1e-9
    upper = h - max(o, cl); lower = min(o, cl) - lo
    found = []
    if body <= 0.1 * rng:
        found.append(("Doji", "indecision"))
    if lower >= 2 * body and upper <= body and body > 0:
        found.append(("Hammer", "bullish (rejection of lows)"))
    if upper >= 2 * body and lower <= body and body > 0:
        found.append(("Shooting Star", "bearish (rejection of highs)"))
    if body >= 0.9 * rng:
        found.append(("Marubozu " + ("up" if cl > o else "down"),
                       "strong " + ("buying" if cl > o else "selling")))
    # 2-candle engulfing
    if cl > o and q["close"] < q["open"] and cl >= q["open"] and o <= q["close"]:
        found.append(("Bullish Engulfing", "bullish reversal"))
    if cl < o and q["close"] > q["open"] and cl <= q["open"] and o >= q["close"]:
        found.append(("Bearish Engulfing", "bearish reversal"))
    return found


# ── proximity evaluation ──────────────────────────────────────────────────────
def evaluate(price, levels, touch=0.0015, near=0.005):
    """levels: list of (price, label, strength). Returns annotated, sorted."""
    out = []
    for lv, label, strength in levels:
        dist = (price - lv) / lv
        status = "TOUCH" if abs(dist) <= touch else ("NEAR" if abs(dist) <= near else "")
        out.append({"level": lv, "label": label, "strength": strength,
                    "dist_pct": 100 * dist, "status": status})
    return sorted(out, key=lambda d: d["level"], reverse=True)


def build_levels(candles, price, step):
    h = [c["high"] for c in candles]; l = [c["low"] for c in candles]
    res, sup = pivots(h, l)
    sr = cluster(res + sup)
    band = 0.04
    levels = []
    for lv, n in sr:
        if price * (1 - band) < lv < price * (1 + band):
            levels.append((lv, "S/R", n))
    for lv, kind in round_levels(price, step, band):
        levels.append((lv, kind, 0))
    # session hi/lo
    levels.append((max(h[-96:]), "24h-high", 0))
    levels.append((min(l[-96:]), "24h-low", 0))
    return levels


def snapshot(client, symbol, res, step):
    candles = fetch(client, symbol, res, 300)
    price = candles[-1]["close"]
    levels = build_levels(candles, price, step)
    rows = evaluate(price, levels)
    pats = patterns(candles)

    print(f"\n{'='*60}\n  {symbol} {res} ALERT SNAPSHOT — {ist(candles[-1]['time'])} IST")
    print(f"  Price: {price:.1f}\n{'='*60}")
    print(f"  Last candle: O{candles[-1]['open']:.1f} H{candles[-1]['high']:.1f} "
          f"L{candles[-1]['low']:.1f} C{price:.1f}")
    print(f"  Pattern(s): {', '.join(f'{n} [{b}]' for n,b in pats) if pats else 'none'}")

    res_above = [r for r in rows if r["level"] > price]
    sup_below = [r for r in rows if r["level"] <= price]
    nr = res_above[-1] if res_above else None
    ns = sup_below[0] if sup_below else None
    print(f"\n  Nearest RESISTANCE: {nr['level']:.1f} ({nr['dist_pct']:+.2f}%, {nr['label']})" if nr else "")
    print(f"  Nearest SUPPORT   : {ns['level']:.1f} ({ns['dist_pct']:+.2f}%, {ns['label']})" if ns else "")

    print(f"\n  {'LEVEL':>10} {'TYPE':<9} {'STR':>3} {'DIST%':>7}  STATUS")
    for r in rows:
        mark = "<-- " + r["status"] if r["status"] else ""
        s = f"x{r['strength']}" if r["strength"] else ""
        print(f"  {r['level']:>10.1f} {r['label']:<9} {s:>3} {r['dist_pct']:>+7.2f}  {mark}")

    active = [r for r in rows if r["status"] == "TOUCH"]
    print(f"\n  >> WHAT'S GOING ON: ", end="")
    if active:
        a = active[0]
        print(f"price is AT {a['label']} {a['level']:.1f}. ", end="")
    if pats:
        print(f"{pats[0][0]} forming ({pats[0][1]}). ", end="")
    if nr and ns:
        print(f"Boxed between support {ns['level']:.0f} and resistance {nr['level']:.0f}.")
    else:
        print("")
    return rows, pats


def watch(client, symbol, res, step, interval):
    """Poll every `interval`s, emit one line per NEW level-touch or candle pattern.
    Hysteresis: a level re-alerts only after price clears its NEAR band."""
    full = fetch(client, symbol, res, 300)
    price = full[-1]["close"]
    levels = build_levels(full, price, step)
    last_rebuild = time.time()
    alerted = set()
    prev_price = price
    last_closed = full[-2]["time"]
    emit(f"ARMED {symbol} {res} every {interval}s | price {price:.1f} | "
         f"{len(levels)} levels | {ist(full[-1]['time'])} IST")
    while True:
        try:
            c = fetch(client, symbol, res, 4)
            price = c[-1]["close"]
            if time.time() - last_rebuild > 600:        # refresh levels every 10 min
                full = fetch(client, symbol, res, 300)
                levels = build_levels(full, price, step); last_rebuild = time.time()
            rows = evaluate(price, levels)
            for r in rows:
                if r["status"] == "TOUCH" and r["level"] not in alerted:
                    arrow = "from BELOW ^" if price >= prev_price else "from ABOVE v"
                    emit(f"{datetime.now(IST):%H:%M:%S} TOUCH {r['label']} {r['level']:.1f} {arrow} "
                         f"| price {price:.1f} ({r['dist_pct']:+.2f}%) "
                         f"{'STR x'+str(r['strength']) if r['strength'] else ''}")
                    alerted.add(r["level"])
                elif abs(r["dist_pct"]) > 0.20 and r["level"] in alerted:
                    alerted.discard(r["level"])         # cleared 0.2% away -> can re-alert
            prev_price = price
            closed = c[:-1]                              # drop in-progress candle
            if closed[-1]["time"] != last_closed:
                pats = patterns(closed)
                if pats:
                    emit(f"{datetime.now(IST):%H:%M:%S} PATTERN {pats[0][0]} [{pats[0][1]}] "
                         f"| price {price:.1f} @ {ist(closed[-1]['time'])} close")
                last_closed = closed[-1]["time"]
        except Exception as e:
            print(f"{datetime.now(IST):%H:%M:%S} [warn] {str(e)[:80]}", flush=True)
        time.sleep(interval)


# ── stateless single cycle (for GitHub Actions cron) ──────────────────────────
def load_state(path):
    """Restore hysteresis state persisted between scheduled runs."""
    try:
        s = json.loads(Path(path).read_text())
        return set(s.get("alerted", [])), s.get("last_closed", 0), s.get("prev_price")
    except Exception:
        return set(), 0, None


def save_state(path, alerted, last_closed, prev_price):
    Path(path).write_text(json.dumps({
        "alerted": sorted(alerted), "last_closed": last_closed, "prev_price": prev_price,
    }))


def run_once(client, symbol, res, step, state_path):
    """One poll cycle with state read from / written to a file. Same alert logic
    as watch(), but no infinite loop — designed to be run on a cron schedule.
    State (which levels have already fired, last candle seen) is persisted so
    scheduled runs don't re-alert the same touch every time."""
    alerted, last_closed, prev_price = load_state(state_path)

    full = fetch(client, symbol, res, 300)
    price = full[-1]["close"]
    if prev_price is None:
        prev_price = price
    levels = build_levels(full, price, step)
    rows = evaluate(price, levels)

    for r in rows:
        if r["status"] == "TOUCH" and r["level"] not in alerted:
            arrow = "from BELOW ^" if price >= prev_price else "from ABOVE v"
            emit(f"{datetime.now(IST):%H:%M:%S} TOUCH {r['label']} {r['level']:.1f} {arrow} "
                 f"| price {price:.1f} ({r['dist_pct']:+.2f}%) "
                 f"{'STR x'+str(r['strength']) if r['strength'] else ''}")
            alerted.add(r["level"])
        elif abs(r["dist_pct"]) > 0.20 and r["level"] in alerted:
            alerted.discard(r["level"])          # cleared 0.2% away -> can re-alert

    closed = full[:-1]                            # drop in-progress candle
    if closed[-1]["time"] != last_closed:
        pats = patterns(closed)
        if pats:
            emit(f"{datetime.now(IST):%H:%M:%S} PATTERN {pats[0][0]} [{pats[0][1]}] "
                 f"| price {price:.1f} @ {ist(closed[-1]['time'])} close")
        last_closed = closed[-1]["time"]

    save_state(state_path, alerted, last_closed, price)
    print(f"{datetime.now(IST):%H:%M:%S} ok | price {price:.1f} | "
          f"{sum(1 for r in rows if r['status']=='TOUCH')} touch | "
          f"{len(alerted)} armed", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="ETHUSD")
    ap.add_argument("--res", default="15m")
    ap.add_argument("--step", type=float, default=None)
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="run a single poll cycle (for cron / GitHub Actions)")
    ap.add_argument("--state", default=".watch_state.json",
                    help="state file for --once hysteresis")
    ap.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()
    sym = args.symbol.upper()
    step = args.step or DEFAULT_STEP.get(sym, 20)
    load_env()
    client = make_client()
    if args.once:
        run_once(client, sym, args.res, step, args.state)
    elif args.watch:
        watch(client, sym, args.res, step, args.interval)
    else:
        snapshot(client, sym, args.res, step)


if __name__ == "__main__":
    main()
