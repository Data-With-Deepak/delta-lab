"""
Bar-by-bar backtest engine with mark-to-market equity and realistic costs.

One position at a time, 1x notional (returns in %). Exit modes:
  - 'reverse'     : flip when the opposite entry signal fires (trend-following)
  - 'atr_target'  : ATR stop + R-multiple target
  - 'trailing'    : ATR trailing stop
Optional time_stop (bars) and intrabar stop/target fills via high/low.

Costs: `cost_bps` per ROUND TRIP (fee+slippage), charged on the exit bar.
Default 14 bps ≈ Delta taker 5bps/side + ~2bps slippage/side.
"""
import numpy as np
import pandas as pd


def run(df, long_sig, short_sig, exit_mode="atr_target", *, allow_long=True,
        allow_short=True, atr_mult=2.0, rr=2.0, trail_mult=3.0,
        time_stop=None, cost_bps=14.0):
    close = df.close.values; high = df.high.values; low = df.low.values
    atr = df.atr.values
    L = np.asarray(long_sig, bool); S = np.asarray(short_sig, bool)
    n = len(df); cost = cost_bps / 1e4
    pos = 0; entry = stop = target = 0.0; bars = 0; entry_i = 0
    bar_ret = np.zeros(n); trades = []

    def open_pos(side, i):
        nonlocal pos, entry, stop, target, bars, entry_i
        pos = side; entry = close[i]; bars = 0; entry_i = i
        if exit_mode in ("atr_target", "trailing"):
            a = atr[i] if atr[i] == atr[i] else 0.0
            stop = entry - side*atr_mult*a
            target = entry + side*rr*atr_mult*a

    def close_pos(i, px, reason):
        nonlocal pos
        r = pos*(px/entry - 1) - cost
        trades.append({"side": "L" if pos > 0 else "S", "entry_i": entry_i,
                       "exit_i": i, "entry": entry, "exit": px, "bars": bars,
                       "ret": r, "reason": reason})
        bar_ret[i] += pos*(px/close[i-1] - 1) - cost
        pos = 0

    for i in range(1, n):
        if pos != 0:
            bar_ret[i] = pos*(close[i]/close[i-1] - 1)   # MTM (overwritten if exit)
            bars += 1
            done = False
            if exit_mode in ("atr_target", "trailing"):
                if pos > 0:
                    if low[i] <= stop: close_pos(i, stop, "stop"); done = True
                    elif exit_mode == "atr_target" and high[i] >= target:
                        close_pos(i, target, "target"); done = True
                else:
                    if high[i] >= stop: close_pos(i, stop, "stop"); done = True
                    elif exit_mode == "atr_target" and low[i] <= target:
                        close_pos(i, target, "target"); done = True
                if not done and exit_mode == "trailing" and atr[i] == atr[i]:
                    stop = (max(stop, close[i]-trail_mult*atr[i]) if pos > 0
                            else min(stop, close[i]+trail_mult*atr[i]))
            if not done and exit_mode == "reverse":
                if (pos > 0 and S[i]) or (pos < 0 and L[i]):
                    close_pos(i, close[i], "reverse"); done = True
            if not done and time_stop and bars >= time_stop:
                close_pos(i, close[i], "time"); done = True
        if pos == 0:
            if allow_long and L[i]:
                open_pos(1, i); bar_ret[i] -= cost
            elif allow_short and S[i]:
                open_pos(-1, i); bar_ret[i] -= cost
    return trades, bar_ret


def metrics(df, trades, bar_ret, periods_per_year):
    if not trades:
        return None
    rets = np.array([t["ret"] for t in trades])
    wins = rets[rets > 0]; losses = rets[rets <= 0]
    eq = np.cumprod(1 + bar_ret)
    peak = np.maximum.accumulate(eq)
    maxdd = float(((peak - eq)/peak).max()) * 100
    # Sharpe from per-bar MTM returns, annualized
    mu, sd = bar_ret.mean(), bar_ret.std()
    sharpe = (mu/sd*np.sqrt(periods_per_year)) if sd > 0 else 0.0
    L = [t for t in trades if t["side"] == "L"]; Sh = [t for t in trades if t["side"] == "S"]
    pf = (wins.sum()/abs(losses.sum())) if losses.sum() != 0 else float("inf")
    return {
        "trades": len(trades), "net_%": (eq[-1]-1)*100, "win_%": 100*len(wins)/len(trades),
        "avg_win/avg_loss": (wins.mean()/abs(losses.mean())) if len(losses) and len(wins) else float("nan"),
        "profit_factor": pf, "max_dd_%": maxdd, "sharpe": sharpe,
        "expectancy_%": rets.mean()*100, "long_n": len(L), "short_n": len(Sh),
        "long_net_%": 100*np.prod([1+t["ret"] for t in L])-100 if L else 0,
        "short_net_%": 100*np.prod([1+t["ret"] for t in Sh])-100 if Sh else 0,
        "eq": eq,
    }
