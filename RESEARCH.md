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

## H6. Gap and go without look-ahead (added after H4 results, because H4a passed but has a known look-ahead)
H4a's volume filter uses the whole day's volume, which is not known at the open. These versions use only
information available at entry. Same universe, same 4% gap-up rule, same costs, same pass criteria as H4.
- **H6a No volume filter:** buy every 4%+ gap-up at the open, sell at the close.
- **H6b Opening-volume filter:** after the first 15 minutes (9:30-9:45), keep only stocks whose 15-minute volume
  is at least 20% of their 20-day average daily volume; buy at 9:45 (the first 15-minute bar's close), sell at the
  close.

## Results (development / validation), recorded after running
| Hypothesis | Result | Pass |
|---|---|---|
| H1a Turn of month | Sharpe 0.66 / 0.33 vs SPY 1.00 / 0.57 | no |
| H1b Overnight | Sharpe -1.12 / -1.99 (daily costs) | no |
| H1c Pre-holiday | Sharpe 0.39 / 2.01 vs SPY 1.00 / 0.57 | no |
| H2 Sector weekly reversal | Sharpe 0.46 / 0.36 vs basket 0.91 / 0.57 | no |
| H3 Sector momentum | Sharpe 0.71 / 0.72 vs basket 0.91 / 0.57 | no |
| H4a Gap and go (up), full-day volume | +0.54% / +0.83% per trade, t 2.38 / 2.39 | yes, but look-ahead |
| H4b Gap fade (up) | -0.94% / -1.23% | no |
| H4c Gap down, short | +0.74% / +0.15%, t 4.01 / 1.42 | no |
| H4d Gap-down bounce | -1.14% / -0.55% | no |
| H4e Post-gap drift up, 5 days | -0.45% / -0.57% | no |
| H4f Post-gap drift down, 5 days | +0.10% / -0.55% | no |
| H5 Large-cap weekly reversal | Sharpe 0.18 / 0.35 vs basket 0.97 / 0.35 | no |
| H6a Gap and go, no volume filter | -0.15% / -0.32%, t -9.1 / -5.1 | no |
| H6b Gap and go, opening volume, entry 9:45 | -0.38% / -0.18%, t -5.1 / -1.1 | no |

Conclusion: H4a's edge came from the same-day volume look-ahead; with only information available at entry
(H6a, H6b) gap-and-go loses money. No hypothesis passed honestly, so the holdout was not opened.
