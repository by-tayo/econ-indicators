"""Verify the FRED API key is present and reachable before running the pipeline."""
import sys

from econ_common import get_fred_client


def main() -> int:
    try:
        fred = get_fred_client()
    except RuntimeError as e:
        print(f"[FAIL] {e}")
        return 1

    try:
        s = fred.get_series("USREC")
    except Exception as e:
        print(f"[FAIL] Could not reach FRED: {e}")
        return 1

    print(f"[OK] FRED API key works. USREC series has {len(s)} observations, "
          f"most recent: {s.index[-1].date()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
