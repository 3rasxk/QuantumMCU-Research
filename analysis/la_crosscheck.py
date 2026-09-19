#!/usr/bin/env python3
# la_crosscheck.py — เทียบความกว้างพัลส์จาก Logic Analyzer (analysis/la_pulses.py)
# กับ exec_time_us ที่ MCU รายงานเอง (micros()) ต่อ rep แล้วสรุปเป็นแถวเดียวต่อจุดข้อมูล
# ลงไฟล์ใหม่ data/raw/telemetry/la_crosscheck.csv — ไม่แก้ data/raw/phase2/*_raw.csv
# หรือ data/raw/telemetry/points.csv เลย (ไม่เพิ่มคอลัมน์ว่างเข้าไปในไฟล์ที่มีอยู่แล้ว
# ตามที่ตกลงไว้)
#
# *** หมายเหตุสำคัญ: join กับ *_raw.csv ไม่ใช่ points.csv ***
# งานนี้เดิมขอให้ join กับ data/raw/telemetry/points.csv แต่ points.csv เก็บสถิติ "ระดับ
# จุดข้อมูล" เท่านั้น (device_exec_s รวมทั้ง 100 rep เป็นตัวเลขเดียว ไม่มีคอลัมน์ rep เลย)
# จึงไม่มีความละเอียดพอจะเทียบ "ต่อ rep" ตามที่โจทย์ต้องการจริง ๆ (เทียบพัลส์ที่ 37 กับ
# micros() ของ rep ที่ 37) ค่า exec_time_us ต่อ rep ที่ต้องการอยู่ใน
# data/raw/phase2/<board>_raw.csv (คอลัมน์ rep, exec_time_us) อยู่แล้วตั้งแต่ก่อนมี
# telemetry — ไฟล์นี้จึง join กับไฟล์นั้นแทน ไม่ใช่ points.csv (เบี่ยงจากคำสั่งเดิมโดย
# ตั้งใจ เพราะทำตามตัวอักษรแล้วจะ join ไม่ได้จริง — ดู session report ประกอบ)
#
# ---------------------------------------------------------------------------
# ข้อตกลงชื่อไฟล์ capture (ต้องบันทึกไว้ที่นี่และใน run_checklist.md ให้ตรงกัน):
#   data/raw/la/<board>_<circuit>_n<N>.csv
#   เช่น data/raw/la/uno_h_all_n2.csv, data/raw/la/esp32_grover_n10.csv
#   1 ไฟล์ = 1 จุดข้อมูล = REPS พัลส์ (ไม่ใช่ 1 ไฟล์ต่อ rep — capture ต่อเนื่องทั้ง
#   session ของจุดนั้น แล้วแยกพัลส์ทีหลังด้วย la_pulses.py)
#
# ---------------------------------------------------------------------------
# การ join ต่อ rep: "เรียงตามลำดับ" ไม่ใช่ตาม ID ที่ฝังมากับสัญญาณ
#   LA ไม่รู้ "นี่คือ rep ที่เท่าไหร่" — รู้แค่ลำดับเวลาที่พัลส์เกิดขึ้น สมมติฐานคือพัลส์ที่
#   i (0-based, เรียงตามเวลา) ในไฟล์ capture ตรงกับแถว rep=i ใน *_raw.csv พอดี ซึ่งเป็นจริง
#   ก็ต่อเมื่อ capture "สะอาด" เท่านั้น (ไม่มี truncation, ไม่มี pulse หาย, ไม่มี glitch
#   ปนจนนับพัลส์ผิด) — ถ้า capture ไม่ ParseResult.is_clean สคริปต์นี้จะ "ปฏิเสธ" ไม่ join
#   จุดนั้น (ข้ามพร้อมเหตุผล) แทนที่จะเดา offset เอาเอง เพราะ join ผิดตำแหน่งจะให้ผลลัพธ์
#   ที่ดูสมเหตุสมผลแต่ผิดจริง (ตัวเลขไม่ error ออกมาให้เห็น) อันตรายกว่าการไม่มีผลลัพธ์เลย

import argparse
import csv
import glob
import re
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import timing_model as tm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from la_pulses import extract_pulses  # noqa: E402

LA_DIR = REPO_ROOT / "data" / "raw" / "la"
RAW_DIR = REPO_ROOT / "data" / "raw" / "phase2"
OUT_PATH = REPO_ROOT / "data" / "raw" / "telemetry" / "la_crosscheck.csv"

FILENAME_RE = re.compile(r"^(uno|esp32|esp8266)_(.+)_n(\d+)\.csv$")

OUT_FIELDS = [
    "board", "circuit", "n", "n_pulses_matched",
    "median_la_width_us", "la_iqr_low_us", "la_iqr_high_us",
    "median_mcu_exec_time_us", "mcu_iqr_low_us", "mcu_iqr_high_us",
    "median_abs_diff_us", "median_relative_diff",
    "max_abs_diff_us", "max_relative_diff",
    "flagged", "capture_format", "n_glitches",
    "leading_truncated", "trailing_truncated", "notes",
]


def find_capture_files(la_dir: Path):
    out = []
    for path in sorted(la_dir.glob("*.csv")):
        m = FILENAME_RE.match(path.name)
        if not m:
            print(f"skip: {path.name} does not match <board>_<circuit>_n<N>.csv, ignoring")
            continue
        board, circuit, n = m.group(1), m.group(2), int(m.group(3))
        out.append((board, circuit, n, path))
    return out


def load_mcu_exec_times(board: str, circuit: str, n: int, raw_dir: Path = RAW_DIR):
    """คืน list ของ exec_time_us เรียงตาม rep (0..) จาก <board>_raw.csv
    คืน None ถ้าไม่มีข้อมูลของจุดนี้เลย"""
    path = raw_dir / f"{board}_raw.csv"
    if not path.exists():
        return None
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("circuit") == circuit and int(r.get("n", -1)) == n:
                rows.append((int(r["rep"]), float(r["exec_time_us"])))
    if not rows:
        return None
    rows.sort(key=lambda t: t[0])
    return [v for _, v in rows]


def _iqr(values):
    arr = np.asarray(values, dtype=float)
    return float(np.percentile(arr, 25)), float(np.percentile(arr, 75))


def crosscheck_one(board, circuit, n, capture_path: Path, expected_reps, min_pulse_width_us,
                    sample_rate_hint, max_relative_diff, raw_dir=RAW_DIR):
    result = extract_pulses(capture_path, expected_reps=expected_reps,
                             min_pulse_width_us=min_pulse_width_us,
                             sample_rate_hz_hint=sample_rate_hint)

    if not result.is_clean:
        reasons = []
        if result.leading_truncated:
            reasons.append("leading_truncated")
        if result.trailing_truncated:
            reasons.append("trailing_truncated")
        if result.glitches:
            reasons.append(f"{len(result.glitches)}_glitch(es)")
        if result.count_mismatch:
            reasons.append(f"count={len(result.pulses)}_expected={expected_reps}")
        note = f"REFUSED to join: capture not clean ({', '.join(reasons)}) — rep-order alignment unsafe"
        print(f"{board}/{circuit}/n={n}: {note}")
        return {
            "board": board, "circuit": circuit, "n": n, "n_pulses_matched": 0,
            "flagged": True, "capture_format": result.format_detected,
            "n_glitches": len(result.glitches),
            "leading_truncated": result.leading_truncated,
            "trailing_truncated": result.trailing_truncated,
            "notes": note,
        }

    mcu_times = load_mcu_exec_times(board, circuit, n, raw_dir)
    if mcu_times is None:
        note = f"no matching rows in {board}_raw.csv for circuit={circuit} n={n}"
        print(f"{board}/{circuit}/n={n}: REFUSED to join: {note}")
        return {
            "board": board, "circuit": circuit, "n": n, "n_pulses_matched": 0,
            "flagged": True, "capture_format": result.format_detected,
            "n_glitches": len(result.glitches),
            "leading_truncated": result.leading_truncated,
            "trailing_truncated": result.trailing_truncated,
            "notes": note,
        }
    if len(mcu_times) != expected_reps:
        note = (f"{board}_raw.csv has {len(mcu_times)} rows for circuit={circuit} n={n}, "
                f"expected {expected_reps} — refusing rep-order join")
        print(f"{board}/{circuit}/n={n}: REFUSED to join: {note}")
        return {
            "board": board, "circuit": circuit, "n": n, "n_pulses_matched": 0,
            "flagged": True, "capture_format": result.format_detected,
            "n_glitches": len(result.glitches),
            "leading_truncated": result.leading_truncated,
            "trailing_truncated": result.trailing_truncated,
            "notes": note,
        }

    la_widths = [p.width_us for p in result.pulses]
    abs_diffs = [abs(la - mcu) for la, mcu in zip(la_widths, mcu_times)]
    rel_diffs = [d / mcu for d, mcu in zip(abs_diffs, mcu_times) if mcu > 0]

    la_med = float(np.median(la_widths))
    mcu_med = float(np.median(mcu_times))
    la_q1, la_q3 = _iqr(la_widths)
    mcu_q1, mcu_q3 = _iqr(mcu_times)
    med_abs_diff = float(np.median(abs_diffs))
    med_rel_diff = float(np.median(rel_diffs)) if rel_diffs else float("nan")
    max_abs_diff = max(abs_diffs)
    max_rel_diff = max(rel_diffs) if rel_diffs else float("nan")

    flagged = med_rel_diff > max_relative_diff
    note = "" if not flagged else (
        f"median relative diff {med_rel_diff:.1%} exceeds threshold {max_relative_diff:.1%}"
    )

    return {
        "board": board, "circuit": circuit, "n": n, "n_pulses_matched": len(la_widths),
        "median_la_width_us": round(la_med, 3), "la_iqr_low_us": round(la_q1, 3),
        "la_iqr_high_us": round(la_q3, 3),
        "median_mcu_exec_time_us": round(mcu_med, 3), "mcu_iqr_low_us": round(mcu_q1, 3),
        "mcu_iqr_high_us": round(mcu_q3, 3),
        "median_abs_diff_us": round(med_abs_diff, 3),
        "median_relative_diff": round(med_rel_diff, 5),
        "max_abs_diff_us": round(max_abs_diff, 3),
        "max_relative_diff": round(max_rel_diff, 5),
        "flagged": flagged, "capture_format": result.format_detected,
        "n_glitches": len(result.glitches),
        "leading_truncated": result.leading_truncated,
        "trailing_truncated": result.trailing_truncated,
        "notes": note,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--la-dir", type=Path, default=LA_DIR)
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--expected-reps", type=int, default=tm.REPS)
    ap.add_argument("--min-pulse-width-us", type=float, default=1.0)
    ap.add_argument("--sample-rate", type=float, default=None,
                     help="เฉพาะไฟล์ FORMAT B ที่คอลัมน์แรกเป็น sample index")
    ap.add_argument("--max-relative-diff", type=float, default=0.05,
                     help="threshold สัดส่วนความต่าง (median) ที่ถือว่าต้อง flag ค่าเริ่มต้น 5%%")
    args = ap.parse_args()

    if not args.la_dir.exists():
        print(f"error: {args.la_dir} not found — nothing to cross-check yet", file=sys.stderr)
        sys.exit(1)

    captures = find_capture_files(args.la_dir)
    if not captures:
        print(f"no capture files matching <board>_<circuit>_n<N>.csv under {args.la_dir}")
        sys.exit(0)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    is_new = not args.out.exists()
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        if is_new:
            w.writeheader()
            f.flush()
        for board, circuit, n, path in captures:
            row = crosscheck_one(board, circuit, n, path, args.expected_reps,
                                  args.min_pulse_width_us, args.sample_rate,
                                  args.max_relative_diff, args.raw_dir)
            w.writerow({k: row.get(k, "") for k in OUT_FIELDS})
            f.flush()
            if row.get("n_pulses_matched"):
                print(f"{board}/{circuit}/n={n}: LA median={row['median_la_width_us']}us  "
                      f"MCU median={row['median_mcu_exec_time_us']}us  "
                      f"rel_diff={row['median_relative_diff']:.1%}  flagged={row['flagged']}")

    print(f"\nresults -> {args.out}")


if __name__ == "__main__":
    main()
