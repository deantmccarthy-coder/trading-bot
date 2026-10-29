"""H6 from RESEARCH.md: gap and go without look-ahead.

    python research_h6.py fetch          # download the 9:30-9:45 bar for every gap-up event (resumable)
    python research_h6.py                # evaluate H6a and H6b on development + validation
    python research_h6.py --holdout      # also the holdout (only if a hypothesis passed)
"""
import argparse
import pathlib

import pandas as pd
import requests

from research_h4_h5 import GAP_COST, load, period_label, trade_stats

CACHE = pathlib.Path(__file__).parent / "data_cache" / "opening_bars"
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"


def events(df):
    ok = (df["prev_close"] > 5) & (df["avg_dollar_vol"] > 10e6)
    up = ok & (df["gap"] >= 0.04) & (df["gap"] <= 3) & (df["intraday"].abs() <= 3)
    return df.loc[up, ["date", "symbol", "open", "close", "avg_vol"]].reset_index(drop=True)


def fetch_opening_bars(ev):
    """First 15-minute bar (9:30-9:45 New York) for each event, cached per month."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for month, grp in ev.groupby(ev["date"].dt.to_period("M")):
        path = CACHE / f"{month}.csv"
        if path.exists():
            continue
        rows = []
        for day, g in grp.groupby("date"):
            syms = sorted(g["symbol"].unique())
            start = pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(hours=9, minutes=30)
            for i in range(0, len(syms), 200):
                params = {"symbols": ",".join(syms[i:i + 200]), "timeframe": "15Min", "feed": "sip",
                          "start": start.isoformat(), "end": (start + pd.Timedelta(minutes=14)).isoformat(),
                          "adjustment": "all", "limit": 10000}
                r = requests.get(BARS_URL, params=params, timeout=60)
                r.raise_for_status()
                for sym, bars in (r.json().get("bars") or {}).items():
                    for b in bars:
                        rows.append({"date": day, "symbol": sym, "open15": b["o"], "close15": b["c"], "vol15": b["v"]})
        pd.DataFrame(rows, columns=["date", "symbol", "open15", "close15", "vol15"]).to_csv(path, index=False)
        print(f"fetched {month}", flush=True)


def evaluate(ev, include_holdout):
    rows = []
    # H6a: every 4%+ gap-up, open to close
    a = pd.DataFrame({"date": ev["date"], "ret": ev["close"] / ev["open"] - 1 - GAP_COST})
    a["period"] = period_label(a["date"], include_holdout)
    for p, g in a.dropna(subset=["period"]).groupby("period"):
        rows.append({"hypothesis": "H6a Gap and go, no volume filter", "period": p, **trade_stats(g)})
    # H6b: opening 15-minute volume >= 20% of average daily volume, buy at 9:45, sell at the close
    bars = pd.concat([pd.read_csv(p, parse_dates=["date"]) for p in sorted(CACHE.glob("*.csv"))])
    b = ev.merge(bars, on=["date", "symbol"], how="inner")
    b = b[(b["vol15"] >= 0.2 * b["avg_vol"]) & (b["close15"] > 0)]
    b = pd.DataFrame({"date": b["date"], "ret": b["close"] / b["close15"] - 1 - GAP_COST})
    b["period"] = period_label(b["date"], include_holdout)
    for p, g in b.dropna(subset=["period"]).groupby("period"):
        rows.append({"hypothesis": "H6b Gap and go, opening-volume filter, entry 9:45", "period": p, **trade_stats(g)})
    out = pd.DataFrame(rows).set_index(["hypothesis", "period"])
    dev, val = out.xs("development", level="period"), out.xs("validation", level="period")
    passed = ((dev["mean_per_trade"] > 0) & (dev["t_stat_daily"] > 2) & (dev["trades"] >= 100)
              & (val["mean_per_trade"] > 0) & (val["t_stat_daily"] > 1.5) & (val["trades"] >= 100))
    out["PASS"] = out.index.get_level_values(0).map(lambda h: "yes" if passed.get(h, False) else "")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?", default="evaluate", choices=["fetch", "evaluate"])
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    ev = events(load())
    print(f"{len(ev):,} gap-up events", flush=True)
    if args.action == "fetch":
        fetch_opening_bars(ev)
        print("done", flush=True)
        return
    out = evaluate(ev, args.holdout)
    out.to_csv("results/research_h6.csv")
    print(out.round(4).to_string())


if __name__ == "__main__":
    main()
