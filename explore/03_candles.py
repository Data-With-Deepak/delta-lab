"""
03 — Historical OHLCV candles (PUBLIC, no API key needed)

Fetches recent candles for a symbol so you can backtest / analyze.
Usage: python 03_candles.py [SYMBOL] [RESOLUTION] [BARS]
       python 03_candles.py BTCUSD 1h 48
"""

import sys
import time
from datetime import datetime

sys.path.insert(0, "..")
from delta import make_client

RES_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    resolution = sys.argv[2] if len(sys.argv) > 2 else "1h"
    bars = int(sys.argv[3]) if len(sys.argv) > 3 else 24

    step = RES_SECONDS.get(resolution, 3600)
    end = int(time.time())
    start = end - step * bars

    client = make_client()
    candles = client.get_candles(symbol, resolution, start, end)["result"]
    candles = sorted(candles, key=lambda c: c["time"])

    print(f"{symbol} {resolution} — {len(candles)} candles\n")
    print(f"{'time':<20}{'open':>12}{'high':>12}{'low':>12}{'close':>12}{'volume':>12}")
    for c in candles:
        ts = datetime.utcfromtimestamp(c["time"]).strftime("%Y-%m-%d %H:%M")
        print(f"{ts:<20}{c['open']:>12}{c['high']:>12}{c['low']:>12}{c['close']:>12}{c['volume']:>12}")


if __name__ == "__main__":
    main()
