# Edge research: pre-registered hypotheses

Written before any of these tests were run. Rules, periods and pass criteria are fixed here and are not
changed after seeing results. Anything that changes later is recorded as a new hypothesis, not an edit.

Periods (daily data): development 2016-2021, validation 2022-2024, holdout 2025 onward (opened once, only for
hypotheses that pass both earlier periods). Costs: 5 bps per side for SPY/ETFs/large caps, 10 bps per side for
gap stocks. All signals use information available at the decision time; trades fill at the next open or close
as stated.

## H1. Calendar effects on SPY (cash in BIL otherwise)
- **H1a Turn of month:** hold SPY from the close of the last trading day of the month to the close of the
  3rd trading day of the next month.
- **H1b Overnight:** buy SPY at the close, sell at the next open, every day.
- **H1c Pre-holiday:** hold SPY from the close two trading days before a market holiday to the close of the
  day before it.
- Pass: Sharpe above SPY buy-and-hold in both development and validation, after costs.

## H2. Sector ETF short-term reversal
- Every Friday close, hold the 3 sector ETFs (XLK XLF XLE XLV XLI XLY XLP XLU XLB) with the worst 5-day
  return, equal weight, for one week.
- Pass: Sharpe above the equal-weight sector basket in both periods.

## H3. Sector ETF momentum (control: the classic version of a strategy that already failed on mixed ETFs)
- Each month end, hold the 3 sectors with the best 12-month return excluding the last month.
- Pass: same as H2.

## H4. Stocks in play: big gaps on heavy volume (broad universe incl. delisted where available)
Universe: US stocks priced over $5 with 20-day average dollar volume over $10M. A stock is "in play" on a day
when it opens at least 4% above (or below) the prior close and that day's volume is at least 2x its 20-day
average.
- **H4a Gap and go (up):** buy at the open, sell at the close the same day.
- **H4b Gap fade (up):** short at the open, cover at the close.
- **H4c Gap and go (down):** short at the open, cover at the close.
- **H4d Gap-down bounce:** buy at the open, sell at the close.
- **H4e Post-gap drift (up):** buy at the gap day's close, sell 5 trading days later.
- **H4f Post-gap drift (down):** short at the gap day's close, cover 5 trading days later.
- Note: same-day volume is only fully known at the close, so H4a-d use the 2x volume filter as an
  approximation of "heavy opening volume"; this is recorded as a known look-ahead in H4a-d, and H4e-f do not
  have it.
- Pass: mean net return per trade > 0 with t-statistic > 2 in development AND mean > 0 with t > 1.5 in
  validation, at least 100 trades in each.

## H5. Large-cap weekly reversal
- Same universe as H4 but only the 200 most liquid stocks each week. Every Friday close, buy the 10 worst
  5-day performers, hold one week, equal weight.
- Pass: Sharpe above the equal-weight 200-stock basket in both periods.

## Multiple testing
Twelve hypotheses are tested. At this count, one or two may pass by luck alone, so only the strongest
passer(s) go to the holdout, and only results that hold up there count.
