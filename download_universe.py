"""Download daily bars for the broad US stock universe (active + delisted) into data_cache/universe/.

Resumable: chunks already on disk are skipped.  python download_universe.py
"""
import datetime as dt
import json
import pathlib
import sys

import pandas as pd
import requests

from data import _fetch

OUT = pathlib.Path(__file__).parent / "data_cache" / "universe"
EXCHANGES = {"NYSE", "NASDAQ", "AMEX"}   # ARCA/BATS listings are mostly ETFs
CHUNK = 100


def universe():
    syms = set()
    for status in ("active", "inactive"):
        r = requests.get("https://paper-api.alpaca.markets/v2/assets",
                         params={"status": status, "asset_class": "us_equity"}, timeout=120)
        r.raise_for_status()
        syms |= {a["symbol"] for a in r.json()
                 if a["exchange"] in EXCHANGES and a["symbol"].isalpha() and len(a["symbol"]) <= 5}
    return sorted(syms)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    syms = universe()
    (OUT / "symbols.json").write_text(json.dumps(syms))
    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    chunks = [syms[i:i + CHUNK] for i in range(0, len(syms), CHUNK)]
    for n, chunk in enumerate(chunks):
        path = OUT / f"chunk_{n:04d}.csv.gz"
        if path.exists():
            continue
        frames = []
        for sym, df in _fetch(chunk, "2015-01-01", end, "sip").items():
            frames.append(df.assign(symbol=sym))
        pd.concat(frames).to_csv(path) if frames else pd.DataFrame().to_csv(path)
        print(f"{n + 1}/{len(chunks)} chunks", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
