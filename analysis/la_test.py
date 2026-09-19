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

RESULTS = []
RATE = 24_000_000


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


def write_raw(path, pulse_widths_us, gap_us=50.0, start_high=False, extend_trailing_high=False):
    """สร้างไฟล์ FORMAT A (sigrok-cli raw, 1 sample/บรรทัด) จำลอง capture"""
    period = 1.0 / RATE
    levels = []

    def add(seconds, level):
        n = max(1, round(seconds * period ** -1 * period))  # keep style consistent
        n = max(1, round(seconds * RATE))
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
        f.write(f";Rate: {RATE}\n;Channels: D0\n")
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

    sys.argv = ["la_crosscheck.py", "--la-dir", str(la_dir), "--raw-dir", str(raw_dir),
                "--out", str(out_path), "--min-pulse-width-us", "1.0"]
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

    # re-running must APPEND, not overwrite (matches every other telemetry file's contract)
    lac.main()
    rows2 = list(csv.DictReader(open(out_path)))
    check("crosscheck: rerun appends rather than overwrites", len(rows2) == 8, len(rows2))


def main():
    scratch = Path(tempfile.mkdtemp(prefix="la_test_"))
    real_la_dir = REPO_ROOT / "data" / "raw" / "la"
    real_telemetry_dir = REPO_ROOT / "data" / "raw" / "telemetry"
    before_la = set(real_la_dir.glob("**/*")) if real_la_dir.exists() else set()
    before_tel = set(real_telemetry_dir.glob("**/*")) if real_telemetry_dir.exists() else set()
    try:
        test_la_pulses(scratch / "pulses")
        test_la_crosscheck(scratch / "crosscheck")
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
