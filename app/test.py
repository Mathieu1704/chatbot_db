#!/usr/bin/env python3
"""
Test rapide de la détection de misconfig par asset.
"""

import argparse
from datetime import datetime
from pprint import pprint
from app.tools.misconfiguration import detect_misconfig


def main():
    p = argparse.ArgumentParser(
        description="Test detect_misconfig (asset level)"
    )
    p.add_argument("--company", required=True)
    p.add_argument("--days",       type=int, default=20)
    p.add_argument("--window",     type=int, default=10)
    p.add_argument("--threshold",  type=int, default=3)
    args = p.parse_args()

    print(f"[INFO] MongoDB reachable")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Building baseline over last {args.days} days …")
    # Baseline doit être lancée avant ce test si besoin

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Running misconfiguration detection (window={args.window}, freq_threshold={args.threshold}) …\n")

    report = detect_misconfig(
        company        = args.company,
        since_days     = args.days,
        last_n         = args.window,
        freq_threshold = args.threshold
    )

    counts = report["counts"]
    print("=== SUMMARY ===")
    pprint(counts)
    print()

    if counts["misconfigured"] == 0:
        print("No misconfigured assets detected 🎉")
    else:
        print("── List of misconfigured assets ──")
        for idx, doc in enumerate(report["items"], 1):
            print(f"\n#{idx} • asset_id : {doc['asset_id']}")
            print(f"   last_acq : {doc['last_acq']}")
            print(f"   freq_err : {doc['freq_err']}")
            print(f"   errcodes : {doc['errcodes']}")
            print(f"   err_name : {doc['err_name']}")
            print(f"   severity : {doc['severity']}")
            print(f"   cause    : {doc['cause']}")


if __name__ == "__main__":
    main()
