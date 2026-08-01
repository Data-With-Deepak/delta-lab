"""
Strategy signal generators (OHLCV-testable subset of the 30-strategy list).
Each returns (long_bool, short_bool, exit_kwargs). OI/order-book/spread filters
are omitted where the data doesn't exist historically (noted in the report).
"""
import numpy as np
import pandas as pd
import features as F


def _cross_up(a, b):   return (a > b) & (a.shift(1) <= b.shift(1))
def _cross_dn(a, b):   return (a < b) & (a.shift(1) >= b.shift(1))
def _fresh(cond):      return cond & ~cond.shift(1).fillna(False)


def build_all(df):
    c, o, h, l, v = df.close, df.open, df.high, df.low, df.volume
    rng = df["range"]; vma = df["vol_ma20"]
    out = {}
    A = lambda x: x.fillna(False).values

    # ---- 1. TREND: EMA crossovers (reverse exit) ----
    for f, s in [(9, 21), (20, 50), (50, 200)]:
        ef, es = df[f"ema{f}"], df[f"ema{s}"]
        out[f"EMA {f}/{s} cross"] = (A(_cross_up(ef, es)), A(_cross_dn(ef, es)),
                                     dict(exit_mode="reverse"))

    # ---- 2. VWAP reclaim / reject ----
    out["VWAP reclaim/reject"] = (A(_cross_up(c, df.vwap)), A(_cross_dn(c, df.vwap)),
                                  dict(exit_mode="atr_target", atr_mult=1.5, rr=2))

    # ---- 3. Supertrend (reverse exit) ----
    for p, m in [(10, 3), (7, 2), (14, 3)]:
        st = F.supertrend(df, p, m)
        out[f"Supertrend {p},{m}"] = (A(_fresh(st == 1)), A(_fresh(st == -1)),
                                      dict(exit_mode="reverse"))

    # ---- 4/5/12. Range & prev-day breakouts (vol-confirmed) ----
    for n in [20, 50]:
        hh = h.rolling(n).max().shift(1); ll = l.rolling(n).min().shift(1)
        volok = v > 1.5*vma
        out[f"Range breakout {n} (vol)"] = (A(_fresh((c > hh) & volok)),
                                            A(_fresh((c < ll) & volok)),
                                            dict(exit_mode="atr_target", atr_mult=1.5, rr=2))
    date = df.dt.dt.date
    dh = df.groupby(date)["high"].max(); dl = df.groupby(date)["low"].min()
    pdh = pd.Series(date).map(dh.shift(1)).values; pdl = pd.Series(date).map(dl.shift(1)).values
    pdh = pd.Series(pdh, index=df.index); pdl = pd.Series(pdl, index=df.index)
    out["Prev-day H/L breakout"] = (A(_cross_up(c, pdh)), A(_cross_dn(c, pdl)),
                                    dict(exit_mode="atr_target", atr_mult=1.5, rr=2))

    # ---- 6. Opening-range breakout (UTC day, first 4 bars) ----
    k = 4
    di = df.groupby(date).cumcount()
    orh = df.assign(d=date).groupby("d")["high"].transform(lambda x: x.iloc[:k].max())
    orl = df.assign(d=date).groupby("d")["low"].transform(lambda x: x.iloc[:k].min())
    out["Opening-range breakout"] = (A(_fresh((di >= k) & (c > orh))),
                                     A(_fresh((di >= k) & (c < orl))),
                                     dict(exit_mode="atr_target", atr_mult=1.5, rr=2))

    # ---- 7. RSI mean reversion ----
    for rp in ["rsi2", "rsi7", "rsi14"]:
        out[f"RSI MR ({rp})"] = (A(_cross_dn(df[rp], pd.Series(30, index=df.index))),
                                 A(_cross_up(df[rp], pd.Series(70, index=df.index))),
                                 dict(exit_mode="atr_target", atr_mult=1.5, rr=1.5, time_stop=20))

    # ---- 8. Bollinger reversal ----
    out["Bollinger reversal"] = (A((c.shift(1) < df.bb_low.shift(1)) & (c > df.bb_low)),
                                 A((c.shift(1) > df.bb_up.shift(1)) & (c < df.bb_up)),
                                 dict(exit_mode="atr_target", atr_mult=1.5, rr=1.5, time_stop=20))

    # ---- 9. VWAP deviation ----
    for kdev in [1.5, 2.0]:
        lo = c < df.vwap - kdev*df.vwap_std; hi = c > df.vwap + kdev*df.vwap_std
        out[f"VWAP dev {kdev}σ"] = (A(_fresh(lo)), A(_fresh(hi)),
                                    dict(exit_mode="atr_target", atr_mult=1.5, rr=1.5, time_stop=24))

    # ---- 10. Volume-spike continuation ----
    near_hi = c >= h - 0.25*rng; near_lo = c <= l + 0.25*rng
    out["Volume-spike continuation"] = (A((c > o) & near_hi & (v > 2*vma)),
                                        A((c < o) & near_lo & (v > 2*vma)),
                                        dict(exit_mode="atr_target", atr_mult=1.5, rr=2))
    # ---- 11. Volume-exhaustion reversal ----
    out["Volume-exhaustion reversal"] = (A((df.ret < -0.01) & (v > 2*vma) & (c > l + 0.5*rng)),
                                         A((df.ret > 0.01) & (v > 2*vma) & (c < h - 0.5*rng)),
                                         dict(exit_mode="atr_target", atr_mult=1.5, rr=1.5, time_stop=20))

    # ---- 21. ATR breakout ----
    out["ATR breakout (1×)"] = (A(_fresh(c > c.shift(1) + df.atr)),
                                A(_fresh(c < c.shift(1) - df.atr)),
                                dict(exit_mode="trailing", atr_mult=1.5, trail_mult=3))

    # ---- 22. Low-volatility squeeze breakout ----
    sq = df.bb_w.shift(1) < df.bb_w.rolling(100).quantile(0.2).shift(1)
    out["Vol-squeeze breakout"] = (A(_fresh(sq & (c > df.bb_up))), A(_fresh(sq & (c < df.bb_low))),
                                   dict(exit_mode="atr_target", atr_mult=1.5, rr=2.5))

    # ---- 23. High-volatility fade ----
    out["High-vol fade"] = (A((df.ret.shift(1) < -0.025) & (c > o)),
                            A((df.ret.shift(1) > 0.025) & (c < o)),
                            dict(exit_mode="atr_target", atr_mult=1.5, rr=1.5, time_stop=16))
    return out
