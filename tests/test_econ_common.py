import pandas as pd
import pytest

from econ_common import (
    backtest,
    build_composite,
    find_crossings,
    find_recession_starts,
    months_between,
    recession_periods,
    smooth,
    to_monthly,
    zscore,
)


def monthly_index(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=periods, freq="MS")


# ---------------------------------------------------------------------------
# zscore / to_monthly / smooth
# ---------------------------------------------------------------------------

def test_zscore_mean_zero_std_one():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    z = zscore(s)
    assert z.mean() == pytest.approx(0, abs=1e-9)
    assert z.std() == pytest.approx(1, abs=1e-9)


def test_zscore_rejects_constant_series():
    s = pd.Series([5, 5, 5], dtype=float)
    with pytest.raises(ValueError):
        zscore(s)


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
    idx = monthly_index("2020-01-01", 5)
    a = pd.Series([1, 2, 3, 4, 5], index=idx, dtype=float)
    b = pd.Series([5, 4, 3, 2, 1], index=idx, dtype=float)
    composite = build_composite({"a": a, "b": b})
    # a and b are mirror images with equal weight -> composite is ~0 everywhere
    assert composite.abs().max() == pytest.approx(0, abs=1e-9)


def test_build_composite_inverts_named_series():
    idx = monthly_index("2020-01-01", 5)
    a = pd.Series([1, 2, 3, 4, 5], index=idx, dtype=float)
    composite = build_composite({"a": a}, weights={"a": 1.0}, invert={"a"})
    assert (composite == -zscore(a)).all()


def test_build_composite_rejects_bad_weights():
    idx = monthly_index("2020-01-01", 3)
    a = pd.Series([1, 2, 3], index=idx, dtype=float)
    with pytest.raises(ValueError):
        build_composite({"a": a}, weights={"a": 0.5})


def test_build_composite_only_uses_overlapping_dates():
    a = pd.Series([1.0, 2.0, 3.0], index=monthly_index("2020-01-01", 3))
    b = pd.Series([1.0, 2.0], index=monthly_index("2020-01-01", 2))
    composite = build_composite({"a": a, "b": b})
    assert len(composite) == 2


# ---------------------------------------------------------------------------
# find_crossings / find_recession_starts / months_between
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
