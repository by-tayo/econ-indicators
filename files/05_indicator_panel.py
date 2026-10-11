"""Small-multiples panel of the 4 leading indicators (raw levels, not the
composite) so a reader can see which indicator is actually driving a dip in
the composite, saved to output/indicator_panel.png.
"""
import matplotlib.pyplot as plt
import pandas as pd

from econ_common import DATA_PROCESSED, INDICATORS, LEADING_SERIES, OUTPUT, load_cached, recession_periods, to_monthly

LINE_COLOR = "#2a78d6"       # dataviz palette: categorical slot 1 (blue)
RECESSION_COLOR = "#c3c2b7"  # dataviz palette: muted/baseline ink
GRID_COLOR = "#e1e0d9"       # dataviz palette: hairline gridline
AXIS_COLOR = "#898781"       # dataviz palette: muted ink


def main() -> None:
    dashboard = pd.read_csv(DATA_PROCESSED / "dashboard.csv", index_col=0, parse_dates=True)
    usrec = to_monthly(load_cached("USREC"), method="last")
    periods = recession_periods(usrec.loc[usrec.index <= dashboard.index.max()])

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), facecolor="#fcfcfb")
    for ax, series_id in zip(axes.flat, LEADING_SERIES):
        s = dashboard[series_id].dropna()
        ax.set_facecolor("#fcfcfb")
        for start, end in periods:
            ax.axvspan(start, end, color=RECESSION_COLOR, alpha=0.3, linewidth=0)
        ax.plot(s.index, s.values, color=LINE_COLOR, linewidth=1.5)
        ax.set_title(INDICATORS[series_id]["name"], fontsize=11, color="#0b0b0b")
        ax.set_xlim(s.index.min(), s.index.max())
        ax.grid(color=GRID_COLOR, linewidth=0.8)
        ax.tick_params(colors=AXIS_COLOR, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)

    fig.suptitle("Leading Indicators — Raw Levels", fontsize=13, color="#0b0b0b")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "indicator_panel.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved panel to {out_path}")


if __name__ == "__main__":
    main()
