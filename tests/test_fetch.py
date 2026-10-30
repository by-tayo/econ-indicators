import sys
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_data as fd  # noqa: E402

KEY = "SECRETKEY123"


def frame(rows):
    return pd.DataFrame({"date": pd.to_datetime([r[0] for r in rows]), "value": [r[1] for r in rows]})


class Resp:
    def __init__(self, code=200, payload=None):
        self.status_code = code
        self._p = payload

    def json(self):
        if self._p is None:
            raise ValueError("bad json")
        return self._p


def payload(rows):
    return {"observations": [{"date": d, "value": v} for d, v in rows]}


class FakeSession:
    """Answers each series id with a monthly series that rises 1 per month from 100."""
    def __init__(self, fail_on=None):
        self.fail_on, self.calls = fail_on, []

    def get(self, url, params, timeout):
        sid = params["series_id"]
        self.calls.append(sid)
        if sid == self.fail_on:
            return Resp(500)
        dates = pd.date_range("2019-01-01", periods=36, freq="MS")
        if sid == "USREC":
            return Resp(200, payload([(d.date().isoformat(), "1" if d.year == 2020 and d.month in (3, 4, 5) else "0") for d in dates]))
        return Resp(200, payload([(d.date().isoformat(), str(100 + i)) for i, d in enumerate(dates)]))


def test_parse_drops_missing_dot():
    df = fd.parse_observations(payload([("2020-01-01", "5.0"), ("2020-02-01", "."), ("2020-03-01", "6.0")]))
    assert list(df["value"]) == [5.0, 6.0]
    assert df["date"].is_monotonic_increasing


def test_yoy_level_is_percent_change():
    df = frame([("2019-01-01", 100.0), ("2020-01-01", 110.0)])
    out = fd.add_yoy(df, "level")
    assert pd.isna(out["yoy"].iloc[0])
    assert out["yoy"].iloc[1] == pytest.approx(10.0)
    assert out["year_ago"].iloc[1] == 100.0


def test_yoy_rate_is_point_difference():
    df = frame([("2019-01-01", 4.0), ("2020-01-01", 3.5)])
    assert fd.add_yoy(df, "rate")["yoy"].iloc[1] == pytest.approx(-0.5)


def test_yoy_weekly_uses_nearest_week_and_gaps_give_nan():
    df = frame([("2019-01-05", 200.0), ("2020-01-04", 220.0), ("2021-06-01", 300.0)])
    out = fd.add_yoy(df, "level")
    assert out["yoy"].iloc[1] == pytest.approx(10.0)      # 2019-01-05 is 1 day from 2019-01-04
    assert pd.isna(out["yoy"].iloc[2])                    # nothing near 2020-06-01


def test_recession_periods_group_runs():
    months = pd.date_range("2020-01-01", periods=8, freq="MS")
    usrec = frame([(d.date().isoformat(), v) for d, v in zip(months, [0, 1, 1, 0, 1, 0, 0, 0])])
    rec = fd.recession_periods(usrec)
    assert [d.date().isoformat() for d in rec["start"]] == ["2020-02-01", "2020-05-01"]
    assert [d.date().isoformat() for d in rec["end"]] == ["2020-03-31", "2020-05-31"]


def test_recession_flag_by_month_and_blank_when_unknown():
    usrec = frame([("2020-01-01", 0), ("2020-02-01", 1)])
    dates = pd.Series(pd.to_datetime(["2020-02-17", "2020-01-03", "2020-09-01"]))
    flag = fd.recession_flag(dates, usrec)
    assert flag.iloc[0] == 1 and flag.iloc[1] == 0 and pd.isna(flag.iloc[2])


def test_frequency_labels():
    assert fd.frequency(frame([("2020-01-01", 1), ("2020-01-02", 1), ("2020-01-03", 1)])) == "Daily"
    assert fd.frequency(frame([("2020-01-04", 1), ("2020-01-11", 1), ("2020-01-18", 1)])) == "Weekly"
    assert fd.frequency(frame([("2020-01-01", 1), ("2020-02-01", 1), ("2020-03-01", 1)])) == "Monthly"
    assert fd.frequency(frame([("2020-01-01", 1), ("2020-04-01", 1), ("2020-07-01", 1)])) == "Quarterly"


def test_run_writes_three_tidy_files(tmp_path):
    fd.run(KEY, tmp_path, session=FakeSession(), log=lambda *_: None)
    obs = pd.read_csv(tmp_path / "observations.csv")
    summ = pd.read_csv(tmp_path / "series_summary.csv")
    rec = pd.read_csv(tmp_path / "recessions.csv")
    assert list(obs.columns) == ["date", "series_id", "label", "group", "value", "yoy", "recession"]
    assert len(obs) == 36 * len(fd.SERIES)
    assert set(obs["series_id"]) == {s[0] for s in fd.SERIES}
    assert len(summ) == len(fd.SERIES)
    row = summ[summ["series_id"] == "CPIAUCSL"].iloc[0]
    assert row["latest_value"] == 135 and row["previous_value"] == 134 and row["year_ago_value"] == 123
    assert row["yoy"] == pytest.approx((135 / 123 - 1) * 100, abs=1e-3)
    assert row["yoy_unit"] == "% change"
    assert summ[summ["series_id"] == "UNRATE"].iloc[0]["yoy_unit"] == "percentage points"
    assert rec.iloc[0].tolist() == ["2020-03-01", "2020-05-31"]
    assert obs[(obs["series_id"] == "UNRATE") & (obs["date"] == "2020-04-01")]["recession"].iloc[0] == 1


def test_failed_series_writes_nothing(tmp_path):
    out = tmp_path / "data"
    with pytest.raises(fd.FetchError):
        fd.run(KEY, out, session=FakeSession(fail_on="HOUST"), log=lambda *_: None)
    assert not out.exists()


def test_retry_then_success(monkeypatch):
    monkeypatch.setattr(fd.time, "sleep", lambda s: None)

    class S:
        n = 0

        def get(self, url, params, timeout):
            S.n += 1
            return Resp(429) if S.n == 1 else Resp(200, payload([("2020-01-01", "5")]))
    assert len(fd.fetch_series("UNRATE", KEY, session=S())) == 1 and S.n == 2


def test_busy_forever_gives_friendly_error(monkeypatch):
    monkeypatch.setattr(fd.time, "sleep", lambda s: None)

    class S:
        def get(self, url, params, timeout):
            return Resp(429)
    with pytest.raises(fd.FetchError, match="busy"):
        fd.fetch_series("UNRATE", KEY, session=S())


def test_network_error_does_not_leak_key():
    class S:
        def get(self, url, params, timeout):
            raise requests.ConnectionError(f"failed for {url}?api_key={params['api_key']}")
    with pytest.raises(fd.FetchError) as e:
        fd.fetch_series("UNRATE", KEY, session=S())
    assert KEY not in str(e.value) and KEY not in repr(e.value.__cause__)


def test_bad_key_message_has_no_key():
    class S:
        def get(self, url, params, timeout):
            return Resp(400)
    with pytest.raises(fd.FetchError) as e:
        fd.fetch_series("UNRATE", KEY, session=S())
    assert "FRED_API_KEY" in str(e.value) and KEY not in str(e.value)


def test_empty_series_is_an_error():
    class S:
        def get(self, url, params, timeout):
            return Resp(200, payload([]))
    with pytest.raises(fd.FetchError, match="no readings"):
        fd.fetch_series("UNRATE", KEY, session=S())


def test_main_without_key_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(fd, "load_dotenv", lambda *a, **k: None)
    assert fd.main(["--out", str(tmp_path)]) == 2
    assert "FRED_API_KEY" in capsys.readouterr().err


def test_dotenv_does_not_override_environment(monkeypatch, tmp_path):
    p = tmp_path / ".env"
    p.write_text('# c\nFRED_API_KEY="fromfile"\nOTHER=1\n')
    monkeypatch.setenv("FRED_API_KEY", "fromenv")
    monkeypatch.delenv("OTHER", raising=False)
    fd.load_dotenv(p)
    assert fd.os.environ["FRED_API_KEY"] == "fromenv" and fd.os.environ["OTHER"] == "1"
    monkeypatch.delenv("OTHER", raising=False)
