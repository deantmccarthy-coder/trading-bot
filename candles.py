"""Candlestick pattern signals and a trade simulator with stops and targets.

Every pattern is decided from bars up to and including the signal bar. Trades enter on the NEXT bar
(at its open, or for inside-bar breakouts when price crosses the inside bar's high/low), with:
  stop   = beyond the pattern's extreme, plus a 0.1 ATR buffer
  target = entry +/- REWARD_R x risk
  exit   = stop, target, or the close of the MAX_HOLD-th bar, whichever comes first.
If a bar touches both stop and target, the stop is assumed to come first (conservative).
Results are in R: profit divided by the amount risked, after costs.
"""
import numpy as np
import pandas as pd

REWARD_R = 2.0
COST_BPS = 5.0          # per side
STOP_BUFFER_ATR = 0.1
MAX_RISK_ATR = 3.0


def atr(df, n=14):
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def patterns(df):
    """Boolean signal columns (True on the bar that completes the pattern) and each pattern's span in bars."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    green, red = c > o, c < o
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    o1, c1, h1, l1, body1 = o.shift(1), c.shift(1), h.shift(1), l.shift(1), body.shift(1)
    o2, c2, body2, rng2 = o.shift(2), c.shift(2), body.shift(2), rng.shift(2)
    fell = c1 < c.shift(6)          # prior decline into the bar
    rose = c1 > c.shift(6)          # prior rally into the bar
    mid1 = (o1 + c1) / 2
    mid2 = (o2 + c2) / 2

    sig = {
        # bullish
        "Bullish engulfing": (red.shift(1) & green & (o <= c1) & (c >= o1) & (body > body1), 2, 1),
        "Hammer": (fell & (body <= 0.35 * rng) & (lower >= 2 * body) & (upper <= 0.25 * rng), 1, 1),
        "Morning star": (red.shift(2) & (body2 > 0.5 * rng2) & (body1 <= 0.3 * body2) & green & (c > mid2), 3, 1),
        "Piercing line": (red.shift(1) & (body1 > 0.5 * rng.shift(1)) & green & (o < c1) & (c > mid1) & (c < o1), 2, 1),
        "Three white soldiers": (green & green.shift(1) & green.shift(2) & (c > c1) & (c1 > c2)
                                 & (o > o1) & (o < c1) & (o1 > o2) & (o1 < c2)
                                 & (body > 0.5 * rng) & (body1 > 0.5 * rng.shift(1)) & (body2 > 0.5 * rng2), 3, 1),
        # bearish
        "Bearish engulfing": (green.shift(1) & red & (o >= c1) & (c <= o1) & (body > body1), 2, -1),
        "Shooting star": (rose & (body <= 0.35 * rng) & (upper >= 2 * body) & (lower <= 0.25 * rng), 1, -1),
        "Evening star": (green.shift(2) & (body2 > 0.5 * rng2) & (body1 <= 0.3 * body2) & red & (c < mid2), 3, -1),
        "Dark cloud cover": (green.shift(1) & (body1 > 0.5 * rng.shift(1)) & red & (o > c1) & (c < mid1) & (c > o1), 2, -1),
        "Three black crows": (red & red.shift(1) & red.shift(2) & (c < c1) & (c1 < c2)
                              & (o < o1) & (o > c1) & (o1 < o2) & (o1 > c2)
                              & (body > 0.5 * rng) & (body1 > 0.5 * rng.shift(1)) & (body2 > 0.5 * rng2), 3, -1),
    }
    inside = (h < h1) & (l > l1)
    sig["Inside bar breakout (long)"] = (inside, 1, 1)
    sig["Inside bar breakdown (short)"] = (inside, 1, -1)
    return {name: (mask.fillna(False), span, side) for name, (mask, span, side) in sig.items()}


def context(df):
    """Context filters, all known at the signal bar's close."""
    c = df["close"]
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200).mean()
    vol_up = df["volume"] > df["volume"].rolling(20).mean()
    return {
        "up": (c > sma50) & (sma50 > sma200),
        "down": (c < sma50) & (sma50 < sma200),
        "volume": vol_up.fillna(False),
    }


def simulate(df, signal_idx, side, span, max_hold, stop_entry=False, day=None):
    """Simulate one trade from a signal at integer position signal_idx. Returns (entry_date, R) or None.

    With `day` (one label per bar), the trade must enter on the signal's day and is closed by that day's last bar.
    """
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = df["atr"].to_numpy()
    i = signal_idx
    j = i + 1
    if j >= len(df) or np.isnan(a[i]) or (day is not None and day[j] != day[i]):
        return None
    last = min(j + max_hold, len(df))
    if day is not None:
        last = j + int(np.searchsorted(day[j:last], day[j], side="right"))
    lo, hi = l[i - span + 1:i + 1].min(), h[i - span + 1:i + 1].max()

    if stop_entry:  # inside-bar: enter only if the next bar breaks the inside bar
        if side > 0 and h[j] > h[i]:
            entry = max(o[j], h[i])
        elif side < 0 and l[j] < l[i]:
            entry = min(o[j], l[i])
        else:
            return None
    else:
        entry = o[j]

    stop = lo - STOP_BUFFER_ATR * a[i] if side > 0 else hi + STOP_BUFFER_ATR * a[i]
    risk = (entry - stop) * side
    if risk <= 0 or risk > MAX_RISK_ATR * a[i]:
        return None
    target = entry + side * REWARD_R * risk

    exit_price = None
    for k in range(j, last):
        first_bar = k == j
        if side > 0:
            if not first_bar and o[k] <= stop:
                exit_price = o[k]
            elif l[k] <= stop:
                exit_price = stop
            elif not first_bar and o[k] >= target:
                exit_price = o[k]
            elif h[k] >= target:
                exit_price = target
        else:
            if not first_bar and o[k] >= stop:
                exit_price = o[k]
            elif h[k] >= stop:
                exit_price = stop
            elif not first_bar and o[k] <= target:
                exit_price = o[k]
            elif l[k] <= target:
                exit_price = target
        if exit_price is not None:
            break
    if exit_price is None:
        exit_price = c[last - 1]
    r = (exit_price - entry) * side / risk - 2 * COST_BPS / 1e4 * entry / risk
    return df.index[j], r


def backtest_symbol(df, max_hold=10, variants=("none", "trend", "trend+volume"), intraday=False):
    """All trades for one symbol: rows of (pattern, variant, side, entry_date, R)."""
    df = df.copy()
    df["atr"] = atr(df)
    day = df.index.normalize().to_numpy() if intraday else None
    ctx = context(df)
    rows = []
    for name, (mask, span, side) in patterns(df).items():
        stop_entry = name.startswith("Inside bar")
        trend_ok = ctx["up"] if side > 0 else ctx["down"]
        for variant in variants:
            m = mask.copy()
            if variant in ("trend", "trend+volume"):
                m &= trend_ok
            if variant == "trend+volume":
                m &= ctx["volume"]
            for i in np.flatnonzero(m.to_numpy()):
                if i < 200:
                    continue
                t = simulate(df, i, side, span, max_hold, stop_entry, day)
                if t:
                    rows.append((name, variant, "long" if side > 0 else "short", t[0], t[1]))
    return rows


def summarize(trades):
    """Per pattern/variant: trades, win rate, average R, profit factor, total R."""
    g = trades.groupby(["pattern", "variant"])["R"]
    out = pd.DataFrame({
        "trades": g.size(),
        "win_rate": g.apply(lambda r: (r > 0).mean()),
        "avg_R": g.mean(),
        "profit_factor": g.apply(lambda r: r[r > 0].sum() / -r[r < 0].sum() if (r < 0).any() else np.nan),
        "total_R": g.sum(),
    })
    return out
