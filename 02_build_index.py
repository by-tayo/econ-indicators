"""Align all indicators to monthly frequency, build the leading composite
(month-over-month change, walk-forward z-scored, equally-weighted, threshold
fixed a priori) and a dashboard of the remaining coincident/lagging
indicators for context.
"""
import pandas as pd

from econ_common import (
    COMPOSITE_WEIGHTS,
    DATA_PROCESSED,
    INDICATORS,
    LEADING_SERIES,
    build_composite,
    load_cached,
    smooth,
    to_monthly,
    walkforward_zscore,
)


def main() -> None:
    monthly = {}
    for series_id, meta in INDICATORS.items():
        raw = load_cached(series_id)
        monthly[series_id] = to_monthly(raw, method=meta["resample"])

    # Level series like PPI trend for decades, which would otherwise swamp
    # the composite with a secular ramp instead of cyclical signal. Feed the
    # composite month-over-month % change instead, so it reflects momentum.
    leading_components = {sid: monthly[sid].pct_change().dropna() for sid in LEADING_SERIES}
    invert = {sid for sid in LEADING_SERIES if INDICATORS[sid]["invert"]}

    composite = build_composite(leading_components, COMPOSITE_WEIGHTS, invert, standardize=walkforward_zscore)
    composite_smoothed = smooth(composite, window=3)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    out = pd.DataFrame({
        "composite": composite,
        "composite_smoothed": composite_smoothed,
    })
    out.to_csv(DATA_PROCESSED / "composite.csv")

    dashboard = pd.DataFrame(monthly)
    dashboard.to_csv(DATA_PROCESSED / "dashboard.csv")

    print(f"Composite built from {LEADING_SERIES} ({len(composite)} months, "
          f"{composite.index[0].date()} - {composite.index[-1].date()}).")
    print(f"Saved composite to {DATA_PROCESSED / 'composite.csv'}")
    print(f"Saved dashboard series to {DATA_PROCESSED / 'dashboard.csv'}")


if __name__ == "__main__":
    main()
