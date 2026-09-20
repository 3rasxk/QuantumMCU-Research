#!/usr/bin/env python3
# phase2_plot.py
# สร้างกราฟ Phase 2 จากข้อมูลจริงเท่านั้น (ไม่คำนวณ/ประมาณค่าใหม่):
#   1. Execution Time vs n (log-scale y) — 1 subplot ต่อวงจร, 1 เส้นต่อบอร์ด
#      Median + แถบ IQR จาก data/processed/phase2/summary.csv
#      -> data/figures/phase2/exec_time_vs_n.{png,svg}
#   2. Memory Wall: n สูงสุดตามทฤษฎี (2^n*8 <= SRAM) เทียบ n สูงสุดที่วัดได้จริง
#      จาก data/raw/<board>/<circuit>/phase2/memory_wall.csv (ทุก board+circuit — เส้นทาง
#      นี้เปลี่ยนจาก data/raw/phase2/*_memory_wall.csv เดิมเมื่อ 2026-09-20, ดู run_log.md
#      "per-board per-algorithm layout")
#      -> data/processed/phase2/memory_wall_summary.csv
#      -> data/figures/phase2/memory_wall_comparison.{png,svg}
#
# จัดกลุ่มกราฟ exec time ตามวงจร (ไม่ใช่ตามบอร์ดเหมือนเดิม) เพื่อให้สีคงความหมาย
# "บอร์ด" เหมือนทุกกราฟอื่นในโปรเจกต์ — สี/marker/ป้ายชื่อมาจาก pc/shared/plot_style.py

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

RAW_ROOT = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "phase2"
FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase2"
SUMMARY_PATH = PROCESSED_DIR / "summary.csv"
MEMORY_WALL_SUMMARY_PATH = PROCESSED_DIR / "memory_wall_summary.csv"

# SRAM รวมของแต่ละบอร์ด (bytes) — ใช้คำนวณ n สูงสุดตามทฤษฎี (2^n * 8 <= SRAM)
BOARD_SRAM_BYTES = {
    "uno": 2048,        # ATmega328P
    "esp8266": 81920,   # NodeMCU (~80KB usable heap โดยประมาณ)
    "esp32": 327680,    # ESP32 DevKit V1 (~320KB usable heap โดยประมาณ)
}

# ค่า status ใน *_memory_wall.csv -> ข้อความสั้นบนกราฟ
FAILURE_LABEL = {
    "build_or_upload_fail": "build/upload failure",
    "malloc_failed": "malloc() returned NULL",
}


def failure_label(status: str) -> str:
    if status.startswith("runtime_hang_or_reset"):
        return "runtime hang/reset"
    return FAILURE_LABEL.get(status, status)


def load_summary():
    if not SUMMARY_PATH.exists():
        return []
    with open(SUMMARY_PATH, newline="") as f:
        return list(csv.DictReader(f))


def load_memory_wall():
    rows = []
    for path in sorted(RAW_ROOT.glob("*/*/phase2/memory_wall.csv")):
        with open(path, newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def reps_by_board(summary_rows):
    out = {}
    for r in summary_rows:
        out.setdefault(r["board"], []).append(int(r["n_trials"]))
    return out


def plot_exec_time(summary_rows):
    circuits = [c for c in ps.CIRCUIT_ORDER if any(r["circuit"] == c for r in summary_rows)]
    fig, axes = plt.subplots(1, len(circuits), figsize=(4.6 * len(circuits), 4.6),
                             sharey=True, squeeze=False, layout="constrained")
    axes = axes[0]

    for ax, circuit in zip(axes, circuits):
        for board in ps.BOARD_ORDER:
            pts = sorted(
                (int(r["n"]), float(r["median_exec_time_us"]), float(r["iqr_low_us"]), float(r["iqr_high_us"]))
                for r in summary_rows if r["board"] == board and r["circuit"] == circuit
            )
            if not pts:
                continue
            ns = [p[0] for p in pts]
            medians = [p[1] for p in pts]
            color = ps.BOARD_COLOR[board]
            ax.fill_between(ns, [p[2] for p in pts], [p[3] for p in pts],
                            color=color, alpha=ps.IQR_ALPHA, linewidth=0, zorder=2)
            ax.plot(ns, medians, color=color, marker=ps.BOARD_MARKER[board], markersize=5,
                    markeredgecolor="white", markeredgewidth=0.7, linewidth=1.8,
                    label=ps.BOARD_LABEL[board], zorder=3)
            for n in ps.resolve_anomalies(board, circuit, ns, medians, "local", "local"):
                ps.mark_anomaly(ax, n, medians[ns.index(n)], "anomaly (also flagged in n=30 run)")

        ps.style_axes(ax, log_y=True)
        ax.set_title(ps.CIRCUIT_LABEL[circuit])
        ax.set_xlabel("Number of qubits, n (qubits)")
    axes[0].set_ylabel("Execution time (µs, log scale)")

    # legend รวมทุก subplot (บอร์ดเดียวกันสีเดียวกันทุก subplot) วางนอกพื้นที่พล็อต
    handles = {}
    for ax in axes:
        for h, lab in zip(*ax.get_legend_handles_labels()):
            handles.setdefault(lab, h)
    fig.legend(list(handles.values()), list(handles.keys()), loc="outside lower center", ncol=3)
    fig.suptitle("Phase 2 — Local execution time vs number of qubits")

    reps = [int(r["n_trials"]) for r in summary_rows]
    ps.add_footnote(fig, f"Line = median, band = IQR (25th–75th percentile); {ps.reps_phrase(reps)}.")
    ps.save_figure(fig, FIGURES_DIR, "exec_time_vs_n")


def theoretical_max_n(sram_bytes: int) -> int:
    n = 0
    while (1 << (n + 1)) * 8 <= sram_bytes:
        n += 1
    return n


def summarize_memory_wall(wall_rows):
    """สรุปต่อบอร์ดจากสถานะดิบ ต่างจากเดิมที่ first_failing_n = measured+1 เสมอ:
    ตอนนี้อ่าน n ที่ล้มเหลวจริงจากไฟล์ (ว่างถ้า sweep ไม่เจอความล้มเหลวเลย)

    retry_count (คอลัมน์ใหม่จาก pc/phase2_sweep/*.py, deviation จาก n=30 methodology
    — ดู run_log.md): sweep ปัจจุบัน retry ความล้มเหลวชั่วคราว (hang/reset/serial error)
    1 ครั้งก่อนสรุปว่าเป็น Memory Wall จริง ไฟล์เก่าที่ไม่มีคอลัมน์นี้ (ก่อน deviation)
    ยังอ่านได้ — .get() คืน "" แทน"""
    summary = []
    for board in ps.BOARD_ORDER:
        rows = [r for r in wall_rows if r["board"] == board]
        if not rows:
            continue
        ok_ns = [int(r["n"]) for r in rows if r["status"] == "ok"]
        fails = sorted(
            (int(r["n"]), r["status"], r.get("retry_count", ""))
            for r in rows if r["status"] != "ok"
        )
        measured_max = max(ok_ns) if ok_ns else 0
        first_fail_n, first_fail_status, first_fail_retry = fails[0] if fails else ("", "", "")
        if fails and ok_ns and measured_max > first_fail_n:
            # *_memory_wall.csv เป็น append-only: ถ้ารันซ้ำหลายรอบ อาจมี ok ที่ n สูงกว่า
            # จุดล้มเหลวรอบก่อน (เช่นล้มเพราะสายหลุดชั่วคราว) — ไม่ตัดสินแทน ให้คนดู
            print(f"warning: {board}: ok at n={measured_max} but a failure at n={first_fail_n} "
                  f"({first_fail_status}) — check for repeated/transient sweeps in the raw CSV")
        sram = BOARD_SRAM_BYTES.get(board, 0)
        theo = theoretical_max_n(sram)
        summary.append({
            "board": board,
            "total_sram_bytes": sram,
            "theoretical_max_n": theo,
            "measured_max_n_safe": measured_max,
            "theoretical_bytes_at_max_n": (1 << theo) * 8,
            "first_failing_n": first_fail_n,
            "first_failure_status": first_fail_status,
            "first_failure_after_retry": first_fail_retry,
        })
    return summary


def write_memory_wall_summary(summary):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["board", "total_sram_bytes", "theoretical_max_n", "measured_max_n_safe",
              "theoretical_bytes_at_max_n", "first_failing_n", "first_failure_status",
              "first_failure_after_retry"]
    with open(MEMORY_WALL_SUMMARY_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(summary)
    print(f"table -> {MEMORY_WALL_SUMMARY_PATH}")


def draw_memory_wall(summary, reps):
    """วาด Memory Wall จากแถวสรุป (dict ที่มี key ตาม memory_wall_summary.csv)
    ใช้ร่วมกับ appendix_c_memory_wall_bar.py — reps = {board: [n_trials, ...]}"""
    rows = {r["board"]: r for r in summary}
    boards = [b for b in ps.BOARD_ORDER if b in rows]
    theo_ns = [int(rows[b]["theoretical_max_n"]) for b in boards]
    meas_ns = [int(rows[b]["measured_max_n_safe"]) for b in boards]

    fig, ax = plt.subplots(figsize=(7.5, 5), layout="constrained")
    width = 0.36
    for i, b in enumerate(boards):
        color = ps.BOARD_COLOR[b]
        # ทฤษฎี = กรอบสีบอร์ด + ลายเส้นทแยง, วัดจริง = ทึบสีบอร์ด (legend ใช้ตัวแทนสีกลาง)
        theo = ax.bar(i - width / 2, theo_ns[i], width, facecolor="white", edgecolor=color,
                      hatch="///", linewidth=1.2, zorder=3)
        meas = ax.bar(i + width / 2, meas_ns[i], width, color=color, edgecolor="white",
                      linewidth=1.0, zorder=3)
        ax.bar_label(theo, padding=2, fontsize=9, color=ps.INK_PRIMARY)
        ax.bar_label(meas, padding=2, fontsize=9, color=ps.INK_PRIMARY)

    ticklabels = []
    for b in boards:
        fail_n = rows[b].get("first_failing_n", "")
        status = rows[b].get("first_failure_status", "")
        if str(fail_n).strip():
            detail = f"first failure: n = {fail_n}" + (f"\n({failure_label(status)})" if status else "")
        else:
            detail = "no failure within sweep range"
        ticklabels.append(f"{ps.BOARD_LABEL[b]}\n{detail}")
    ax.set_xticks(range(len(boards)))
    ax.set_xticklabels(ticklabels, fontsize=9)
    ax.tick_params(axis="x", length=0)

    ps.style_axes(ax, integer_x=False)
    ax.grid(False, axis="x")
    ax.set_ylim(0, max(theo_ns + meas_ns + [1]) * 1.18)
    ax.set_ylabel("Maximum number of qubits, n (qubits)")
    ax.set_title("Phase 2 — Memory Wall: theoretical vs measured maximum qubits")

    proxies = [
        Patch(facecolor="white", edgecolor=ps.INK_SECONDARY, hatch="///",
              label="Theoretical: largest n with 2ⁿ × 8 bytes ≤ total SRAM"),
        Patch(facecolor=ps.INK_SECONDARY, label="Measured: largest n that ran to completion (status ok)"),
    ]
    fig.legend(handles=proxies, loc="outside lower center", ncol=1)

    all_reps = [c for b in boards for c in reps.get(b, [])]
    ps.add_footnote(fig, f"Bar colour identifies the board. Each measured point: {ps.reps_phrase(all_reps)}.")
    ps.save_figure(fig, FIGURES_DIR, "memory_wall_comparison")

    for b, t, m in zip(boards, theo_ns, meas_ns):
        print(f"  {b:8s} theoretical={t:2d}  measured={m:2d}  gap={t - m} qubit(s)")


def main():
    summary_rows = load_summary()
    wall_rows = load_memory_wall()
    if not summary_rows and not wall_rows:
        raise SystemExit(f"error: no data. ต้องมี {SUMMARY_PATH} (รัน analysis/phase2_summarize.py) "
                         f"หรือ {RAW_ROOT}/*/*/phase2/memory_wall.csv")
    ps.apply_style()
    if summary_rows:
        plot_exec_time(summary_rows)
    if wall_rows:
        summary = summarize_memory_wall(wall_rows)
        write_memory_wall_summary(summary)
        draw_memory_wall(summary, reps_by_board(summary_rows))


if __name__ == "__main__":
    main()
