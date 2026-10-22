"""Paper-trading bot: SPY with volatility targeting, the rest in T-bills (BIL).

Run once per trading day, during market hours (e.g. 9:45 New York time):
    python bot.py --dry-run   # show what it would do, place nothing
    python bot.py             # place the orders in the PAPER account

Safety:
  - Talks only to Alpaca's PAPER endpoint. Live trading needs a deliberate code change.
  - Only ever trades SPY and BIL, never more than 100% of equity, never borrows.
  - Kill switch: create a file named KILL next to this script and the bot does nothing.
  - Circuit breaker: if equity falls 25% below its high-water mark (from Alpaca's equity history), the bot stops
    trading. To re-arm after a review, add a file BREAKER_RESET containing a date (YYYY-MM-DD); the high-water mark
    is then measured from that date on.
  - Trades at most once per day: it checks Alpaca for today's bot orders (use --force to override).

The bot keeps no files between runs; Alpaca's order and equity history is the record.
"""
import argparse
import datetime as dt
import json
import logging
import pathlib
import sys
import time

import pandas as pd
import requests

from data import _fetch
from strategies import vol_exposure

PAPER_URL = "https://paper-api.alpaca.markets"
SYMBOL, CASH = "SPY", "BIL"
TARGET_VOL = 0.15
CASH_BUFFER = 0.02          # keep 2% uninvested so orders never exceed buying power
REBALANCE_BAND = 0.05       # skip trades that would move a weight by less than 5% of equity
MAX_DRAWDOWN = 0.25         # circuit breaker

HERE = pathlib.Path(__file__).parent
LOG_DIR = HERE / "logs"
KILL_FILE = HERE / "KILL"
BREAKER_RESET_FILE = HERE / "BREAKER_RESET"
ORDER_PREFIX = "volbot"

log = logging.getLogger("bot")


def api(method, path, **kwargs):
    r = requests.request(method, PAPER_URL + path, timeout=30, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text}")
    return r.json() if r.text else None


def traded_today(today):
    """True if Alpaca already has an order from this bot dated today."""
    orders = api("GET", "/v2/orders", params={"status": "all", "after": f"{today - dt.timedelta(days=1)}T23:59:59Z",
                                               "limit": 100})
    return any((o.get("client_order_id") or "").startswith(f"{ORDER_PREFIX}-{today}") for o in orders)


def peak_equity(current):
    """High-water mark from Alpaca's daily equity history (optionally only since the BREAKER_RESET date)."""
    hist = api("GET", "/v2/account/portfolio/history", params={"period": "1A", "timeframe": "1D"})
    since = None
    if BREAKER_RESET_FILE.exists():
        since = dt.datetime.fromisoformat(BREAKER_RESET_FILE.read_text().strip()).replace(tzinfo=dt.timezone.utc)
    values = [e for t, e in zip(hist.get("timestamp") or [], hist.get("equity") or [])
              if e and (since is None or dt.datetime.fromtimestamp(t, dt.timezone.utc) >= since)]
    return max(values + [current])


def target_exposure(today):
    """SPY exposure from daily closes up to and including yesterday (same rule as the backtest)."""
    start = (today - dt.timedelta(days=90)).isoformat()
    end = (today - dt.timedelta(days=1)).isoformat()
    bars = _fetch([SYMBOL], start, end, feed="sip")[SYMBOL]
    closes = pd.DataFrame({SYMBOL: bars["close"]})
    return float(vol_exposure(closes, SYMBOL, TARGET_VOL).iloc[-1]), float(bars["close"].iloc[-1]), bars.index[-1]


def plan_orders(equity, positions, prices, exposure):
    """Whole-share orders that move the account toward the target weights. Sells come first."""
    investable = equity * (1 - CASH_BUFFER)
    targets = {SYMBOL: investable * exposure, CASH: investable * (1 - exposure)}
    orders = []
    for sym, target_value in targets.items():
        held = positions.get(sym, 0)
        current_value = held * prices[sym]
        if abs(target_value - current_value) / equity < REBALANCE_BAND:
            continue
        qty = int(target_value / prices[sym] + 1e-9) - held
        if qty != 0:
            orders.append({"symbol": sym, "qty": abs(qty), "side": "buy" if qty > 0 else "sell"})
    return sorted(orders, key=lambda o: o["side"] != "sell")


def wait_for_fill(order_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        o = api("GET", f"/v2/orders/{order_id}")
        if o["status"] in ("filled", "canceled", "expired", "rejected"):
            return o
        time.sleep(3)
    return api("GET", f"/v2/orders/{order_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print the plan, place no orders")
    parser.add_argument("--force", action="store_true", help="trade even if the bot already traded today")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "bot.log"), logging.StreamHandler(sys.stdout)])

    if KILL_FILE.exists():
        log.warning("KILL file present: doing nothing.")
        return

    clock = api("GET", "/v2/clock")
    if not clock["is_open"]:
        log.info("Market is closed (next open %s). Nothing to do.", clock["next_open"])
        return
    today = dt.date.fromisoformat(clock["timestamp"][:10])
    if traded_today(today) and not args.force and not args.dry_run:
        log.info("Already traded today. Nothing to do.")
        return

    account = api("GET", "/v2/account")
    equity = float(account["equity"])
    peak = peak_equity(equity)
    if equity < peak * (1 - MAX_DRAWDOWN):
        log.error("CIRCUIT BREAKER: equity %.2f is more than %.0f%% below peak %.2f. Not trading. "
                  "Review, then add a BREAKER_RESET file to re-arm.", equity, MAX_DRAWDOWN * 100, peak)
        return

    positions = {p["symbol"]: int(float(p["qty"])) for p in api("GET", "/v2/positions")}
    others = set(positions) - {SYMBOL, CASH}
    if others:
        log.warning("Ignoring positions the bot does not manage: %s", sorted(others))

    exposure, spy_close, as_of = target_exposure(today)
    bil = _fetch([CASH], (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=1)).isoformat(), "sip")
    prices = {SYMBOL: spy_close, CASH: float(bil[CASH]["close"].iloc[-1])}
    orders = plan_orders(equity, positions, prices, exposure)

    decision = {
        "date": today.isoformat(), "signal_as_of": str(as_of.date()), "equity": equity,
        "target_spy_exposure": exposure, "positions_before": positions, "orders": orders, "dry_run": args.dry_run,
    }
    log.info("Equity $%.2f | target SPY %.0f%% / BIL %.0f%% | positions %s | orders %s",
             equity, exposure * 100, (1 - exposure) * 100, positions, orders or "none")

    if not args.dry_run:
        for o in orders:
            assert o["symbol"] in (SYMBOL, CASH)
            assert o["qty"] * prices[o["symbol"]] <= equity, "order larger than the whole account"
            placed = api("POST", "/v2/orders", json={**o, "type": "market", "time_in_force": "day",
                                                      "client_order_id": f"{ORDER_PREFIX}-{today}-{o['symbol']}-{o['side']}"})
            result = wait_for_fill(placed["id"])
            log.info("%s %s %s: %s at %s", o["side"], o["qty"], o["symbol"], result["status"],
                     result.get("filled_avg_price"))
            o["status"], o["fill_price"] = result["status"], result.get("filled_avg_price")

    with open(LOG_DIR / "decisions.jsonl", "a") as f:
        f.write(json.dumps(decision) + "\n")


if __name__ == "__main__":
    main()
