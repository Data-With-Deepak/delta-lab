"""
04 — Your account (PRIVATE, needs API key + secret in .env)

Reads wallet balances, open positions, and open orders.
This is READ-ONLY — it does not place or cancel anything.
"""

import sys

sys.path.insert(0, "..")
from delta import make_client, DeltaError


def main():
    client = make_client()
    try:
        print("=== Wallet balances ===")
        for b in client.get_balances()["result"]:
            if float(b.get("balance", 0)) != 0:
                print(f"  {b['asset_symbol']:<8} balance={b['balance']} available={b.get('available_balance')}")

        print("\n=== Open positions ===")
        positions = client.get_positions()["result"]
        if not positions:
            print("  (none)")
        for p in positions:
            print(f"  {p.get('product_symbol')}: size={p.get('size')} entry={p.get('entry_price')} pnl={p.get('unrealized_pnl')}")

        print("\n=== Open orders ===")
        orders = client.get_open_orders()["result"]
        if not orders:
            print("  (none)")
        for o in orders:
            print(f"  {o.get('product_symbol')}: {o.get('side')} {o.get('size')} @ {o.get('limit_price')} [{o.get('state')}]")

    except DeltaError as e:
        print(f"\nAPI error: {e}")
        print("Check that DELTA_API_KEY / DELTA_API_SECRET in .env are correct,")
        print("and that the key has the right permissions + your IP is whitelisted.")


if __name__ == "__main__":
    main()
