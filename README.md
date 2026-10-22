# trading-bot

Research engine and an Alpaca **paper-trading** bot.

## The bot (`bot.py`)
Holds SPY with volatility targeting (target 15% annual volatility, exposure in 10% steps, never above 100%);
the rest sits in T-bills (BIL). Runs once per trading day during market hours.

    python bot.py --dry-run   # show the plan, place nothing
    python bot.py             # trade the PAPER account

Safety: paper endpoint only; trades only SPY and BIL; never borrows; trades at most once per day (it checks Alpaca for
today's bot orders); stops trading if equity falls 25% below its peak in Alpaca's equity history. To re-arm the circuit
breaker after a review, add a file `BREAKER_RESET` containing a date (YYYY-MM-DD); the peak is then measured from it.

**Kill switch:** add a file named `KILL` to the repository root (on github.com: Add file → Create new file → name it
`KILL` → Commit). The bot does nothing while it exists. Delete the file to resume.

The bot keeps no files between runs: Alpaca's order and equity history is the record, so it can run from a fresh copy
of this public repository each day. Local runs also write `logs/` (not committed).

## Research engine

    python run.py --universe stocks|etfs|risk     # development + validation periods
    python tests/test_engine.py && python tests/test_bot.py

Credentials come from the environment's network secrets (APCA-API-KEY-ID / APCA-API-SECRET-KEY headers for
*.alpaca.markets) or the APCA_API_KEY_ID / APCA_API_SECRET_KEY environment variables. Never commit keys.
