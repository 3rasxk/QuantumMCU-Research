#!/usr/bin/env python3
# la_test.py — self-contained tests for analysis/la_pulses.py and
# analysis/la_crosscheck.py using synthetic Logic Analyzer captures (no real LA
# hardware exists in this project yet — these are the only captures available).
#
# รันด้วย: .venv/bin/python analysis/la_test.py
# ไม่ใช้ pytest (repo นี้ไม่มี test infra มาก่อน) — รูปแบบเดียวกับ
# pc/shared/telemetry_test.py: PASS/FAIL ผ่าน stdout, exit code != 0 ถ้ามี FAIL
#
# เขียนไฟล์ทดสอบทั้งหมดลง tempfile scratch dir — ไม่แตะ data/raw/la/ หรือ
# data/raw/telemetry/ ของจริงเด็ดขาด (ตรวจท้ายไฟล์ว่าไม่มีอะไรหลุดไปจริง)

import csv
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "analysis"))

import la_pulses as lap  # noqa: E402
import la_crosscheck as lac  # noqa: E402
import la_capture_plan as lcp  # noqa: E402

RESULTS = []
RATE = 24_000_000


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


def write_raw(path, pulse_widths_us, gap_us=50.0, start_high=False, extend_trailing_high=False,
              rate=RATE):
    """สร้างไฟล์ FORMAT A (sigrok-cli raw, 1 sample/บรรทัด) จำลอง capture ที่ rate ใด ๆ
    (ค่าเริ่มต้น 24MHz แต่รับ rate ต่ำเพื่อทดสอบ capture ความละเอียดต่ำได้ด้วย)"""
    levels = []

    def add(seconds, level):
        n = max(1, round(seconds * rate))
        levels.extend([level] * n)

    if not start_high:
        add(10e-6, 0)
    for w in pulse_widths_us:
        add(w * 1e-6, 1)
        add(gap_us * 1e-6, 0)
    if extend_trailing_high:
        for i in range(1, 50):
            levels[-i] = 1
    with open(path, "w") as f:
        f.write(f";Rate: {rate}\n;Channels: D0\n")
        f.write("\n".join(str(v) for v in levels))
        f.write("\n")


def write_edges(path, pulse_widths_us, gap_us=50.0, as_seconds=True):
    t = 0.0
    rows = [(0.0, 0)]
    for w in pulse_widths_us:
        t += 5e-9
        rows.append((t, 1))
        t += w * 1e-6
        rows.append((t, 0))
        t += gap_us * 1e-6
    with open(path, "w") as f:
        f.write("time,D0\n" if as_seconds else "sample,D0\n")
        for ts, lvl in rows:
            if as_seconds:
                f.write(f"{ts:.9f},{lvl}\n")
            else:
                f.write(f"{round(ts * RATE)},{lvl}\n")


def test_la_pulses(scratch: Path):
    scratch.mkdir(parents=True)

    # --- clean 100 pulses ---
    write_raw(scratch / "clean.csv", [284.0] * 100)
    r = lap.extract_pulses(scratch / "clean.csv", expected_reps=100)
    check("clean: 100 pulses extracted", len(r.pulses) == 100, len(r.pulses))
    check("clean: is_clean=True", r.is_clean)
    check("clean: widths correct (~284us)", abs(r.pulses[0].width_us - 284.0) < 0.1, r.pulses[0].width_us)

    # --- missing pulse ---
    write_raw(scratch / "missing.csv", [284.0] * 99)
    r = lap.extract_pulses(scratch / "missing.csv", expected_reps=100)
    check("missing pulse: count_mismatch detected", r.count_mismatch)
    check("missing pulse: is_clean=False", not r.is_clean)
    check("missing pulse: got exactly 99", len(r.pulses) == 99)

    # --- glitch ---
    widths = [284.0] * 50 + [0.05] + [284.0] * 50
    write_raw(scratch / "glitch.csv", widths)
    r = lap.extract_pulses(scratch / "glitch.csv", expected_reps=100, min_pulse_width_us=1.0)
    check("glitch: exactly 1 glitch detected", len(r.glitches) == 1, len(r.glitches))
    check("glitch: glitch excluded from clean pulse count (100, not 101)", len(r.pulses) == 100)
    check("glitch: is_clean=False (glitches present)", not r.is_clean)

    # --- truncated leading ---
    write_raw(scratch / "trunc_lead.csv", [284.0] * 100, start_high=True)
    r = lap.extract_pulses(scratch / "trunc_lead.csv", expected_reps=100)
    check("truncated leading: flagged", r.leading_truncated)
    check("truncated leading: is_clean=False", not r.is_clean)
    check("truncated leading: truncated pulse excluded (99 clean)", len(r.pulses) == 99)

    # --- truncated trailing ---
    write_raw(scratch / "trunc_trail.csv", [284.0] * 100, extend_trailing_high=True)
    r = lap.extract_pulses(scratch / "trunc_trail.csv", expected_reps=100)
    check("truncated trailing: flagged", r.trailing_truncated)
    check("truncated trailing: is_clean=False", not r.is_clean)

    # --- format B (edges), seconds column ---
    write_edges(scratch / "edges_seconds.csv", [284.0] * 100, as_seconds=True)
    r = lap.extract_pulses(scratch / "edges_seconds.csv", expected_reps=100)
    check("format B (seconds): detected as 'edges'", r.format_detected == "edges")
    check("format B (seconds): 100 clean pulses", len(r.pulses) == 100 and r.is_clean)

    # --- low sample rate (100kHz): coarser resolution but still correct within it ---
    # ใช้พัลส์ยาว 10ms (สอดคล้องกับที่ analysis/la_capture_plan.py จะแนะนำ 100kHz จริง ๆ
    # สำหรับพัลส์ระดับนี้) resolution ที่ 100kHz = 10us ต่อ sample -> error ที่ยอมรับได้
    # ต้องไม่เกิน ~1 sample period (10us)
    write_raw(scratch / "low_rate_100k.csv", [10_000.0] * 20, gap_us=500.0, rate=100_000)
    r = lap.extract_pulses(scratch / "low_rate_100k.csv", expected_reps=20)
    check("100kHz: sample_rate parsed correctly from header", r.sample_rate_hz == 100_000, r.sample_rate_hz)
    check("100kHz: 20 clean pulses extracted", len(r.pulses) == 20 and r.is_clean, len(r.pulses))
    check("100kHz: width correct within 1 sample period (10us) of true 10000us",
          abs(r.pulses[0].width_us - 10_000.0) <= 10.0, r.pulses[0].width_us)

    # --- mismatched sample rate: index column without --sample-rate must raise ---
    write_edges(scratch / "edges_index.csv", [284.0] * 5, as_seconds=False)
    try:
        lap.extract_pulses(scratch / "edges_index.csv", expected_reps=5)
        check("mismatched rate: missing --sample-rate raises ValueError", False)
    except ValueError:
        check("mismatched rate: missing --sample-rate raises ValueError", True)

    r_correct = lap.extract_pulses(scratch / "edges_index.csv", expected_reps=5,
                                    sample_rate_hz_hint=RATE)
    check("mismatched rate: correct rate gives correct widths (~284us)",
          abs(r_correct.pulses[0].width_us - 284.0) < 0.1, r_correct.pulses[0].width_us)

    r_wrong = lap.extract_pulses(scratch / "edges_index.csv", expected_reps=5,
                                  sample_rate_hz_hint=RATE / 2)
    check("mismatched rate: wrong rate silently doubles width (visibly wrong, not crashed)",
          abs(r_wrong.pulses[0].width_us - 568.0) < 0.1, r_wrong.pulses[0].width_us)


def test_la_crosscheck(scratch: Path):
    la_dir = scratch / "la"
    raw_dir = scratch / "phase2"
    out_path = scratch / "telemetry" / "la_crosscheck.csv"
    la_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    # point 1: clean, LA and MCU agree closely -> not flagged
    mcu_1 = [284.0] * 100
    write_raw(la_dir / "uno_h_all_n2.csv", [284.05] * 100)
    with open(raw_dir / "uno_raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us",
                     "free_heap_before", "free_heap_after", "timeout_budget_s"])
        for i, t in enumerate(mcu_1):
            w.writerow(["uno", "h_all", 2, i, t, 1000, 999, 90])

    # point 2: systematic 20% diff -> flagged
    write_raw(la_dir / "uno_qft_n3.csv", [1932.0 * 1.2] * 100)
    with open(raw_dir / "uno_raw.csv", "a", newline="") as f:
        w = csv.writer(f)
        for i in range(100):
            w.writerow(["uno", "qft", 3, i, 1932.0, 1000, 999, 90])

    # point 3: dirty capture (glitch) -> refused
    widths_3 = [150.0] * 50 + [0.02] + [150.0] * 49
    write_raw(la_dir / "uno_bell_ghz_n2.csv", widths_3)
    with open(raw_dir / "uno_raw.csv", "a", newline="") as f:
        w = csv.writer(f)
        for i in range(100):
            w.writerow(["uno", "bell_ghz", 2, i, 150.0, 1000, 999, 90])

    # point 4: capture exists, no matching raw data -> refused
    write_raw(la_dir / "esp32_grover_n6.csv", [292.8] * 100)

    # point 5: filename that doesn't match the naming convention -> ignored, not crashed
    write_raw(la_dir / "not_a_valid_name.csv", [1.0] * 5)

    # --plan ต้องชี้ไปที่ไฟล์ที่ไม่มีอยู่จริงเสมอในเทสต์นี้ (ไม่งั้น default ของ
    # la_crosscheck.py จะไปหาไฟล์ data/raw/la/capture_plan.csv ของจริงในเครื่อง ทำให้
    # ผลเทสต์ขึ้นกับ state ของ repo จริง ณ เวลาที่รันแทนที่จะเป็นอิสระเหมือนที่ควรจะเป็น)
    no_plan = scratch / "no_such_plan.csv"
    sys.argv = ["la_crosscheck.py", "--la-dir", str(la_dir), "--raw-dir", str(raw_dir),
                "--out", str(out_path), "--min-pulse-width-us", "1.0", "--plan", str(no_plan)]
    lac.main()

    rows = {r["circuit"] + str(r["n"]): r for r in csv.DictReader(open(out_path))}
    check("crosscheck: 4 valid captures processed (invalid filename ignored)", len(rows) == 4,
          list(rows.keys()))
    check("crosscheck: clean point not flagged", rows["h_all2"]["flagged"] == "False")
    check("crosscheck: clean point rel diff small", float(rows["h_all2"]["median_relative_diff"]) < 0.01)
    check("crosscheck: systematic-diff point IS flagged", rows["qft3"]["flagged"] == "True")
    check("crosscheck: systematic-diff point rel diff ~20%",
          abs(float(rows["qft3"]["median_relative_diff"]) - 0.20) < 0.01)
    check("crosscheck: dirty capture refused (0 pulses matched)", rows["bell_ghz2"]["n_pulses_matched"] == "0")
    check("crosscheck: dirty capture flagged=True (refused, not silently skipped)",
          rows["bell_ghz2"]["flagged"] == "True")
    check("crosscheck: missing raw data refused with clear note",
          "no matching rows" in rows["grover6"]["notes"])
    check("crosscheck: status field: pass/flagged/refused/refused",
          [rows["h_all2"]["status"], rows["qft3"]["status"],
           rows["bell_ghz2"]["status"], rows["grover6"]["status"]] ==
          ["pass", "flagged", "refused", "refused"])

    # re-running must APPEND, not overwrite (matches every other telemetry file's contract)
    lac.main()
    rows2 = list(csv.DictReader(open(out_path)))
    check("crosscheck: rerun appends rather than overwrites", len(rows2) == 8, len(rows2))

    # --- reduced-capture join: only 5 pulses captured, must join against the FIRST 5
    # reps of the 100-row raw CSV, refusing the old "must equal REPS" behavior ---
    la_dir2 = scratch / "la_reduced"
    raw_dir2 = scratch / "phase2_reduced"
    out_path2 = scratch / "telemetry_reduced" / "la_crosscheck.csv"
    la_dir2.mkdir(parents=True)
    raw_dir2.mkdir(parents=True)

    # full 100-rep raw CSV exists (as a real completed point would have), but only the
    # first 5 reps' pulses were actually captured by the LA (long-pulse point)
    mcu_full_100 = [50_000.0 + i for i in range(100)]  # deliberately varying per rep
    with open(raw_dir2 / "esp8266_raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us",
                     "free_heap_before", "free_heap_after", "timeout_budget_s"])
        for i, t in enumerate(mcu_full_100):
            w.writerow(["esp8266", "grover", 9, i, t, 60000, 59000, 14400])
    write_raw(la_dir2 / "esp8266_grover_n9.csv", [t + 0.5 for t in mcu_full_100[:5]],
              gap_us=1000.0, rate=10_000)

    # (a) explicit --expected-reps override
    sys.argv = ["la_crosscheck.py", "--la-dir", str(la_dir2), "--raw-dir", str(raw_dir2),
                "--out", str(out_path2), "--min-pulse-width-us", "1.0",
                "--plan", str(scratch / "no_such_plan2.csv"), "--expected-reps", "5"]
    lac.main()
    rows3 = list(csv.DictReader(open(out_path2)))
    check("reduced join: 1 row written", len(rows3) == 1, len(rows3))
    check("reduced join: expected_reps=5 recorded", rows3[0]["expected_reps"] == "5")
    check("reduced join: n_pulses_matched=5 (not refused)", rows3[0]["n_pulses_matched"] == "5",
          rows3[0])
    check("reduced join: median MCU time matches first-5-reps median, not full-100 median",
          abs(float(rows3[0]["median_mcu_exec_time_us"]) - 50_002.0) < 1.0,
          rows3[0]["median_mcu_exec_time_us"])

    # (b) same thing but via a capture_plan.csv lookup instead of --expected-reps
    plan_path = scratch / "plan_for_reduced.csv"
    with open(plan_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=lcp.PLAN_FIELDS)
        w.writeheader()
        w.writerow({"board": "esp8266", "circuit": "grover", "n": 9, "pulse_width_us": 500000,
                    "recommended_sample_rate_hz": 10_000, "resolution_insufficient": False,
                    "n_reps_to_capture": 5, "reduced_reps": True, "capture_duration_s": 2.5,
                    "format_a_size_bytes": 50000, "format_b_size_bytes": 200,
                    "recommended_format": "B", "exceeds_size_limit": False})
    out_path3 = scratch / "telemetry_reduced2" / "la_crosscheck.csv"
    sys.argv = ["la_crosscheck.py", "--la-dir", str(la_dir2), "--raw-dir", str(raw_dir2),
                "--out", str(out_path3), "--min-pulse-width-us", "1.0", "--plan", str(plan_path)]
    lac.main()
    rows4 = list(csv.DictReader(open(out_path3)))
    check("reduced join via plan: expected_reps=5 picked up from capture_plan.csv",
          rows4[0]["expected_reps"] == "5", rows4[0]["expected_reps"])
    check("reduced join via plan: n_pulses_matched=5", rows4[0]["n_pulses_matched"] == "5")

    # (c) a genuinely-dirty reduced capture (wrong pulse count) must still be refused
    write_raw(la_dir2 / "esp8266_grover_n9.csv", [t + 0.5 for t in mcu_full_100[:4]],
              gap_us=1000.0, rate=10_000)  # only 4 pulses now, still asking for 5
    out_path4 = scratch / "telemetry_reduced3" / "la_crosscheck.csv"
    sys.argv = ["la_crosscheck.py", "--la-dir", str(la_dir2), "--raw-dir", str(raw_dir2),
                "--out", str(out_path4), "--min-pulse-width-us", "1.0",
                "--plan", str(scratch / "no_such_plan3.csv"), "--expected-reps", "5"]
    lac.main()
    rows5 = list(csv.DictReader(open(out_path4)))
    check("reduced join: pulse-count mismatch against the reduced target is still refused",
          rows5[0]["n_pulses_matched"] == "0" and rows5[0]["flagged"] == "True", rows5[0])

    # --- dual-threshold (relative AND absolute floor) boundary cases ---
    # (A) Uno, short pulse: 3us abs diff, 150% relative diff. Relative alone would flag
    # this (way over the 5% default threshold), but 3us is BELOW Uno's 4us micros()
    # tick floor -- this is exactly the quantization-noise case the floor exists for.
    # Expect: NOT flagged.
    la_dir_b = scratch / "la_boundary"
    raw_dir_b = scratch / "phase2_boundary"
    la_dir_b.mkdir(parents=True)
    raw_dir_b.mkdir(parents=True)
    write_raw(la_dir_b / "uno_h_all_n1.csv", [5.0] * 100)
    with open(raw_dir_b / "uno_raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us",
                     "free_heap_before", "free_heap_after", "timeout_budget_s"])
        for i in range(100):
            w.writerow(["uno", "h_all", 1, i, 2.0, 1000, 999, 90])

    # (B) ESP8266, same 3us abs diff / 150% relative diff -- but ESP8266's floor is 1us,
    # so the same magnitude of difference DOES exceed its floor. Expect: flagged.
    write_raw(la_dir_b / "esp8266_h_all_n1.csv", [5.0] * 100)
    with open(raw_dir_b / "esp8266_raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us",
                     "free_heap_before", "free_heap_after", "timeout_budget_s"])
        for i in range(100):
            w.writerow(["esp8266", "h_all", 1, i, 2.0, 60000, 59000, 90])

    # (C) ESP32, long pulse flagged resolution_insufficient in the capture plan: a big
    # diff (20ms, 10% relative -- would otherwise flag) must be reported as
    # "limited_by_micros_resolution" instead of pass/fail.
    write_raw(la_dir_b / "esp32_grover_n14.csv", [220_000.0] * 3, gap_us=1000.0, rate=1_000)
    with open(raw_dir_b / "esp32_raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us",
                     "free_heap_before", "free_heap_after", "timeout_budget_s"])
        for i in range(3):
            w.writerow(["esp32", "grover", 14, i, 200_000.0, 100000, 99000, 14400])
    plan_path_b = scratch / "plan_boundary.csv"
    with open(plan_path_b, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=lcp.PLAN_FIELDS)
        w.writeheader()
        w.writerow({"board": "esp32", "circuit": "grover", "n": 14, "pulse_width_us": 200000,
                    "recommended_sample_rate_hz": 1000, "resolution_insufficient": True,
                    "n_reps_to_capture": 3, "reduced_reps": True, "capture_duration_s": 0.6,
                    "format_a_size_bytes": 1200, "format_b_size_bytes": 120,
                    "recommended_format": "B", "exceeds_size_limit": False})

    out_path_b = scratch / "telemetry_boundary" / "la_crosscheck.csv"
    sys.argv = ["la_crosscheck.py", "--la-dir", str(la_dir_b), "--raw-dir", str(raw_dir_b),
                "--out", str(out_path_b), "--min-pulse-width-us", "1.0",
                "--plan", str(plan_path_b)]
    lac.main()
    rowsb = {r["board"] + r["circuit"] + str(r["n"]): r for r in csv.DictReader(open(out_path_b))}

    uno_b = rowsb["unoh_all1"]
    check("boundary: Uno 3us abs diff below its 4us floor -> NOT flagged",
          uno_b["flagged"] == "False" and uno_b["status"] == "pass", uno_b)
    check("boundary: Uno abs_floor_us recorded as 4.0", float(uno_b["abs_floor_us"]) == 4.0)

    esp_b = rowsb["esp8266h_all1"]
    check("boundary: ESP8266 same 3us abs diff exceeds its 1us floor -> flagged",
          esp_b["flagged"] == "True" and esp_b["status"] == "flagged", esp_b)
    check("boundary: ESP8266 abs_floor_us recorded as 1.0", float(esp_b["abs_floor_us"]) == 1.0)

    grover_b = rowsb["esp32grover14"]
    check("boundary: resolution_insufficient point reported as limited, not pass/fail",
          grover_b["status"] == "limited_by_micros_resolution" and grover_b["flagged"] == "False",
          grover_b)
    check("boundary: resolution_insufficient flag itself carried through from the plan",
          grover_b["resolution_insufficient"] == "True")


def test_capture_plan():
    """หน่วยทดสอบตรรกะของ analysis/la_capture_plan.py ล้วน ๆ ไม่ต้องมีไฟล์เลย —
    ตรวจขอบเขตการเลือก rate, การลด reps, และการคำนวณขนาดไฟล์"""
    rates = [24_000_000, 12_000_000, 6_000_000, 1_000_000, 100_000, 10_000]

    # --- rate selection boundaries ---
    # พัลส์กว้าง 10,000us (10ms): resolution 0.1% ต้องการ <= 10us/sample -> rate >= 100kHz
    # (period 10us พอดี) และ min_samples_per_pulse=10 ต้องการ >= 10 sample/pulse ที่ 100kHz
    # ได้ 1000 sample/pulse ผ่านสบาย ๆ -> คาดว่าได้ 100kHz (ตัวต่ำสุดที่ผ่านทั้งคู่)
    rate, insufficient = lcp.choose_sample_rate(10_000.0, rates, 0.001, 10)
    check("rate selection: 10ms pulse picks 100kHz (lowest that satisfies both constraints)",
          rate == 100_000 and not insufficient, (rate, insufficient))

    # พัลส์แคบมาก (0.5us): resolution 0.1% ต้องการ <= 0.0005us/sample = 2GHz -- ไม่มี rate
    # ไหนใน list ทำได้ -> ต้อง fallback เป็น rate สูงสุด (24MHz) พร้อม flag insufficient=True
    rate, insufficient = lcp.choose_sample_rate(0.5, rates, 0.001, 10)
    check("rate selection: 0.5us pulse falls back to max rate with insufficient=True",
          rate == 24_000_000 and insufficient, (rate, insufficient))

    # ขอบเขตพอดี: min_samples_per_pulse บังคับ rate สูงกว่าที่ resolution อย่างเดียวจะให้
    # พัลส์ 1000us, resolution 0.1% -> ต้องการ <= 1us/sample -> rate >= 1MHz ผ่านที่ 1MHz
    # ด้วย resolution เพียงอย่างเดียว (1000 sample/pulse ที่ 1MHz > 10 อยู่แล้ว) ทดสอบว่า
    # min_samples_per_pulse ที่สูงเกินจริง (เช่น 100,000) บังคับให้ต้องขยับไป rate สูงกว่า
    rate, insufficient = lcp.choose_sample_rate(1000.0, rates, 0.001, 100_000)
    # ที่ rate ใดก็ตามใน list, samples_per_pulse = 1000us * rate / 1e6 -- ที่ 24MHz ได้
    # 24000 sample/pulse ซึ่งยังไม่ถึง 100,000 -> ไม่มี rate ไหนผ่าน -> fallback สูงสุด
    check("rate selection: unreasonably high min_samples_per_pulse falls back with insufficient=True",
          rate == 24_000_000 and insufficient, (rate, insufficient))

    # --- reps reduction boundary ---
    check("reps: exactly at threshold uses full reps (boundary is > not >=)",
          lcp.choose_reps(1_000_000.0, 1_000_000.0, 100, 5) == 100)
    check("reps: just above threshold reduces", lcp.choose_reps(1_000_000.1, 1_000_000.0, 100, 5) == 5)
    check("reps: well below threshold uses full reps", lcp.choose_reps(100.0, 1_000_000.0, 100, 5) == 100)

    # --- size calculation ---
    # 100 reps, 284us pulse, chosen rate from the real selector (should be 24MHz given
    # such a short pulse at default resolution_fraction) -> verify FORMAT A/B byte math
    plan = lcp.plan_point("uno", "h_all", 2, rates, 0.001, 10, 1_000_000.0, 100, 5, 50_000_000)
    expected_duration_s = plan["pulse_width_us"] * 100 * 1e-6
    expected_format_a = expected_duration_s * plan["recommended_sample_rate_hz"] * lcp.BYTES_PER_SAMPLE_RAW
    check("size calc: FORMAT A bytes match duration * rate * bytes_per_sample",
          abs(plan["format_a_size_bytes"] - expected_format_a) < 1.0,
          (plan["format_a_size_bytes"], expected_format_a))
    check("size calc: FORMAT B bytes match 2 edges/pulse * reps * bytes_per_row",
          plan["format_b_size_bytes"] == round(100 * 2 * lcp.BYTES_PER_EDGE_ROW_ESTIMATE),
          plan["format_b_size_bytes"])
    check("size calc: exceeds_size_limit=False for a tiny point with a generous limit",
          not plan["exceeds_size_limit"])

    # a deliberately tiny size limit must trip the flag
    plan_tight = lcp.plan_point("uno", "h_all", 2, rates, 0.001, 10, 1_000_000.0, 100, 5, 10)
    check("size calc: exceeds_size_limit=True when the limit is set absurdly low",
          plan_tight["exceeds_size_limit"])

    # a genuinely long pulse should trigger reduced reps end-to-end through plan_point
    plan_long = lcp.plan_point("esp8266", "grover", 9, rates, 0.001, 10, 1_000_000.0, 100, 5, 50_000_000)
    check("size calc: long-pulse point (grover n=9) gets reduced_reps=True end-to-end",
          plan_long["reduced_reps"] and plan_long["n_reps_to_capture"] == 5, plan_long)


def main():
    scratch = Path(tempfile.mkdtemp(prefix="la_test_"))
    real_la_dir = REPO_ROOT / "data" / "raw" / "la"
    real_telemetry_dir = REPO_ROOT / "data" / "raw" / "telemetry"
    before_la = set(real_la_dir.glob("**/*")) if real_la_dir.exists() else set()
    before_tel = set(real_telemetry_dir.glob("**/*")) if real_telemetry_dir.exists() else set()
    try:
        test_la_pulses(scratch / "pulses")
        test_la_crosscheck(scratch / "crosscheck")
        test_capture_plan()
    finally:
        after_la = set(real_la_dir.glob("**/*")) if real_la_dir.exists() else set()
        after_tel = set(real_telemetry_dir.glob("**/*")) if real_telemetry_dir.exists() else set()
        check("no test run touched the real data/raw/la/ directory", after_la == before_la)
        check("no test run touched the real data/raw/telemetry/ directory", after_tel == before_tel)
        shutil.rmtree(scratch, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\nTOTAL: {len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
