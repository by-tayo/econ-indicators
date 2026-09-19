import numpy as np
import pandas as pd
import pytest

from econ_common import (
    backtest,
    build_composite,
    find_crossings,
    find_recession_starts,
    months_between,
    recession_periods,
    recessions_in_coverage,
    smooth,
    to_monthly,
    transform_series,
    walkforward_zscore,
    zscore,
)


def monthly_index(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=periods, freq="MS")


# ---------------------------------------------------------------------------
# transform_series
# ---------------------------------------------------------------------------

def test_transform_series_pct_is_symmetric():
    s = pd.Series([100.0, 110.0, 100.0])
    out = transform_series(s, "pct")
    assert out.iloc[0] == pytest.approx(-out.iloc[1])


def test_transform_series_diff_is_simple_difference():
    s = pd.Series([1.0, 3.0, 6.0])
    out = transform_series(s, "diff")
    assert list(out) == [2.0, 3.0]


def test_transform_series_rejects_unknown_transform():
    with pytest.raises(ValueError):
        transform_series(pd.Series([1.0, 2.0]), "bogus")


def test_components_measure_the_cycle_not_the_calendar():
    """A transformed component should not be strongly correlated with time.

    A raw level series that trends (PPI, housing starts) correlates near 1.0
    with a time counter. After transforming to changes, that correlation
    should collapse. If it doesn't, the index is measuring what year it is.
    """
    trending = pd.Series(
        np.exp(np.linspace(0, 2, 240)),
        index=pd.date_range("2000-01-01", periods=240, freq="MS"),
    )
    time_counter = np.arange(len(trending))

    raw_corr = abs(np.corrcoef(trending.values, time_counter)[0, 1])
    changed = transform_series(trending, "pct")
    changed_corr = abs(np.corrcoef(changed.values, time_counter[1:])[0, 1])

    assert raw_corr > 0.9        # the level is basically a clock
    assert changed_corr < 0.3    # the change is not


# ---------------------------------------------------------------------------
# zscore / walkforward_zscore / to_monthly / smooth
# ---------------------------------------------------------------------------

def test_zscore_mean_zero_std_one():
    idx = monthly_index("2020-01-01", 30)
    s = pd.Series(range(1, 31), index=idx, dtype=float)
    z = zscore(s)
    assert z.mean() == pytest.approx(0, abs=1e-9)
    assert z.std() == pytest.approx(1, abs=1e-9)


def test_zscore_rejects_constant_series():
    idx = monthly_index("2020-01-01", 30)
    s = pd.Series([5.0] * 30, index=idx)
    with pytest.raises(ValueError):
        zscore(s)


def test_zscore_rejects_short_training_window():
    idx = monthly_index("2020-01-01", 10)
    s = pd.Series(range(10), index=idx, dtype=float)
    with pytest.raises(ValueError):
        zscore(s)


def test_zscore_uses_training_window_only():
    # Stable values through the training window, then a wild swing after
    # train_end. A full-history zscore lets the wild values drag the mean/std
    # used to score the training-window points; a train-window zscore does not.
    idx = monthly_index("2020-01-01", 30)
    values = list(range(1, 25)) + [1000.0, -1000.0, 2000.0, -2000.0, 500.0, -500.0]
    s = pd.Series(values, index=idx, dtype=float)
    train_end = idx[23]

    z_trained = zscore(s, train_end=train_end)
    z_full = zscore(s, train_end=None)

    assert not z_trained.iloc[:24].equals(z_full.iloc[:24])
    assert z_trained.iloc[:24].mean() == pytest.approx(0, abs=1e-6)


def test_walkforward_zscore_ignores_future_values():
    # A large spike late in the series should not shift the standardization
    # of points scored long before it happened.
    idx = monthly_index("2020-01-01", 10)
    baseline = pd.Series([1, 2, 3, 4, 1, 2, 3, 4] + [1000, 1000], index=idx, dtype=float)
    without_spike = walkforward_zscore(baseline, min_periods=4)
    with_bigger_spike = baseline.copy()
    with_bigger_spike.iloc[-1] = 1_000_000
    with_spike = walkforward_zscore(with_bigger_spike, min_periods=4)
    # Points before the spike are computed from an expanding window that
    # hasn't reached the spike yet, so they're identical either way.
    assert without_spike.iloc[:8].equals(with_spike.iloc[:8])


def test_walkforward_zscore_nan_before_min_periods():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=monthly_index("2020-01-01", 5))
    z = walkforward_zscore(s, min_periods=3)
    assert z.iloc[:2].isna().all()
    assert not pd.isna(z.iloc[2])


def test_to_monthly_mean_resamples_weekly():
    idx = pd.date_range("2020-01-01", periods=8, freq="W")
    s = pd.Series(range(8), index=idx, dtype=float)
    monthly = to_monthly(s, method="mean")
    assert monthly.index.freqstr == "MS"
    assert len(monthly) == 2


def test_to_monthly_ffill_holds_quarterly_value():
    idx = pd.date_range("2020-01-01", periods=2, freq="QS")
    s = pd.Series([100.0, 110.0], index=idx)
    monthly = to_monthly(s, method="ffill")
    assert monthly.loc["2020-02-01"] == 100.0


def test_smooth_is_rolling_mean():
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=monthly_index("2020-01-01", 4))
    smoothed = smooth(s, window=2)
    assert smoothed.iloc[1] == pytest.approx(1.5)
    assert smoothed.iloc[3] == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# build_composite
# ---------------------------------------------------------------------------

def test_build_composite_equal_weight_average_of_zscores():
    idx = monthly_index("2020-01-01", 30)
    values = (np.arange(30) ** 2).astype(float)
    a = pd.Series(values, index=idx)
    b = pd.Series(-values, index=idx)
    composite = build_composite({"a": a, "b": b}, transforms={"a": "diff", "b": "diff"})
    # a and b are mirror images with equal weight -> composite is ~0 everywhere
    assert composite.abs().max() == pytest.approx(0, abs=1e-9)


def test_build_composite_inverts_named_series():
    idx = monthly_index("2020-01-01", 30)
    a = pd.Series(np.arange(10.0, 40.0), index=idx)
    composite = build_composite({"a": a}, weights={"a": 1.0}, invert={"a"})
    expected = -zscore(transform_series(a, "pct"), train_end=None)
    assert composite.equals(expected)


def test_build_composite_rejects_bad_weights():
    idx = monthly_index("2020-01-01", 3)
    a = pd.Series([1, 2, 3], index=idx, dtype=float)
    with pytest.raises(ValueError):
        build_composite({"a": a}, weights={"a": 0.5})


def test_build_composite_only_uses_overlapping_dates():
    a_idx = monthly_index("2020-01-01", 30)
    b_idx = monthly_index("2020-04-01", 27)  # starts 3 months later, ends the same month as a
    a = pd.Series(np.arange(30.0) ** 2 + 1.0, index=a_idx)
    b = pd.Series(np.arange(27.0) ** 1.7 + 1.0, index=b_idx)
    composite = build_composite({"a": a, "b": b}, transforms={"a": "diff", "b": "diff"})
    assert len(composite) == 26  # diff(b) has 26 points, all within diff(a)'s range


def test_build_composite_respects_train_end():
    idx = monthly_index("2020-01-01", 30)
    a = pd.Series(np.arange(30.0) ** 2 + 1.0, index=idx)
    composite_full = build_composite({"a": a}, weights={"a": 1.0}, transforms={"a": "diff"}, train_end=None)
    composite_trained = build_composite(
        {"a": a}, weights={"a": 1.0}, transforms={"a": "diff"}, train_end=idx[24]
    )
    assert not composite_full.equals(composite_trained)


# ---------------------------------------------------------------------------
# find_crossings / find_recession_starts / months_between / recessions_in_coverage
# ---------------------------------------------------------------------------

def test_find_crossings_detects_downward_crossing_only():
    idx = monthly_index("2020-01-01", 5)
    s = pd.Series([1.0, 0.5, -1.0, -1.0, 1.0], index=idx)
    crossings = find_crossings(s, threshold=0.0)
    assert crossings == [idx[2]]


def test_find_recession_starts_detects_transition_to_one():
    idx = monthly_index("2020-01-01", 5)
    usrec = pd.Series([0, 0, 1, 1, 0], index=idx)
    starts = find_recession_starts(usrec)
    assert starts == [idx[2]]


def test_recession_periods_groups_contiguous_ones():
    idx = monthly_index("2020-01-01", 6)
    usrec = pd.Series([0, 1, 1, 0, 1, 0], index=idx)
    periods = recession_periods(usrec)
    assert periods == [(idx[1], idx[2]), (idx[4], idx[4])]


def test_months_between():
    a = pd.Timestamp("2020-01-01")
    b = pd.Timestamp("2020-06-01")
    assert months_between(a, b) == 5
    assert months_between(b, a) == -5


def test_recessions_in_coverage_filters_out_recessions_before_index_start():
    idx = monthly_index("1990-01-01", 5)
    index_series = pd.Series([1.0] * 5, index=idx)
    starts = [pd.Timestamp("1980-01-01"), pd.Timestamp("1990-03-01")]
    assert recessions_in_coverage(starts, index_series) == [pd.Timestamp("1990-03-01")]


def test_recessions_in_coverage_empty_index_returns_empty():
    assert recessions_in_coverage([pd.Timestamp("1990-01-01")], pd.Series(dtype=float)) == []


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------

def test_backtest_scores_a_clean_hit_with_correct_lead_time():
    idx = monthly_index("2020-01-01", 6)
    composite = pd.Series([1.0, 1.0, -1.0, -1.0, -1.0, -1.0], index=idx)
    usrec = pd.Series([0, 0, 0, 0, 1, 1], index=idx)

    outcome = backtest(composite, usrec, threshold=0.0)

    assert len(outcome["results"]) == 1
    result = outcome["results"][0]
    assert result["hit"] is True
    assert result["signal_date"] == idx[2]
    assert result["lead_months"] == 2
    assert outcome["false_positives"] == []


def test_backtest_reports_a_miss_when_no_crossing_precedes_recession():
    idx = monthly_index("2020-01-01", 4)
    composite = pd.Series([1.0, 1.0, 1.0, 1.0], index=idx)
    usrec = pd.Series([0, 0, 0, 1], index=idx)

    outcome = backtest(composite, usrec, threshold=0.0)

    assert outcome["results"][0]["hit"] is False
    assert outcome["results"][0]["signal_date"] is None


def test_backtest_flags_unmatched_crossing_as_false_positive():
    idx = monthly_index("2020-01-01", 20)
    composite = pd.Series([1.0] * 20, index=idx)
    composite.iloc[5] = -1.0  # single isolated downward crossing, no recession ever follows
    usrec = pd.Series([0] * 20, index=idx)

    outcome = backtest(composite, usrec, threshold=0.0, false_positive_horizon_months=6)

    assert outcome["results"] == []
    assert outcome["false_positives"] == [idx[5]]


def test_backtest_does_not_flag_late_crossing_during_recession_as_false_positive():
    # Crossing happens two months *after* the recession already started: it's
    # too late to count as a lead-time hit, but it also isn't a false alarm —
    # it's a coincident confirmation, not a bogus warning about the future.
    idx = monthly_index("2020-01-01", 8)
    composite = pd.Series([1.0, 1.0, 1.0, -1.0, -1.0, -1.0, 1.0, 1.0], index=idx)
    usrec = pd.Series([0, 0, 1, 1, 1, 1, 0, 0], index=idx)

    outcome = backtest(composite, usrec, threshold=0.0, max_lookback_months=1)

    assert outcome["results"][0]["hit"] is False  # crossing at idx[3] is after recession start idx[2]
    assert outcome["false_positives"] == []
