# Economic Indicators

A small research pipeline built around the indicator list in *Investing 101* (Michele Cagan): GDP, CPI, Consumer Confidence, Job Growth, Initial Unemployment Claims, Housing Starts, the Leading Economic Index, Business Inventories, and PPI. Rather than just tracking them on a dashboard, this project builds a **composite leading index from the genuinely leading indicators, and backtests it against actual NBER recessions** with a documented, non-black-box methodology and an honest report of where it worked and where it didn't.

Companion project: [pce-compare](https://github.com/by-tayo/pce-compare) (personal spending vs. national PCE benchmarks).

## Why not just use all 9 indicators as "leading"?

The book's list mixes indicators that sit in different places in the business cycle. Feeding lagging indicators like CPI or GDP into a *leading* index would blunt its lead time by the time GDP confirms a slowdown, it's already happened. So each indicator is classified, and only the leading ones feed the composite. The rest are tracked for context.

| Indicator | FRED series | Class | In composite? | What it measures |
|---|---|---|---|---|
| Initial Unemployment Claims (UI) | [`ICSA`](https://fred.stlouisfed.org/series/ICSA) | Leading | ✅ (inverted) | New jobless benefit claims each week, one of the fastest-moving signals of labor market stress. |
| Housing Starts | [`HOUST`](https://fred.stlouisfed.org/series/HOUST) | Leading | ✅ | New residential construction starts, sensitive to interest rates and confidence, moves before broader activity. |
| 10Y-3M Treasury Yield Spread | [`T10Y3M`](https://fred.stlouisfed.org/series/T10Y3M) | Leading | ✅ | The spread between long- and short-term Treasury yields. A narrowing or inverted (negative) spread has preceded every recession since 1970 and is one of the ten components of the Conference Board's actual Leading Economic Index. Replaces PPI (see note below). |
| Consumer Confidence (CC) | [`UMCSENT`](https://fred.stlouisfed.org/series/UMCSENT) | Leading | ✅ | University of Michigan Consumer Sentiment. The Conference Board's own Consumer Confidence Index isn't freely available on FRED, so this widely-used free equivalent stands in for it. |
| Job Growth | [`PAYEMS`](https://fred.stlouisfed.org/series/PAYEMS) | Coincident | Dashboard only | Total nonfarm payroll employment confirms the cycle roughly in real time rather than ahead of it. |
| GDP | [`GDPC1`](https://fred.stlouisfed.org/series/GDPC1) | Coincident/Lagging | Dashboard only | Real GDP - the broadest measure of output, but reported quarterly and revised after the fact. |
| CPI | [`CPIAUCSL`](https://fred.stlouisfed.org/series/CPIAUCSL) | Lagging | Dashboard only | Consumer Price Index - headline inflation, the main driver of Fed rate decisions per the book's thesis, but a lagging confirmation of price pressure that already happened. |
| Business Inventories | [`BUSINV`](https://fred.stlouisfed.org/series/BUSINV) | Lagging | Dashboard only | Total business inventories — tends to build up *after* demand has already turned. |
| Producer Price Index (PPI) | [`PPIACO`](https://fred.stlouisfed.org/series/PPIACO) | Lagging | Dashboard only | Prices producers receive for output. Inflation is a *lagging* indicator in the Conference Board's own framework — it isn't one of the ten LEI components — so it's tracked for context but no longer feeds the composite. See "What changed" below. |

Two benchmark series are also pulled, but never used as composite inputs:

- **`USREC`** — the NBER recession indicator (the ground truth the composite is scored against).
- **`USSLIND`** — the Philadelphia Fed's own "Leading Index for the United States." This is the Conference Board's official LEI's free cousin; it's included only as a secondary reference series, never as an input, since using someone else's leading index to build your own would be circular. (Note: this particular FRED series stops updating in early 2020 in the cached pull — treat it as historical context, not a live benchmark.)

## Current snapshot

Latest value per indicator vs. 12 months prior (`python 06_snapshot.py`, as of the last `01_fetch_data.py` run):

| Indicator | Class | Latest | as of | 12mo ago | Trend |
|---|---|---|---|---|---|
| Initial Unemployment Claims | leading | 201,000 | 2026-09-01 | 234,000 | Falling |
| Housing Starts | leading | 1,275 | 2026-08-01 | 1,291 | Falling |
| 10-Year minus 3-Month Treasury Yield Spread | leading | 0.88 | 2026-09-01 | 0.05 | Rising |
| Consumer Sentiment (Consumer Confidence proxy) | leading | 55.2 | 2026-07-01 | 61.7 | Falling |
| Nonfarm Payrolls (Job Growth) | coincident | 159,075 | 2026-08-01 | 158,472 | Flat |
| Real GDP | coincident/lagging | 24,269.61 | 2026-04-01 | 23,770.98 | Rising |
| CPI | lagging | 334.13 | 2026-08-01 | 323.29 | Rising |
| Business Inventories | lagging | 2,764,708 | 2026-07-01 | 2,663,019 | Rising |
| Producer Price Index | lagging | 287.93 | 2026-08-01 | 262.11 | Rising |

Note "Falling" for Initial Claims is *good* news (fewer people filing for unemployment) direction alone doesn't say good or bad the same way across every row, which is exactly why the indicator table above spells out what each series measures.

![Leading indicators panel](output/indicator_panel.png)

## Methodology

1. **Fetch** all series from FRED, caching raw pulls to `data/raw/` so reruns don't hit the API.
2. **Align to monthly**: weekly claims are averaged per month; the daily yield spread is averaged per month; quarterly GDP is forward-filled; the rest are already monthly.
3. **Transform**: each of the 4 leading series is converted to a month-over-month change before anything else — either a symmetric percent change (`ICSA`, `HOUST`, the Conference Board's own convention: a rise and an equally sized fall come out equal and opposite) or a simple difference (`T10Y3M`, `UMCSENT` — already a spread/index, not a level to take a percent of). A raw level series that trends for decades (PPI, housing starts) would otherwise dominate the composite with what year it is instead of a cyclical signal; the change removes the trend and keeps the cycle.
4. **Normalize**: each change series is z-scored on a **fixed training window** (through 2018-12-31) — the mean/std used to score *every* month, including ones long after 2018, come only from data through that cutoff. This is a standard train/test split: it keeps the score from any month contaminated by data that didn't exist yet *relative to that cutoff*, and it's simpler to reason about and audit than an expanding window. Initial Claims is inverted (rising claims is bad news) before combining; the yield spread and sentiment are already signed the same direction the composite wants.
5. **Weight**: equal weight (25% each) across the 4 leading series — fixed before ever looking at backtest results, on purpose. Tuning weights against the same data used to score performance would make the backtest meaningless.
6. **Combine**: weighted sum of z-scores, plus a 3-month moving average (the raw composite is noisy month to month).
7. **Signal rule**: the composite crossing below **-0.5** (fixed a priori, never fit to the data) counts as a recession warning.

All of this lives in [`econ_common.py`](econ_common.py), covered by unit tests on synthetic data (`tests/test_econ_common.py`) — no network access required to verify the math, including a test that a trending raw level correlates with a plain time counter and a transformed one doesn't (`test_components_measure_the_cycle_not_the_calendar`).

### What changed, and why

Two earlier versions of this pipeline had real methodology problems, found and corrected in order:

1. **Z-scoring raw levels over the full sample.** That version scored 2/8 recessions, but the miss pattern tracked PPI's decades-long upward trend almost exactly — a methodology artifact (measuring what year it is), not a finding.
2. **Keeping PPI in the composite, inverted, and walk-forward (expanding) z-scoring.** That fixed the trend problem and scored 5/6, but two issues remained: PPI isn't a leading indicator by the Conference Board's own framework (inflation is lagging — it's what causes tightening, not what leads a slowdown), and an expanding z-score, while not leaking *future* data, still let 2026 flatter a training procedure that a fixed train/test split makes more legible and easier to audit.

This version replaces PPI with the 10Y-3M Treasury yield spread (a genuine leading indicator, and one of the Conference Board LEI's actual ten components) and switches to a fixed 2018-12-31 training cutoff for z-scoring. The cost: `T10Y3M` only starts in 1982, so the composite can no longer be scored against the 1980-81 recession — coverage drops from 6 scoreable recessions to 4. See git history for the prior versions if you want to compare.

A related bug, fixed in this pass rather than found by an external review: the backtest script used to truncate `USREC` to the composite's own date range *before* detecting recession starts, which made a recession already underway when the composite's history begins look like a brand-new recession starting exactly there — a phantom 0-lead "hit". Recession starts are now detected from the full, untruncated NBER series, and coverage is handled separately and explicitly.

## Backtest results

`T10Y3M` doesn't start until 1982-01, so the composite's first valid reading is **1982-02** — it structurally cannot be scored against the 1953, 1957, 1960, 1970, 1973-75, 1980, or 1981-82 recessions, which fall before that. Run against every recession the composite can actually see (`python 03_backtest.py`):

| Recession start | Signal date | Lead (months) | Caught? |
|---|---|---|---|
| 1990-08 | 1989-04 | 16 | ✅ |
| 2001-04 | 2000-12 | 4 | ✅ |
| 2008-01 | — | — | ❌ |
| 2020-03 | 2020-03 | 0 | ✅ |

**3/4 recessions caught within coverage** (1953 through 1981-82 are out of reach, not misses — see the script output for the full list), average lead time when it did catch one: **6.7 months**. It also threw **12 false positives** — threshold crossings with no recession following within 12 months (1984-08, 1988-01, 1995-03, 2002-09, 2005-09, 2010-07, 2011-08, 2018-12, 2022-07, 2022-12, 2024-07, 2025-03) — three times as many false alarms as real signals.

![Composite index vs. NBER recessions](output/index_vs_recessions.png)

### Honest evaluation

Replacing PPI with the yield spread and moving to a fixed training-window z-score is the methodologically correct call — PPI genuinely isn't a leading indicator, and a fixed train/test split is more standard and auditable than an expanding one. It is **not** a free win on the scoreboard: the corrected index **missed 2008**, the most consequential recession in the sample, and threw 12 false positives against only 3 real hits. That's a materially worse-looking result than the previous (methodologically flawed) version's 5/6 with 8 false positives — and that's the point. The earlier number was flattered by a component that shouldn't have been there and a longer history it was quietly borrowing signal from; this number reflects what 4 free, equally-weighted monthly indicators, honestly evaluated, actually deliver on the sample available.

Missing 2008 specifically is worth sitting with: the 2007-08 credit crisis was a slow-building financial imbalance, exactly the kind of thing a yield-curve/claims/housing/sentiment composite should be well-placed to catch. That it didn't suggests either the -0.5 threshold is too strict for this component mix, or the fixed 2018 training window's mean/std don't characterize the 2006-07 run-up well, or four equally-weighted components genuinely aren't enough signal — this project doesn't have the sample size to tell those apart.

**2020 hold-out**: the threshold and weights were fixed using the general methodology above, without ever tuning against 2020 data. The composite **caught** the COVID recession, though with 0 months of lead — it confirmed the downturn the month it started rather than anticipating it, which fits: a sudden external demand shock isn't the kind of gradually-building imbalance these components are built to catch ahead of time.

### Limitations

- Only 4 components, equally weighted — the official Conference Board LEI uses ~10 components with non-equal, empirically-derived weights (which this project deliberately avoids to keep the method transparent, at the cost of some accuracy).
- `T10Y3M`'s 1982 start date pushes the composite's usable history to 1982 onward, so it can only be scored against 4 of the 8 recessions since 1970 — and it missed one of those four.
- A -0.5 z-score threshold and a 2018-12-31 training cutoff are each one reasonable choice, not the only one; the backtest results would shift with either changed, and this project deliberately doesn't refit them against the outcome above.
- 4 scoreable recessions is a small sample — one hit or miss changes the headline ratio by 25 percentage points. **The honest conclusion is that a handful of free monthly indicators, equally weighted, are not enough to call recessions reliably** — this is a more useful finding than a tuned index that catches everything in hindsight.

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
06_snapshot.py          # latest-value snapshot across all 9 indicators
tests/                 # pytest suite for econ_common.py
data/raw/              # cached raw FRED pulls (gitignored)
data/processed/        # composite + dashboard series (gitignored)
output/                # results.csv, snapshot.csv, charts (committed)
```
