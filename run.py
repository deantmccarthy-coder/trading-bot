"""Download data, run every strategy, and report results per period.

    python run.py                    # 40 large US stocks: development + validation periods
    python run.py --universe etfs    # diversified ETFs (no survivorship bias)
    python run.py --holdout          # also unlock the final holdout period (do this ONCE, at the very end)
"""
import argparse
import datetime as dt
import pathlib

import pandas as pd

import backtest
from data import load_daily, to_panel
from strategies import ETF_STRATEGIES, RISK_STRATEGIES, SHORT_STRATEGIES, STRATEGIES

# Today's large caps: convenient, but survivorship-biased (we already know these became winners).
STOCKS = [
    "SPY",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "V",
    "MA", "UNH", "XOM", "JNJ", "PG", "HD", "COST", "LLY", "MRK", "ABBV",
    "PEP", "KO", "WMT", "BAC", "CVX", "ADBE", "CRM", "NFLX", "AMD", "ORCL",
    "CSCO", "INTC", "QCOM", "TXN", "IBM", "CAT", "GE", "HON", "MCD", "NKE",
]

# Diversified ETFs that all traded before 2016: no survivorship bias.
ETFS = [
    "SPY", "QQQ", "IWM", "EFA", "EEM",                          # stocks: US large, tech, small, developed, emerging
    "TLT", "IEF",                                               # bonds: long and intermediate Treasuries
    "GLD", "DBC", "VNQ",                                        # gold, commodities, real estate
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB",  # US sectors
]

UNIVERSES = {
    "stocks": (STOCKS, STRATEGIES),
    "etfs": (ETFS, ETF_STRATEGIES),
    "risk": (["SPY", "BIL", "IEF"], RISK_STRATEGIES),  # BIL = T-bills, the "cash" that still earns interest
    "short": (["SPY", "BIL", "SH"], SHORT_STRATEGIES),  # SH = -1x daily S&P 500 inverse ETF
}

# Decided before looking at any results. Strategies are designed on DEVELOPMENT, checked on VALIDATION,
# and the HOLDOUT stays locked until a single final strategy has been chosen.
PERIODS = {
    "development": ("2016-01-01", "2021-12-31"),
    "validation": ("2022-01-01", "2024-12-31"),
    "holdout": ("2025-01-01", "2100-01-01"),
}

COST_BPS = 5.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true", help="also report the locked holdout period")
    parser.add_argument("--universe", choices=UNIVERSES, default="stocks")
    args = parser.parse_args()
    symbols, strategies = UNIVERSES[args.universe]

    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    data = load_daily(symbols, "2015-01-01", end)
    opens, closes = to_panel(data, "open"), to_panel(data, "close")
    print(f"Loaded {len(data)} symbols, {closes.index.min().date()} to {closes.index.max().date()}")

    periods = ["development", "validation"] + (["holdout"] if args.holdout else [])
    rows = []
    for name, strat in strategies.items():
        net, held = backtest.run(strat(closes), opens, COST_BPS)
        for p in periods:
            start, stop = PERIODS[p]
            m = backtest.metrics(*backtest.slice_period(net, held, start, stop))
            rows.append({"strategy": name, "period": p, **m})

    table = pd.DataFrame(rows).set_index(["strategy", "period"])
    out = pathlib.Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    table.to_csv(out / f"results_{args.universe}.csv")

    fmt = table.copy()
    for col in ["total_return", "cagr", "volatility", "max_drawdown", "time_invested"]:
        fmt[col] = fmt[col].map(lambda x: f"{x:.1%}")
    for col in ["sharpe", "calmar", "profit_factor_daily"]:
        fmt[col] = fmt[col].map(lambda x: f"{x:.2f}")
    print(fmt.to_string())


if __name__ == "__main__":
    main()
