"""Backtest selling cash-secured SPY puts each month, using Alpaca's historical option prices (from Feb 2024).

    python options_backtest.py              # development + validation periods
    python options_backtest.py --holdout    # also the locked holdout period (once, at the end)

Rules (fixed before testing):
  - On the first trading day after each monthly expiration, sell puts expiring at the next monthly expiration
    (third Friday), at the strike nearest to SPY x moneyness (1.00 = at the money, 0.95 = about 5% below).
  - Cash-secured: contracts = equity / (strike x 100), fractional so the strategy itself is measured (a real
    $100k account would use XSP, the 1/10-size S&P option, to get close to this). All cash, including premiums,
    earns the T-bill return (BIL).
  - Fill at 3% below the option's daily close (a conservative stand-in for the bid).
  - Held to expiration and settled at intrinsic value against SPY's close; positions are marked to market
    daily at the option's close.
"""
import argparse
import datetime as dt

import numpy as np
import pandas as pd
import requests

import backtest
from data import load_daily

CONTRACTS_URL = "https://paper-api.alpaca.markets/v2/options/contracts"
BARS_URL = "https://data.alpaca.markets/v1beta1/options/bars"
SELL_HAIRCUT = 0.03
PERIODS = {
    "development": ("2024-02-01", "2025-03-31"),
    "validation": ("2025-04-01", "2025-12-31"),
    "holdout": ("2026-01-01", "2100-01-01"),
}


def monthly_expirations(start, end):
    """Third Fridays between start and end."""
    out = []
    for m in pd.date_range(pd.Timestamp(start).replace(day=1), end, freq="MS"):
        fridays = pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="W-FRI")
        out.append(fridays[2])
    return [d for d in out if pd.Timestamp(start) <= d <= pd.Timestamp(end)]


def put_contracts(expiry):
    """All SPY put contracts for one expiration date, from Alpaca (expired and active)."""
    rows = []
    for status in ("inactive", "active"):
        params = {"underlying_symbols": "SPY", "type": "put", "status": status, "limit": 10000,
                  "expiration_date": expiry.date().isoformat()}
        r = requests.get(CONTRACTS_URL, params=params, timeout=30)
        r.raise_for_status()
        rows += r.json().get("option_contracts", [])
    return {float(c["strike_price"]): c["symbol"] for c in rows}


def option_closes(symbol, start, end):
    end = min(end, pd.Timestamp(dt.date.today() - dt.timedelta(days=1)))  # free data stops at yesterday
    params = {"symbols": symbol, "timeframe": "1Day", "start": start.date().isoformat(),
              "end": end.date().isoformat(), "limit": 10000}
    r = requests.get(BARS_URL, params=params, timeout=30)
    r.raise_for_status()
    bars = (r.json().get("bars") or {}).get(symbol, [])
    if not bars:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(b["t"]).tz_convert("America/New_York").normalize().tz_localize(None): b["c"]
                   for b in bars})
    return s.sort_index()


def run_putwrite(spy, bil, moneyness, start="2024-02-01", fractional=True):
    """Daily returns of the put-write strategy, plus a list of per-cycle results."""
    days = spy.index[spy.index >= start]
    bil_ret = bil.pct_change().reindex(days).fillna(0.0)
    expiries = monthly_expirations(days[0], days[-1] + pd.Timedelta(days=40))
    equity, values, cycles = 100_000.0, {}, []
    cash, n, strike, marks, expiry = equity, 0, None, None, None
    entry_day = days[0]
    for d in days:
        cash *= 1 + bil_ret[d]
        if expiry is not None and d >= expiry:  # settle at expiration (or the first trading day after)
            payoff = n * 100 * max(0.0, strike - spy[d])
            cash -= payoff
            cycles.append({"expiry": expiry.date(), "strike": strike, "contracts": round(n, 3),
                           "spy_at_expiry": round(spy[d], 2), "paid_out": round(payoff, 2)})
            n, strike, marks, expiry = 0, None, None, None
            entry_day = d
        if expiry is None and d >= entry_day:
            nxt = [e for e in expiries if e > d + pd.Timedelta(days=20)]
            if nxt:
                e = nxt[0]
                strikes = put_contracts(e)
                if strikes:
                    k = min(strikes, key=lambda s: abs(s - spy[d] * moneyness))
                    closes = option_closes(strikes[k], d, e)
                    if d in closes.index:
                        cnt = cash / (k * 100) if fractional else int(cash // (k * 100))
                        premium = closes[d] * (1 - SELL_HAIRCUT)
                        cash += cnt * 100 * premium
                        n, strike, marks, expiry = cnt, k, closes, e
                        cycles.append({"opened": d.date(), "expiry": e.date(), "strike": k, "contracts": round(cnt, 3),
                                       "premium": round(premium, 2), "spy": round(spy[d], 2)})
        liability = 0.0
        if n:
            mark = marks[:d].iloc[-1] if len(marks[:d]) else 0.0
            liability = n * 100 * mark
        values[d] = cash - liability
    eq = pd.Series(values)
    return eq.pct_change().fillna(0.0), cycles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()

    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    data = load_daily(["SPY", "BIL"], "2023-01-01", end)
    spy, bil = data["SPY"]["close"], data["BIL"]["close"]

    results = {"SPY buy & hold": spy.pct_change().fillna(0.0)}
    for label, m in (("Put-write at the money", 1.00), ("Put-write 5% below", 0.95)):
        rets, cycles = run_putwrite(spy, bil, m)
        results[label] = rets
        pd.DataFrame(cycles).to_csv(f"results/putwrite_{int(m * 100)}.csv", index=False)

    periods = ["development", "validation"] + (["holdout"] if args.holdout else [])
    rows = []
    for name, r in results.items():
        r = r[r.index >= "2024-02-01"]
        for p in periods:
            a, b = PERIODS[p]
            m = backtest.metrics(r[(r.index >= a) & (r.index <= b)])
            rows.append({"strategy": name, "period": p, **{k: m[k] for k in
                         ("total_return", "cagr", "volatility", "sharpe", "max_drawdown")}})
    t = pd.DataFrame(rows).set_index(["strategy", "period"])
    for col in ("total_return", "cagr", "volatility", "max_drawdown"):
        t[col] = t[col].map(lambda x: f"{x:.1%}")
    t["sharpe"] = t["sharpe"].map(lambda x: f"{x:.2f}")
    print(t.to_string())


if __name__ == "__main__":
    main()
