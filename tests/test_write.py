"""Tests for write_csvs: new files replace old ones only when every write succeeded."""
from pathlib import Path

import pandas as pd
import pytest

import fetch_data as fd


def tables():
    df = pd.DataFrame({"a": [1, 2]})
    return {"observations.csv": df, "series_summary.csv": df, "recessions.csv": df}


def test_write_csvs_writes_all_files_and_leaves_no_temp_files(tmp_path):
    fd.write_csvs(tmp_path, tables())
    for name in ("observations.csv", "series_summary.csv", "recessions.csv"):
        assert pd.read_csv(tmp_path / name)["a"].tolist() == [1, 2]
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_failure_leaves_existing_files_untouched(tmp_path, monkeypatch):
    (tmp_path / "observations.csv").write_text("old")
    (tmp_path / "series_summary.csv").write_text("old")
    real_to_csv = pd.DataFrame.to_csv

    def flaky(self, path, *args, **kwargs):
        if Path(path).name == ".series_summary.csv.tmp":
            raise OSError("disk full")
        return real_to_csv(self, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_csv", flaky)
    with pytest.raises(OSError):
        fd.write_csvs(tmp_path, tables())

    assert (tmp_path / "observations.csv").read_text() == "old"
    assert (tmp_path / "series_summary.csv").read_text() == "old"
    assert not (tmp_path / "recessions.csv").exists()
    assert not list(tmp_path.glob(".*.tmp"))