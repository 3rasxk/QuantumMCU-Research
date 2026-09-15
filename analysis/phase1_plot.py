#!/usr/bin/env python3
# phase1_plot.py
# สร้างกราฟ Infidelity vs Circuit Depth (แกน y เป็น log-scale) จาก
# data/raw/phase1/infidelity_tvd.csv — ห้ามคำนวณค่าใหม่ในไฟล์นี้ อ่านค่าที่วัดจริงเท่านั้น
#
# สีที่ใช้เลือกตามลำดับ categorical แบบตายตัว (ไม่สุ่ม/ไม่หมุนเวียน) จาก
# palette ที่ผ่านการตรวจสอบ colorblind-safe แล้ว (dataviz skill, slot 1-3):
#   h_all=blue #2a78d6, bell_ghz=orange #eb6834, qft=aqua #159873

import csv
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "phase1"
FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase1"
CSV_PATH = RAW_DIR / "infidelity_tvd.csv"
FONT_PATH = Path.home() / "Library" / "Fonts" / "THSarabunNew.ttf"
THRESHOLD = 1e-3

COLOR_BY_CIRCUIT = {
    "h_all": "#2a78d6",
    "bell_ghz": "#eb6834",
    "qft": "#159873",
}
LABEL_BY_CIRCUIT = {
    "h_all": "Hadamard ทุกคิวบิต (h_all)",
    "bell_ghz": "Bell/GHZ state (bell_ghz)",
    "qft": "Quantum Fourier Transform (qft)",
}


def load_font():
    if FONT_PATH.exists():
        fm.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=str(FONT_PATH)).get_name()
    else:
        print(f"warning: ไม่พบฟอนต์ไทยที่ {FONT_PATH}, จะใช้ฟอนต์ default แทน (อาจแสดงภาษาไทยไม่ได้)")


def load_rows():
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def main():
    load_font()
    rows = load_rows()

    fig, ax = plt.subplots(figsize=(8, 5), dpi=220)
    ax.set_facecolor("#fcfcfb")

    for circuit in ["h_all", "bell_ghz", "qft"]:
        pts = sorted(
            ((int(r["depth"]), float(r["infidelity"])) for r in rows if r["circuit"] == circuit),
            key=lambda p: p[0],
        )
        depths = [p[0] for p in pts]
        infids = [p[1] for p in pts]
        ax.plot(
            depths, infids,
            marker="o", markersize=7, markeredgewidth=1.2, markeredgecolor="white",
            linewidth=2.4, color=COLOR_BY_CIRCUIT[circuit], label=LABEL_BY_CIRCUIT[circuit],
            zorder=3,
        )

    ax.axhline(THRESHOLD, color="#767676", linestyle="--", linewidth=1.5, zorder=2,
                label=f"เกณฑ์ผ่าน (Infidelity = {THRESHOLD:.0e})")

    ax.set_yscale("log")
    ax.set_xlabel("ความลึกวงจร (Circuit Depth)", fontsize=11)
    ax.set_ylabel("Infidelity (1 − F, log scale)", fontsize=11)
    ax.set_title("Phase 1: Infidelity ของ C++ Simulator เทียบกับ Qiskit Aer", fontsize=13, pad=12)
    ax.grid(True, which="major", axis="y", alpha=0.3, linewidth=0.8, zorder=0)
    ax.grid(True, which="minor", axis="y", alpha=0.12, linewidth=0.6, zorder=0)
    ax.grid(True, which="major", axis="x", alpha=0.15, linewidth=0.6, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(fontsize=9.5, loc="upper left", frameon=False)

    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES_DIR / "fig_infidelity_vs_depth.png"
    fig.savefig(out_path, bbox_inches="tight")
    print(f"graph -> {out_path}")


if __name__ == "__main__":
    main()
