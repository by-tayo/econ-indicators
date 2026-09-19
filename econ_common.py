"""Shared utilities: FRED access with local caching, index construction math,
and backtest scoring. The math functions here take plain pandas objects and
make no network calls, so they're unit-testable with synthetic data.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

DATA_RAW = Path("data/raw")
DATA_PROCESSED = Path("data/processed")
OUTPUT = Path("output")

# Indicators from the book's list, classified by where they sit in the cycle.
# Only "leading" series feed the composite that gets backtested; the rest are
# tracked for context/explanation but would blunt the composite's lead time
# if mixed in (GDP and CPI, in particular, are reported well after the fact).
INDICATORS = {
    "ICSA": {
        "name": "Initial Unemployment Claims",
        "cls": "leading",
        "resample": "mean",
        "invert": True,  # rising claims is bad news
        "in_composite": True,
    },
    "HOUST": {
        "name": "Housing Starts",
        "cls": "leading",
        "resample": "mean",
        "invert": False,
        "in_composite": True,
    },
    "PPIACO": {
        "name": "Producer Price Index",
        "cls": "leading",
        "resample": "mean",
        "invert": False,
        "in_composite": True,
    },
    "UMCSENT": {
        "name": "Consumer Sentiment (Consumer Confidence proxy)",
        "cls": "leading",
        "resample": "mean",
        "invert": False,
        "in_composite": True,
    },
    "PAYEMS": {
        "name": "Nonfarm Payrolls (Job Growth)",
        "cls": "coincident",
        "resample": "mean",
        "invert": False,
        "in_composite": False,
    },
    "GDPC1": {
        "name": "Real GDP",
        "cls": "coincident/lagging",
        "resample": "ffill",
        "invert": False,
        "in_composite": False,
    },
    "CPIAUCSL": {
        "name": "CPI",
        "cls": "lagging",
        "resample": "mean",
        "invert": False,
        "in_composite": False,
    },
    "BUSINV": {
        "name": "Business Inventories",
        "cls": "lagging",
        "resample": "mean",
        "invert": False,
        "in_composite": False,
    },
}

BENCHMARKS = {
    "USREC": "NBER Recession Indicator (backtest target)",
    "USSLIND": "Philly Fed Leading Index (secondary comparison, not an input)",
}

LEADING_SERIES = [k for k, v in INDICATORS.items() if v["in_composite"]]
COMPOSITE_WEIGHTS = {k: 1.0 / len(LEADING_SERIES) for k in LEADING_SERIES}
COMPOSITE_THRESHOLD = -0.5  # fixed a priori, not fit to backtest results


# ---------------------------------------------------------------------------
# FRED access (network — not covered by unit tests)
# ---------------------------------------------------------------------------

def get_fred_client():
    from dotenv import load_dotenv
    from fredapi import Fred

    load_dotenv()
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FRED_API_KEY not set. Copy .env.example to .env and add your key "
            "(free, instant activation at https://fred.stlouisfed.org/docs/api/api_key.html)."
        )
    return Fred(api_key=api_key)


def fetch_series(fred, series_id: str, cache_dir: Path = DATA_RAW, force: bool = False) -> pd.Series:
    """Fetch a series from FRED, caching to CSV so reruns don't hit the API."""
    cache_path = Path(cache_dir) / f"{series_id}.csv"
    if cache_path.exists() and not force:
        return load_cached(series_id, cache_dir)
    s = fred.get_series(series_id)
    s.name = series_id
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(cache_path)
    return s


def load_cached(series_id: str, cache_dir: Path = DATA_RAW) -> pd.Series:
    """Load a previously-fetched series from the local cache (no network)."""
    cache_path = Path(cache_dir) / f"{series_id}.csv"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"No cached data for {series_id} at {cache_path}. Run 01_fetch_data.py first."
        )
    s = pd.read_csv(cache_path, index_col=0, parse_dates=True).iloc[:, 0]
    s.name = series_id
    return s


# ---------------------------------------------------------------------------
# Index construction math (pure functions, unit-tested)
# ---------------------------------------------------------------------------

def to_monthly(s: pd.Series, method: str = "mean") -> pd.Series:
    """Resample a series (weekly, monthly, or quarterly) onto month-start dates."""
    if method == "mean":
        return s.resample("MS").mean()
    if method == "ffill":
        return s.resample("MS").ffill()
    if method == "last":
        return s.resample("MS").last()
    raise ValueError(f"unknown resample method: {method}")


def zscore(s: pd.Series) -> pd.Series:
    """Standardize a series over its own full history."""
    std = s.std()
    if std == 0 or pd.isna(std):
        raise ValueError("cannot z-score a constant or all-NaN series")
    return (s - s.mean()) / std


def build_composite(
    components: dict[str, pd.Series],
    weights: dict[str, float] | None = None,
    invert: set[str] | frozenset[str] = frozenset(),
) -> pd.Series:
    """Align components on a common index, z-score each, invert sign where
    noted, and combine with a weighted sum. Weights must sum to 1.
    """
    if weights is None:
        weights = {k: 1.0 / len(components) for k in components}
    if set(weights) != set(components):
        raise ValueError("weights keys must match components keys")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1")

    df = pd.DataFrame(components).dropna(how="any")
    if df.empty:
        raise ValueError("no overlapping dates across components")

    z = df.apply(zscore)
    for name in invert:
        if name in z.columns:
            z[name] = -z[name]

    w = pd.Series(weights)
    composite = z.mul(w, axis=1).sum(axis=1)
    composite.name = "composite"
    return composite


def smooth(s: pd.Series, window: int = 3) -> pd.Series:
    return s.rolling(window=window, min_periods=1).mean()


# ---------------------------------------------------------------------------
# Backtest scoring (pure functions, unit-tested)
# ---------------------------------------------------------------------------

def months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def find_crossings(composite: pd.Series, threshold: float) -> list[pd.Timestamp]:
    """Dates where the composite drops from >= threshold to < threshold —
    a downward crossing, treated as a recession warning signal."""
    below = composite < threshold
    prev_below = below.shift(1, fill_value=False)
    crossing_mask = below & ~prev_below
    return list(composite.index[crossing_mask])


def find_recession_starts(usrec: pd.Series) -> list[pd.Timestamp]:
    """Dates where USREC (0/1) turns on — the start of an NBER recession."""
    on = usrec.astype(int)
    prev = on.shift(1, fill_value=0)
    start_mask = (on == 1) & (prev == 0)
    return list(on.index[start_mask])


def recession_periods(usrec: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous (start, end) blocks where USREC == 1."""
    on = usrec.astype(int)
    periods = []
    start = None
    prev_date = None
    for date, value in on.items():
        if value == 1 and start is None:
            start = date
        if value == 0 and start is not None:
            periods.append((start, prev_date))
            start = None
        prev_date = date
    if start is not None:
        periods.append((start, prev_date))
    return periods


def backtest(
    composite: pd.Series,
    usrec: pd.Series,
    threshold: float = COMPOSITE_THRESHOLD,
    max_lookback_months: int = 24,
    false_positive_horizon_months: int = 12,
) -> dict:
    """Score a composite index against NBER recession starts.

    For each recession, the signal is the most recent downward threshold
    crossing within `max_lookback_months` beforehand (a miss if none exists).
    A crossing not matched to any recession, with no recession starting
    within `false_positive_horizon_months` after it, counts as a false
    positive.
    """
    crossings = find_crossings(composite, threshold)
    recession_starts = find_recession_starts(usrec)
    periods = recession_periods(usrec)

    results = []
    matched = set()
    for r_start in recession_starts:
        candidates = [
            c for c in crossings
            if c <= r_start and months_between(c, r_start) <= max_lookback_months
        ]
        if candidates:
            signal = max(candidates)
            results.append({
                "recession_start": r_start,
                "signal_date": signal,
                "lead_months": months_between(signal, r_start),
                "hit": True,
            })
            matched.add(signal)
        else:
            results.append({
                "recession_start": r_start,
                "signal_date": None,
                "lead_months": None,
                "hit": False,
            })

    false_positives = []
    for c in crossings:
        if c in matched:
            continue
        during_recession = any(start <= c <= end for start, end in periods)
        if during_recession:
            continue  # late/coincident confirmation, not a false alarm
        followed_by_recession = any(
            0 <= months_between(c, r) <= false_positive_horizon_months
            for r in recession_starts
        )
        if not followed_by_recession:
            false_positives.append(c)

    return {"results": results, "false_positives": false_positives}
