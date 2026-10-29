"""H4 (stocks in play: gaps on heavy volume) and H5 (large-cap weekly reversal) from RESEARCH.md.

Needs data_cache/universe/ from download_universe.py.
    python research_h4_h5.py             # development + validation
    python research_h4_h5.py --holdout   # also the holdout (only for hypotheses that passed)

Significance is measured on the daily average of all trades taken that day (trades on the same day are
correlated), which is stricter than treating every trade as independent.
Data cleaning (fixed before results): drop bars with non-positive prices, and gap/holding returns beyond
+/-300%, which in this data are almost always ticker reuse or bad prints rather than real trades.
"""
import argparse
import pathlib

import numpy as np
import pandas as pd

from run import PERIODS

DATA = pathlib.Path(__file__).parent / "data_cache" / "universe"
GAP_COST = 2 * 10 / 1e4      # 10 bps per side
LARGE_COST = 2 * 5 / 1e4     # 5 bps per side


def load():
    frames = [pd.read_csv(p, parse_dates=["date"]) for p in sorted(DATA.glob("chunk_*.csv.gz"))]
    df = pd.concat([f for f in frames if len(f)], ignore_index=True)
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    g = df.groupby("symbol", sort=False)
    df["prev_close"] = g["close"].shift(1)
    df["gap"] = df["open"] / df["prev_close"] - 1
    df["avg_vol"] = g["volume"].transform(lambda v: v.shift(1).rolling(20).mean())
    df["avg_dollar_vol"] = g.apply(lambda x: (x["close"] * x["volume"]).shift(1).rolling(20).mean(),
                                   include_groups=False).reset_index(level=0, drop=True)
    df["vol_ratio"] = df["volume"] / df["avg_vol"]
    df["intraday"] = df["close"] / df["open"] - 1
    df["fwd5"] = g["close"].shift(-5) / df["close"] - 1
    return df


def period_label(dates, include_holdout):
    out = pd.Series(None, index=dates.index, dtype=object)
    for name, (a, b) in PERIODS.items():
        if name == "holdout" and not include_holdout:
            continue
        out[(dates >= a) & (dates <= b)] = name
    return out


def trade_stats(trades):
    daily = trades.groupby("date")["ret"].mean()
    t_daily = daily.mean() / daily.std() * np.sqrt(len(daily)) if len(daily) > 1 else np.nan
    return {"trades": len(trades), "days": len(daily), "mean_per_trade": trades["ret"].mean(),
            "win_rate": (trades["ret"] > 0).mean(), "t_stat_daily": t_daily}


def h4(df, include_holdout):
    ok = (df["prev_close"] > 5) & (df["avg_dollar_vol"] > 10e6) & (df["vol_ratio"] >= 2)
    up = ok & (df["gap"] >= 0.04) & (df["gap"] <= 3)
    down = ok & (df["gap"] <= -0.04) & (df["gap"] >= -0.9)
    sane_intraday = df["intraday"].abs() <= 3
    sane_fwd = df["fwd5"].abs() <= 3
    tests = {
        "H4a Gap and go (up): long open->close": (up & sane_intraday, df["intraday"]),
        "H4b Gap fade (up): short open->close": (up & sane_intraday, -df["intraday"]),
        "H4c Gap and go (down): short open->close": (down & sane_intraday, -df["intraday"]),
        "H4d Gap-down bounce: long open->close": (down & sane_intraday, df["intraday"]),
        "H4e Post-gap drift (up): long 5 days": (up & sane_fwd, df["fwd5"]),
        "H4f Post-gap drift (down): short 5 days": (down & sane_fwd, -df["fwd5"]),
    }
    rows = []
    for name, (mask, ret) in tests.items():
        t = pd.DataFrame({"date": df.loc[mask, "date"], "ret": ret[mask] - GAP_COST}).dropna()
        t["period"] = period_label(t["date"], include_holdout)
        for p, g in t.dropna(subset=["period"]).groupby("period"):
            rows.append({"hypothesis": name, "period": p, **trade_stats(g)})
    out = pd.DataFrame(rows).set_index(["hypothesis", "period"])
    dev = out.xs("development", level="period")
    val = out.xs("validation", level="period")
    passed = ((dev["mean_per_trade"] > 0) & (dev["t_stat_daily"] > 2) & (dev["trades"] >= 100)
              & (val["mean_per_trade"] > 0) & (val["t_stat_daily"] > 1.5) & (val["trades"] >= 100))
    out["PASS"] = out.index.get_level_values(0).map(lambda h: "yes" if passed.get(h, False) else "")
    return out


def h5(df, include_holdout):
    """Weekly: among the 200 most liquid stocks, hold the 10 worst 5-day performers for a week."""
    close = df.pivot(index="date", columns="symbol", values="close")
    dvol = df.pivot(index="date", columns="symbol", values="avg_dollar_vol")
    fridays = close.index.to_series().groupby(close.index.to_period("W-FRI")).transform("max") == close.index
    fri = close.index[fridays.values]
    rows = []
    for d0, d1 in zip(fri[:-1], fri[1:]):
        liquid = dvol.loc[d0].dropna().nlargest(200).index
        past = (close.loc[d0, liquid] / close.shift(5).loc[d0, liquid] - 1).dropna()
        fwd = (close.loc[d1, liquid] / close.loc[d0, liquid] - 1).dropna()
        fwd = fwd[fwd.abs() <= 3]
        losers = past.nsmallest(10).index.intersection(fwd.index)
        if len(losers) and len(fwd):
            rows.append({"date": d1, "reversal": fwd[losers].mean() - LARGE_COST, "basket": fwd.mean()})
    w = pd.DataFrame(rows).set_index("date")
    res = []
    for p, (a, b) in PERIODS.items():
        if p == "holdout" and not include_holdout:
            continue
        x = w[(w.index >= a) & (w.index <= b)]
        for col in ("reversal", "basket"):
            r = x[col]
            res.append({"strategy": "H5 Large-cap weekly reversal" if col == "reversal" else "Equal-weight 200 liquid (benchmark)",
                        "period": p, "annual_return": (1 + r).prod() ** (52 / len(r)) - 1,
                        "sharpe": r.mean() / r.std() * np.sqrt(52), "max_drawdown": ((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min()})
    return pd.DataFrame(res).set_index(["strategy", "period"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    df = load()
    print(f"Loaded {df['symbol'].nunique()} symbols, {len(df):,} daily bars")
    r4 = h4(df, args.holdout)
    r4.to_csv("results/research_h4.csv")
    pd.set_option("display.width", 200)
    print(r4.round(4).to_string())
    r5 = h5(df, args.holdout)
    r5.to_csv("results/research_h5.csv")
    print(r5.round(3).to_string())


if __name__ == "__main__":
    main()
