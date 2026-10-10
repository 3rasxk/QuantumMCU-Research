#!/usr/bin/env python3
# phase3_crossover_plot.py
# กราฟที่สำคัญที่สุดของ Phase 3: เทียบ Local Execution Time (จาก Phase 2) กับ
# Offload E2E Latency (จาก Phase 3) แกน y เป็น log scale หนึ่งไฟล์ต่อบอร์ด
# ภายในไฟล์แบ่ง 1 subplot ต่อวงจร — เส้นทึบ/marker ทึบ = local, เส้นประ/marker กลวง =
# offload (ใช้ baud สูงสุดที่มีข้อมูล) ทั้งคู่เป็นสีบอร์ด พร้อมแถบ IQR
# และหา Crossover Point (n แรกที่ median offload < median local) ต่อวงจรต่อบอร์ด
#
# ผลลัพธ์: data/figures/phase3/crossover_{board}.png
#          data/processed/phase3/crossover_summary.csv

import csv
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

PHASE2_PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "phase2"
PHASE3_PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "phase3"
PHASE3_FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase3"
NO_CROSSOVER = "none_in_tested_range"


def load_local():
    """{(board, circuit, n): (median, q1, q3, n_trials)} จาก Phase 2"""
    path = PHASE2_PROCESSED_DIR / "summary.csv"
    if not path.exists():
        raise SystemExit(f"error: {path} not found. รัน analysis/phase2_summarize.py ก่อน")
    local = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            local[(r["board"], r["circuit"], int(r["n"]))] = (
                float(r["median_exec_time_us"]), float(r["iqr_low_us"]),
                float(r["iqr_high_us"]), int(r["n_trials"]),
            )
    return local


def load_offload():
    path = PHASE3_PROCESSED_DIR / "summary.csv"
    if not path.exists():
        raise SystemExit(f"error: {path} not found. รัน analysis/phase3_summarize.py ก่อน")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


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


def series_for(board, circuit, baud, local, offload_rows):
    """ดึงข้อมูลเส้น local/offload ของ (board, circuit) บนแกน n เดียวกัน
    n ที่ local ไม่มีข้อมูล (เกิน Memory Wall) ใส่ NaN — offload ยังพล็อตได้"""
    off = sorted(
        (int(r["n"]), float(r["median_e2e_latency_us"]), float(r["iqr_low_us"]),
         float(r["iqr_high_us"]), int(r["n_trials"]))
        for r in offload_rows
        if r["board"] == board and r["circuit"] == circuit and int(r["baud_rate"]) == baud
    )
    if not off:
        return None
    nan = (math.nan, math.nan, math.nan, None)
    ns = [p[0] for p in off]
    loc = [local.get((board, circuit, n), nan) for n in ns]
    return {
        "ns": ns,
        "off_med": [p[1] for p in off], "off_q1": [p[2] for p in off], "off_q3": [p[3] for p in off],
        "off_trials": [p[4] for p in off],
        "loc_med": [p[0] for p in loc], "loc_q1": [p[1] for p in loc], "loc_q3": [p[2] for p in loc],
        "loc_trials": [p[3] for p in loc if p[3] is not None],
    }


def find_crossover(s):
    """n แรกที่ median offload < median local (ข้าม n ที่ไม่มีข้อมูล local)"""
    for n, lt, ot in zip(s["ns"], s["loc_med"], s["off_med"]):
        if not math.isnan(lt) and ot < lt:
            return n, ot
    return None, None


def draw_series(ax, board, circuit, s, band_alpha=ps.IQR_ALPHA):
    """วาด local (ทึบ) + offload (ประ, marker กลวง) สีบอร์ด พร้อมแถบ IQR และ
    ทำเครื่องหมายจุดผิดปกติที่ยืนยันแล้ว — ใช้ร่วมกับ appendix_c_crossover_subplots.py"""
    color = ps.BOARD_COLOR[board]
    marker = ps.BOARD_MARKER[board]
    ns = s["ns"]
    ax.fill_between(ns, s["loc_q1"], s["loc_q3"], color=color, alpha=band_alpha, linewidth=0, zorder=2)
    ax.fill_between(ns, s["off_q1"], s["off_q3"], color=color, alpha=band_alpha * 0.7,
                    linewidth=0, zorder=2)
    ax.plot(ns, s["loc_med"], color=color, linestyle="-", linewidth=1.8, marker=marker, markersize=5,
            markeredgecolor="white", markeredgewidth=0.7, zorder=3,
            label=f"{ps.BOARD_SHORT[board]} — local")
    ax.plot(ns, s["off_med"], color=color, linestyle="--", linewidth=1.6, marker=marker, markersize=5,
            markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.1, zorder=3,
            label=f"{ps.BOARD_SHORT[board]} — offload")

    label = "anomaly (also flagged in n=30 run)"
    for n in ps.resolve_anomalies(board, circuit, ns, s["loc_med"], "local", "local"):
        ps.mark_anomaly(ax, n, s["loc_med"][ns.index(n)], label)
    for n in ps.resolve_anomalies(board, circuit, ns, s["off_med"], "offload", "offload"):
        ps.mark_anomaly(ax, n, s["off_med"][ns.index(n)], label)


def main():
    local = load_local()
    offload_rows = load_offload()
    boards = [b for b in ps.BOARD_ORDER if any(r["board"] == b for r in offload_rows)]
    best_baud = best_baud_per_board(offload_rows)
    ps.apply_style()

    crossover_summary = []

    for board in boards:
        baud = best_baud[board]
        circuits = [c for c in ps.CIRCUIT_ORDER
                    if any(r["board"] == board and r["circuit"] == c for r in offload_rows)]
        fig, axes = plt.subplots(1, len(circuits), figsize=(4.6 * len(circuits), 4.6),
                                 sharey=True, squeeze=False, layout="constrained")
        axes = axes[0]
        loc_trials, off_trials = [], []
        any_crossover = False

        for ax, circuit in zip(axes, circuits):
            s = series_for(board, circuit, baud, local, offload_rows)
            if s is None:
                continue
            loc_trials += s["loc_trials"]
            off_trials += s["off_trials"]
            draw_series(ax, board, circuit, s)

            crossover_n, _ = find_crossover(s)
            if crossover_n is not None:
                any_crossover = True
                ax.axvline(crossover_n, color=ps.REFERENCE_LINE, linestyle=":", linewidth=1.2, zorder=1)
                ax.annotate(f"crossover\nn = {crossover_n}", xy=(crossover_n, 1), xycoords=("data", "axes fraction"),
                            xytext=(4, -4), textcoords="offset points", ha="left", va="top",
                            fontsize=8, color=ps.INK_PRIMARY)
            crossover_summary.append({
                "board": board, "circuit": circuit, "baud_used": baud,
                "crossover_n": crossover_n if crossover_n is not None else NO_CROSSOVER,
                "n_tested_max": max(s["ns"]),
            })

            ps.style_axes(ax, log_y=True)
            ax.set_title(ps.CIRCUIT_LABEL[circuit])
            ax.set_xlabel("Number of qubits, n (qubits)")
        axes[0].set_ylabel("Time per run (µs, log scale)")

        handles, labels = axes[0].get_legend_handles_labels()
        if any_crossover:
            handles.append(Line2D([], [], color=ps.REFERENCE_LINE, linestyle=":", linewidth=1.2))
            labels.append("Crossover point (first n where offload median < local median)")
        fig.legend(handles, labels, loc="outside lower center", ncol=3)
        fig.suptitle(f"Phase 3 — {ps.BOARD_LABEL[board]}: local execution vs offload end-to-end latency "
                     f"(baud {baud})")
        ps.add_footnote(
            fig,
            "Line = median, band = IQR (25th–75th percentile); "
            f"{ps.reps_phrase(loc_trials, 'local')}; {ps.reps_phrase(off_trials, 'offload')}.",
        )
        ps.save_figure_png_only(fig, PHASE3_FIGURES_DIR, f"crossover_{board}")

    # เขียนตารางสรุป Crossover Point
    PHASE3_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = PHASE3_PROCESSED_DIR / "crossover_summary.csv"
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
