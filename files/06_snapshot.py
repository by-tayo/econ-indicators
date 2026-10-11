"""Build a current-values snapshot across all 9 book indicators: latest
value, value 12 months prior, and direction. Writes output/snapshot.csv and
prints a ready-to-paste markdown table.
"""
import pandas as pd

from econ_common import DATA_PROCESSED, INDICATORS, OUTPUT


def direction(prev: float, latest: float) -> str:
    if prev == 0:
        return "n/a"
    pct_change = (latest - prev) / abs(prev)
    if pct_change > 0.005:
        return "Rising"
    if pct_change < -0.005:
        return "Falling"
    return "Flat"


def main() -> None:
    dashboard = pd.read_csv(DATA_PROCESSED / "dashboard.csv", index_col=0, parse_dates=True)

    rows = []
    for series_id, meta in INDICATORS.items():
        s = dashboard[series_id].dropna()
        latest_date, latest_value = s.index[-1], s.iloc[-1]
        prior_idx = s.index[s.index <= latest_date - pd.DateOffset(months=12)]
        prior_value = s.loc[prior_idx[-1]] if len(prior_idx) else None

        rows.append({
            "indicator": meta["name"],
            "series_id": series_id,
            "class": meta["cls"],
            "latest_date": latest_date.date(),
            "latest_value": round(latest_value, 2),
            "value_12mo_ago": round(prior_value, 2) if prior_value is not None else None,
            "trend": direction(prior_value, latest_value) if prior_value is not None else "n/a",
        })

    snapshot = pd.DataFrame(rows)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    snapshot.to_csv(OUTPUT / "snapshot.csv", index=False)

    print("| Indicator | Class | Latest | as of | 12mo ago | Trend |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['indicator']} | {r['class']} | {r['latest_value']:,} | "
              f"{r['latest_date']} | {r['value_12mo_ago']:,} | {r['trend']} |")


if __name__ == "__main__":
    main()
