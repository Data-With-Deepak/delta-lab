"""Run all strategies over 1yr ETH data, compute full metrics, rank, save."""
import os, sys, argparse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F, engine as E, strategies as ST

DATADIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PPY = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520, "1h": 8760, "1d": 365}

def load(sym, res):
    df = pd.read_csv(os.path.join(DATADIR, f"{sym}_{res}.csv"), parse_dates=["dt"])
    return F.add_core(df)

def run_tf(sym, res, cost_bps):
    df = load(sym, res)
    specs = ST.build_all(df)
    rows = []
    for name, (lon, sho, ek) in specs.items():
        ek = dict(ek); ek.setdefault("cost_bps", cost_bps)
        trades, br = E.run(df, lon, sho, **ek)
        m = E.metrics(df, trades, br, PPY[res])
        if not m:
            rows.append({"strategy": name, "tf": res, "trades": 0}); continue
        m.pop("eq")
        rows.append({"strategy": name, "tf": res, **{k: round(v, 2) if isinstance(v, float) else v
                                                     for k, v in m.items()}})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="ETHUSD")
    ap.add_argument("--tfs", default="15m,1h")
    ap.add_argument("--cost_bps", type=float, default=14.0)
    args = ap.parse_args()
    all_rows = []
    for res in args.tfs.split(","):
        all_rows += run_tf(args.sym, res, args.cost_bps)
    r = pd.DataFrame(all_rows)
    out = os.path.join(DATADIR, f"results_{args.sym}.csv")
    r.to_csv(out, index=False)
    cols = ["strategy","tf","trades","net_%","win_%","profit_factor","avg_win/avg_loss",
            "max_dd_%","sharpe","expectancy_%","long_net_%","short_net_%"]
    r = r.reindex(columns=cols)
    print(f"\n=== {args.sym} | 1-year backtest | round-trip cost {args.cost_bps}bps ===")
    print(f"(period: data covers 1yr; one position at a time, 1x notional)\n")
    with pd.option_context("display.width", 200, "display.max_columns", 30, "display.max_rows", 100):
        print(r.sort_values("net_%", ascending=False).to_string(index=False))
    print(f"\nSaved -> {out}")

if __name__ == "__main__":
    main()
