#!/usr/bin/env python3
# timing_report.py — อ่าน telemetry sessions.csv/points.csv ของทุก (board, circuit, phase)
# ภายใต้ data/raw/ (2026-09-20: ย้ายจากไฟล์รวมเดียว data/raw/telemetry/{sessions,points}.csv
# มาเป็นไฟล์แยกต่อ board+circuit ใน data/raw/<board>/<circuit>/phase<N>/ — ดู run_log.md
# "per-board per-algorithm layout" และ pc/shared/paths.py) แล้วสรุป:
#   1. actual vs estimated ต่อ session, ต่อวงจร, ต่อ phase
#   2. ค่ามัธยฐานของ reflash (compile_s + upload_s) ที่วัดจริงต่อบอร์ด — ใช้แทนที่
#      pc/shared/timing_model.REFLASH_COST_S (ตอนนี้เป็นค่าประมาณ ไม่ใช่ค่าที่วัดจริง)
#
# ไม่คำนวณอะไรใหม่ที่ไม่มีอยู่ในข้อมูลดิบ — สรุปสถิติล้วน ๆ (เหมือน phase2_summarize.py
# / phase3_summarize.py) อ่านอย่างเดียว ไม่แก้ timing_model.py ให้เอง (การแทนที่
# REFLASH_COST_S ด้วยค่าที่วัดจริงเป็นการตัดสินใจที่ต้องทำแยก ไม่ใช่ผลข้างเคียงของ
# การรันสคริปต์รายงาน)

import csv
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import timing_model as tm  # noqa: E402

RAW_ROOT = REPO_ROOT / "data" / "raw"


def load_rows(path: Path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_all(filename):
    """Aggregate one telemetry file (sessions.csv or points.csv) across every
    (board, circuit, phase) directory under data/raw/ -- these used to be one
    shared file, now split per algorithm (see module header)."""
    rows = []
    for path in sorted(RAW_ROOT.glob(f"*/*/phase*/{filename}")):
        rows.extend(load_rows(path))
    return rows


def _f(row, key, default=None):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def report_sessions(sessions):
    if not sessions:
        print("no session records yet — run a sweep script first")
        return
    print("=" * 100)
    print("SESSIONS: actual vs estimated")
    print("=" * 100)
    print(f"{'board':8s} {'phase':5s} {'circuits':30s} {'estimated':>10s} {'actual':>10s} {'ratio':>7s}")
    for r in sessions:
        est = _f(r, "estimated_total_s")
        act = _f(r, "actual_total_s")
        ratio = _f(r, "ratio_actual_over_estimated")
        est_h = tm.human_duration(est) if est is not None else "n/a"
        act_h = tm.human_duration(act) if act is not None else "n/a"
        ratio_s = f"{ratio:.2f}x" if ratio is not None else "n/a"
        circuits = r.get("circuits", "")[:30]
        print(f"{r.get('board',''):8s} {r.get('phase',''):5s} {circuits:30s} {est_h:>10s} {act_h:>10s} {ratio_s:>7s}")

    ratios = [_f(r, "ratio_actual_over_estimated") for r in sessions]
    ratios = [r for r in ratios if r is not None]
    if ratios:
        print(f"\nmedian actual/estimated ratio across all sessions: {statistics.median(ratios):.2f}x "
              f"(n={len(ratios)})")


def report_skip_reasons(sessions):
    """สรุปจำนวนจุดที่ถูกข้ามต่อเหตุผล รวมทุก session — จุดที่ข้าม (ไม่ว่าเหตุผลไหน)
    ไม่มีค่า timing ใด ๆ ให้บวก (ดู report_by_algorithm: ฟิลด์ device_exec_s/
    build_compile_s/upload_s ของแถวข้ามเป็นค่าว่างเสมอ อ่านเป็น 0.0 อัตโนมัติ) จึงไม่
    ปนเข้า actual-time totals อยู่แล้วโดยไม่ต้องกรองเพิ่ม — ฟังก์ชันนี้แค่แสดงให้เห็นว่า
    "ข้ามไปกี่จุด เพราะอะไร" ซึ่งไม่มีที่ไหนอื่นสรุปให้เห็นภาพรวมทั้งรัน"""
    print("\n" + "=" * 100)
    print("SKIPPED POINTS BY REASON (summed across all sessions; excluded from actual-time totals above)")
    print("=" * 100)
    reasons = [
        ("n_points_skipped_resume", "resume (already completed in a previous session)"),
        ("n_points_skipped_known_wall", "known wall (higher n than a previously-found wall)"),
        ("n_points_skipped_compute_infeasible", "compute-infeasible (Phase 2, expected time > ceiling)"),
        ("n_points_skipped_sim_cost_infeasible", "sim-cost-infeasible (Phase 3, PC-side sim > ceiling)"),
    ]
    totals = {field: 0 for field, _ in reasons}
    for r in sessions:
        for field, _ in reasons:
            totals[field] += int(_f(r, field, 0.0) or 0)
    for field, label in reasons:
        print(f"  {totals[field]:5d}  {label}")
    print(f"  {'-' * 5}")
    print(f"  {sum(totals.values()):5d}  total skipped")


def report_by_phase(sessions):
    print("\n" + "=" * 100)
    print("BY PHASE: total actual wall-clock time")
    print("=" * 100)
    by_phase = {}
    for r in sessions:
        act = _f(r, "actual_total_s", 0.0)
        by_phase.setdefault(r.get("phase", "?"), 0.0)
        by_phase[r.get("phase", "?")] += act
    for phase, total in sorted(by_phase.items()):
        print(f"phase {phase}: {tm.human_duration(total)}")


def report_by_algorithm(points):
    print("\n" + "=" * 100)
    print("BY ALGORITHM (circuit): total actual time (device_exec_s + reflash), from POINT records")
    print("=" * 100)
    by_circuit = {}
    for r in points:
        circuit = r.get("circuit", "?")
        device = _f(r, "device_exec_s", 0.0) or 0.0
        compile_s = _f(r, "build_compile_s", 0.0) or 0.0
        upload_s = _f(r, "upload_s", 0.0) or 0.0
        by_circuit.setdefault(circuit, 0.0)
        by_circuit[circuit] += device + compile_s + upload_s
    for circuit, total in sorted(by_circuit.items(), key=lambda kv: -kv[1]):
        print(f"{circuit:14s} {tm.human_duration(total)}")


def measured_reflash_cost(points):
    """ค่ามัธยฐานของ (build_compile_s + upload_s) ต่อบอร์ด จากแถวที่ reflash จริง
    (attempt ที่มี build_compile_s ไม่ว่าง — จุดที่ resume ข้าม/infeasible ไม่มีค่านี้)
    เทียบกับ REFLASH_COST_S ปัจจุบันใน timing_model.py (ค่าประมาณ) ให้เห็นส่วนต่าง"""
    print("\n" + "=" * 100)
    print("MEASURED REFLASH COST vs current REFLASH_COST_S estimate (timing_model.py)")
    print("=" * 100)
    by_board = {}
    for r in points:
        compile_s = _f(r, "build_compile_s")
        upload_s = _f(r, "upload_s")
        if compile_s is None or upload_s is None:
            continue  # จุดที่ไม่ได้ reflash จริง (skip/resume) ไม่มีค่านี้
        board = r.get("board", "?")
        by_board.setdefault(board, []).append(compile_s + upload_s)

    if not by_board:
        print("no reflash measurements yet (no point has both build_compile_s and upload_s populated)")
        return {}

    print(f"{'board':8s} {'n_samples':>9s} {'median_s':>9s} {'current_estimate_s':>19s} {'delta':>8s}")
    medians = {}
    for board, samples in sorted(by_board.items()):
        med = statistics.median(samples)
        medians[board] = med
        current = tm.REFLASH_COST_S.get(board)
        delta = f"{med - current:+.1f}s" if current is not None else "n/a"
        print(f"{board:8s} {len(samples):9d} {med:9.1f} {current if current is not None else 'n/a':>19} {delta:>8s}")
    print("\nto apply: update REFLASH_COST_S in pc/shared/timing_model.py with these medians "
          "(manual step — this script only reports, never edits timing_model.py)")
    return medians


def main():
    sessions = load_all("sessions.csv")
    points = load_all("points.csv")
    report_sessions(sessions)
    report_skip_reasons(sessions)
    report_by_phase(sessions)
    report_by_algorithm(points)
    measured_reflash_cost(points)


if __name__ == "__main__":
    main()
