#!/usr/bin/env python3
# phase2_summarize.py
# อ่านไฟล์ดิบ data/raw/phase2/{board}_raw.csv (ทุกบอร์ดที่มีข้อมูลแล้ว)
# แล้วสรุปเป็น Median ± IQR ของ exec_time_us จำแนกตาม board/circuit/n
# (รายงานแบบ Median ± IQR ตามระเบียบวิธี ไม่ใช่ Mean ± SD เพราะข้อมูลเวลามักเบ้)
#
# ไม่ปรับแต่งค่าใด ๆ — สรุปสถิติจากข้อมูลดิบที่วัดได้จริงเท่านั้น

import csv
import glob
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "phase2"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "phase2"


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
        key = (r["board"], r["circuit"], int(r["n"]))
        groups.setdefault(key, []).append(float(r["exec_time_us"]))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "summary.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "n_trials", "median_exec_time_us",
                    "iqr_low_us", "iqr_high_us", "iqr_width_us"])
        for (board, circuit, n), times in sorted(groups.items()):
            arr = np.array(times)
            median = float(np.median(arr))
            q1 = float(np.percentile(arr, 25))
            q3 = float(np.percentile(arr, 75))
            w.writerow([board, circuit, n, len(arr), median, q1, q3, q3 - q1])
            print(f"{board:6s} {circuit:9s} n={n:2d}  n_trials={len(arr):3d}  "
                  f"median={median:8.1f}us  IQR=[{q1:.1f}, {q3:.1f}]")

    print(f"\nsummary -> {out_path}")


if __name__ == "__main__":
    main()
