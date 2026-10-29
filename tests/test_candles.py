"""Checks of the candlestick simulator.  Run with:  python tests/test_candles.py"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import candles  # noqa: E402

DAYS = pd.bdate_range("2020-01-01", periods=30)


def frame(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=DAYS[:len(rows)])
    df["volume"] = 1000
    df["atr"] = 1.0
    return df


def flat(n):
    return [[100, 100.5, 99.5, 100]] * n


def test_long_hits_target():
    # Signal bar 5 (low 99.5). Entry next open 100, stop 99.4, risk 0.6, target 101.2.
    rows = flat(6) + [[100, 101.5, 99.8, 101.3]] + flat(5)
    date, r = candles.simulate(frame(rows), 5, side=1, span=1, max_hold=10)
    assert date == DAYS[6]
    assert np.isclose(r, 2.0 - 2 * 5 / 1e4 * 100 / 0.6)


def test_stop_wins_when_both_touched():
    rows = flat(6) + [[100, 102, 99, 100]] + flat(5)
    _, r = candles.simulate(frame(rows), 5, side=1, span=1, max_hold=10)
    assert r < -0.99


def test_gap_through_stop_fills_at_open():
    rows = flat(6) + [[100, 100.2, 99.9, 100]] + [[98, 98.5, 97.5, 98]] + flat(3)
    _, r = candles.simulate(frame(rows), 5, side=1, span=1, max_hold=10)
    assert r < -3  # (98 - 100) / 0.6 minus costs


def test_short_mirror():
    rows = flat(6) + [[100, 100.2, 98.5, 98.7]] + flat(5)
    _, r = candles.simulate(frame(rows), 5, side=-1, span=1, max_hold=10)
    assert np.isclose(r, 2.0 - 2 * 5 / 1e4 * 100 / 0.6)


def test_intraday_trade_never_held_overnight():
    idx = pd.to_datetime(["2024-01-02 15:45", "2024-01-02 15:50", "2024-01-02 15:55", "2024-01-03 09:30", "2024-01-03 09:35"])
    df = pd.DataFrame({"open": [100, 100, 100, 110, 110], "high": [100.5, 100.5, 100.5, 111, 111],
                       "low": [99.5, 99.5, 99.5, 109, 109], "close": [100, 100, 100.2, 110, 110]}, index=idx)
    df["atr"] = 1.0
    day = df.index.normalize().to_numpy()
    _, r = candles.simulate(df, 1, side=1, span=1, max_hold=10, day=day)
    assert np.isclose(r, 0.2 / 0.6 - 2 * 5 / 1e4 * 100 / 0.6)   # closed at 15:55 bar's close, not next day's gap
    assert candles.simulate(df, 2, side=1, span=1, max_hold=10, day=day) is None   # no entry on the next morning


def test_patterns_ignore_future_bars():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2018-01-01", periods=400)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    o = c * (1 + rng.normal(0, 0.005, 400))
    df = pd.DataFrame({"open": o, "close": c, "high": np.maximum(o, c) * 1.005, "low": np.minimum(o, c) * 0.995,
                       "volume": rng.integers(1000, 2000, 400).astype(float)}, index=idx)
    changed = df.copy()
    changed.iloc[301:] *= 1.3
    for name, (mask, _, _) in candles.patterns(df).items():
        assert mask.iloc[:301].equals(candles.patterns(changed)[name][0].iloc[:301]), name
    for name, mask in candles.context(df).items():
        assert mask.iloc[:301].equals(candles.context(changed)[name].iloc[:301]), name


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
