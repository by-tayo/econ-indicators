"""Pull the 9 indicators plus benchmark series from FRED, caching raw pulls
to data/raw/ so later steps and reruns don't hit the API again.
"""
from econ_common import BENCHMARKS, INDICATORS, fetch_series, get_fred_client


def main() -> None:
    fred = get_fred_client()
    series_ids = list(INDICATORS) + list(BENCHMARKS)

    for series_id in series_ids:
        s = fetch_series(fred, series_id, force=True)
        print(f"  {series_id}: {len(s)} obs, {s.index[0].date()} - {s.index[-1].date()}")

    print(f"\nCached {len(series_ids)} series to data/raw/.")


if __name__ == "__main__":
    main()
