"""Daily strategies. Each takes price panels (dates x symbols) and returns target weights.

Weights for a day may only use data up to and including that day's close.
"""
import numpy as np
import pandas as pd


def rsi(closes, length=2):
    delta = closes.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def buy_and_hold(closes, symbol="SPY"):
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    w[symbol] = closes[symbol].notna().astype(float)
    return w


def equal_weight(closes, exclude=("SPY",)):
    cols = [c for c in closes.columns if c not in exclude]
    avail = closes[cols].notna().astype(float)
    w = avail.div(avail.sum(axis=1), axis=0).fillna(0.0)
    return w.reindex(columns=closes.columns, fill_value=0.0)


def momentum_rotation(closes, lookback=126, skip=21, top=5, regime="SPY", regime_sma=200, exclude=("SPY",)):
    """Each month hold the `top` symbols with the best 6-month return (skipping the last month), if positive.

    With a regime symbol, go to cash whenever it closes below its 200-day average (regime=None disables this).
    """
    cols = [c for c in closes.columns if c not in exclude]
    mom = closes[cols].shift(skip) / closes[cols].shift(skip + lookback) - 1
    month_end = closes.index.to_series().groupby(closes.index.to_period("M")).transform("max") == closes.index

    w = pd.DataFrame(np.nan, index=closes.index, columns=cols)
    for day in closes.index[month_end.values]:
        picks = mom.loc[day].dropna()
        picks = picks[picks > 0].nlargest(top)
        row = pd.Series(0.0, index=cols)
        row[picks.index] = 1.0 / top
        w.loc[day] = row
    w = w.ffill().fillna(0.0)

    if regime is not None:
        market = closes[regime]
        risk_on = (market > market.rolling(regime_sma).mean()).astype(float)
        w = w.mul(risk_on, axis=0)
    return w.reindex(columns=closes.columns, fill_value=0.0)


def fixed_mix(closes, mix):
    """Constant weights, e.g. {"SPY": 0.6, "IEF": 0.4}, rebalanced daily."""
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for sym, weight in mix.items():
        w[sym] = closes[sym].notna() * weight
    return w


def rsi2_mean_reversion(closes, entry=10, exit_sma=5, trend_sma=200, max_positions=5, exclude=("SPY",)):
    """Buy short, sharp dips in stocks that are in a long-term uptrend; sell on the bounce.

    Enter when RSI(2) < entry and close > 200-day average. Exit when close > 5-day average.
    """
    cols = [c for c in closes.columns if c not in exclude]
    c = closes[cols]
    r = rsi(c, 2)
    trend_ok = c > c.rolling(trend_sma).mean()
    exit_now = c > c.rolling(exit_sma).mean()

    w = pd.DataFrame(0.0, index=c.index, columns=cols)
    holding = set()
    for i, day in enumerate(c.index):
        holding = {s for s in holding if not exit_now.at[day, s]}
        slots = max_positions - len(holding)
        if slots > 0:
            cand = r.loc[day][(r.loc[day] < entry) & trend_ok.loc[day]].drop(list(holding), errors="ignore")
            holding |= set(cand.nsmallest(slots).index)
        for s in holding:
            w.iat[i, cols.index(s)] = 1.0 / max_positions
    return w.reindex(columns=closes.columns, fill_value=0.0)


def trend_following(closes, fast=50, slow=200, exclude=("SPY",)):
    """Hold each stock (equal slot size) while it's above its 200-day average and the 50 is above the 200."""
    cols = [c for c in closes.columns if c not in exclude]
    c = closes[cols]
    on = (c > c.rolling(slow).mean()) & (c.rolling(fast).mean() > c.rolling(slow).mean())
    w = on.astype(float) / len(cols)
    return w.reindex(columns=closes.columns, fill_value=0.0)


def _month_end(index):
    s = index.to_series()
    return (s.groupby(index.to_period("M")).transform("max") == s).values


def _to_weights(closes, exposure, sym, cash):
    """Put `exposure` (0..1) in `sym` and the rest in the cash ETF."""
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    w[sym] = exposure
    w[cash] = (1 - exposure) * closes[cash].notna()
    return w


def trend_exposure(closes, sym="SPY", sma=200, monthly=False):
    """1 while price is above its moving average, else 0. Stays invested until the average exists."""
    c = closes[sym]
    avg = c.rolling(sma).mean()
    on = (c > avg).astype(float).where(avg.notna(), 1.0)
    if monthly:
        on = on.where(_month_end(closes.index)).ffill().fillna(1.0)
    return on


def vol_exposure(closes, sym="SPY", target=0.15, lookback=20):
    """Scale exposure so recent volatility matches `target`; never above 100%, in 10% steps."""
    vol = closes[sym].pct_change().rolling(lookback).std() * np.sqrt(252)
    exp = (target / vol).clip(upper=1.0).fillna(1.0)
    return np.floor(exp * 10) / 10


def trend_filter(closes, sym="SPY", cash="BIL", sma=200, monthly=False):
    return _to_weights(closes, trend_exposure(closes, sym, sma, monthly), sym, cash)


def vol_target(closes, sym="SPY", cash="BIL", target=0.15):
    return _to_weights(closes, vol_exposure(closes, sym, target), sym, cash)


def trend_and_vol(closes, sym="SPY", cash="BIL", sma=200, target=0.15):
    exp = trend_exposure(closes, sym, sma, monthly=True) * vol_exposure(closes, sym, target)
    return _to_weights(closes, exp, sym, cash)


# Hold SPY, step into T-bills (BIL) when risk is high. Settings fixed before testing.
RISK_STRATEGIES = {
    "SPY buy & hold (benchmark)": lambda c: buy_and_hold(c, "SPY"),
    "60/40 SPY/IEF (benchmark)": lambda c: fixed_mix(c, {"SPY": 0.6, "IEF": 0.4}),
    "200-day filter, checked daily": lambda c: trend_filter(c, monthly=False),
    "200-day filter, checked monthly": lambda c: trend_filter(c, monthly=True),
    "Volatility target 15%": vol_target,
    "Monthly 200-day filter + vol target": trend_and_vol,
}

ETF_STRATEGIES = {
    "SPY buy & hold (benchmark)": lambda c: buy_and_hold(c, "SPY"),
    "60/40 SPY/IEF (benchmark)": lambda c: fixed_mix(c, {"SPY": 0.6, "IEF": 0.4}),
    "Equal-weight ETFs (benchmark)": lambda c: equal_weight(c, exclude=()),
    "Momentum rotation (top 3)": lambda c: momentum_rotation(c, top=3, regime=None, exclude=()),
    "RSI(2) mean reversion": lambda c: rsi2_mean_reversion(c, exclude=()),
    "Trend following 50/200": lambda c: trend_following(c, exclude=()),
}

STRATEGIES = {
    "SPY buy & hold (benchmark)": lambda c: buy_and_hold(c, "SPY"),
    "Equal-weight universe (benchmark)": equal_weight,
    "Momentum rotation": momentum_rotation,
    "RSI(2) mean reversion": rsi2_mean_reversion,
    "Trend following 50/200": trend_following,
}
