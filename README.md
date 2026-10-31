# US Economic Indicators

A small data pipeline and a public dashboard that track ten US economic indicators from 1990 to today, with NBER recession periods shaded on the charts.

**Live dashboard:** https://public.tableau.com/app/profile/tania.ortiz/viz/USEconomicIndicatorsDashboard/USEconomicIndicators

The dashboard has three parts:

- **Trend:** one indicator over time with recessions shaded. A dropdown switches between all ten.
- **Yield spread:** the 10-year minus 3-month Treasury spread, with a zero line and recessions shaded.
- **Latest readings:** the most recent value and the change over the past year for every indicator.

## Headline numbers

From the data pulled on 2026-10-30. Changes are over the past year.

| Indicator | Latest | Change |
| --- | --- | --- |
| Consumer sentiment | 48.1 | -12.7% |
| Consumer prices (CPI) | 336.298 | +3.72% |
| Real GDP | 24,611.077 | +2.07% |
| Industrial production | 103.9506 | +2.25% |
| Nonfarm payrolls | 159,044 | +0.31% |
| Initial jobless claims | 194,000 | -12.2% |
| Housing starts | 1,221 | -7.43% |
| Unemployment rate | 4.2% | -0.2 points |
| Federal funds rate | 3.75% | -0.47 points |
| 10-year minus 3-month spread | +0.8 | +0.65 points |

- Output is growing (GDP +2.07%, industrial production +2.25%) while payroll growth is close to flat (+0.31%).
- Consumer sentiment is at 48.1, down 12.7% from a year earlier.
- The yield spread is positive again after the deepest inversion in the data (see below).

## What the data shows

These observations describe the past; they are not a forecast. Four NBER recessions fall inside the 1990 to 2026 window: Aug 1990 to Mar 1991, Apr to Nov 2001, Jan 2008 to Jun 2009, and Mar to Apr 2020.

**1. The yield spread was negative before the 2001 and 2008 recessions.** I measured it as the monthly average of the daily 10-year minus 3-month Treasury spread. It went below zero in Jul 2000 (the 2001 recession began 9 months later) and in Aug 2006 (the 2008 recession began 17 months later). The lead time varied a lot, so the signal says "a recession may be coming", not "when".

**2. The pattern is not clean.** The 1990 recession is outside what this data can judge, because the series starts in Jan 1990. The 2020 recession followed a short inversion in 2019, but a pandemic shutdown is not something an interest-rate spread predicts. The deepest inversion in the data, from Nov 2022 to Dec 2024 (monthly average as low as -1.73 points), has not been followed by an NBER-dated recession as of the latest data. NBER announces recession dates with a long delay, so that question stays open.

**3. Unemployment keeps rising after a recession ends.** In three of the four recessions the unemployment rate peaked well after the recession's last month: about 15 months later in 1991 to 1992 (7.8%), about 19 months later in 2001 to 2003 (6.3%), and about 4 months later in 2009 (10.0%). In 2020 it peaked within the recession itself, at 14.8% in April. Unemployment is a lagging indicator.

**4. Interest rates.** The federal funds rate peaked at 5.33% in 2023 to 2024 and stands at 3.75% in the latest data.

**Limits of this analysis.** Four recessions is a very small sample, so none of these patterns is statistically proven. The yield spread uses monthly averages of daily data. FRED revises some series, and the NBER recession flag is blank where FRED has no reading. This is descriptive work for a portfolio, not investment advice.

## What the pipeline does

`fetch_data.py` pulls public data from the [FRED API](https://fred.stlouisfed.org/docs/api/fred/) (Federal Reserve Bank of St. Louis) and writes three tidy CSV files to `data/`, ready for Tableau.

| File | What it holds |
| --- | --- |
| `observations.csv` | One row per series per date: `date, series_id, label, group, value, yoy, recession` |
| `series_summary.csv` | One row per series: latest value, previous value, year-ago value, change over the year |
| `recessions.csv` | NBER recession start and end dates, used for shading |

### Indicators

| FRED series | Indicator | Group |
| --- | --- | --- |
| UNRATE | Unemployment rate | Labor |
| PAYEMS | Nonfarm payrolls | Labor |
| ICSA | Initial jobless claims | Labor |
| CPIAUCSL | Consumer prices (CPI) | Prices |
| GDPC1 | Real GDP | Output |
| INDPRO | Industrial production | Output |
| FEDFUNDS | Federal funds rate | Rates |
| T10Y3M | 10-year minus 3-month Treasury | Rates |
| HOUST | Housing starts | Housing |
| UMCSENT | Consumer sentiment | Sentiment |

### How the numbers are calculated

- **Year over year (`yoy`):** for index and level series (CPI, GDP, payrolls and similar) it is the percent change from the same period a year earlier. For series that are already rates (unemployment, fed funds, the yield spread) it is the difference in percentage points.
- **Recession flag:** taken from the NBER recession indicator (`USREC`). It is left blank where FRED has no reading, rather than guessed.
- **Year-ago lookup:** each observation is matched to the closest earlier observation about a year back, so monthly, weekly and daily series all work the same way.

### Reliability

- **All-or-nothing writes:** if any series fails to download, no files are written, so `data/` never holds a half-updated set.
- **Retries:** temporary errors and rate limits are retried with backoff.
- **No key leaks:** the API key is read from the environment and is never written to the output files or to error messages.
- **Tests:** 16 tests cover the year-over-year logic, the recession flag, the retry behavior and the error messages.

## Run it yourself

You need Python 3 and a free FRED API key ([get one here](https://fred.stlouisfed.org/docs/api/api_key.html)).

```bash
git clone https://github.com/by-tayo/econ-indicators.git
cd econ-indicators
pip install -r requirements.txt
```

Put your key in a local `.env` file (it is listed in `.gitignore`, so it is never committed). Copy `.env.example` to `.env` and fill in the value:

```
FRED_API_KEY=your_key_here
```

Then run:

```bash
python fetch_data.py
```

Optional flags:

```bash
python fetch_data.py --start 2000-01-01     # first observation date (default 1990-01-01)
python fetch_data.py --out some/folder      # output folder (default data/)
```

Run the tests:

```bash
pytest
```

## Build the dashboard

1. Open Tableau Public and connect to `data/observations.csv`.
2. Add `data/series_summary.csv` as a second data source for the latest-readings table.
3. The `recession` column is 1 during an NBER recession. Plot it as gray bars on a second axis to shade recessions.

## Project layout

```
fetch_data.py        the pipeline
tests/               unit tests
data/                CSV output used by the dashboard
requirements.txt     dependencies
.env.example         template for the API key (copy to .env)
```

## Data and limits

All data is public and comes from FRED (series IDs in the table above, recession flag from NBER `USREC`). Values are as published when the pipeline last ran (2026-10-30 for the numbers in this README). FRED revises some series, so numbers can change slightly between runs. This is a portfolio project for learning and illustration, not investment advice.

## License

MIT. See `LICENSE`.
