"""Pull U.S. economic indicators from FRED and write tidy CSVs for Tableau Public.

    export FRED_API_KEY=your_key        # free: https://fred.stlouisfed.org/docs/api/api_key.html
    python fetch_data.py

Writes three files to data/ (nothing is written if any series fails):

    observations.csv    one row per series per date: date, series_id, label, group, value, yoy, recession
    series_summary.csv  one row per series: latest value, year-ago value, change over the year
    recessions.csv      NBER recession periods (start, end), for shading charts

Only public FRED data is used. The API key is read from the environment (or a local .env file)
and is never written to any output.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

API = "https://api.stlouisfed.org/fred/series/observations"
START = "1990-01-01"
ROOT = Path(__file__).resolve().parent
RETRY_CODES = (429, 500, 502, 503, 504)

# series_id, label, group, units, kind
#   kind "level": the year-over-year change is a percent change
#   kind "rate":  the series is already a rate or spread, so the change is in percentage points
SERIES = [
    ("UNRATE", "Unemployment rate", "Labor", "% of labor force", "rate"),
    ("PAYEMS", "Nonfarm payrolls", "Labor", "thousands of jobs", "level"),
    ("ICSA", "Initial jobless claims", "Labor", "claims per week", "level"),
    ("CPIAUCSL", "Consumer prices (CPI)", "Prices", "index, 1982-84 = 100", "level"),
    ("GDPC1", "Real GDP", "Output", "billions of chained dollars", "level"),
    ("INDPRO", "Industrial production", "Output", "index", "level"),
    ("FEDFUNDS", "Federal funds rate", "Rates", "%", "rate"),
    ("T10Y3M", "10-year minus 3-month Treasury", "Rates", "percentage points", "rate"),
    ("HOUST", "Housing starts", "Housing", "thousands of units, annual rate", "level"),
    ("UMCSENT", "Consumer sentiment", "Sentiment", "index, 1966 Q1 = 100", "level"),
]
RECESSION_ID = "USREC"   # 1 = NBER recession month, 0 = not


class FetchError(Exception):
    """A series could not be fetched. The message never contains the API key."""


def load_dotenv(path: Path = ROOT / ".env"):
    """Read KEY=value lines from a local .env file. Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def parse_observations(payload: dict) -> pd.DataFrame:
    """FRED JSON to a frame of date, value. Missing readings (".") are dropped."""
    rows = [(o["date"], o["value"]) for o in payload.get("observations", [])]
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")   # "." becomes NaN
    return df.dropna().sort_values("date").reset_index(drop=True)


def fetch_series(series_id: str, key: str, start: str = START, session=None,
                 retries: int = 2, pause: float = 1.5) -> pd.DataFrame:
    session = session or requests
    params = {"series_id": series_id, "api_key": key, "file_type": "json", "observation_start": start}
    for attempt in range(retries + 1):
        try:
            r = session.get(API, params=params, timeout=30)
        except requests.RequestException:
            # the exception text contains the URL, and the URL contains the key: say nothing of it
            raise FetchError(f"{series_id}: could not reach FRED.") from None
        if r.status_code in RETRY_CODES and attempt < retries:
            time.sleep(pause * (attempt + 1))
            continue
        if r.status_code in (400, 401, 403):
            raise FetchError(f"{series_id}: FRED rejected the request ({r.status_code}). Check FRED_API_KEY and the series id.")
        if r.status_code in RETRY_CODES:
            raise FetchError(f"{series_id}: FRED is busy. Try again in a minute.")
        if r.status_code != 200:
            raise FetchError(f"{series_id}: FRED answered with an error ({r.status_code}).")
        try:
            df = parse_observations(r.json())
        except (ValueError, KeyError):
            raise FetchError(f"{series_id}: FRED sent something unreadable.") from None
        if df.empty:
            raise FetchError(f"{series_id}: FRED returned no readings.")
        return df
    raise FetchError(f"{series_id}: FRED is busy. Try again in a minute.")  # not reached; keeps the function total


def year_ago(df: pd.DataFrame) -> pd.Series:
    """For each date, the reading closest to one year earlier (within 10 days), else NaN."""
    left = pd.DataFrame({"target": df["date"] - pd.DateOffset(years=1)})
    right = df.rename(columns={"date": "ago_date", "value": "ago"})
    m = pd.merge_asof(left, right, left_on="target", right_on="ago_date",
                      direction="nearest", tolerance=pd.Timedelta(days=10))
    return pd.Series(m["ago"].to_numpy(), index=df.index)


def add_yoy(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    out = df.copy()
    ago = year_ago(out)
    out["year_ago"] = ago
    if kind == "level":
        out["yoy"] = (out["value"] / ago - 1.0) * 100.0
    else:
        out["yoy"] = out["value"] - ago
    return out


def recession_periods(usrec: pd.DataFrame) -> pd.DataFrame:
    """Runs of consecutive 1s in the monthly flag become (start, end) rows."""
    flag = usrec.sort_values("date").reset_index(drop=True)
    on = flag["value"] >= 0.5
    run = (on != on.shift()).cumsum()
    rows = []
    for _, g in flag[on].groupby(run[on]):
        rows.append((g["date"].iloc[0], g["date"].iloc[-1] + pd.offsets.MonthEnd(0)))
    return pd.DataFrame(rows, columns=["start", "end"])


def recession_flag(dates: pd.Series, usrec: pd.DataFrame) -> pd.Series:
    """1 if the date falls in an NBER recession month, 0 if not, blank if the flag has no reading yet."""
    by_month = dict(zip(usrec["date"].dt.to_period("M"), usrec["value"].astype(int)))
    return dates.dt.to_period("M").map(by_month).astype("Int64")


def frequency(df: pd.DataFrame) -> str:
    gap = df["date"].diff().dt.days.median()
    if gap <= 4:
        return "Daily"
    if gap <= 8:
        return "Weekly"
    if gap <= 35:
        return "Monthly"
    return "Quarterly"


def build(frames: dict, usrec: pd.DataFrame, fetched_on: str):
    """frames: series_id -> frame of date, value. Returns (observations, summary, recessions)."""
    obs_parts, summary_rows = [], []
    for sid, label, group, units, kind in SERIES:
        d = add_yoy(frames[sid], kind)
        d["series_id"], d["label"], d["group"] = sid, label, group
        d["recession"] = recession_flag(d["date"], usrec)
        obs_parts.append(d[["date", "series_id", "label", "group", "value", "yoy", "recession"]])
        last = d.iloc[-1]
        summary_rows.append({
            "series_id": sid, "label": label, "group": group, "units": units,
            "frequency": frequency(d), "latest_date": last["date"].date().isoformat(),
            "latest_value": last["value"], "previous_value": d["value"].iloc[-2] if len(d) > 1 else None,
            "year_ago_value": last["year_ago"], "yoy": last["yoy"],
            "yoy_unit": "% change" if kind == "level" else "percentage points",
            "first_date": d["date"].iloc[0].date().isoformat(), "observations": len(d),
            "fetched_on": fetched_on,
        })
    obs = pd.concat(obs_parts, ignore_index=True)
    obs["date"] = obs["date"].dt.date.astype(str)
    obs["value"] = obs["value"].round(4)
    obs["yoy"] = obs["yoy"].round(4)
    summary = pd.DataFrame(summary_rows)
    for c in ("latest_value", "previous_value", "year_ago_value", "yoy"):
        summary[c] = summary[c].astype(float).round(4)
    rec = recession_periods(usrec)
    rec["start"] = rec["start"].dt.date.astype(str)
    rec["end"] = rec["end"].dt.date.astype(str)
    return obs, summary, rec


def run(key: str, out: Path, start: str = START, session=None, log=print) -> None:
    frames = {}
    for sid, *_ in SERIES:
        frames[sid] = fetch_series(sid, key, start, session)
        log(f"  {sid}: {len(frames[sid])} readings, latest {frames[sid]['date'].iloc[-1].date()}")
    usrec = fetch_series(RECESSION_ID, key, start, session)
    log(f"  {RECESSION_ID}: {len(usrec)} months")
    obs, summary, rec = build(frames, usrec, datetime.now(timezone.utc).date().isoformat())
    out.mkdir(parents=True, exist_ok=True)           # reached only if every series succeeded
    obs.to_csv(out / "observations.csv", index=False)
    summary.to_csv(out / "series_summary.csv", index=False)
    rec.to_csv(out / "recessions.csv", index=False)
    log(f"Wrote {len(obs):,} rows to {out / 'observations.csv'}, plus series_summary.csv and recessions.csv")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch FRED indicators into tidy CSVs for Tableau.")
    ap.add_argument("--start", default=START, help=f"first observation date (default {START})")
    ap.add_argument("--out", default=str(ROOT / "data"), help="output folder (default data/)")
    args = ap.parse_args(argv)
    load_dotenv()
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        print("FRED_API_KEY is not set. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html", file=sys.stderr)
        return 2
    try:
        run(key, Path(args.out), args.start)
    except FetchError as e:
        print(f"Stopped, nothing was written: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
