"""
02 — Live price snapshot (PUBLIC, no API key needed)

Prints the current ticker for a symbol (default BTCUSD perpetual).
Usage: python 02_ticker.py [SYMBOL]
"""

import sys

sys.path.insert(0, "..")
from delta import make_client


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    client = make_client()
    t = client.get_ticker(symbol)["result"]

    print(f"Ticker: {symbol}")
    print(f"  mark price : {t.get('mark_price')}")
    print(f"  spot price : {t.get('spot_price')}")
    print(f"  24h high   : {t.get('high')}")
    print(f"  24h low    : {t.get('low')}")
    print(f"  24h volume : {t.get('volume')}")
    print(f"  open interest: {t.get('oi')}")
    print(f"  funding rate : {t.get('funding_rate')}")


if __name__ == "__main__":
    main()
