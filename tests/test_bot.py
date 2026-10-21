"""Offline checks of the bot's order planning.  Run with:  python tests/test_bot.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bot import plan_orders  # noqa: E402

PRICES = {"SPY": 500.0, "BIL": 100.0}


def test_first_run_buys_both():
    orders = plan_orders(100_000, {}, PRICES, 0.8)
    assert orders == [{"symbol": "SPY", "qty": 156, "side": "buy"}, {"symbol": "BIL", "qty": 196, "side": "buy"}]


def test_never_spends_more_than_equity():
    for exposure in (0.0, 0.3, 1.0):
        orders = plan_orders(100_000, {}, PRICES, exposure)
        assert sum(o["qty"] * PRICES[o["symbol"]] for o in orders) <= 100_000


def test_small_drift_is_ignored():
    assert plan_orders(100_000, {"SPY": 156, "BIL": 196}, PRICES, 0.8) == []


def test_derisking_sells_before_buying():
    orders = plan_orders(100_000, {"SPY": 196, "BIL": 0}, PRICES, 0.3)
    assert orders[0] == {"symbol": "SPY", "qty": 138, "side": "sell"}
    assert orders[1]["side"] == "buy" and orders[1]["symbol"] == "BIL"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
