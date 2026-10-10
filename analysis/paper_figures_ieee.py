#!/usr/bin/env python3
# paper_figures_ieee.py
# IEEE two-column paper figures (DRAFT) made only from data on disk; reads data/raw read-only.
#   fig1  per-rep micros() execution time vs n, one panel per board, one line per circuit,
#         median + IQR (25th-75th percentile) over the recorded reps, every rep as a faint dot.
#   fig2  micros() minus ESP32-counter pulse width per point (signed, us and %), per board and circuit,
#         median + IQR over the paired reps. Only points whose reference came from the physical counter.
#
# Inputs : data/raw/phase2/<board>/<circuit>/with_ref/{raw,memory_wall}.csv        (fig1)
#          data/raw/phase2/<board>/<circuit>/with_ref/ref/{ref_compare,ref_compare_points}.csv and
#          .../with_ref/env/*.ref.json                                              (fig2)
# Outputs: paper/figures/<stem>_DRAFT.{pdf,png}  (PDF vector, fonts embedded, metadata stripped; PNG 600 dpi)
#          Never writes under data/raw. No SVG.
# Run    : .venv/bin/python analysis/paper_figures_ieee.py [--raw DIR] [--out DIR] [--only fig1|fig2]
#          .venv/bin/python analysis/paper_figures_ieee.py --synthetic-layout-test   (temp dir, watermarked)

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

DEFAULT_RAW = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "paper" / "figures"
SINGLE_COL_IN, DOUBLE_COL_IN = 3.5, 7.16
FULL_REPS = 100
MIN_PAIRS = 10                                           # fewer paired reps: no median/IQR drawn, point listed instead
WALL_STATUSES = ("malloc_failed", "build_overflow")      # positive evidence of a memory wall
TIME_LIMITED_STATUS = "skipped_compute_infeasible"       # not run: one rep would exceed the per-point time cap
JOINED_STATUSES = ("ok", "anomaly", "count_mismatch")    # ref_compare_points statuses that still carry paired reps
RAW_COLS = ["board", "circuit", "n", "rep", "exec_time_us"]
WALL_COLS = ["board", "circuit", "n", "status"]
COMPARE_COLS = ["board", "circuit", "n", "rep", "micros_us", "counter_us", "diff_us", "diff_pct"]
COMPARE_POINT_COLS = ["board", "circuit", "n", "n_pairs", "ref_status"]
SERIF = ["Times New Roman", "Times", "Nimbus Roman", "Liberation Serif", "STIXGeneral", "DejaVu Serif"]


class DataError(Exception):
    """Input data missing a column, inconsistent, or unfit to plot. Nothing is plotted around it."""


# ----------------------------------------------------------------------------- style

def apply_ieee_style():
    ps.apply_style()
    matplotlib.rcParams.update({
        "font.family": "serif",
        "font.serif": SERIF,
        "mathtext.fontset": "stix",
        "font.size": 7.5,
        "axes.titlesize": 8,
        "axes.labelsize": 7.5,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.minor.width": 0.4,
        "ytick.minor.width": 0.4,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.6,
        "pdf.fonttype": 42,      # embed TrueType fonts (conference requires all fonts embedded)
        "ps.fonttype": 42,
        "axes.unicode_minus": True,
    })


# ----------------------------------------------------------------------------- guards / io

def assert_not_raw(path, raw_root):
    """Never write under the raw data tree."""
    p, r = Path(path).resolve(), Path(raw_root).resolve()
    if p == r or r in p.parents:
        raise DataError(f"refusing to write under the raw data tree: {p}")


def need_columns(df, cols, what):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise DataError(f"{what}: missing column(s) {missing}")


def read_csv(path, cols, what):
    path = Path(path)
    if not path.exists():
        raise DataError(f"{what}: file not found")
    df = pd.read_csv(path)
    need_columns(df, cols, what)
    return df


def point_dir(raw_root, phase, board, circuit):
    return Path(raw_root) / phase / board / circuit / "with_ref"


def iqr(values):
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return None
    return float(np.percentile(v, 25)), float(np.percentile(v, 75))


# ----------------------------------------------------------------------------- fig 1 data

def load_exec_time(raw_root, boards=ps.BOARD_ORDER, circuits=ps.CIRCUIT_ORDER):
    """{(board, circuit): {"points": DataFrame[n, kind, reps, med, q1, q3, values], "events": DataFrame[n, kind]}}.
    kind of a drawn point: 'full' (100 reps) or 'partial' (time-capped, < 100 reps).
    kind of an event: 'wall' (recorded build_overflow / malloc_failed) or 'time_limited' (not run)."""
    out = {}
    for board in boards:
        for circuit in circuits:
            d = point_dir(raw_root, "phase2", board, circuit)
            what = f"{board}/{circuit}"
            if not (d / "raw.csv").exists():
                continue
            raw = read_csv(d / "raw.csv", RAW_COLS, f"{what} raw.csv")
            wall = read_csv(d / "memory_wall.csv", WALL_COLS, f"{what} memory_wall.csv")
            if (raw.exec_time_us <= 0).any():
                raise DataError(f"{what}: non-positive exec_time_us cannot be drawn on a log axis")
            if raw.duplicated(["n", "rep"]).any():
                raise DataError(f"{what}: duplicate (n, rep) rows in raw.csv")
            if wall.duplicated(["n"]).any():
                raise DataError(f"{what}: duplicate n in memory_wall.csv")
            status = dict(zip(wall.n, wall.status))
            unknown = sorted(set(raw.n) - set(status))
            if unknown:
                raise DataError(f"{what}: raw rows for n={unknown} have no memory_wall.csv row")
            pts, ev = [], []
            for n, g in raw.groupby("n"):
                if status[n] != "ok":
                    raise DataError(f"{what}: raw rows exist for n={n} but its recorded status is {status[n]!r}")
                v = g.exec_time_us.to_numpy(dtype=float)
                q = iqr(v)
                pts.append(dict(n=int(n), kind="full" if len(v) == FULL_REPS else "partial", reps=len(v),
                                med=float(np.median(v)), q1=q[0] if q else None, q3=q[1] if q else None, values=v))
            for n, s in status.items():
                if s == "ok" and n not in set(raw.n):
                    raise DataError(f"{what}: n={n} is recorded ok but has no raw rows")
                if s in WALL_STATUSES:
                    ev.append(dict(n=int(n), kind="wall"))
                elif s == TIME_LIMITED_STATUS:
                    ev.append(dict(n=int(n), kind="time_limited"))
            out[(board, circuit)] = dict(points=pd.DataFrame(pts).sort_values("n").reset_index(drop=True),
                                         events=pd.DataFrame(ev, columns=["n", "kind"]).sort_values("n"))
    if not out:
        raise DataError("no phase 2 data found")
    return out


def _fmt_sym(v, _pos):
    if v == 0:
        return "0"
    k = np.log10(abs(v))
    if abs(v) >= 1e4 and abs(k - round(k)) < 1e-9:
        return ("$-$" if v < 0 else "") + f"$10^{{{int(round(k))}}}$"
    return f"{v:g}".replace("-", "\u2212")


def _fmt_us(v, _pos):
    return f"$10^{{{int(round(np.log10(v)))}}}$" if v > 0 and abs(np.log10(v) - round(np.log10(v))) < 1e-9 else ""


def plot_exec_time(data, boards=ps.BOARD_ORDER, circuits=ps.CIRCUIT_ORDER, watermark=None):
    apply_ieee_style()
    fig, axes = plt.subplots(1, len(boards), figsize=(DOUBLE_COL_IN, 2.55), sharey=True)
    axes = np.atleast_1d(axes)
    allv = [v for it in data.values() for v in it["points"]["values"]]
    ymin, ymax = min(float(v.min()) for v in allv), max(float(v.max()) for v in allv)
    lo, hi = 10 ** np.floor(np.log10(ymin)), 10 ** np.ceil(np.log10(ymax))
    strip_top = hi * 10 ** 1.7                      # headroom for the wall / time-limited strip
    for ax, board in zip(axes, boards):
        ax.set_title(ps.BOARD_SHORT[board])
        for ci, circuit in enumerate(circuits):
            item = data.get((board, circuit))
            if item is None:
                continue
            pts, ev = item["points"], item["events"]
            ink, ls, mk = ps.CIRCUIT_INK[circuit], ps.CIRCUIT_LINESTYLE[circuit], ps.CIRCUIT_MARKER[circuit]
            for r in pts.itertuples():
                ax.plot(np.full(len(r.values), r.n), r.values, ls="none", marker="o", ms=1.1, mfc="#8c8c8c",
                        mec="none", alpha=0.22, zorder=1, rasterized=True)
            ax.plot(pts.n, pts.med, ls=ls, color=ink, lw=0.9, zorder=2)
            full, part = pts[pts.kind == "full"], pts[pts.kind == "partial"]
            ax.plot(full.n, full.med, ls="none", marker=mk, color=ink, mfc=ink, mec=ink, zorder=3)
            ax.plot(part.n, part.med, ls="none", marker=mk, color=ink, mfc="white", mec=ink, mew=0.9, zorder=3)
            for r in pts.itertuples():
                if pd.notna(r.q1):
                    ax.plot([r.n, r.n], [r.q1, r.q3], color=ink, lw=1.1, solid_capstyle="butt", zorder=2)
                    for y in (r.q1, r.q3):
                        ax.plot([r.n - 0.12, r.n + 0.12], [y, y], color=ink, lw=0.8, zorder=2)
            ys = strip_top * 10 ** (-0.38 * (ci + 0.5))
            for e in ev.itertuples():
                if e.kind == "wall":
                    ax.plot(e.n, ys, ls="none", marker="X", ms=4.6, color="black", mec="white", mew=0.3, zorder=4)
                else:
                    ax.plot(e.n, ys, ls="none", marker="*", ms=5.6, mfc="white", mec="black", mew=0.7, zorder=4)
        ax.set_yscale("log")
        ax.set_ylim(lo, strip_top)
        xs = [x for (b, _c), it in data.items() if b == board for x in list(it["points"].n) + list(it["events"].n)]
        ax.set_xlim(min(xs) - 0.6, max(xs) + 0.6)
        ps.style_axes(ax, log_y=True)
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(FixedLocator([10.0 ** k for k in range(int(np.log10(lo)), int(np.log10(hi)) + 1)]))
        ax.yaxis.set_major_formatter(FuncFormatter(_fmt_us))
        ax.axhline(hi, color="#bbbbbb", lw=0.4, ls="-", zorder=0)   # separates data from the event strip
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_xlabel("Number of qubits $n$")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("Time per rep ($\\mu$s)")
    handles = [Line2D([], [], ls=ps.CIRCUIT_LINESTYLE[c], marker=ps.CIRCUIT_MARKER[c], color=ps.CIRCUIT_INK[c],
                      mfc=ps.CIRCUIT_INK[c], label=c.replace("_", " "))
               for c in circuits if any(k[1] == c for k in data)]
    handles += [
        Line2D([], [], ls="none", marker="o", mfc="white", mec="black", mew=0.9, label="< 100 reps (time-capped)"),
        Line2D([], [], ls="none", marker="o", ms=2, mfc="#8c8c8c", mec="none", alpha=0.5, label="individual rep"),
        Line2D([], [], ls="none", marker="X", ms=4.6, color="black", label="memory wall (recorded)"),
        Line2D([], [], ls="none", marker="*", ms=5.6, mfc="white", mec="black", mew=0.7, label="time-limited, not run"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles) if len(handles) <= 5 else 4, frameon=False,
               bbox_to_anchor=(0.5, -0.02), columnspacing=1.2, handlelength=2.2)
    fig.tight_layout(rect=(0, 0.13, 1, 1), w_pad=0.6)
    if watermark:
        _watermark(fig, watermark)
    return fig


def _watermark(fig, text):
    fig.text(0.5, 0.5, text, ha="center", va="center", fontsize=15, color="#cc0000", alpha=0.55, rotation=18,
             weight="bold", zorder=100)


# ----------------------------------------------------------------------------- fig 2 data

def physical_counter_sessions(point_directory):
    """True only if every session sidecar of this point directory names a real transport (not the simulator)
    and carries a counter firmware hash. The simulator is only reachable from tests (port 'SIM')."""
    sidecars = sorted((Path(point_directory) / "env").glob("*.ref.json"))
    if not sidecars:
        return False, "no counter sidecar (env/*.ref.json)"
    for s in sidecars:
        j = json.loads(s.read_text())
        port = str(j.get("counter_port", ""))
        if not port or port.upper().startswith("SIM"):
            return False, f"counter_port {port!r}"
        if not j.get("counter_fw_sha256"):
            return False, "empty counter firmware hash"
    return True, ""


def load_counter_diff(raw_root, boards=ps.BOARD_ORDER, circuits=ps.CIRCUIT_ORDER):
    """{(board, circuit): DataFrame[n, ref_status, reps, med_us, q1_us, q3_us, med_pct, q1_pct, q3_pct, us, pct]}
    and a list of (board, circuit, reason) groups that were left out."""
    out, skipped = {}, []
    for board in boards:
        for circuit in circuits:
            d = point_dir(raw_root, "phase2", board, circuit)
            if not (d / "ref" / "ref_compare.csv").exists():
                continue
            what = f"{board}/{circuit}"
            okc, why = physical_counter_sessions(d)
            if not okc:
                skipped.append((board, circuit, why))
                continue
            cmp_ = read_csv(d / "ref" / "ref_compare.csv", COMPARE_COLS, f"{what} ref_compare.csv")
            pts = read_csv(d / "ref" / "ref_compare_points.csv", COMPARE_POINT_COLS, f"{what} ref_compare_points.csv")
            if cmp_.duplicated(["n", "rep"]).any():
                raise DataError(f"{what}: duplicate (n, rep) in ref_compare.csv")
            bad = (cmp_.micros_us - cmp_.counter_us - cmp_.diff_us).abs().max()
            if bad > 1e-3:
                raise DataError(f"{what}: diff_us != micros_us - counter_us (max deviation {bad:.4g})")
            status = dict(zip(pts.n, pts.ref_status))
            rows = []
            for n, g in cmp_.groupby("n"):
                st = status.get(n)
                if st not in JOINED_STATUSES:
                    continue
                if len(g) < MIN_PAIRS:
                    skipped.append((board, circuit, f"n={n}: only {len(g)} paired rep(s)"))
                    continue
                us, pct = g.diff_us.to_numpy(float), g.diff_pct.to_numpy(float)
                qu, qp = iqr(us), iqr(pct)
                rows.append(dict(n=int(n), ref_status=st, reps=len(g), med_us=float(np.median(us)),
                                 q1_us=qu[0] if qu else None, q3_us=qu[1] if qu else None,
                                 med_pct=float(np.median(pct)), q1_pct=qp[0] if qp else None,
                                 q3_pct=qp[1] if qp else None, us=us, pct=pct))
            if rows:
                out[(board, circuit)] = pd.DataFrame(rows).sort_values("n").reset_index(drop=True)
    if not out:
        raise DataError("no paired micros()/counter data from a physical counter session")
    return out, skipped


def plot_counter_diff(data, boards=ps.BOARD_ORDER, circuits=ps.CIRCUIT_ORDER, watermark=None):
    apply_ieee_style()
    fig, axes = plt.subplots(2, len(boards), figsize=(DOUBLE_COL_IN, 4.1), sharex="col")
    dodge = {c: (i - (len(circuits) - 1) / 2) * 0.1 for i, c in enumerate(circuits)}
    for ci_b, board in enumerate(boards):
        for row, (unit, key, lin) in enumerate((("us", "us", 1.0), ("pct", "pct", 0.1))):
            ax = axes[row, ci_b]
            for circuit in circuits:
                df = data.get((board, circuit))
                if df is None:
                    continue
                ink, ls, mk = ps.CIRCUIT_INK[circuit], ps.CIRCUIT_LINESTYLE[circuit], ps.CIRCUIT_MARKER[circuit]
                x = df.n + dodge[circuit]
                for r, xx in zip(df.itertuples(), x):
                    ax.plot(np.full(len(getattr(r, key)), xx), getattr(r, key), ls="none", marker="o", ms=0.9,
                            mfc="#8c8c8c", mec="none", alpha=0.2, zorder=1, rasterized=True)
                ax.plot(x, df[f"med_{unit}"], ls=ls, color=ink, lw=0.9, zorder=2)
                full = df.ref_status == "ok"
                ax.plot(x[full], df[f"med_{unit}"][full], ls="none", marker=mk, color=ink, mfc=ink, zorder=3)
                ax.plot(x[~full], df[f"med_{unit}"][~full], ls="none", marker=mk, color=ink, mfc="white", mew=0.9,
                        zorder=3)
                for r, xx in zip(df.itertuples(), x):
                    q1, q3 = getattr(r, f"q1_{unit}"), getattr(r, f"q3_{unit}")
                    if pd.notna(q1):
                        ax.plot([xx, xx], [q1, q3], color=ink, lw=1.1, solid_capstyle="butt", zorder=2)
            ax.axhline(0, color="#999999", lw=0.5, zorder=0)
            ax.set_yscale("symlog", linthresh=lin, linscale=0.6)
            ax.yaxis.set_major_formatter(FuncFormatter(_fmt_sym))
            ax.grid(True, which="major", color=ps.GRID_COLOR, lw=0.5)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            if row == 0:
                ax.set_title(ps.BOARD_SHORT[board])
            if row == 1:
                ax.set_xlabel("Number of qubits $n$")
            if ci_b == 0:
                ax.set_ylabel("micros() $-$ counter ($\\mu$s)" if unit == "us" else "micros() $-$ counter (%)")
    handles = [Line2D([], [], ls=ps.CIRCUIT_LINESTYLE[c], marker=ps.CIRCUIT_MARKER[c], color=ps.CIRCUIT_INK[c],
                      label=c.replace("_", " ")) for c in circuits if any(k[1] == c for k in data)]
    handles += [
        Line2D([], [], ls="none", marker="o", color="black", label="counter status ok"),
        Line2D([], [], ls="none", marker="o", mfc="white", mec="black", mew=0.9, label="counter flagged (anomaly)"),
        Line2D([], [], ls="none", marker="o", ms=2, mfc="#8c8c8c", mec="none", alpha=0.5, label="individual rep"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.01),
               columnspacing=1.2, handlelength=2.2)
    fig.tight_layout(rect=(0, 0.1, 1, 1), w_pad=0.6, h_pad=0.6)
    if watermark:
        _watermark(fig, watermark)
    return fig


# ----------------------------------------------------------------------------- output

NO_META_PDF = {"Creator": None, "Producer": None, "CreationDate": None, "Title": None, "Author": None,
               "Subject": None, "Keywords": None}
NO_META_PNG = {"Software": None}


def save(fig, out_dir, stem, raw_root=DEFAULT_RAW):
    """PDF (vector, fonts embedded) + 600 dpi PNG, metadata stripped. Refuses to write under the raw tree."""
    out_dir = Path(out_dir)
    assert_not_raw(out_dir, raw_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext, kw in (("pdf", {"metadata": NO_META_PDF}), ("png", {"dpi": 600, "metadata": NO_META_PNG})):
        p = out_dir / f"{stem}.{ext}"
        fig.savefig(p, bbox_inches="tight", pad_inches=0.03, **kw)
        paths.append(p)
    plt.close(fig)
    return paths


# ----------------------------------------------------------------------------- synthetic layout test

def make_synthetic(root, seed=7):
    """Clearly fake data in the real on-disk layout (never real measurements)."""
    rng = np.random.default_rng(seed)
    root = Path(root)
    walls = {"uno": 8, "esp8266": 13, "esp32": 14}
    scale = {"uno": 40.0, "esp8266": 6.0, "esp32": 1.5}
    for board in ps.BOARD_ORDER:
        for circuit in ps.CIRCUIT_ORDER:
            d = point_dir(root, "phase2", board, circuit)
            (d / "ref").mkdir(parents=True)
            (d / "env").mkdir(parents=True)
            (d / "env" / "s.ref.json").write_text(json.dumps({"counter_port": "tcp:0", "counter_fw_sha256": "00"}))
            rows, wall, cmp_rows, cmp_pts = [], [], [], []
            top = walls[board] - 1 if circuit != "grover" else walls[board] - 3
            for n in range(2, walls[board] + 1):
                if n <= top:
                    reps = 100 if n < top else 12
                    base = scale[board] * (2 ** n) * (3 if circuit == "grover" else 1) * (n if circuit == "qft" else 1)
                    vals = base * (1 + 0.04 * rng.standard_normal(reps)) + 1
                    for r, v in enumerate(vals):
                        rows.append(dict(board=board, circuit=circuit, n=n, rep=r, exec_time_us=int(max(v, 1))))
                    wall.append(dict(board=board, circuit=circuit, n=n, status="ok"))
                    diff = rng.normal(-0.01 * base, 0.003 * base + 0.5, reps)
                    for r, v in enumerate(vals):
                        cmp_rows.append(dict(board=board, circuit=circuit, n=n, rep=r, micros_us=int(max(v, 1)),
                                             counter_us=int(max(v, 1)) - diff[r], diff_us=diff[r],
                                             diff_pct=100 * diff[r] / max(v, 1)))
                    cmp_pts.append(dict(board=board, circuit=circuit, n=n, n_pairs=reps,
                                        ref_status="ok" if n % 3 else "anomaly"))
                elif circuit == "grover" and n < walls[board]:
                    wall.append(dict(board=board, circuit=circuit, n=n, status=TIME_LIMITED_STATUS))
                else:
                    wall.append(dict(board=board, circuit=circuit, n=n, status="malloc_failed"))
            pd.DataFrame(rows).to_csv(d / "raw.csv", index=False)
            pd.DataFrame(wall).to_csv(d / "memory_wall.csv", index=False)
            pd.DataFrame(cmp_rows).to_csv(d / "ref" / "ref_compare.csv", index=False)
            pd.DataFrame(cmp_pts).to_csv(d / "ref" / "ref_compare_points.csv", index=False)


# ----------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="IEEE paper figures (DRAFT) from data/raw")
    ap.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="raw data root (read only)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (never under --raw)")
    ap.add_argument("--only", choices=("fig1", "fig2"))
    ap.add_argument("--synthetic-layout-test", action="store_true",
                    help="draw both figures from fake data in a temp dir, watermarked, outside paper/figures/")
    a = ap.parse_args(argv)
    if a.synthetic_layout_test:
        tmp = Path(tempfile.mkdtemp(prefix="synthetic_layout_"))
        make_synthetic(tmp / "raw")
        wm = "SYNTHETIC - LAYOUT TEST ONLY"
        f1 = save(plot_exec_time(load_exec_time(tmp / "raw"), watermark=wm), tmp / "out", "synthetic_fig1", tmp / "raw")
        d, _ = load_counter_diff(tmp / "raw")
        f2 = save(plot_counter_diff(d, watermark=wm), tmp / "out", "synthetic_fig2", tmp / "raw")
        print("\n".join(str(p) for p in f1 + f2))
        return 0
    written = []
    try:
        if a.only in (None, "fig1"):
            data = load_exec_time(a.raw)
            written += save(plot_exec_time(data), a.out, "fig1_exec_time_vs_n_DRAFT", a.raw)
            for (b, c), it in data.items():
                p = it["points"]
                print(f"fig1 {b}/{c}: {len(p)} points ({(p.kind == 'full').sum()} with 100 reps, "
                      f"{(p.kind == 'partial').sum()} time-capped), events: "
                      f"{it['events'].values.tolist()}")
        if a.only in (None, "fig2"):
            data, skipped = load_counter_diff(a.raw)
            written += save(plot_counter_diff(data), a.out, "fig2_micros_minus_counter_DRAFT", a.raw)
            for b, c, why in skipped:
                print(f"fig2 excluded {b}/{c}: {why}")
            for (b, c), df in data.items():
                print(f"fig2 {b}/{c}: {len(df)} points ({(df.ref_status == 'ok').sum()} counter ok, "
                      f"{(df.ref_status != 'ok').sum()} flagged)")
    except DataError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print("\n".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
