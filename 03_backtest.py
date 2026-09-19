"""Score the composite against NBER recession dates (USREC), report lead
times and false positives, and call out the 2020 recession separately since
the threshold/weights were fixed before ever looking at how it performed
there.
"""
import pandas as pd

from econ_common import COMPOSITE_THRESHOLD, DATA_PROCESSED, OUTPUT, backtest, load_cached, to_monthly


def main() -> None:
    composite_df = pd.read_csv(DATA_PROCESSED / "composite.csv", index_col=0, parse_dates=True)
    composite = composite_df["composite_smoothed"].dropna()

    usrec = to_monthly(load_cached("USREC"), method="last")

    common_index = composite.index.intersection(usrec.index)
    composite = composite.loc[common_index]
    usrec = usrec.loc[common_index]

    outcome = backtest(composite, usrec, threshold=COMPOSITE_THRESHOLD)

    rows = []
    for r in outcome["results"]:
        rows.append({
            "recession_start": r["recession_start"].date(),
            "signal_date": r["signal_date"].date() if r["signal_date"] is not None else None,
            "lead_months": r["lead_months"],
            "hit": r["hit"],
        })
    results_df = pd.DataFrame(rows)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(OUTPUT / "results.csv", index=False)

    print(f"Threshold: {COMPOSITE_THRESHOLD} (fixed a priori)\n")
    print(results_df.to_string(index=False))

    n_hit = results_df["hit"].sum()
    n_total = len(results_df)
    avg_lead = results_df.loc[results_df["hit"], "lead_months"].mean()
    print(f"\n{n_hit}/{n_total} recessions caught, avg lead time "
          f"{avg_lead:.1f} months, {len(outcome['false_positives'])} false positive(s).")

    holdout_2020 = results_df[results_df["recession_start"].astype(str).str.startswith("2020")]
    if not holdout_2020.empty:
        row = holdout_2020.iloc[0]
        verdict = "caught" if row["hit"] else "missed"
        print(f"\n2020 hold-out: the composite {verdict} the COVID recession "
              f"(threshold/weights were never adjusted using 2020 data).")

    if outcome["false_positives"]:
        print("\nFalse positive signal dates (no recession followed within 12 months):")
        for fp in outcome["false_positives"]:
            print(f"  {fp.date()}")


if __name__ == "__main__":
    main()
