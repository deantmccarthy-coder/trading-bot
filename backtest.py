"""Portfolio backtester for daily strategies.

A strategy returns target weights per symbol, decided with information up to each day's close.
Those weights are traded at the NEXT day's open, so a signal can never use the price it trades at.
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def run(weights, opens, cost_bps=5.0):
    """Return daily net returns and the positions actually held.

    weights:  dates x symbols, target weight decided at that day's close (NaN = 0).
    opens:    dates x symbols, opening prices.
    cost_bps: cost per unit of turnover (commission + slippage), in basis points.
    """
    weights = weights.reindex_like(opens).fillna(0.0)
    held = weights.shift(1).fillna(0.0)                 # bought at today's open
    open_to_open = (opens.shift(-1) / opens - 1).fillna(0.0)
    gross = (held * open_to_open).sum(axis=1)
    turnover = held.diff().abs().sum(axis=1)
    turnover.iloc[0] = held.iloc[0].abs().sum()
    net = gross - turnover * cost_bps / 1e4
    return net, held


def count_trades(held):
    """Number of entries: a symbol going from flat to holding."""
    on = held.abs() > 1e-12
    return int((on & ~on.shift(1, fill_value=False)).sum().sum())


def metrics(net, held=None):
    net = net.dropna()
    if len(net) == 0:
        return {}
    equity = (1 + net).cumprod()
    years = len(net) / TRADING_DAYS
    total = equity.iloc[-1] - 1
    cagr = equity.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    vol = net.std() * np.sqrt(TRADING_DAYS)
    sharpe = net.mean() / net.std() * np.sqrt(TRADING_DAYS) if net.std() > 0 else np.nan
    max_dd = (equity / equity.cummax() - 1).min()
    gains, losses = net[net > 0].sum(), -net[net < 0].sum()
    out = {
        "total_return": total,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "calmar": cagr / -max_dd if max_dd < 0 else np.nan,
        "profit_factor_daily": gains / losses if losses > 0 else np.nan,
    }
    if held is not None:
        held = held.loc[net.index]
        out["time_invested"] = (held.abs().sum(axis=1) > 1e-12).mean()
        out["trades"] = count_trades(held)
    return out


def slice_period(net, held, start, end):
    mask = (net.index >= start) & (net.index <= end)
    return net[mask], held[mask]
