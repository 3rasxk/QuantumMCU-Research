# plot_style.py — มาตรฐานกราฟกลางของทั้งโปรเจกต์ (แหล่งความจริงเดียว)
#
# ทุกสคริปต์ใน analysis/ ที่สร้างกราฟต้อง import สี/ป้ายชื่อ/ฟังก์ชันบันทึกไฟล์จากที่นี่
# ห้าม hardcode ค่า hex ในสคริปต์เอง — บอร์ดเดียวกันต้องได้สีเดียวกันในทุกกราฟ
#
# Palette บอร์ด = Okabe-Ito (blue / orange / bluish green) ตรวจด้วย dataviz
# validate_palette.js --pairs all บนพื้นขาว: CVD ΔE ต่ำสุด 11.4, normal-vision ΔE
# ต่ำสุด 18.7 — ผ่านทุกเกณฑ์ ยกเว้นสีส้มมี contrast 2.25:1 (WARN) จึงต้องมี
# encoding รอง เสมอ: legend ทุกกราฟ + marker คนละรูปต่อบอร์ด
#
# ป้ายชื่อบนกราฟเป็นภาษาอังกฤษทั้งหมด (รายงานยังเป็นภาษาไทยตามเดิม)

import math
from pathlib import Path

# --- บอร์ด: ลำดับคงที่จากเล็กไปใหญ่ (ไม่ใช้ sorted() ที่จะได้ esp32,esp8266,uno) ---
BOARD_ORDER = ("uno", "esp8266", "esp32")
BOARD_LABEL = {"uno": "Arduino Uno R3", "esp8266": "NodeMCU ESP8266", "esp32": "ESP32 DevKit V1"}
BOARD_SHORT = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
BOARD_COLOR = {"uno": "#0072B2", "esp8266": "#E69F00", "esp32": "#009E73"}
BOARD_MARKER = {"uno": "o", "esp8266": "s", "esp32": "^"}

# --- วงจร: ไม่ยืมสีบอร์ด (สีมีไว้บอกบอร์ดเท่านั้น) ใช้หมึกเทา + marker + linestyle ---
# 6 วงจร: 3 ตัวเดิม (h_all, bell_ghz, qft) + grover/qpe/steane_encode ที่เพิ่มมาให้ครอบคลุม
# สเปกตรัม compute-bound <-> memory-bound <-> depth-scaling กว้างขึ้น (ดู run_log.md)
# ไล่หมึกเทาจากเข้มสุด (h_all) ไปอ่อนสุด (steane_encode) ทุกคู่ห่างกันพอแยกด้วยตาเปล่าได้
# บนพื้นขาว และยังต่างจากโทนสีบอร์ด (Okabe-Ito, สี ไม่ใช่หมึกเทา) อย่างชัดเจนเสมอ
CIRCUIT_ORDER = ("h_all", "bell_ghz", "qft", "grover", "qpe", "steane_encode")
CIRCUIT_LABEL = {
    "h_all": "h_all (Hadamard on every qubit)",
    "bell_ghz": "bell_ghz (Bell / GHZ state)",
    "qft": "qft (Quantum Fourier Transform)",
    "grover": "grover (Grover search, |1...1> marked)",
    "qpe": "qpe (Phase Estimation of P(pi/2))",
    "steane_encode": "steane_encode (Steane [[7,1,3]] encoding, n=7 fixed)",
}
CIRCUIT_INK = {
    "h_all": "#1a1a1a",
    "bell_ghz": "#3d3d3d",
    "qft": "#5e5e5e",
    "grover": "#7d7d7d",
    "qpe": "#9c9c9c",
    "steane_encode": "#b8b8b8",
}
CIRCUIT_MARKER = {
    "h_all": "o", "bell_ghz": "s", "qft": "D", "grover": "^", "qpe": "v", "steane_encode": "P",
}
CIRCUIT_LINESTYLE = {
    "h_all": "-", "bell_ghz": "--", "qft": ":", "grover": "-.", "qpe": (0, (3, 1, 1, 1)),
    "steane_encode": "none",  # จุดเดียว (n=7 คงที่) ไม่มีเส้นให้ลาก
}
# hatch คนละแบบต่อวงจร สำหรับกราฟแท่ง (encoding รองเสริมจากหมึกเทา — ดูออกแม้พิมพ์
# ขาวดำ/ไม่แยกสี) ใช้คู่กับ CIRCUIT_INK เป็น facecolor
CIRCUIT_HATCH = {
    "h_all": None, "bell_ghz": "///", "qft": "...", "grover": "xxx", "qpe": "\\\\\\", "steane_encode": "+++",
}
# วงจรที่ "ไม่" scale ตาม n (คงที่ที่ n เดียวเสมอ) — กราฟที่ลาก exec-time-vs-n ต้องรู้ว่า
# วงจรไหนควรมีจุดเดียวโดด ๆ ไม่ใช่เส้น (ดู pc/shared/circuit_ids.FIXED_N_CIRCUITS
# ที่เป็นแหล่งความจริงของค่า n จริง — ตัวนี้ในนี้มีไว้ให้กราฟใช้ได้โดยไม่ต้อง import ข้าม
# module ไปยัง pc/shared/circuit_ids)
FIXED_N_CIRCUITS = {"steane_encode": 7}

# --- หมึกกลาง (ข้อความ, เส้นอ้างอิง, ค่าทฤษฎี) ---
INK_PRIMARY = "#1a1a1a"
INK_SECONDARY = "#555555"
INK_MUTED = "#8c8c8c"
GRID_COLOR = "#e3e3e3"
REFERENCE_LINE = "#9a9a9a"
ANOMALY_INK = "#1a1a1a"

# ความทึบของแถบ IQR (ไม่ทึบจนบังเส้นบอร์ดอื่น)
IQR_ALPHA = 0.18

RASTER_DPI = 300
VECTOR_FORMAT = "svg"

# --- จุดข้อมูลที่เคยถูกทักว่าผิดปกติ (จาก dataset n=30 ที่ถูกลบไปแล้ว) ---
# ไม่ได้ถือว่ายังผิดปกติอยู่โดยอัตโนมัติ: จะทำเครื่องหมายบนกราฟก็ต่อเมื่อ
# flag_anomalies() ตรวจพบความผิดปกติจริงในข้อมูลใหม่ ณ จุดนั้นด้วย
ANOMALY_WATCHLIST = [
    {
        "board": "esp32",
        "circuit": "qft",
        "n_min": 11,
        "n_max": 12,
        "note": "flagged in n=30 run",
    },
]


# ขนาดผลขั้นต่ำ (บนสเกล log) ที่ flag_anomalies จะยอมทัก — เป็นค่าตัดสินใจเชิงวิธีการ
# ไม่ใช่ค่าที่ได้จากข้อมูล: local = อัตราโตต่อคิวบิตต่างจากปกติเกิน 25%,
# offload = latency ต่างจาก median ของเส้นเกิน 1.5 เท่า
MIN_EFFECT = {"local": math.log(1.25), "offload": math.log(1.5)}


def apply_style():
    """ตั้ง rcParams กลาง เรียกครั้งเดียวก่อนสร้าง figure แรก"""
    import matplotlib

    matplotlib.rcParams.update({
        "font.family": "DejaVu Sans",  # มากับ matplotlib เสมอ มี µ − ≤ × ครบ
        "font.size": 10,
        "axes.titlesize": 11.5,
        "axes.labelsize": 10.5,
        "axes.edgecolor": INK_SECONDARY,
        "axes.labelcolor": INK_PRIMARY,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "xtick.labelcolor": INK_PRIMARY,
        "ytick.labelcolor": INK_PRIMARY,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "figure.titlesize": 13,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.fonttype": "path",  # ฝังรูปทรงตัวอักษร เปิดที่ไหนก็หน้าตาเหมือนกัน
    })


def style_axes(ax, log_y=False, integer_x=True):
    """gridline จาง ๆ อยู่หลังข้อมูล + แกน x เป็นจำนวนเต็ม (จำนวนคิวบิต)"""
    from matplotlib.ticker import MaxNLocator

    if log_y:
        ax.set_yscale("log")
        ax.grid(True, which="minor", axis="y", color=GRID_COLOR, linewidth=0.4, alpha=0.6)
    ax.grid(True, which="major", axis="both", color=GRID_COLOR, linewidth=0.7)
    ax.set_axisbelow(True)
    if integer_x:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))


def reps_phrase(counts, label=None):
    """สรุปจำนวน repetition จากคอลัมน์ n_trials จริง (ไม่ hardcode 100)
    คืนค่าเช่น 'n = 100 repetitions per point' หรือ 'n = 97–100 ... (varies)'"""
    counts = sorted({int(c) for c in counts})
    prefix = f"{label}: " if label else ""
    if not counts:
        return f"{prefix}repetition count unavailable"
    if len(counts) == 1:
        return f"{prefix}n = {counts[0]} repetitions per point"
    return f"{prefix}n = {counts[0]}–{counts[-1]} repetitions per point (varies)"


def add_footnote(fig, text):
    """คำอธิบายสถิติ + ขนาดตัวอย่าง ใต้ figure ชิดขวา (อยู่นอกพื้นที่พล็อต ไม่บังข้อมูล
    — savefig(bbox_inches='tight') ขยายขอบภาพให้ครอบข้อความนี้เอง)"""
    fig.text(0.995, -0.005, text, ha="right", va="top", fontsize=8, color=INK_SECONDARY)


def save_figure(fig, out_dir: Path, stem: str):
    """บันทึก PNG 300 DPI + SVG ชื่อเดียวกันเสมอ: <out_dir>/<stem>.png และ .svg"""
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext, kwargs in (("png", {"dpi": RASTER_DPI}), (VECTOR_FORMAT, {})):
        path = out_dir / f"{stem}.{ext}"
        fig.savefig(path, bbox_inches="tight", pad_inches=0.08, **kwargs)
        paths.append(path)
        print(f"figure -> {path}")
    plt.close(fig)
    return paths


def save_figure_png_only(fig, out_dir: Path, stem: str):
    """บันทึกเฉพาะ PNG 300 DPI (ไม่มี SVG) — ใช้สำหรับ data/figures/<board>/<algorithm>/
    ที่ต้องมีแต่ .png เท่านั้น (2026-09-20, ดู run_log.md "per-board per-algorithm
    layout") ต่างจาก save_figure() ปกติที่ยังเขียน SVG คู่กันเสมอสำหรับกราฟเก่า
    (data/figures/phase2/) ซึ่งไม่ได้อยู่ในข้อกำหนด PNG-only นี้"""
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}.png"
    fig.savefig(path, bbox_inches="tight", pad_inches=0.08, dpi=RASTER_DPI)
    print(f"figure -> {path}")
    plt.close(fig)
    return [path]


def _quartiles(values):
    import numpy as np

    arr = np.asarray(values, dtype=float)
    return float(np.percentile(arr, 25)), float(np.percentile(arr, 75))


def flag_anomalies(ns, medians, kind):
    """ตรวจจุดผิดปกติในอนุกรม median หนึ่งเส้น ด้วย Tukey fence (1.5×IQR)

    kind="local"   : local execution time ควรโตแบบเอ็กซ์โพเนนเชียลตาม n จึงตรวจที่
                     log อัตราส่วน median[n]/median[n-1] — จุดที่อัตราโตหลุด fence
                     หรือเวลา "ลดลง" ทั้งที่ n เพิ่ม ถือว่าผิดปกติ
    kind="offload" : offload latency ควรเกือบคงที่ จึงตรวจที่ log(median) ตรง ๆ

    นอกจากหลุด fence ต้องห่างจาก median ของอนุกรมเกิน MIN_EFFECT ด้วย — กันกรณีค่าเกาะกลุ่ม
    แน่นมาก (IQR เล็ก) จน fence แคบและทักความต่างเล็กน้อยที่ไม่มีความหมายในทางปฏิบัติ

    ต้องมีอย่างน้อย 4 ค่าในการคำนวณ quartile ไม่งั้นคืนแค่กรณีเวลาลดลง
    คืน list ของ n ที่ถูกทัก"""
    import numpy as np

    pts = [(n, m) for n, m in zip(ns, medians) if m is not None and not math.isnan(m) and m > 0]
    pts.sort()
    if kind == "local":
        keyed = [
            (n1, math.log(m1 / m0))
            for (n0, m0), (n1, m1) in zip(pts, pts[1:])
            if n1 == n0 + 1
        ]
        decreasing = {n for n, v in keyed if v < 0}
    elif kind == "offload":
        keyed = [(n, math.log(m)) for n, m in pts]
        decreasing = set()
    else:
        raise ValueError(f"unknown kind {kind!r}")

    if len(keyed) < 4:
        return sorted(decreasing)
    values = [v for _, v in keyed]
    q1, q3 = _quartiles(values)
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    center = float(np.median(values))
    min_effect = MIN_EFFECT[kind]
    outliers = {n for n, v in keyed if (v < lo or v > hi) and abs(v - center) > min_effect}
    return sorted(outliers | decreasing)


def watchlist_note(board, circuit, n):
    for item in ANOMALY_WATCHLIST:
        if item["board"] == board and item["circuit"] == circuit and item["n_min"] <= n <= item["n_max"]:
            return item["note"]
    return None


def resolve_anomalies(board, circuit, ns, medians, kind, series_label):
    """รวม flag_anomalies กับ watchlist:
    - จุดใน watchlist ที่ยังผิดปกติจริงในข้อมูลใหม่ -> คืนไปทำเครื่องหมายบนกราฟ
    - จุดผิดปกติที่ไม่อยู่ใน watchlist -> พิมพ์เตือนทาง console ให้คนตัดสินใจ (ไม่วาด)
    - จุดใน watchlist ที่ข้อมูลใหม่ปกติแล้ว -> พิมพ์ว่าไม่พบซ้ำ"""
    flagged = flag_anomalies(ns, medians, kind)
    to_mark = []
    for n in flagged:
        if watchlist_note(board, circuit, n):
            to_mark.append(n)
        else:
            print(f"note: possible anomaly (not on watchlist) board={board} circuit={circuit} "
                  f"series={series_label} n={n} — review before reporting")
    for item in ANOMALY_WATCHLIST:
        if item["board"] == board and item["circuit"] == circuit:
            tested = [n for n in ns if item["n_min"] <= n <= item["n_max"]]
            if tested and not any(item["n_min"] <= n <= item["n_max"] for n in to_mark):
                print(f"note: watchlist region board={board} circuit={circuit} series={series_label} "
                      f"n={item['n_min']}–{item['n_max']} did not reproduce as an anomaly")
    return to_mark


def mark_anomaly(ax, x, y, text="anomaly"):
    """วงแหวนกลวงสีหมึกกลาง + ป้ายเล็ก ไม่ใช้สีสถานะ/สีบอร์ด"""
    ax.scatter([x], [y], s=190, facecolors="none", edgecolors=ANOMALY_INK,
               linewidths=1.1, linestyle=(0, (2, 1.5)), zorder=6)
    ax.annotate(text, xy=(x, y), xytext=(-8, 14), textcoords="offset points",
                ha="right", va="bottom", fontsize=7.5, color=INK_PRIMARY,
                arrowprops={"arrowstyle": "-", "color": INK_SECONDARY, "linewidth": 0.7},
                zorder=6)
