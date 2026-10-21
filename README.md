# trading-bot

Research engine and an Alpaca **paper-trading** bot.

## The bot (`bot.py`)
Holds SPY with volatility targeting (target 15% annual volatility, exposure in 10% steps, never above 100%);
the rest sits in T-bills (BIL). Runs once per trading day during market hours.

    python bot.py --dry-run   # show the plan, place nothing
    python bot.py             # trade the PAPER account

Safety: paper endpoint only; trades only SPY and BIL; never borrows; stops if equity falls 25% below its peak
(`python bot.py --reset-breaker` after review); runs at most once per day.

**Kill switch:** add a file named `KILL` to the repository root (on github.com: Add file → Create new file → name it
`KILL` → Commit). The bot does nothing while it exists. Delete the file to resume.

Every run is recorded in `logs/bot.log` and `logs/decisions.jsonl`; `state/bot_state.json` holds the last run date and
the equity high-water mark.

## Research engine

    python run.py --universe stocks|etfs|risk     # development + validation periods
    python tests/test_engine.py && python tests/test_bot.py

Credentials come from the environment's network secrets (APCA-API-KEY-ID / APCA-API-SECRET-KEY headers for
*.alpaca.markets) or the APCA_API_KEY_ID / APCA_API_SECRET_KEY environment variables. Never commit keys.
