"""Paginated 1-year OHLCV downloader for Delta, cached to CSV."""
import sys, time, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from delta import make_client

RES_S = {"5m":300,"15m":900,"1h":3600,"1d":86400}
DATADIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
client = make_client()

def fetch_history(symbol, res, days):
    step = RES_S[res]; end = int(time.time()); start_target = end - days*86400
    rows, cur_end = [], end
    while cur_end > start_target:
        win = client.get_candles(symbol, res, max(start_target, cur_end-step*3900), cur_end)["result"]
        if not win: break
        rows += win
        earliest = min(c["time"] for c in win)
        if earliest >= cur_end: break
        cur_end = earliest - 1
        time.sleep(0.25)
    df = pd.DataFrame(rows).drop_duplicates("time").sort_values("time")
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df[["time","dt","open","high","low","close","volume"]]

jobs = [("ETHUSD","15m",365),("ETHUSD","1h",365),("ETHUSD","1d",400),
        ("BTCUSD","15m",365),("BTCUSD","1h",365),("BTCUSD","1d",400)]
for sym,res,days in jobs:
    df = fetch_history(sym,res,days)
    path = os.path.join(DATADIR, f"{sym}_{res}.csv")
    df.to_csv(path, index=False)
    print(f"{sym} {res}: {len(df):>6} candles | {df.dt.min().date()} -> {df.dt.max().date()} -> {os.path.basename(path)}")
