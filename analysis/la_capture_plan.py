#!/usr/bin/env python3
# la_capture_plan.py — สร้างแผนการ capture Logic Analyzer ต่อจุดข้อมูล (board, circuit,
# n) จากค่าประมาณเวลาต่อ trial ที่มีอยู่แล้วใน pc/shared/timing_model.py แทนที่จะ capture
# ทุกจุดที่ 24MHz เต็มอัตราแบบเดิม (ดู run_log.md — วิธีเดิมให้ไฟล์ใหญ่ถึง 627GB สำหรับ
# grover n สูง) ไฟล์นี้เลือก sample rate ให้พอดีกับความกว้างพัลส์จริงของแต่ละจุด และลด
# จำนวน rep ที่ต้อง capture สำหรับพัลส์ที่ยาวมาก — พัลส์ยิ่งยาว ยิ่งไม่ต้องการ resolution
# สูง (micros() ที่จะเทียบด้วยก็ไม่ได้ละเอียดกว่า 1us อยู่แล้ว)
#
# หลักการ: cross-check ต้องการแค่ตรวจว่า micros() ใกล้เคียงความจริงแค่ไหน ไม่ได้ต้องการ
# ความละเอียดระดับ nanosecond สำหรับพัลส์ที่กว้างเป็นวินาที/ชั่วโมง — 24MHz (resolution
# ~0.04us) มีความหมายกับพัลส์ 2us (h_all n=2 บางบอร์ด) แต่ "เกินความจำเป็นมหาศาล" กับ
# พัลส์ 130 วินาที (grover n=9 บน ESP8266) ที่ 10kHz (resolution 100us) ก็ยังละเอียดกว่า
# ความกว้างพัลส์นั้นถึงล้านเท่า

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import timing_model as tm  # noqa: E402
from shared.circuit_ids import CIRCUIT_IDS, n_values_for_sweep  # noqa: E402
from shared import paths as sp  # noqa: E402

# *** ยังไม่ยืนยันกับ LA จริง (ยังไม่มีเครื่องยืม) — รายการนี้เป็น "ตัวอย่างค่าที่น่าจะมี"
# (การหาร SI ตรง ๆ) ไม่ใช่รายการ sample rate ที่ LA รุ่นที่จะยืมมารองรับจริง เช่น LA
# ราคาถูกที่ใช้ชิป Cypress FX2 ทั่วไปมักรองรับเฉพาะชุดค่าคงที่ (24M,16M,8M,4M,1M,500k,
# 200k,100k,50k,20k,10k,5k,1k Hz ฯลฯ) ซึ่งไม่ตรงกับลิสต์นี้เป๊ะ — ต้องตรวจสอบด้วย
# `sigrok-cli --driver <ชื่อไดรเวอร์ของ LA นั้น> --config samplerate` (หรือเอกสาร
# ของ LA เอง) แล้วปรับ --rate-list ให้ตรงก่อนใช้แผนนี้จริง ไม่งั้น sigrok-cli อาจ
# ปัดค่า sample rate ที่ขอไปเป็นค่าที่ใกล้เคียงที่สุดที่รองรับแบบเงียบ ๆ
DEFAULT_RATE_LIST_HZ = [24_000_000, 12_000_000, 6_000_000, 1_000_000, 100_000, 10_000]

DEFAULT_RESOLUTION_FRACTION = 0.001    # 0.1% ของความกว้างพัลส์
DEFAULT_MIN_SAMPLES_PER_PULSE = 10
DEFAULT_REPS_THRESHOLD_US = 1_000_000.0  # 1 วินาที: พัลส์ยาวกว่านี้ถือว่า "ยาว" ลด rep
DEFAULT_REDUCED_REPS = 5
DEFAULT_MAX_SIZE_BYTES = 50_000_000     # 50MB — ค่าเริ่มต้นตามอำเภอใจ ปรับได้ตามพื้นที่ดิสก์จริง

# วัดจริงจากไฟล์ synthetic capture รอบก่อน (analysis/la_test.py): แต่ละบรรทัด FORMAT A
# คือ "0\n" หรือ "1\n" เสมอ = 2 byte/sample เป๊ะ ไม่ใช่ค่าประมาณ
BYTES_PER_SAMPLE_RAW = 2.0
# FORMAT B: "0.000005000,1\n" ~ 15-20 ตัวอักษร ต่อแถว (1 แถว = 1 edge, 2 edge/พัลส์)
# เป็นค่าประมาณ (ไม่ได้วัดจากไฟล์จริงเหมือน FORMAT A เพราะความยาว timestamp string
# แปรผันได้เล็กน้อยตามจำนวนหลัก)
BYTES_PER_EDGE_ROW_ESTIMATE = 20.0

CIRCUITS = list(CIRCUIT_IDS.keys())
# n-max ต่อบอร์ด — ใช้ค่าเดียวกับที่ run_checklist.md แนะนำให้สวีปจริง (เพดานกว้างกว่า
# measured wall 1 ขั้น) ไม่ใช่ค่าจากที่อื่น
BOARD_NMAX = {"uno": 8, "esp8266": 13, "esp32": 14}

PLAN_FIELDS = [
    "board", "circuit", "n", "pulse_width_us",
    "recommended_sample_rate_hz", "resolution_insufficient",
    "n_reps_to_capture", "reduced_reps", "capture_duration_s",
    "format_a_size_bytes", "format_b_size_bytes", "recommended_format",
    "exceeds_size_limit",
]


def choose_sample_rate(pulse_width_us, rate_list, resolution_fraction, min_samples_per_pulse):
    """เลือก rate ต่ำสุดใน rate_list ที่ผ่านทั้งสองเงื่อนไข (resolution และจำนวน sample
    ต่อพัลส์ขั้นต่ำ) — เรียงจากต่ำไปสูงแล้วคืนตัวแรกที่ผ่าน ยิ่ง rate ต่ำ ยิ่งไฟล์เล็ก
    ถ้าไม่มีตัวไหนผ่านเลย (พัลส์แคบมากจนแม้ rate สูงสุดในลิสต์ก็ยังหยาบไป) คืน rate
    สูงสุดที่มีพร้อม flag resolution_insufficient=True แทนที่จะปฏิเสธไปเลย — อย่างน้อย
    ก็ยังดีที่สุดเท่าที่ทำได้จาก list ที่ให้มา"""
    for rate in sorted(rate_list):
        resolution_us = 1e6 / rate
        samples_per_pulse = pulse_width_us * rate / 1e6
        if resolution_us <= resolution_fraction * pulse_width_us and samples_per_pulse >= min_samples_per_pulse:
            return rate, False
    return max(rate_list), True


def choose_reps(pulse_width_us, reps_threshold_us, full_reps, reduced_reps):
    """พัลส์ยาวกว่า threshold -> ลด rep เก็บแค่ reduced_reps ตัวแรก (ไม่ใช่สุ่ม — ต้อง
    เป็นตัวแรกเสมอเพื่อให้ join เข้ากับ rep index 0..N-1 ใน raw CSV ได้ตรงไปตรงมา ดู
    analysis/la_crosscheck.py) ถ้า WARMUP_REPS (pc/shared/telemetry.py) ถูกตั้งค่า > 0
    ในอนาคต ต้องแน่ใจว่า reduced_reps > WARMUP_REPS ไม่งั้นจะไม่เหลือ rep ที่ไม่ใช่
    warm-up ให้เอาไปคำนวณสถิติเลย (ตอนนี้ WARMUP_REPS=0 จึงยังไม่ใช่ปัญหา)"""
    if pulse_width_us > reps_threshold_us:
        return reduced_reps
    return full_reps


def plan_point(board, circuit, n, rate_list, resolution_fraction, min_samples_per_pulse,
               reps_threshold_us, full_reps, reduced_reps, max_size_bytes):
    pulse_width_us = tm.expected_exec_time_us(board, circuit, n)
    rate_hz, resolution_insufficient = choose_sample_rate(
        pulse_width_us, rate_list, resolution_fraction, min_samples_per_pulse)
    n_reps = choose_reps(pulse_width_us, reps_threshold_us, full_reps, reduced_reps)

    total_duration_us = pulse_width_us * n_reps
    format_a_bytes = total_duration_us * 1e-6 * rate_hz * BYTES_PER_SAMPLE_RAW
    format_b_bytes = n_reps * 2 * BYTES_PER_EDGE_ROW_ESTIMATE  # 2 edge (rising+falling) ต่อพัลส์

    return {
        "board": board, "circuit": circuit, "n": n,
        "pulse_width_us": round(pulse_width_us, 4),
        "recommended_sample_rate_hz": rate_hz,
        "resolution_insufficient": resolution_insufficient,
        "n_reps_to_capture": n_reps,
        "reduced_reps": n_reps < full_reps,
        "capture_duration_s": round(total_duration_us / 1e6, 6),
        "format_a_size_bytes": round(format_a_bytes),
        "format_b_size_bytes": round(format_b_bytes),
        "recommended_format": "B" if format_b_bytes <= format_a_bytes else "A",
        "exceeds_size_limit": format_a_bytes > max_size_bytes,
    }


def build_plan(rate_list, resolution_fraction, min_samples_per_pulse,
               reps_threshold_us, full_reps, reduced_reps, max_size_bytes):
    rows = []
    for board in ("uno", "esp8266", "esp32"):
        wall = tm.MEASURED_WALL_N[board]
        for circuit in CIRCUITS:
            for n in n_values_for_sweep(circuit, 2, BOARD_NMAX[board]):
                if n > wall + 1:
                    continue
                if tm.is_compute_infeasible(board, circuit, n):
                    continue
                rows.append(plan_point(board, circuit, n, rate_list, resolution_fraction,
                                        min_samples_per_pulse, reps_threshold_us,
                                        full_reps, reduced_reps, max_size_bytes))
    return rows


def print_plan(rows):
    print(f"{'board':8s} {'circuit':14s} {'n':>3s} {'pulse_width':>14s} {'rate':>10s} "
          f"{'reps':>5s} {'duration':>10s} {'fmtA':>10s} {'fmtB':>8s} {'rec':>3s} note")
    for r in rows:
        pw = r["pulse_width_us"]
        pw_s = f"{pw:.2f}us" if pw < 1000 else f"{pw/1000:.2f}ms" if pw < 1e6 else f"{pw/1e6:.2f}s"
        rate_s = f"{r['recommended_sample_rate_hz']/1e6:.0f}MHz" if r["recommended_sample_rate_hz"] >= 1e6 \
            else f"{r['recommended_sample_rate_hz']/1e3:.0f}kHz"
        dur = r["capture_duration_s"]
        dur_s = f"{dur*1000:.1f}ms" if dur < 1 else f"{dur:.2f}s" if dur < 60 else f"{dur/60:.1f}min"
        fmta = f"{r['format_a_size_bytes']/1e6:.2f}MB" if r['format_a_size_bytes'] < 1e9 \
            else f"{r['format_a_size_bytes']/1e9:.2f}GB"
        fmtb = f"{r['format_b_size_bytes']} B"
        notes = []
        if r["reduced_reps"]:
            notes.append(f"reduced to {r['n_reps_to_capture']} reps")
        if r["resolution_insufficient"]:
            notes.append("resolution insufficient at max rate")
        if r["exceeds_size_limit"]:
            notes.append("EXCEEDS SIZE LIMIT")
        print(f"{r['board']:8s} {r['circuit']:14s} {r['n']:3d} {pw_s:>14s} {rate_s:>10s} "
              f"{r['n_reps_to_capture']:5d} {dur_s:>10s} {fmta:>10s} {fmtb:>8s} "
              f"{r['recommended_format']:>3s} {', '.join(notes)}")


def summarize(rows):
    by_rate = {}
    total_a = total_b = 0
    n_reduced = n_exceeds = n_insufficient = 0
    for r in rows:
        by_rate.setdefault(r["recommended_sample_rate_hz"], 0)
        by_rate[r["recommended_sample_rate_hz"]] += 1
        total_a += r["format_a_size_bytes"]
        total_b += r["format_b_size_bytes"]
        n_reduced += r["reduced_reps"]
        n_exceeds += r["exceeds_size_limit"]
        n_insufficient += r["resolution_insufficient"]

    print(f"\n{len(rows)} points planned")
    for rate in sorted(by_rate, reverse=True):
        label = f"{rate/1e6:.0f}MHz" if rate >= 1e6 else f"{rate/1e3:.0f}kHz"
        print(f"  {by_rate[rate]:3d} point(s) at {label}")
    print(f"{n_reduced} point(s) using reduced reps")
    print(f"{n_insufficient} point(s) where resolution is insufficient even at the highest listed rate")
    print(f"{n_exceeds} point(s) still exceeding the size limit even with the chosen rate/reps")
    print(f"total FORMAT A size across all points: {total_a/1e9:.2f} GB")
    print(f"total FORMAT B size across all points: {total_b/1e6:.2f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rate-list", type=float, nargs="+", default=DEFAULT_RATE_LIST_HZ,
                     help="Hz, ตัวเลือก sample rate ที่ยอมใช้ (ต้องตรวจกับ LA จริงก่อนใช้งานจริง)")
    ap.add_argument("--resolution-fraction", type=float, default=DEFAULT_RESOLUTION_FRACTION)
    ap.add_argument("--min-samples-per-pulse", type=int, default=DEFAULT_MIN_SAMPLES_PER_PULSE)
    ap.add_argument("--reps-threshold-us", type=float, default=DEFAULT_REPS_THRESHOLD_US)
    ap.add_argument("--full-reps", type=int, default=tm.REPS)
    ap.add_argument("--reduced-reps", type=int, default=DEFAULT_REDUCED_REPS)
    ap.add_argument("--max-size-bytes", type=float, default=DEFAULT_MAX_SIZE_BYTES)
    ap.add_argument("--out", type=Path, default=None,
                     help="write ONE combined plan file here instead of the default -- "
                          "split per (board, circuit), one capture_plan.csv per circuit's "
                          "own la/ dir (see pc/shared/paths.la_dir, 2026-09-20 layout change)")
    args = ap.parse_args()

    rows = build_plan(args.rate_list, args.resolution_fraction, args.min_samples_per_pulse,
                       args.reps_threshold_us, args.full_reps, args.reduced_reps,
                       args.max_size_bytes)
    print_plan(rows)
    summarize(rows)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PLAN_FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"\nplan -> {args.out}")
        return

    by_board_circuit = {}
    for r in rows:
        by_board_circuit.setdefault((r["board"], r["circuit"]), []).append(r)
    print()
    for (board, circuit), group_rows in sorted(by_board_circuit.items()):
        out_path = sp.la_dir(board, circuit, phase=2) / "capture_plan.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PLAN_FIELDS)
            w.writeheader()
            w.writerows(group_rows)
        print(f"plan -> {out_path}  ({len(group_rows)} point(s))")


if __name__ == "__main__":
    main()
