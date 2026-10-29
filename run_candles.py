"""Backtest candlestick patterns with stops and targets on daily bars.

    python run_candles.py                 # development + validation periods
    python run_candles.py --holdout       # also the locked holdout period (once, at the end)
"""
import argparse
import datetime as dt
import pathlib

import pandas as pd

import candles
from data import load_daily, load_intraday
from run import ETFS, PERIODS, STOCKS

# Decided before looking: a pattern/variant "passes" only if it is profitable in BOTH periods with enough trades.
MIN_TRADES = 30

# 5-minute data is large, so the intraday test uses fewer symbols and recent years, with its own split.
INTRADAY_SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "AMZN"]
INTRADAY_PERIODS = {
    "development": ("2023-01-01", "2024-12-31"),
    "validation": ("2025-01-01", "2025-12-31"),
    "holdout": ("2026-01-01", "2100-01-01"),
}


def run_universe(symbols, max_hold, intraday=False):
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    if intraday:
        data = load_intraday(symbols, "2023-01-01", end)
    else:
        data = load_daily(symbols, "2015-01-01", end)
    rows = []
    for df in data.values():
        rows += candles.backtest_symbol(df.dropna(), max_hold=max_hold, intraday=intraday)
    return pd.DataFrame(rows, columns=["pattern", "variant", "side", "date", "R"])


def period_of(dates, include_holdout, periods=PERIODS):
    out = pd.Series(None, index=dates.index, dtype=object)
    for name, (start, stop) in periods.items():
        if name == "holdout" and not include_holdout:
            continue
        out[(dates >= start) & (dates <= stop)] = name
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--max-hold", type=int, default=None, help="bars before a time exit (10 daily, 12 intraday)")
    parser.add_argument("--intraday", action="store_true", help="5-minute bars, trades closed by end of day")
    args = parser.parse_args()
    max_hold = args.max_hold or (12 if args.intraday else 10)
    periods = INTRADAY_PERIODS if args.intraday else PERIODS
    universes = (("5-minute", INTRADAY_SYMBOLS),) if args.intraday else (("ETFs", ETFS), ("Stocks", STOCKS))

    out_dir = pathlib.Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    for label, symbols in universes:
        trades = run_universe(symbols, max_hold, args.intraday)
        trades["period"] = period_of(trades["date"], args.holdout, periods)
        trades = trades.dropna(subset=["period"])
        tables = {p: candles.summarize(t) for p, t in trades.groupby("period")}
        table = pd.concat(tables, axis=1)
        dev, val = table["development"], table["validation"]
        table["PASS"] = ((dev["avg_R"] > 0) & (val["avg_R"] > 0)
                         & (dev["trades"] >= MIN_TRADES) & (val["trades"] >= MIN_TRADES)).map({True: "yes", False: ""})
        table.to_csv(out_dir / f"candles_{label.lower()}.csv")

        show = pd.DataFrame({
            "dev trades": dev["trades"], "dev win%": (dev["win_rate"] * 100).round(0), "dev avg R": dev["avg_R"].round(3),
            "val trades": val["trades"], "val win%": (val["win_rate"] * 100).round(0), "val avg R": val["avg_R"].round(3),
            "PASS": table["PASS"],
        })
        bars = "5-minute bars, flat by the close" if args.intraday else "daily bars"
        print(f"\n===== {label} ({bars}, stop beyond pattern, target {candles.REWARD_R}R, max hold {max_hold}) =====")
        print(show.to_string())


if __name__ == "__main__":
    main()
