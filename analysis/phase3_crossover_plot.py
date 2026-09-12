#!/usr/bin/env python3
# phase3_crossover_plot.py
# กราฟที่สำคัญที่สุดของ Phase 3: เทียบ Local Execution Time (จาก Phase 2) กับ
# Offload E2E Latency (จาก Phase 3) แกน y เป็น log scale หนึ่งกราฟต่อบอร์ด
# เส้นทึบ = local, เส้นประ = offload (ใช้ baud ที่เสถียรสูงสุดที่มีข้อมูล)
# พร้อมหา Crossover Point (n แรกที่ offload เร็วกว่า local) ต่อวงจรต่อบอร์ด

import csv
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE2_DIR = REPO_ROOT / "results" / "phase2"
PHASE3_DIR = REPO_ROOT / "results" / "phase3"
FONT_PATH = Path.home() / "Library" / "Fonts" / "THSarabunNew.ttf"

COLOR_BY_CIRCUIT = {"h_all": "#2a78d6", "bell_ghz": "#eb6834", "qft": "#159873"}
LABEL_BY_CIRCUIT = {"h_all": "Hadamard ทุกคิวบิต", "bell_ghz": "Bell/GHZ state", "qft": "Quantum Fourier Transform"}


def load_font():
    if FONT_PATH.exists():
        fm.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=str(FONT_PATH)).get_name()


def load_local():
    path = PHASE2_DIR / "summary.csv"
    local = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            local[(r["board"], r["circuit"], int(r["n"]))] = float(r["median_exec_time_us"])
    return local


def load_offload():
    path = PHASE3_DIR / "summary.csv"
    rows = list(csv.DictReader(open(path, newline="")))
    return rows


def best_baud_per_board(rows):
    """เลือก baud สูงสุดที่มีข้อมูลอย่างน้อย 1 จุดสำหรับแต่ละบอร์ด เพื่อพล็อตเป็น
    'offload latency ที่ดีที่สุดเท่าที่ทดสอบได้จริง'"""
    best = {}
    for r in rows:
        board = r["board"]
        baud = int(r["baud_rate"])
        if board not in best or baud > best[board]:
            best[board] = baud
    return best


def main():
    load_font()
    local = load_local()
    offload_rows = load_offload()
    boards = sorted(set(r["board"] for r in offload_rows))
    best_baud = best_baud_per_board(offload_rows)

    crossover_summary = []

    for board in boards:
        baud = best_baud[board]
        fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=220)
        ax.set_facecolor("#fcfcfb")

        for circuit in ["h_all", "bell_ghz", "qft"]:
            pts = sorted(
                (int(r["n"]), float(r["median_e2e_latency_us"]))
                for r in offload_rows
                if r["board"] == board and r["circuit"] == circuit and int(r["baud_rate"]) == baud
            )
            if not pts:
                continue
            ns = [p[0] for p in pts]
            offload_latencies = [p[1] for p in pts]
            local_times = [local.get((board, circuit, n)) for n in ns]

            color = COLOR_BY_CIRCUIT[circuit]
            ax.plot(ns, local_times, marker="o", markersize=6.5, markeredgewidth=1.1,
                     markeredgecolor="white", linewidth=2.4, linestyle="-",
                     color=color, label=f"{LABEL_BY_CIRCUIT[circuit]} — Local", zorder=3)
            ax.plot(ns, offload_latencies, marker="s", markersize=6, markeredgewidth=1.1,
                     markeredgecolor="white", linewidth=2, linestyle="--",
                     color=color, alpha=0.8, label=f"{LABEL_BY_CIRCUIT[circuit]} — Offload", zorder=3)

            # หา crossover point: n แรกที่ offload < local
            crossover_n = None
            crossover_y = None
            for n, lt, ot in zip(ns, local_times, offload_latencies):
                if lt is not None and ot < lt:
                    crossover_n = n
                    crossover_y = ot
                    break
            if crossover_n is not None:
                ax.scatter([crossover_n], [crossover_y], s=110, facecolors="none",
                           edgecolors=color, linewidths=2, zorder=4)
            crossover_summary.append({
                "board": board, "circuit": circuit, "baud_used": baud,
                "crossover_n": crossover_n if crossover_n is not None else "ไม่พบในช่วงที่ทดสอบ",
                "n_tested_max": max(ns),
            })

        ax.set_yscale("log")
        ax.set_xlabel("จำนวนคิวบิต (n)", fontsize=11)
        ax.set_ylabel("เวลา (µs, log scale)", fontsize=11)
        ax.set_title(f"Phase 3: Local vs Offload E2E Latency — {board.upper()} (baud={baud})", fontsize=13, pad=12)
        ax.grid(True, which="major", axis="y", alpha=0.3, linewidth=0.8, zorder=0)
        ax.grid(True, which="minor", axis="y", alpha=0.12, linewidth=0.6, zorder=0)
        ax.grid(True, which="major", axis="x", alpha=0.15, linewidth=0.6, zorder=0)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.legend(fontsize=8.5, loc="lower right", ncol=1, frameon=False)
        fig.tight_layout()
        out_path = PHASE3_DIR / f"fig_phase3_{board}_crossover.png"
        fig.savefig(out_path, bbox_inches="tight")
        print(f"graph -> {out_path}")

    # เขียนตารางสรุป Crossover Point
    summary_path = PHASE3_DIR / "crossover_summary.csv"
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "baud_used", "crossover_n", "n_tested_max"])
        for row in crossover_summary:
            w.writerow([row["board"], row["circuit"], row["baud_used"], row["crossover_n"], row["n_tested_max"]])
    print(f"table -> {summary_path}")

    for row in crossover_summary:
        print(f"{row['board']:8s} {row['circuit']:9s} baud={row['baud_used']:7d}  "
              f"crossover_n={row['crossover_n']}  (tested up to n={row['n_tested_max']})")


if __name__ == "__main__":
    main()
