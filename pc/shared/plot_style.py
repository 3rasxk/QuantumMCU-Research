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
# linestyle + marker pair per board, stable in every chart (moved here from _graph_data). Reference / model curves
# are dashed grey WITHOUT markers; no board pair equals a circuit pair (the markers differ).
# colour-only series (Phase 1/2/3 charts): one colour per circuit, the same in every chart. Blue / vermillion / green /
# purple checked with dataviz validate_palette.js (--pairs all): lightness, chroma, normal-vision floor (min dE 18.7)
# and 3:1 contrast pass; CVD separation is in the 6-8 floor band (purple vs blue 6.7), so every chart also has a legend.
CIRCUIT_COLOR = {"h_all": "#0072B2", "bell_ghz": "#D55E00", "qft": "#009E73", "grover": "#7B3294"}
# extra colours for the non-board, non-circuit lines of one chart (heap, largest block, reliability, ...)
EXTRA_COLOR = {"purple": "#7B3294", "brown": "#8C510A", "vermillion": "#D55E00", "sky": "#56B4E9", "dark": "#333333"}
BOARD_LINESTYLE = {"uno": "-", "esp8266": "--", "esp32": ":"}

# --- วงจร: ไม่ยืมสีบอร์ด (สีมีไว้บอกบอร์ดเท่านั้น) ใช้หมึกเทา + marker + linestyle ---
# 4 วงจร (แผนใหม่ 2026-10-03): h_all, bell_ghz, qft, grover — qpe/steane_encode ถูกถอดออกจากแผน
# สเปกตรัม compute-bound <-> memory-bound <-> depth-scaling กว้างขึ้น (ดู run_log.md)
# ไล่หมึกเทาจากเข้มสุด (h_all) ไปอ่อนสุด (grover) ทุกคู่ห่างกันพอแยกด้วยตาเปล่าได้
# บนพื้นขาว และยังต่างจากโทนสีบอร์ด (Okabe-Ito, สี ไม่ใช่หมึกเทา) อย่างชัดเจนเสมอ
CIRCUIT_ORDER = ("h_all", "bell_ghz", "qft", "grover")
CIRCUIT_LABEL = {
    "h_all": "h_all (Hadamard on every qubit)",
    "bell_ghz": "bell_ghz (Bell / GHZ state)",
    "qft": "qft (Quantum Fourier Transform)",
    "grover": "grover (Grover search, |1...1> marked)",
}
CIRCUIT_INK = {
    "h_all": "#1a1a1a",
    "bell_ghz": "#3d3d3d",
    "qft": "#5e5e5e",
    "grover": "#7d7d7d",
}
# circuit markers avoid the board markers (o s ^) and the outcome markers of the Phase 2/3 run charts
# (o X s v P *), so a (linestyle, marker) pair identifies exactly one board or one circuit everywhere
CIRCUIT_MARKER = {
    "h_all": "D", "bell_ghz": "p", "qft": "h", "grover": "<",
}
CIRCUIT_LINESTYLE = {
    "h_all": "-", "bell_ghz": "--", "qft": ":", "grover": "-.",
}
# hatch คนละแบบต่อวงจร สำหรับกราฟแท่ง (encoding รองเสริมจากหมึกเทา — ดูออกแม้พิมพ์
# ขาวดำ/ไม่แยกสี) ใช้คู่กับ CIRCUIT_INK เป็น facecolor
CIRCUIT_HATCH = {
    "h_all": None, "bell_ghz": "///", "qft": "...", "grover": "xxx",
}
# วงจรที่ "ไม่" scale ตาม n (คงที่ที่ n เดียวเสมอ) — กราฟที่ลาก exec-time-vs-n ต้องรู้ว่า
# วงจรไหนควรมีจุดเดียวโดด ๆ ไม่ใช่เส้น (ดู pc/shared/circuit_ids.FIXED_N_CIRCUITS
# ที่เป็นแหล่งความจริงของค่า n จริง — ตัวนี้ในนี้มีไว้ให้กราฟใช้ได้โดยไม่ต้อง import ข้าม
# module ไปยัง pc/shared/circuit_ids)
FIXED_N_CIRCUITS = {}  # ไม่มีวงจรคงที่ n ในแผนปัจจุบัน

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


# --- clean style (2026-10-11): plain matplotlib look, full box, no grid, thin lines, small markers ---
LINE_WIDTH = 1.3          # pt, data lines
MARKER_SIZE = 4.0         # pt, data-point markers (outcome markers in the run charts stay larger on purpose)
REF_LINE_WIDTH = 1.0      # pt, dashed reference / model curves
BAND_ALPHA = IQR_ALPHA    # light IQR band
SHOW_REPS = False         # individual reps as faint dots only when a script/option turns this on
FONT_SANS = ["DejaVu Sans"]  # ships with matplotlib, has the micro sign, minus, <=, x
FONT_SERIF = ["Times New Roman", "Times", "Nimbus Roman", "Liberation Serif", "STIXGeneral", "DejaVu Serif"]
IEEE_SINGLE_COL_IN, IEEE_DOUBLE_COL_IN = 3.5, 7.16
_TAB10 = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")
_SERIES_LINESTYLES = ("-", "--", "-.", ":")
_SERIES_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "<", ">", "p", "h", "*")
_PAPER = False


def apply_clean_style(paper=False):
    """Set the project rcParams once, before the first figure.
    paper=False: sans-serif, 9 pt labels / 8 pt ticks and legend, for data/figures/ PNGs.
    paper=True : IEEE sizes (8 pt labels, 7 pt ticks and legend), Times-like serif, TrueType fonts embedded
                 (pdf/ps fonttype 42), no in-figure title or footnote (the caption carries them), no metadata."""
    import matplotlib

    global _PAPER
    _PAPER = bool(paper)
    label, tick, legend, title = (8, 7, 7, 8) if paper else (10, 9, 9, 10.5)
    matplotlib.rcParams.update({
        "font.family": "serif" if paper else "sans-serif",
        "font.serif": FONT_SERIF,
        "font.sans-serif": FONT_SANS,
        "mathtext.fontset": "stix" if paper else "dejavusans",
        "font.size": 9.5 if not paper else 7.5,
        "axes.titlesize": title,
        "axes.titleweight": "normal",
        "axes.labelsize": label,
        "xtick.labelsize": tick,
        "ytick.labelsize": tick,
        "legend.fontsize": legend,
        "figure.titlesize": title + 1,
        "axes.edgecolor": "black",
        "axes.linewidth": 0.7 if paper else 0.8,
        "axes.labelcolor": "black",
        "axes.axisbelow": True,
        "axes.grid": False,
        "axes.spines.top": True,
        "axes.spines.right": True,
        "xtick.color": "black",
        "ytick.color": "black",
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.top": False,
        "xtick.bottom": True,
        "ytick.right": False,
        "ytick.left": True,
        "xtick.minor.visible": False,    # log axes still draw their own minor ticks
        "ytick.minor.visible": False,
        "xtick.major.width": 0.7 if paper else 1.1,    # clear tick mark at every labelled number
        "ytick.major.width": 0.7 if paper else 1.1,
        "xtick.major.size": 3.5 if paper else 6.0,
        "ytick.major.size": 3.5 if paper else 6.0,
        "xtick.minor.width": 0.6 if paper else 0.8,
        "ytick.minor.width": 0.6 if paper else 0.8,
        "xtick.minor.size": 2.0 if paper else 3.5,
        "ytick.minor.size": 2.0 if paper else 3.5,
        "xtick.major.pad": 3.5,
        "ytick.major.pad": 3.5,
        "lines.linewidth": LINE_WIDTH,
        "lines.markersize": MARKER_SIZE,
        "legend.frameon": True,
        "legend.fancybox": False,
        "legend.framealpha": 0.9,
        "legend.edgecolor": "#c8c8c8",
        "legend.borderpad": 0.4,
        "legend.labelspacing": 0.3,
        "legend.handlelength": 2.4,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.unicode_minus": True,
        "pdf.fonttype": 42,              # embed TrueType fonts (conference requires all fonts embedded)
        "ps.fonttype": 42,
    })


def apply_style():
    """Back-compat name used by every chart script: the non-paper clean style."""
    apply_clean_style(paper=False)


def is_paper():
    return _PAPER


def style_for_series(index):
    """(color, linestyle, marker) for the index-th series of a generic chart. Colour from the tab10 cycle, plus a
    linestyle and a marker, so no two of the first 60 series share the full triple and each stays readable in
    grayscale. Boards and circuits do NOT use this: they have fixed styles (BOARD_* / CIRCUIT_*) that are the same in
    every chart."""
    i = int(index)
    return (_TAB10[i % len(_TAB10)], _SERIES_LINESTYLES[i % len(_SERIES_LINESTYLES)],
            _SERIES_MARKERS[i % len(_SERIES_MARKERS)])


def board_style(board):
    """(color, linestyle, marker) of a board, the same in every chart."""
    return BOARD_COLOR[board], BOARD_LINESTYLE[board], BOARD_MARKER[board]


def circuit_style(circuit):
    """(color, linestyle, marker) of a circuit (grey ink), the same in every chart."""
    return CIRCUIT_INK[circuit], CIRCUIT_LINESTYLE[circuit], CIRCUIT_MARKER[circuit]


def all_fixed_styles():
    """{name: (linestyle, marker)} of every board and circuit (names prefixed board:/circuit:)."""
    out = {f"board:{b}": (BOARD_LINESTYLE[b], BOARD_MARKER[b]) for b in BOARD_ORDER}
    out.update({f"circuit:{c}": (CIRCUIT_LINESTYLE[c], CIRCUIT_MARKER[c]) for c in CIRCUIT_ORDER})
    return out


class EveryIntegerLocator:
    """Tick (and label) at EVERY integer while the axis spans <= 24 of them, then every 2nd/3rd/... so labels stay
    readable. Qubit counts are small integers, so each n gets its own tick mark."""

    def __init__(self):
        self.axis = None

    def set_axis(self, axis):
        self.axis = axis

    def __call__(self):
        lo, hi = self.axis.get_view_interval()
        return self.tick_values(lo, hi)

    def tick_values(self, vmin, vmax):
        import math
        import numpy as np
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        step = max(1, math.ceil((vmax - vmin) / 24))
        first = math.ceil(vmin / step) * step
        return np.arange(first, vmax + 1e-9, step)

    def view_limits(self, vmin, vmax):
        return vmin, vmax

    def nonsingular(self, vmin, vmax):
        return (vmin - 1, vmax + 1) if vmin == vmax else (vmin, vmax)

    def raise_if_exceeds(self, locs):
        return locs


def plain_number_formatter():
    """Tick labels as plain numbers with a real minus sign (1, 10, -100, 0.1), for symlog axes where 10^k with a
    leading minus is hard to read."""
    from matplotlib.ticker import FuncFormatter

    def fmt(v, _pos):
        if v == 0:
            return "0"
        s = f"{abs(v):g}"
        return ("\u2212" if v < 0 else "") + s

    return FuncFormatter(fmt)


def style_axes(ax, log_y=False, integer_x=True):
    """Every integer x gets its own tick + label (qubit counts) and, for log_y, a log y axis. No grid (clean style).
    Kept under the old name so every existing script gets the clean look without edits."""
    from matplotlib.ticker import Locator

    if log_y:
        ax.set_yscale("log")
    ax.grid(False)
    ax.set_axisbelow(True)
    if integer_x:
        class _Loc(EveryIntegerLocator, Locator):
            pass
        ax.xaxis.set_major_locator(_Loc())


def add_panel_label(ax, text, inside=False):
    """Panel label such as "(a)": centred below the panel (under the x label) by default, or inside the top-left
    corner with inside=True."""
    if inside:
        return ax.text(0.03, 0.96, text, transform=ax.transAxes, ha="left", va="top", fontsize=8 if _PAPER else 9)
    return ax.annotate(text, xy=(0.5, 0.0), xycoords="axes fraction", xytext=(0, -(30 if _PAPER else 36)),
                       textcoords="offset points", ha="center", va="top", fontsize=8 if _PAPER else 9.5)


def iqr_band(ax, xs, q1, q3, color, alpha=None, half_width=0.18, **kw):
    """Light shaded IQR band (25th-75th percentile over the reps) behind a median line. q1/q3 entries that are None
    (a point with a single value, so no IQR) get NO band. Neighbouring points with an IQR are joined; an isolated
    one gets a narrow patch of width 2*half_width in x so it is still visible. Returns the number of band pieces."""
    alpha = BAND_ALPHA if alpha is None else alpha
    run = []
    pieces = 0

    def flush():
        nonlocal run, pieces
        if not run:
            return
        if len(run) == 1:
            x, lo, hi = run[0]
            ax.fill_between([x - half_width, x + half_width], [lo, lo], [hi, hi], color=color, alpha=alpha,
                            linewidth=0, zorder=kw.get("zorder", 2))
        else:
            ax.fill_between([r[0] for r in run], [r[1] for r in run], [r[2] for r in run], color=color,
                            alpha=alpha, linewidth=0, zorder=kw.get("zorder", 2))
        pieces += 1
        run = []

    for x, lo, hi in zip(xs, q1, q3):
        if lo is None or hi is None:
            flush()
        else:
            run.append((x, lo, hi))
    flush()
    return pieces


def git_tag():
    """Short git tag/commit of the code that drew the chart ('+' suffix = uncommitted changes), or 'commit unknown'."""
    import subprocess

    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty=+"], cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True, timeout=10, check=True)
        return out.stdout.strip() or "commit unknown"
    except Exception:  # noqa: BLE001 - a chart must never fail because git is missing
        return "commit unknown"


def suptitle(fig, text, tag=False, **kw):
    """Chart title for data/figures PNGs. paper=True figures carry no in-figure title (the caption does)."""
    if _PAPER:
        return None
    return fig.suptitle(f"{text} [{git_tag()}]" if tag else text, **kw)


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


def add_footnote(fig, text, y=-0.005):
    """คำอธิบายสถิติ + ขนาดตัวอย่าง ใต้ figure ชิดขวา (อยู่นอกพื้นที่พล็อต ไม่บังข้อมูล
    — savefig(bbox_inches='tight') ขยายขอบภาพให้ครอบข้อความนี้เอง)"""
    if _PAPER:
        return None   # the paper caption carries the statistics note
    fig.text(0.995, y, text, ha="right", va="top", fontsize=8.5, color=INK_SECONDARY)


PAPER_PNG_DPI = 600
_FORBIDDEN_DIRS = (("data", "raw"), ("data", "archive"))
_PNG_META = {"Software": None}                       # matplotlib would write "Software: Matplotlib version ..."
_PDF_META = {"Creator": None, "Producer": None, "CreationDate": None, "Title": None, "Author": None,
             "Subject": None, "Keywords": None}      # nothing identifying in a paper PDF


def _check_output_path(path, suffix):
    path = Path(path)
    if path.suffix.lower() != suffix:
        raise ValueError(f"only {suffix} output is allowed here, got {path.name}")
    parts = path.resolve().parts
    for forbidden in _FORBIDDEN_DIRS:
        for i in range(len(parts) - 1):
            if parts[i:i + 2] == forbidden:
                raise ValueError(f"refusing to write under {'/'.join(forbidden)}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def remove_minor_ticks(fig):
    """No minor tick marks anywhere (log axes draw them by default): only the labelled major ticks remain."""
    for ax in fig.axes:
        for a in [ax] + list(ax.child_axes):      # child_axes: secondary x / y axes
            a.minorticks_off()


def save_png(fig, path, dpi=None, close=True):
    """Save a PNG (never SVG): 300 dpi for data/figures/, 600 dpi in paper mode. Refuses the raw-data and archived-data trees.
    No Software metadata. Returns the path."""
    import matplotlib.pyplot as plt

    path = _check_output_path(path, ".png")
    remove_minor_ticks(fig)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, dpi=dpi or (PAPER_PNG_DPI if _PAPER else RASTER_DPI),
                metadata=_PNG_META)
    print(f"figure -> {path}")
    if close:
        plt.close(fig)
    return path


def save_pdf(fig, path, close=True):
    """Vector PDF for paper figures: TrueType fonts embedded (pdf.fonttype 42), no Creator/Producer/date metadata.
    Refuses the raw-data and archived-data trees. Returns the path."""
    import matplotlib.pyplot as plt

    path = _check_output_path(path, ".pdf")
    remove_minor_ticks(fig)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02, format="pdf", metadata=_PDF_META)
    print(f"figure -> {path}")
    if close:
        plt.close(fig)
    return path


def save_figure_png_only(fig, out_dir: Path, stem: str):
    """<out_dir>/<stem>.png only (data/figures/ is PNG-only). Same call signature as before."""
    return [save_png(fig, Path(out_dir) / f"{stem}.png")]


def save_figure(fig, out_dir: Path, stem: str):
    """Kept for old callers: now PNG only as well (no SVG anywhere)."""
    return save_figure_png_only(fig, out_dir, stem)


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
