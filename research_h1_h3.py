"""H1-H3 from RESEARCH.md: calendar effects on SPY, sector reversal, sector momentum.

    python research_h1_h3.py             # development + validation
    python research_h1_h3.py --holdout   # also the holdout (only for hypotheses that passed)
"""
import argparse
import datetime as dt

import numpy as np
import pandas as pd
import requests

import backtest
from data import load_daily, to_panel
from run import PERIODS

COST = 5 / 1e4
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]


def trading_calendar(start, end):
    r = requests.get("https://paper-api.alpaca.markets/v2/calendar", params={"start": start, "end": end}, timeout=30)
    r.raise_for_status()
    return pd.DatetimeIndex([d["date"] for d in r.json()])


def timing_returns(spy_close, spy_open, bil_ret, in_market):
    """Close-to-close: hold SPY on days where in_market is True (decided in advance), else BIL; cost per switch."""
    ret = spy_close.pct_change()
    held = in_market.astype(float)
    switches = held.diff().abs().fillna(held.iloc[0])
    return (held * ret + (1 - held) * bil_ret - switches * COST).fillna(0.0)


def h1a_turn_of_month(close, opn, bil_ret):
    days = close.index
    month = days.to_period("M")
    n_in_month = pd.Series(1, index=days).groupby(month).cumsum()
    # Returns earned on trading days 1-3 of each month (held from the prior month's last close).
    return timing_returns(close, opn, bil_ret, pd.Series(n_in_month.values <= 3, index=days))


def h1b_overnight(close, opn, bil_ret):
    overnight = opn / close.shift(1) - 1
    return (overnight - 2 * COST).fillna(0.0)


def h1c_pre_holiday(close, opn, bil_ret, calendar):
    days = close.index
    weekdays = pd.bdate_range(days[0], days[-1] + pd.Timedelta(days=10))
    holidays = weekdays.difference(calendar)
    pos = pd.Series(range(len(calendar)), index=calendar)
    hold = pd.Series(False, index=days)
    for h in holidays:
        before = calendar[calendar < h]
        if len(before):
            hold.loc[hold.index == before[-1]] = True   # earn the return of the day before the holiday
    return timing_returns(close, opn, bil_ret, hold)


def weekly_rotation(closes, score, top, rebalance):
    """Equal-weight the `top` symbols by score on rebalance days, held until the next rebalance."""
    ret = closes.pct_change()
    w = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    for d in closes.index[rebalance]:
        s = score.loc[d].dropna()
        if len(s) >= top:
            row = pd.Series(0.0, index=closes.columns)
            row[s.nlargest(top).index] = 1.0 / top
            w.loc[d] = row
    w = w.ffill().fillna(0.0)
    held = w.shift(1).fillna(0.0)
    turnover = held.diff().abs().sum(axis=1).fillna(0.0)
    return ((held * ret).sum(axis=1) - turnover * COST).fillna(0.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    data = load_daily(["SPY", "BIL"] + SECTORS, "2015-01-01", end)
    close, opn = to_panel(data, "close"), to_panel(data, "open")
    calendar = trading_calendar("2015-01-01", end)
    spy_c, spy_o = close["SPY"], opn["SPY"]
    bil_ret = close["BIL"].pct_change().fillna(0.0)

    sec = close[SECTORS]
    fridays = sec.index.to_series().groupby(sec.index.to_period("W-FRI")).transform("max") == sec.index
    month_end = sec.index.to_series().groupby(sec.index.to_period("M")).transform("max") == sec.index

    series = {
        "SPY buy & hold (benchmark)": spy_c.pct_change().fillna(0.0),
        "H1a Turn of month": h1a_turn_of_month(spy_c, spy_o, bil_ret),
        "H1b Overnight": h1b_overnight(spy_c, spy_o, bil_ret),
        "H1c Pre-holiday": h1c_pre_holiday(spy_c, spy_o, bil_ret, calendar),
        "Equal-weight sectors (benchmark)": weekly_rotation(sec, pd.DataFrame(1.0, index=sec.index, columns=SECTORS), 9, fridays.values),
        "H2 Sector weekly reversal": weekly_rotation(sec, -sec.pct_change(5), 3, fridays.values),
        "H3 Sector momentum": weekly_rotation(sec, sec.shift(21) / sec.shift(252) - 1, 3, month_end.values),
    }
    periods = ["development", "validation"] + (["holdout"] if args.holdout else [])
    rows = []
    for name, r in series.items():
        for p in periods:
            a, b = PERIODS[p]
            m = backtest.metrics(r[(r.index >= a) & (r.index <= b)])
            rows.append({"strategy": name, "period": p, "cagr": m["cagr"], "volatility": m["volatility"],
                         "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"]})
    t = pd.DataFrame(rows).set_index(["strategy", "period"])
    t.to_csv("results/research_h1_h3.csv")
    for c in ("cagr", "volatility", "max_drawdown"):
        t[c] = t[c].map(lambda x: f"{x:.1%}")
    t["sharpe"] = t["sharpe"].map(lambda x: f"{x:.2f}")
    print(t.to_string())


if __name__ == "__main__":
    main()
