#!/usr/bin/env python3
# build_measured_medians.py -- one-off generator for pc/shared/measured_medians.json.
#
# Reads the points.csv files of a RETIRED dataset (the 2026-10-03 restart
# archive) and freezes the medians pc/shared/eta.py needs into a committed JSON,
# so run-time code never reads the archive (pc/run_test.py's archive-independence
# test forbids that). The source directory is a required argument on purpose.
#
#   python pc/shared/build_measured_medians.py --source <archive>/data/raw/phase2
#
# Only status=ok rows are used. Per-(circuit, n) device times are kept for the
# Uno (the only board whose full sweep was measured); compile/upload/boot are
# pooled per board. Nothing here is a new measurement.

import argparse
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).with_name("measured_medians.json")
CIRCUITS = ("h_all", "bell_ghz", "qft", "grover")
CHEAP_DEVICE_S = 0.05  # model exec below this = point is overhead-only (serial/boot)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(source: Path, board: str):
    rows = []
    for circuit in CIRCUITS:
        p = source / board / circuit / "no_la" / "points.csv"
        if not p.exists():
            continue
        with open(p, newline="") as f:
            rows += [r for r in csv.DictReader(f) if r["status"] == "ok"]
    return rows


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True,
                    help="<retired dataset>/data/raw/phase2")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "source": str(args.source), "boards": {}}
    for board in ("uno", "esp32"):
        rows = load(args.source, board)
        entry = {
            "n_ok_points": len(rows),
            "compile_s": med([_f(r["build_compile_s"]) for r in rows]),
            "upload_s": med([_f(r["upload_s"]) for r in rows]),
            "boot_wait_s": med([_f(r["boot_wait_s"]) for r in rows]),
        }
        # Fixed per-point device-side overhead (boot wait + serial transfer of 100 rows):
        # median device_exec_s over points whose real compute is negligible.
        small = [_f(r["device_exec_s"]) for r in rows
                 if r["circuit"] in ("h_all", "bell_ghz") and int(r["n"]) <= 6]
        entry["device_overhead_s"] = med(small)
        if board == "uno":
            entry["device_s"] = {}
            for r in rows:
                d = _f(r["device_exec_s"])
                if d is not None:
                    entry["device_s"].setdefault(r["circuit"], {})[r["n"]] = round(d, 3)
        out["boards"][board] = entry
    args.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    for b, e in out["boards"].items():
        print(b, {k: v for k, v in e.items() if k != "device_s"})


if __name__ == "__main__":
    main()
