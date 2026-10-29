"""Daily price data from Alpaca's market data API, cached to disk.

Authentication (free Alpaca account, paper keys are fine), either:
  - the environment's network secrets add the APCA-API-KEY-ID / APCA-API-SECRET-KEY headers, or
  - the environment variables APCA_API_KEY_ID and APCA_API_SECRET_KEY are set.
"""
import os
import pathlib
import time

import pandas as pd
import requests

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
CACHE_DIR = pathlib.Path(__file__).parent / "data_cache"


def _headers():
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        return {}  # the network-secrets proxy adds the auth headers
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _fetch(symbols, start, end, feed, timeframe="1Day"):
    """Download split/dividend-adjusted daily bars for many symbols, following pagination."""
    params = {
        "symbols": ",".join(symbols),
        "timeframe": timeframe,
        "start": start,
        "end": end,
        "adjustment": "all",
        "feed": feed,
        "limit": 10000,
    }
    bars = {s: [] for s in symbols}
    while True:
        r = requests.get(BARS_URL, headers=_headers(), params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(2)
            continue
        r.raise_for_status()
        body = r.json()
        for sym, rows in (body.get("bars") or {}).items():
            bars[sym].extend(rows)
        token = body.get("next_page_token")
        if not token:
            break
        params["page_token"] = token

    out = {}
    for sym, rows in bars.items():
        if not rows:
            continue
        df = pd.DataFrame(rows)
        ts = pd.to_datetime(df["t"]).dt.tz_convert("America/New_York")
        df["date"] = (ts.dt.normalize() if timeframe == "1Day" else ts).dt.tz_localize(None)
        df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        out[sym] = df.set_index("date")[["open", "high", "low", "close", "volume"]].sort_index()
    return out


def load_daily(symbols, start, end, feed="sip"):
    """Return {symbol: DataFrame} of daily OHLCV, using the disk cache when possible.

    The free Alpaca plan serves SIP history up to 15 minutes ago; if SIP is refused we fall back to IEX.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    result, missing = {}, []
    for sym in symbols:
        path = CACHE_DIR / f"{sym}_{feed}_{start}_{end}.csv"
        if path.exists():
            result[sym] = pd.read_csv(path, index_col="date", parse_dates=True)
        else:
            missing.append(sym)

    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        try:
            fetched = _fetch(chunk, start, end, feed)
        except requests.HTTPError as e:
            if feed == "sip" and e.response is not None and e.response.status_code in (402, 403):
                return load_daily(symbols, start, end, feed="iex")
            raise
        for sym, df in fetched.items():
            df.to_csv(CACHE_DIR / f"{sym}_{feed}_{start}_{end}.csv")
            result[sym] = df
    return result


def to_panel(data, field):
    """One wide DataFrame (dates x symbols) for a single field such as 'close'."""
    return pd.DataFrame({sym: df[field] for sym, df in data.items()}).sort_index()


def load_intraday(symbols, start, end, timeframe="5Min", feed="sip"):
    """Regular-hours (9:30-16:00 New York) intraday bars, cached to disk like load_daily."""
    CACHE_DIR.mkdir(exist_ok=True)
    result = {}
    for sym in symbols:
        path = CACHE_DIR / f"{sym}_{feed}_{timeframe}_{start}_{end}.csv"
        if path.exists():
            df = pd.read_csv(path, index_col="date", parse_dates=True)
        else:
            df = _fetch([sym], start, end, feed, timeframe).get(sym)
            if df is None:
                continue
            df = df.between_time("09:30", "15:55")
            df.to_csv(path)
        result[sym] = df
    return result
