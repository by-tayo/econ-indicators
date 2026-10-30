# US Economic Indicators

A small data pipeline and a public dashboard that track ten US economic indicators from 1990 to today, with NBER recession periods shaded on the charts.

**Live dashboard:** https://public.tableau.com/app/profile/tania.ortiz/viz/USEconomicIndicatorsDashboard/USEconomicIndicators

The dashboard has three parts:

- **Trend:** one indicator over time with recessions shaded. A dropdown switches between all ten.
- **Yield spread:** the 10-year minus 3-month Treasury spread, with a zero line and recessions shaded.
- **Latest readings:** the most recent value and the change over the past year for every indicator.

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

- **Year over year (`yoy`):** for index and level series (CPI, GDP, payrolls and similar) it is the percent change from the same period a year earlier. For series that are already rates (unemployment, fed funds, the yield spread) it is the difference in percentage points. `series_summary.csv` labels which one each row uses in the `yoy_unit` column.
- **Recession flag:** taken from the NBER recession indicator (`USREC`). It is left blank where FRED has no reading, rather than guessed.
- **Year-ago lookup:** each observation is matched to the closest earlier observation about a year back, so monthly, weekly and daily series all work the same way.

### Reliability

- **All-or-nothing writes:** if any series fails to download, no files are written, so `data/` never holds a half-updated set.
- **Retries:** temporary errors and rate limits are retried with backoff.
- **No key leaks:** the API key is read from the environment and is never written to the output files or to error messages.
- **Tests:** 16 tests cover the year-over-year logic, the recession flag, the retry behavior and the error messages.

## Run it yourself

You need Python 3.9 or newer and a free FRED API key ([get one here](https://fred.stlouisfed.org/docs/api/api_key.html)).

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

All data is public and comes from FRED. Values are as published at the time the pipeline last ran; the "fetched on" date is stored in `series_summary.csv`. FRED revises some series, so numbers can change slightly between runs. This is a portfolio project for learning and illustration, not investment advice.

## License

MIT. See `LICENSE`.
