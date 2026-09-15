#!/usr/bin/env python3
# appendix_c_crossover_subplots.py — ภาคผนวก ค, ภาพที่ ค-12
# กราฟเส้น 3 subplot — 1 algorithm (วงจร) ต่อ subplot: h_all, bell_ghz, qft
# แกน x = จำนวนคิวบิต (n), แกน y = เวลา (µs, log scale)
# แต่ละ subplot มี 6 เส้น = 3 บอร์ด (Uno/ESP8266/ESP32) × 2 เส้นทาง (local ทึบ,
# offload ประ) — ครบทั้ง Local Execution Time (Phase 2) และ Offload E2E Latency
# (Phase 3) อยู่ในกราฟเดียวกัน ไม่ต้องแยกไฟล์ offload ต่างหาก เพราะเส้นประ *คือ*
# ข้อมูล offload อยู่แล้ว
#
# จัดกลุ่มตาม "algorithm" (วงจร) แทนที่จะจัดตามบอร์ดเหมือนกราฟเดิมใน
# fig_phase3_{board}_crossover.png — เพื่อให้เทียบ "บอร์ดไหนเร็วกว่ากัน" ที่วงจร
# เดียวกันได้ในหน้าเดียว ตรงข้ามกับกราฟเดิมที่เทียบ "วงจรไหนคุ้ม offload ก่อน"
# ที่บอร์ดเดียวกัน — สองมุมมองคนละคำถาม ไม่ใช่กราฟซ้ำ
#
# จุดตัด (crossover point) ทำเครื่องหมายด้วยวงกลมกลวงสีเดียวกับเส้นบอร์ดนั้น
# บวกเส้นประแนวตั้งบาง ๆ ลงแกน x — อ่านค่าจาก results/phase3/crossover_summary.csv
# ตรง ๆ (ไม่คำนวณซ้ำ) เพื่อให้ตรงกับตัวเลขที่รายงานบทที่ 4 ทุกประการ
#
# แหล่งข้อมูล: results/phase2/summary.csv (local), results/phase3/summary.csv
# (offload), results/phase3/crossover_summary.csv (ตำแหน่งจุดตัดที่คำนวณไว้แล้ว)
#
# ผลลัพธ์: results/phase3/crossover_all_boards.png (300 DPI)

import csv
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE2_DIR = REPO_ROOT / "results" / "phase2"
PHASE3_DIR = REPO_ROOT / "results" / "phase3"
OUT_PATH = PHASE3_DIR / "crossover_all_boards.png"
FONT_PATH = Path.home() / "Library" / "Fonts" / "THSarabunNew.ttf"

CIRCUIT_ORDER = ["h_all", "bell_ghz", "qft"]
CIRCUIT_TITLE = {
    "h_all": "h_all (Hadamard ทุกคิวบิต)",
    "bell_ghz": "bell_ghz (Bell/GHZ state)",
    "qft": "qft (Quantum Fourier Transform)",
}
BOARD_ORDER = ["uno", "esp8266", "esp32"]
BOARD_LABEL = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
# สีต่อบอร์ด (เดิมใน fig_phase3_{board}_crossover.png ใช้ 3 สีนี้แทนวงจร — กราฟนี้
# สลับแกนกลุ่ม จึงสลับความหมายสีมาเป็นบอร์ดแทน ยังอยู่ใน categorical slot 1-3 เดิม)
COLOR_BY_BOARD = {"uno": "#2a78d6", "esp8266": "#eb6834", "esp32": "#159873"}


def load_font():
    if FONT_PATH.exists():
        fm.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=str(FONT_PATH)).get_name()


def load_local():
    path = PHASE2_DIR / "summary.csv"
    if not path.exists():
        raise SystemExit(f"error: {path} not found. รัน analysis/phase2_summarize.py ก่อน")
    local = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            local[(r["board"], r["circuit"], int(r["n"]))] = float(r["median_exec_time_us"])
    return local


def load_offload():
    path = PHASE3_DIR / "summary.csv"
    if not path.exists():
        raise SystemExit(f"error: {path} not found. รัน analysis/phase3_summarize.py ก่อน")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_crossover():
    path = PHASE3_DIR / "crossover_summary.csv"
    if not path.exists():
        raise SystemExit(f"error: {path} not found. รัน analysis/phase3_crossover_plot.py ก่อน")
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            n = r["crossover_n"]
            out[(r["board"], r["circuit"])] = int(n) if n.isdigit() else None
    return out


def best_baud_per_board(rows):
    best = {}
    for r in rows:
        board, baud = r["board"], int(r["baud_rate"])
        if board not in best or baud > best[board]:
            best[board] = baud
    return best


def main():
    load_font()
    local = load_local()
    offload_rows = load_offload()
    crossover = load_crossover()
    best_baud = best_baud_per_board(offload_rows)
    circuits = [c for c in CIRCUIT_ORDER if any(r["circuit"] == c for r in offload_rows)]
    if not circuits:
        raise SystemExit("error: ไม่มีข้อมูล Phase 3 ที่ตรงกับวงจรใน CIRCUIT_ORDER")

    fig, axes = plt.subplots(1, len(circuits), figsize=(6.2 * len(circuits), 5.6), dpi=300, sharey=True)
    if len(circuits) == 1:
        axes = [axes]

    for ax, circuit in zip(axes, circuits):
        ax.set_facecolor("#fcfcfb")

        for board in BOARD_ORDER:
            baud = best_baud.get(board)
            if baud is None:
                continue
            pts = sorted(
                (int(r["n"]), float(r["median_e2e_latency_us"]))
                for r in offload_rows
                if r["board"] == board and r["circuit"] == circuit and int(r["baud_rate"]) == baud
            )
            if not pts:
                continue
            ns = [p[0] for p in pts]
            offload_t = [p[1] for p in pts]
            local_t = [local.get((board, circuit, n)) for n in ns]
            color = COLOR_BY_BOARD[board]

            ax.plot(ns, local_t, marker="o", markersize=6, markeredgewidth=1.0,
                     markeredgecolor="white", linewidth=2.2, linestyle="-",
                     color=color, label=f"{BOARD_LABEL[board]} — Local", zorder=3)
            ax.plot(ns, offload_t, marker="s", markersize=5.5, markeredgewidth=1.0,
                     markeredgecolor="white", linewidth=1.8, linestyle="--",
                     color=color, alpha=0.8, label=f"{BOARD_LABEL[board]} — Offload", zorder=3)

            # จุดตัด: อ่านจาก crossover_summary.csv ตรง ๆ (n แรกที่ offload < local)
            cn = crossover.get((board, circuit))
            if cn is not None and cn in ns:
                idx = ns.index(cn)
                if local_t[idx] is not None:
                    ax.scatter([cn], [offload_t[idx]], s=130, facecolors="none",
                               edgecolors=color, linewidths=2.2, zorder=5)
                    ax.axvline(x=cn, color=color, linestyle=":", linewidth=1.1, alpha=0.5, zorder=1)

        ax.set_yscale("log")
        ax.set_xlabel("จำนวนคิวบิต (n)", fontsize=11.5)
        ax.set_title(CIRCUIT_TITLE[circuit], fontsize=13, pad=10)
        ax.grid(True, which="major", axis="y", alpha=0.3, linewidth=0.8, zorder=0)
        ax.grid(True, which="minor", axis="y", alpha=0.12, linewidth=0.6, zorder=0)
        ax.grid(True, which="major", axis="x", alpha=0.15, linewidth=0.6, zorder=0)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    axes[0].set_ylabel("เวลา (µs, log scale)", fontsize=12)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=6, fontsize=8.8,
               frameon=False, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("Local Execution Time เทียบ Offload E2E Latency ต่อ Algorithm — วงกลมกลวง = จุดตัด (Crossover Point)",
                 fontsize=13.5, y=1.02)
    fig.tight_layout()

    fig.savefig(OUT_PATH, bbox_inches="tight", dpi=300)
    print(f"graph -> {OUT_PATH}")


if __name__ == "__main__":
    main()
