#!/usr/bin/env python3
# phase2_plot.py
# สร้างกราฟ Phase 2 จากข้อมูลจริงเท่านั้น (ไม่คำนวณ/ประมาณค่าใหม่):
#   1. Execution Time vs n (log-scale y) ต่อบอร์ด จาก results/phase2/summary.csv
#   2. Bar chart Memory Wall: n สูงสุดตามทฤษฎี (2^n*8 <= SRAM) เทียบ n สูงสุดที่วัดได้จริง
#      จาก results/phase2/*_memory_wall.csv
#
# สีวงจรใช้ palette เดียวกับ Phase 1 (dataviz skill, categorical slot 1-3)
# เพื่อความสอดคล้องกันทั้งรายงาน: h_all=blue, bell_ghz=orange, qft=aqua

import csv
import glob
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "phase2"
FONT_PATH = Path.home() / "Library" / "Fonts" / "THSarabunNew.ttf"

# SRAM รวมของแต่ละบอร์ด (bytes) — ใช้คำนวณ n สูงสุดตามทฤษฎี (2^n * 8 <= SRAM)
BOARD_SRAM_BYTES = {
    "uno": 2048,        # ATmega328P
    "esp8266": 81920,   # NodeMCU (~80KB usable heap โดยประมาณ)
    "esp32": 327680,    # ESP32 DevKit V1 (~320KB usable heap โดยประมาณ)
}

COLOR_BY_CIRCUIT = {"h_all": "#2a78d6", "bell_ghz": "#eb6834", "qft": "#159873"}
LABEL_BY_CIRCUIT = {
    "h_all": "Hadamard ทุกคิวบิต",
    "bell_ghz": "Bell/GHZ state",
    "qft": "Quantum Fourier Transform",
}


def load_font():
    if FONT_PATH.exists():
        fm.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=str(FONT_PATH)).get_name()


def load_summary():
    path = RESULTS_DIR / "summary.csv"
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_memory_wall():
    rows = []
    for path in sorted(glob.glob(str(RESULTS_DIR / "*_memory_wall.csv"))):
        with open(path, newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def plot_exec_time(summary_rows):
    boards = sorted(set(r["board"] for r in summary_rows))
    for board in boards:
        fig, ax = plt.subplots(figsize=(8, 5), dpi=220)
        ax.set_facecolor("#fcfcfb")
        for circuit in ["h_all", "bell_ghz", "qft"]:
            pts = sorted(
                (
                    (int(r["n"]), float(r["median_exec_time_us"]), float(r["iqr_low_us"]), float(r["iqr_high_us"]))
                    for r in summary_rows if r["board"] == board and r["circuit"] == circuit
                ),
                key=lambda p: p[0],
            )
            if not pts:
                continue
            ns = [p[0] for p in pts]
            medians = [p[1] for p in pts]
            lo = [p[1] - p[2] for p in pts]
            hi = [p[3] - p[1] for p in pts]
            ax.errorbar(
                ns, medians, yerr=[lo, hi],
                marker="o", markersize=7, markeredgewidth=1.2, markeredgecolor="white",
                linewidth=2.4, capsize=4, capthick=1.4, elinewidth=1.4,
                color=COLOR_BY_CIRCUIT[circuit], label=LABEL_BY_CIRCUIT[circuit], zorder=3,
            )
        ax.set_yscale("log")
        ax.set_xlabel("จำนวนคิวบิต (n)", fontsize=11)
        ax.set_ylabel("Execution Time (µs, log scale, Median ± IQR)", fontsize=11)
        ax.set_title(f"Phase 2: Execution Time vs n — {board.upper()}", fontsize=13, pad=12)
        ax.grid(True, which="major", axis="y", alpha=0.3, linewidth=0.8, zorder=0)
        ax.grid(True, which="minor", axis="y", alpha=0.12, linewidth=0.6, zorder=0)
        ax.grid(True, which="major", axis="x", alpha=0.15, linewidth=0.6, zorder=0)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.legend(fontsize=9.5, loc="upper left", frameon=False)
        fig.tight_layout()
        out_path = RESULTS_DIR / f"fig_phase2_{board}_exectime.png"
        fig.savefig(out_path, bbox_inches="tight")
        print(f"graph -> {out_path}")


def theoretical_max_n(sram_bytes: int) -> int:
    n = 0
    while (1 << (n + 1)) * 8 <= sram_bytes:
        n += 1
    return n


def plot_memory_wall(wall_rows):
    boards = sorted(set(r["board"] for r in wall_rows))
    theo_ns, meas_ns = [], []
    for board in boards:
        rows = [r for r in wall_rows if r["board"] == board]
        ok_ns = [int(r["n"]) for r in rows if r["status"] == "ok"]
        measured_max = max(ok_ns) if ok_ns else 0
        theo_max = theoretical_max_n(BOARD_SRAM_BYTES.get(board, 0))
        theo_ns.append(theo_max)
        meas_ns.append(measured_max)

    x = range(len(boards))
    width = 0.34
    fig, ax = plt.subplots(figsize=(7, 5), dpi=220)
    ax.set_facecolor("#fcfcfb")
    bars_theo = ax.bar([i - width / 2 for i in x], theo_ns, width,
                        label="ทฤษฎี (2^n × 8 ≤ SRAM รวม)", color="#9a9a9a", zorder=3)
    bars_meas = ax.bar([i + width / 2 for i in x], meas_ns, width,
                        label="วัดจริง (n สูงสุดที่รันสำเร็จ)", color="#2a78d6", zorder=3)
    for bars in (bars_theo, bars_meas):
        ax.bar_label(bars, fontsize=9.5, padding=2, color="#2a2a2a")
    ax.set_xticks(list(x))
    ax.set_xticklabels([b.upper() for b in boards], fontsize=11)
    ax.set_ylabel("จำนวนคิวบิตสูงสุด (n)", fontsize=11)
    ax.set_title("Phase 2: Memory Wall — ทฤษฎี vs วัดจริง", fontsize=13, pad=12)
    ax.set_ylim(0, max(theo_ns + meas_ns) * 1.18)
    ax.grid(True, which="major", axis="y", alpha=0.3, linewidth=0.8, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(fontsize=9.5, loc="upper left", frameon=False)
    fig.tight_layout()
    out_path = RESULTS_DIR / "fig_phase2_memory_wall.png"
    fig.savefig(out_path, bbox_inches="tight")
    print(f"graph -> {out_path}")

    # เขียนตารางสรุปเทียบทฤษฎีกับวัดจริงเป็น CSV แยกจากกราฟ
    summary_path = RESULTS_DIR / "memory_wall_summary.csv"
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "total_sram_bytes", "theoretical_max_n", "measured_max_n_safe",
                    "theoretical_bytes_at_max_n", "first_failing_n"])
        for board, theo_n, meas_n in zip(boards, theo_ns, meas_ns):
            sram = BOARD_SRAM_BYTES.get(board, 0)
            w.writerow([board, sram, theo_n, meas_n, (1 << theo_n) * 8, meas_n + 1])
    print(f"table -> {summary_path}")


def main():
    load_font()
    summary_rows = load_summary()
    wall_rows = load_memory_wall()
    if summary_rows:
        plot_exec_time(summary_rows)
    if wall_rows:
        plot_memory_wall(wall_rows)


if __name__ == "__main__":
    main()
