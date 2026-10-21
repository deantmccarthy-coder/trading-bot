"""Checks on synthetic prices that the backtester and strategies behave correctly.

Run with:  python tests/test_engine.py
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import backtest  # noqa: E402
import strategies  # noqa: E402

DAYS = pd.bdate_range("2020-01-01", periods=400)


def test_fully_invested_matches_price_growth():
    opens = pd.DataFrame({"A": 100 * 1.01 ** np.arange(len(DAYS))}, index=DAYS)
    w = pd.DataFrame({"A": 1.0}, index=DAYS)
    net, held = backtest.run(w, opens, cost_bps=0)
    # Day 0 decides, day 1 buys at the open; every later day earns exactly 1% open-to-open.
    assert net.iloc[0] == 0
    assert np.allclose(net.iloc[1:-1], 0.01)


def test_signal_cannot_trade_at_its_own_price():
    # Price jumps 10% between the open of day 50 and day 51. A weight set on day 50 must miss it.
    prices = np.full(len(DAYS), 100.0)
    prices[51:] = 110.0
    opens = pd.DataFrame({"A": prices}, index=DAYS)
    w = pd.DataFrame({"A": 0.0}, index=DAYS)
    w.iloc[50] = 1.0
    net, _ = backtest.run(w, opens, cost_bps=0)
    assert net.abs().sum() == 0


def test_costs_charged_on_turnover():
    opens = pd.DataFrame({"A": np.full(len(DAYS), 100.0)}, index=DAYS)
    w = pd.DataFrame({"A": 0.0}, index=DAYS)
    w.iloc[10:20] = 1.0
    net, held = backtest.run(w, opens, cost_bps=10)
    assert np.isclose(net.sum(), -2 * 10 / 1e4)  # one buy + one sell
    assert backtest.count_trades(held) == 1


def test_strategies_never_lever_up():
    rng = np.random.default_rng(0)
    cols = ["SPY"] + [f"S{i}" for i in range(12)]
    closes = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, (len(DAYS), len(cols))), axis=0)),
                          index=DAYS, columns=cols)
    for name, strat in strategies.STRATEGIES.items():
        w = strat(closes)
        assert (w >= -1e-12).all().all(), name
        assert (w.sum(axis=1) <= 1 + 1e-9).all(), name


def test_risk_strategies_fully_allocated_and_no_lookahead():
    rng = np.random.default_rng(2)
    cols = ["SPY", "BIL", "IEF"]
    a = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, (len(DAYS), 3)), axis=0)),
                     index=DAYS, columns=cols)
    b = a.copy()
    b.iloc[301:] *= 0.5
    for name, strat in strategies.RISK_STRATEGIES.items():
        w = strat(a)
        assert (w >= -1e-12).all().all(), name
        assert np.allclose(w.sum(axis=1), 1.0), name
        pd.testing.assert_frame_equal(w.iloc[:301], strat(b).iloc[:301], obj=name)


def test_strategy_weights_ignore_future_prices():
    # Changing prices after day 300 must not change any weight up to day 300.
    rng = np.random.default_rng(1)
    cols = ["SPY"] + [f"S{i}" for i in range(8)]
    base = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, (len(DAYS), len(cols))), axis=0))
    a = pd.DataFrame(base, index=DAYS, columns=cols)
    b = a.copy()
    b.iloc[301:] *= 1.5
    for name, strat in strategies.STRATEGIES.items():
        pd.testing.assert_frame_equal(strat(a).iloc[:301], strat(b).iloc[:301], obj=name)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
