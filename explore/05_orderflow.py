"""
05 — Order flow dashboard (PUBLIC, no API key needed)

For one symbol, shows three things people actually want:
  1. Bid/ask spread + order book depth (who's stacked to buy vs sell)
  2. Recent trades broken into aggressive BUY vs aggressive SELL volume
  3. Open interest + 6h change (are positions being opened or closed?)

Usage: python 05_orderflow.py [SYMBOL]    e.g. python 05_orderflow.py ETHUSD

NOTE: Open interest cannot be split into "longs vs shorts" — every contract
has a long AND a short, so they're always equal. We infer pressure instead
from the aggressor side of trades and from how OI is changing.
"""

import sys

sys.path.insert(0, "..")
from delta import make_client


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ETHUSD"
    client = make_client()

    # --- 1. Order book: spread + depth imbalance ----------------------------
    ob = client.get_orderbook(symbol)["result"]
    bids, asks = ob["buy"], ob["sell"]
    best_bid, best_ask = fnum(bids[0]["price"]), fnum(asks[0]["price"])
    spread = best_ask - best_bid
    bid_depth = sum(fnum(b["size"]) for b in bids)
    ask_depth = sum(fnum(a["size"]) for a in asks)
    total_depth = bid_depth + ask_depth or 1

    print(f"\n========== ORDER FLOW: {symbol} ==========\n")
    print("--- ORDER BOOK (resting orders) ---")
    print(f"  Best bid : {best_bid}")
    print(f"  Best ask : {best_ask}")
    print(f"  Spread   : {spread:.2f}  ({spread / best_ask * 100:.3f}%)")
    print(f"  Buy-side depth  : {bid_depth:,.0f} contracts  ({bid_depth/total_depth*100:.1f}%)")
    print(f"  Sell-side depth : {ask_depth:,.0f} contracts  ({ask_depth/total_depth*100:.1f}%)")
    lean = "BUYERS stacked deeper" if bid_depth > ask_depth else "SELLERS stacked deeper"
    print(f"  -> Book leans: {lean}")

    # --- 2. Recent trades: aggressive buy vs sell ---------------------------
    trades = client.get_trades(symbol)["result"]
    buy_vol = sum(fnum(t["size"]) for t in trades if t.get("buyer_role") == "taker")
    sell_vol = sum(fnum(t["size"]) for t in trades if t.get("seller_role") == "taker")
    total_vol = buy_vol + sell_vol or 1

    print(f"\n--- RECENT TRADES (last {len(trades)} prints) ---")
    print(f"  Aggressive BUY volume  : {buy_vol:,.0f} contracts  ({buy_vol/total_vol*100:.1f}%)")
    print(f"  Aggressive SELL volume : {sell_vol:,.0f} contracts  ({sell_vol/total_vol*100:.1f}%)")
    flow = "BUYERS are the aggressors" if buy_vol > sell_vol else "SELLERS are the aggressors"
    print(f"  -> Flow: {flow}")

    # --- 3. Open interest ---------------------------------------------------
    t = client.get_ticker(symbol)["result"]
    oi_contracts = fnum(t.get("oi_contracts"))
    oi_usd = fnum(t.get("oi_value_usd"))
    oi_chg_6h = fnum(t.get("oi_change_usd_6h"))

    print(f"\n--- OPEN INTEREST (live positions still open) ---")
    print(f"  Open contracts : {oi_contracts:,.0f}")
    print(f"  OI value (USD) : ${oi_usd:,.0f}")
    print(f"  6h change (USD): ${oi_chg_6h:,.0f}")
    if oi_chg_6h > 0:
        print("  -> OI RISING: new positions being opened (fresh money entering)")
    else:
        print("  -> OI FALLING: positions being closed (money leaving / squaring off)")
    print()


if __name__ == "__main__":
    main()
