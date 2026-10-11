"""Score the composite against NBER recession dates (USREC), report lead
times and false positives, and call out the 2020 recession separately since
the threshold/weights were fixed before ever looking at how it performed
there.
"""
import pandas as pd

from econ_common import (
    COMPOSITE_THRESHOLD,
    DATA_PROCESSED,
    OUTPUT,
    backtest,
    find_recession_starts,
    load_cached,
    recessions_in_coverage,
    to_monthly,
)


def main() -> None:
    composite_df = pd.read_csv(DATA_PROCESSED / "composite.csv", index_col=0, parse_dates=True)
    composite = composite_df["composite_smoothed"].dropna()

    # Pass the FULL usrec history (not truncated to the composite's own date
    # range) into backtest(): truncating first would make find_recession_starts
    # treat a recession already underway when the composite's data begins as
    # a brand-new recession starting right there (a boundary artifact, not a
    # real signal). Coverage is instead handled explicitly below.
    usrec = to_monthly(load_cached("USREC"), method="last")
    all_recession_starts = find_recession_starts(usrec)
    in_coverage = recessions_in_coverage(all_recession_starts, composite)
    out_of_coverage = [r for r in all_recession_starts if r not in in_coverage]

    outcome = backtest(composite, usrec, threshold=COMPOSITE_THRESHOLD)

    rows = []
    for r in outcome["results"]:
        if r["recession_start"] not in in_coverage:
            continue  # composite didn't exist yet; not a real miss, see coverage note below
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
    print(f"\n{n_hit}/{n_total} recessions caught within coverage, avg lead time "
          f"{avg_lead:.1f} months, {len(outcome['false_positives'])} false positive(s).")
    # Recessions before FRED's modern series coverage (UMCSENT starts 1952)
    # are structurally irrelevant noise here, not part of this index's story.
    modern_out_of_coverage = [r for r in out_of_coverage if r >= pd.Timestamp("1950-01-01")]
    if modern_out_of_coverage:
        named = ", ".join(r.date().isoformat() for r in modern_out_of_coverage)
        print(f"Outside coverage (index doesn't start early enough to have warned): {named}")

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
