"""Chart the composite index against shaded NBER recession periods, with
backtest signal dates marked, saved to output/index_vs_recessions.png.
"""
import matplotlib.pyplot as plt
import pandas as pd

from econ_common import COMPOSITE_THRESHOLD, DATA_PROCESSED, OUTPUT, load_cached, recession_periods, to_monthly


def main() -> None:
    composite_df = pd.read_csv(DATA_PROCESSED / "composite.csv", index_col=0, parse_dates=True)
    usrec = to_monthly(load_cached("USREC"), method="last")

    common_index = composite_df.index.intersection(usrec.index)
    composite_df = composite_df.loc[common_index]
    usrec = usrec.loc[common_index]

    try:
        results_df = pd.read_csv(OUTPUT / "results.csv", parse_dates=["signal_date"])
        signal_dates = results_df["signal_date"].dropna()
    except FileNotFoundError:
        signal_dates = pd.Series(dtype="datetime64[ns]")

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(composite_df.index, composite_df["composite"], color="#9aa5b1", linewidth=0.8, label="Composite (raw)")
    ax.plot(composite_df.index, composite_df["composite_smoothed"], color="#1f4e79", linewidth=1.8, label="Composite (3mo avg)")
    ax.axhline(COMPOSITE_THRESHOLD, color="#c0392b", linestyle="--", linewidth=1, label=f"Threshold ({COMPOSITE_THRESHOLD})")

    for start, end in recession_periods(usrec):
        ax.axvspan(start, end, color="grey", alpha=0.25)

    for d in signal_dates:
        ax.axvline(d, color="#c0392b", linewidth=0.8, alpha=0.6)

    ax.set_title("Leading Composite Index vs. NBER Recessions")
    ax.set_ylabel("Composite (z-score units)")
    ax.legend(loc="lower left")
    fig.tight_layout()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "index_vs_recessions.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved chart to {out_path}")


if __name__ == "__main__":
    main()
