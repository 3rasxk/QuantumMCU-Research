#!/usr/bin/env python3
# phase3_summarize.py
# อ่านไฟล์ดิบ data/raw/phase3/{board}_raw.csv ทุกบอร์ดที่มีข้อมูลแล้ว
# สรุปเป็น Median ± IQR ของ e2e_latency_us จำแนกตาม board/circuit/n/baud_rate
# พร้อมอัตรา error (CRC ผิด + timeout) ต่อจุดข้อมูล — ไม่ปรับแต่งค่าใด ๆ

import csv
import glob
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared.timing_model import REPS  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw" / "phase3"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "phase3"


def load_raw():
    rows = []
    for path in sorted(glob.glob(str(RAW_DIR / "*_raw.csv"))):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    return rows


def main():
    rows = load_raw()
    if not rows:
        print(f"no *_raw.csv files found under {RAW_DIR}/")
        return

    groups = {}
    for r in rows:
        key = (r["board"], r["circuit"], int(r["n"]), r["baud_rate"])
        groups.setdefault(key, []).append(r)

    # เกราะกัน contamination เดียวกับ phase2_summarize.py — ดูเหตุผลที่นั่น
    over_reps = {k: len(v) for k, v in groups.items() if len(v) > REPS}
    if over_reps:
        print(f"error: {len(over_reps)} group(s) have more than REPS={REPS} rows — "
              "refusing to summarize a possibly-contaminated sample.", file=sys.stderr)
        for (board, circuit, n, baud), count in sorted(over_reps.items()):
            print(f"  board={board} circuit={circuit} n={n} baud={baud}: {count} rows "
                  f"found (expected <= {REPS})", file=sys.stderr)
        print("likely cause: a sweep ran with --fresh against the wrong file, or two "
              "sessions wrote to the same *_raw.csv concurrently. Inspect and de-duplicate "
              "the offending rows in the raw CSV before re-running this script.",
              file=sys.stderr)
        sys.exit(1)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "summary.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "baud_rate", "n_trials", "median_e2e_latency_us",
                    "iqr_low_us", "iqr_high_us", "iqr_width_us", "error_rate"])
        for (board, circuit, n, baud), items in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
            latencies = np.array([int(r["e2e_latency_us"]) for r in items])
            errors = sum(1 for r in items if r.get("crc_error") == "1" or r.get("timed_out") == "1")
            median = float(np.median(latencies))
            q1 = float(np.percentile(latencies, 25))
            q3 = float(np.percentile(latencies, 75))
            error_rate = errors / len(items)
            w.writerow([board, circuit, n, baud, len(items), median, q1, q3, q3 - q1, f"{error_rate:.4f}"])
            print(f"{board:8s} {circuit:9s} n={n:2d}  baud={baud:7s}  n_trials={len(items):3d}  "
                  f"median={median:8.0f}us  IQR=[{q1:.0f}, {q3:.0f}]  error_rate={error_rate:.0%}")

    print(f"\nsummary -> {out_path}")


if __name__ == "__main__":
    main()
