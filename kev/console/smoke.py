"""python -m kev.console.smoke CLI entry."""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-db", action="store_true", help="Run smoke probes from the DB (spec §3.7).")
    parser.add_argument("--scenario", type=str, default=None, help="Limit to one scenario slug.")
    args = parser.parse_args()
    if args.from_db:
        from kev.console.services.smoke import run_from_db
        results = run_from_db(args.scenario)
        for r in results:
            mark = "OK" if r["matched"] else "FAIL"
            print(f"{mark}  {r['scenario']}: actual={r['actual_label']} expected={r['expected_label']}")
        return 0 if all(r["matched"] for r in results) else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())