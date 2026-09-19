# econ-indicators

A small research pipeline built around the indicator list in *Investing 101* (Michele Cagan): GDP, CPI, Consumer Confidence, Job Growth, Initial Unemployment Claims, Housing Starts, the Leading Economic Index, Business Inventories, and PPI. Rather than just tracking them on a dashboard, this project builds a **composite leading index from the genuinely leading indicators, and backtests it against actual NBER recessions** — with a documented, non-black-box methodology and an honest report of where it worked and where it didn't.

Companion project: [pce-compare](https://github.com/by-tayo/pce-compare) (personal spending vs. national PCE benchmarks).

## Why not just use all 9 indicators as "leading"?

The book's list mixes indicators that sit in different places in the business cycle. Feeding lagging indicators like CPI or GDP into a *leading* index would blunt its lead time — by the time GDP confirms a slowdown, it's already happened. So each indicator is classified, and only the leading ones feed the composite. The rest are tracked for context.

| Indicator | FRED series | Class | In composite? | What it measures |
|---|---|---|---|---|
| Initial Unemployment Claims (UI) | [`ICSA`](https://fred.stlouisfed.org/series/ICSA) | Leading | ✅ (inverted) | New jobless benefit claims each week — one of the fastest-moving signals of labor market stress. |
| Housing Starts | [`HOUST`](https://fred.stlouisfed.org/series/HOUST) | Leading | ✅ | New residential construction starts — sensitive to interest rates and confidence, moves before broader activity. |
| Producer Price Index (PPI) | [`PPIACO`](https://fred.stlouisfed.org/series/PPIACO) | Leading | ✅ (inverted) | Prices producers receive for output — feeds into future consumer prices (CPI). Rising PPI is a warning sign (it's what pushes the Fed to tighten), so it's inverted like Initial Claims. |
| Consumer Confidence (CC) | [`UMCSENT`](https://fred.stlouisfed.org/series/UMCSENT) | Leading | ✅ | University of Michigan Consumer Sentiment. The Conference Board's own Consumer Confidence Index isn't freely available on FRED, so this widely-used free equivalent stands in for it. |
| Job Growth | [`PAYEMS`](https://fred.stlouisfed.org/series/PAYEMS) | Coincident | Dashboard only | Total nonfarm payroll employment — confirms the cycle roughly in real time rather than ahead of it. |
| GDP | [`GDPC1`](https://fred.stlouisfed.org/series/GDPC1) | Coincident/Lagging | Dashboard only | Real GDP — the broadest measure of output, but reported quarterly and revised after the fact. |
| CPI | [`CPIAUCSL`](https://fred.stlouisfed.org/series/CPIAUCSL) | Lagging | Dashboard only | Consumer Price Index — headline inflation, the main driver of Fed rate decisions per the book's thesis, but a lagging confirmation of price pressure that already happened. |
| Business Inventories | [`BUSINV`](https://fred.stlouisfed.org/series/BUSINV) | Lagging | Dashboard only | Total business inventories — tends to build up *after* demand has already turned. |

Two benchmark series are also pulled, but never used as composite inputs:

- **`USREC`** — the NBER recession indicator (the ground truth the composite is scored against).
- **`USSLIND`** — the Philadelphia Fed's own "Leading Index for the United States." This is the Conference Board's official LEI's free cousin; it's included only as a secondary reference series, never as an input, since using someone else's leading index to build your own would be circular. (Note: this particular FRED series stops updating in early 2020 in the cached pull — treat it as historical context, not a live benchmark.)

## Current snapshot

Latest value per indicator vs. 12 months prior (`python 06_snapshot.py`, as of the last `01_fetch_data.py` run):

| Indicator | Class | Latest | as of | 12mo ago | Trend |
|---|---|---|---|---|---|
| Initial Unemployment Claims | leading | 201,000 | 2026-09-01 | 234,000 | Falling |
| Housing Starts | leading | 1,275 | 2026-08-01 | 1,291 | Falling |
| Producer Price Index | leading | 287.93 | 2026-08-01 | 262.11 | Rising |
| Consumer Sentiment (Consumer Confidence proxy) | leading | 55.2 | 2026-07-01 | 61.7 | Falling |
| Nonfarm Payrolls (Job Growth) | coincident | 159,075 | 2026-08-01 | 158,472 | Flat |
| Real GDP | coincident/lagging | 24,269.61 | 2026-04-01 | 23,770.98 | Rising |
| CPI | lagging | 334.13 | 2026-08-01 | 323.29 | Rising |
| Business Inventories | lagging | 2,764,708 | 2026-07-01 | 2,663,019 | Rising |

Note "Falling" for Initial Claims is *good* news (fewer people filing for unemployment) — direction alone doesn't say good or bad the same way across every row, which is exactly why the indicator table above spells out what each series measures.

![Leading indicators panel](output/indicator_panel.png)

## Methodology

1. **Fetch** all series from FRED, caching raw pulls to `data/raw/` so reruns don't hit the API.
2. **Align to monthly**: weekly claims are averaged per month; quarterly GDP is forward-filled; the rest are already monthly.
3. **Transform**: each of the 4 leading series is converted to its month-over-month % change before anything else. Levels like PPI trend upward for decades, which would otherwise dominate the composite with a secular ramp instead of a cyclical signal — the change removes the trend and keeps the cycle.
4. **Normalize**: each change series is z-scored with a **walk-forward (expanding) window** — the mean/std at any given month use only data up to and including that month, with at least 24 months of history required before a score is produced. A full-history z-score would let 1980's score be computed partly from data through 2026, which is a backtest leak; this isn't. Initial Claims and PPI are inverted (rising claims and rising producer prices are both bad news) before combining.
5. **Weight**: equal weight (25% each) across the 4 leading series — fixed before ever looking at backtest results, on purpose. Tuning weights against the same data used to score performance would make the backtest meaningless.
6. **Combine**: weighted sum of z-scores, plus a 3-month moving average (the raw composite is noisy month to month).
7. **Signal rule**: the composite crossing below **-0.5** (fixed a priori, never fit to the data) counts as a recession warning.

All of this lives in [`econ_common.py`](econ_common.py), covered by unit tests on synthetic data (`tests/test_econ_common.py`) — no network access required to verify the math.

An earlier version of this pipeline z-scored raw levels over the full sample instead. That version scored 2/8 recessions, but the miss pattern tracked PPI's decades-long upward trend almost exactly (every miss was in the trending part of the sample) rather than anything about the economy — a methodology artifact, not a finding. See git history for the prior version if you want to compare.

## Backtest results

The composite needs 24 months of history to produce its first walk-forward score, and `UMCSENT` was only collected quarterly before 1978, so the composite's first valid reading is **1980-01** — it structurally cannot be scored against the 1970-02 or 1974-02 recessions, which fall before that. Run against every recession the composite can actually see (`python 03_backtest.py`):

| Recession start | Signal date | Lead (months) | Caught? |
|---|---|---|---|
| 1980-02 | — | — | ❌ |
| 1981-08 | 1980-03 | 17 | ✅ |
| 1990-08 | 1990-08 | 0 | ✅ |
| 2001-04 | 2001-01 | 3 | ✅ |
| 2008-01 | 2007-11 | 2 | ✅ |
| 2020-03 | 2020-03 | 0 | ✅ |

**5/6 recessions caught** (within the composite's coverage — 1970 and 1974 are out of reach, not misses), average lead time when it did catch one: **4.4 months**. But it also threw **8 false positives** — threshold crossings with no recession following within 12 months (2003-02, 2005-09, 2006-05, 2011-04, 2021-02, 2022-03, 2025-03, 2026-04) — against only 5 true signals, so a crossing is roughly as likely to be noise as a real warning.

![Composite index vs. NBER recessions](output/index_vs_recessions.png)

### Honest evaluation

Fixing the methodology (change instead of level, PPI's sign, walk-forward standardization — see the note above) moved the hit rate from a weak 2/8 to a strong-looking 5/6. That's not a free win, though: two of the five hits (1990 and 2020) have a **0-month lead** — the composite dropped below threshold the same month the recession started, which is a coincident confirmation, not an early warning, even though the backtest's rules count it as a hit. And the false-positive count went from 1 to 8, so the corrected index is far more trigger-happy. Read together, this composite is a **noisy leading indicator**: it does tend to dip around real recessions, often with genuine lead time (17, 3, and 2 months for 1981, 2001, and 2008), but it also dips just as often when nothing follows, and a chunk of its "hits" are same-month confirmations rather than advance warning.

**2020 hold-out**: the threshold and weights were fixed using the general methodology above, without ever tuning against 2020 data. The composite **caught** the COVID recession, though with 0 months of lead — it confirmed the downturn the month it started rather than anticipating it, which fits: a sudden external demand shock isn't the kind of gradually-building imbalance (credit tightening, housing overbuilding, inventory glut) these components are built to catch ahead of time.

### Limitations

- Only 4 components, equally weighted — the official Conference Board LEI uses ~10 components with non-equal, empirically-derived weights (which this project deliberately avoids to keep the method transparent, at the cost of some accuracy).
- The 24-month walk-forward warm-up plus `UMCSENT`'s quarterly-before-1978 collection push the composite's usable history to 1980 onward, so it can only be scored against 6 of the 8 recessions since 1970.
- A -0.5 z-score threshold is one reasonable choice, not the only one; the backtest results would shift with a different threshold, and a lower false-positive rate would likely need a stricter one.
- 6 scoreable recessions is a small sample — one or two additional hits/misses would meaningfully change the hit rate.

## Setup

```powershell
pip install -r requirements.txt
copy .env.example .env
# edit .env and add your FRED API key (free, instant activation:
# https://fred.stlouisfed.org/docs/api/api_key.html)
```

## Usage

```powershell
python 00_check_setup.py     # verify API key + connectivity
python 01_fetch_data.py      # pull all series, cache to data/raw/
python 02_build_index.py     # build the composite + dashboard series
python 03_backtest.py        # score against NBER recessions, writes output/results.csv
python 04_plot_results.py    # writes output/index_vs_recessions.png
python 05_indicator_panel.py # writes output/indicator_panel.png
python 06_snapshot.py        # writes output/snapshot.csv + prints the markdown table above
```

Run the test suite (no API key needed — it only exercises the pure math):

```powershell
pytest tests/
```

## Project layout

```
econ_common.py       # FRED fetch + caching, index math, backtest scoring (unit-tested)
00_check_setup.py     # verify API key
01_fetch_data.py       # pull + cache raw series
02_build_index.py      # build composite + dashboard
03_backtest.py         # score vs. USREC, write results.csv
04_plot_results.py     # chart composite vs. recessions
05_indicator_panel.py  # small-multiples chart of the 4 leading indicators
06_snapshot.py          # latest-value snapshot across all 8 indicators
tests/                 # pytest suite for econ_common.py
data/raw/              # cached raw FRED pulls (gitignored)
data/processed/        # composite + dashboard series (gitignored)
output/                # results.csv, snapshot.csv, charts (committed)
```
