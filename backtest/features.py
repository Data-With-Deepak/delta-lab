"""Indicator / feature library (OHLCV-only — all that's historically available)."""
import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + up/dn.replace(0, np.nan))


def atr(df, n=14):
    h, l, c = df.high, df.low, df.close
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def session_vwap(df):
    """VWAP anchored to each UTC day (reset daily)."""
    tp = (df.high + df.low + df.close) / 3
    day = df.dt.dt.date
    pv = (tp * df.volume).groupby(day).cumsum()
    vv = df.volume.groupby(day).cumsum().replace(0, np.nan)
    return pv / vv


def session_vwap_std(df, vwap):
    """Rolling std of (price - vwap) within the day, for deviation bands."""
    dev = df.close - vwap
    day = df.dt.dt.date
    return dev.groupby(day).transform(lambda x: x.expanding().std())


def bbands(s, n=20, k=2):
    mid = s.rolling(n).mean()
    sd = s.rolling(n).std()
    return mid, mid + k*sd, mid - k*sd, (4*sd/mid*100)   # mid, up, low, width%


def supertrend(df, period=10, mult=3.0):
    a = atr(df, period)
    hl2 = (df.high + df.low) / 2
    upper = hl2 + mult*a
    lower = hl2 - mult*a
    n = len(df)
    fu, fl = upper.copy().values, lower.copy().values
    dir_ = np.ones(n)            # +1 = bullish (green), -1 = bearish (red)
    close = df.close.values
    for i in range(1, n):
        fu[i] = min(upper.iloc[i], fu[i-1]) if close[i-1] <= fu[i-1] else upper.iloc[i]
        fl[i] = max(lower.iloc[i], fl[i-1]) if close[i-1] >= fl[i-1] else lower.iloc[i]
        if close[i] > fu[i-1]:
            dir_[i] = 1
        elif close[i] < fl[i-1]:
            dir_[i] = -1
        else:
            dir_[i] = dir_[i-1]
    return pd.Series(dir_, index=df.index)


def add_core(df):
    """Attach the common feature set used across strategies."""
    df = df.reset_index(drop=True).copy()
    c = df.close
    for n in (9, 21, 20, 50, 200):
        df[f"ema{n}"] = ema(c, n)
    df["rsi2"] = rsi(c, 2); df["rsi7"] = rsi(c, 7); df["rsi14"] = rsi(c, 14)
    df["atr"] = atr(df, 14)
    df["vwap"] = session_vwap(df)
    df["vwap_std"] = session_vwap_std(df, df["vwap"])
    df["bb_mid"], df["bb_up"], df["bb_low"], df["bb_w"] = bbands(c, 20, 2)
    df["vol_ma20"] = df.volume.rolling(20).mean()
    df["ret"] = c.pct_change()
    df["body"] = (c - df.open).abs()
    df["range"] = (df.high - df.low).replace(0, np.nan)
    df["hour"] = df.dt.dt.hour
    df["dow"] = df.dt.dt.dayofweek
    return df
