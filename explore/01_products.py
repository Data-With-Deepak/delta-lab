"""
01 — What can I trade? (PUBLIC, no API key needed)

Lists how many products exist and breaks them down by type
(perpetual futures, call/put options, futures), then prints a few examples.
"""

import sys
from collections import Counter

sys.path.insert(0, "..")  # allow running from inside explore/
from delta import make_client


def main():
    client = make_client()
    products = client.get_products()["result"]

    print(f"Total products: {len(products)}\n")

    by_type = Counter(p["contract_type"] for p in products)
    print("Breakdown by contract type:")
    for ctype, n in by_type.most_common():
        print(f"  {ctype:>22}: {n}")

    print("\nSample perpetual futures:")
    perps = [p for p in products if p["contract_type"] == "perpetual_futures"][:8]
    for p in perps:
        print(f"  {p['symbol']:<16} underlying={p.get('underlying_asset', {}).get('symbol', '?')}")

    print("\nSample options:")
    opts = [p for p in products if "options" in p["contract_type"]][:8]
    for p in opts:
        print(f"  {p['symbol']:<22} strike={p.get('strike_price')} type={p['contract_type']}")


if __name__ == "__main__":
    main()
