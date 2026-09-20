#!/usr/bin/env python3
# phase2_uno_run_plots.py
#
# Per-run diagnostic plots for the Uno Phase 2 REPS=100 collection, generated
# once per algorithm right after that algorithm's sweep finishes (see the
# "GRAPHS" standing rule, run_log.md 2026-09-20). This is a separate tool from
# analysis/phase2_plot.py on purpose, not a "smallest possible addition" to
# it: phase2_plot.py answers a different question (the final cross-board,
# cross-circuit comparison, built from data/processed/phase2/summary.csv
# after every board is done) with a different output tree
# (data/figures/phase2/). These plots answer "what just happened in this one
# algorithm's run, on this one board" while collection is still in progress,
# need data/raw/phase2/*_raw.csv (per-rep, for the model overlay and warm-up
# exclusion), *_memory_wall.csv (per-point outcome + evidence), AND
# data/raw/telemetry/points.csv (per-attempt compile/upload time and retry
# counts) all three together -- phase2_plot.py touches only the first two,
# pre-aggregated, and never per-attempt. Forcing this into phase2_plot.py
# would mean two incompatible calling conventions (once-at-the-end vs
# once-per-algorithm) and two incompatible output trees in one file.
#
# Read-only against data/raw/ -- every function here only ever opens raw/
# telemetry files for reading. Output: figures/phase2/<board>/*.png (+ .svg,
# via pc/shared/plot_style.save_figure's house convention) and nothing else.
#
# ใช้:
#   .venv/bin/python analysis/phase2_uno_run_plots.py --board uno --circuit h_all
# (สร้างกราฟ 3 อันของ h_all + กราฟสะสม all_algorithms_so_far ใหม่ทั้งหมด)

import argparse
import csv
import glob
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402
from shared import resume as rs  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared.telemetry import is_warmup  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw" / "phase2"
TELEMETRY_DIR = REPO_ROOT / "data" / "raw" / "telemetry"
FIGURES_ROOT = REPO_ROOT / "figures" / "phase2"

SUBTITLE = "Uno R3, Phase 2, micros() timing (no Logic Analyzer data)"


def _board_sram_bytes(board):
    return {"uno": 2048, "esp8266": 81920, "esp32": 327680}[board]


def load_raw(board, circuit):
    path = RAW_DIR / f"{board}_raw.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if r["circuit"] == circuit]


def load_wall(board, circuit=None):
    path = RAW_DIR / f"{board}_memory_wall.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if circuit is None or r["circuit"] == circuit]


def load_points(board, circuit):
    path = TELEMETRY_DIR / "points.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if r["board"] == board and r["circuit"] == circuit]


def collection_commit(board, circuit):
    """git commit these points were collected under, per data/raw/telemetry/
    sessions.csv -- more accurate than the script's own current HEAD, which
    may have moved on by the time this is run."""
    path = TELEMETRY_DIR / "sessions.csv"
    if not path.exists():
        return "unknown"
    commit = "unknown"
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["board"] != board:
                continue
            if circuit in r["circuits"].split(";"):
                commit = r["git_commit"][:12] or commit
    return commit


def current_head():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _title(board, circuit, extra, commit_note):
    return (f"{ps.BOARD_LABEL[board]} -- {ps.CIRCUIT_LABEL.get(circuit, circuit)} -- "
            f"{extra} (REPS={tm.REPS}, {commit_note})")


def _finish(fig, ax_or_axes, board, circuit, title_extra, commit_note):
    fig.suptitle(_title(board, circuit, title_extra, commit_note))
    axes = ax_or_axes if isinstance(ax_or_axes, (list, tuple, np.ndarray)) else [ax_or_axes]
    axes = list(np.ravel(axes))
    axes[0].text(0.0, 1.10, SUBTITLE, transform=axes[0].transAxes,
                 fontsize=8.5, color=ps.INK_SECONDARY, ha="left")


def plot_exec_time_vs_n(board, circuit):
    """1. Per-rep execution time vs n: median + IQR from the raw trials of
    each ok point (warm-up reps excluded per telemetry.is_warmup), log y,
    with the timing_model per-rep estimate overlaid as its own series."""
    raw = load_raw(board, circuit)
    wall = load_wall(board, circuit)
    ok_ns = sorted({int(r["n"]) for r in wall if r["status"] == "ok"})
    if not ok_ns:
        print(f"[{circuit}] no ok points -- skipping exec_time_vs_n")
        return None

    ns, medians, q1s, q3s, ntrials = [], [], [], [], []
    for n in ok_ns:
        vals = [float(r["exec_time_us"]) for r in raw
                if int(r["n"]) == n and not is_warmup(int(r["rep"]))]
        if not vals:
            continue
        arr = np.array(vals)
        ns.append(n)
        medians.append(float(np.median(arr)))
        q1s.append(float(np.percentile(arr, 25)))
        q3s.append(float(np.percentile(arr, 75)))
        ntrials.append(len(arr))

    model_ns = ok_ns
    model_us = [tm.expected_exec_time_us(board, circuit, n) for n in model_ns]

    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    yerr = [[m - q1 for m, q1 in zip(medians, q1s)], [q3 - m for m, q3 in zip(medians, q3s)]]
    ax.errorbar(ns, medians, yerr=yerr, fmt=ps.BOARD_MARKER[board], color=ps.BOARD_COLOR[board],
                markersize=6, markeredgecolor="white", markeredgewidth=0.7, linewidth=1.8,
                capsize=3, label="measured (median, IQR error bars)", zorder=3)
    ax.plot(model_ns, model_us, linestyle="--", marker="x", color=ps.INK_SECONDARY,
            linewidth=1.3, label="timing_model estimate (expected_exec_time_us)", zorder=2)

    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Execution time per rep (µs, log scale)")
    ax.legend(loc="upper left")

    commit_note = f"commit {collection_commit(board, circuit)}"
    _finish(fig, ax, board, circuit, "per-rep execution time vs n", commit_note)
    ps.add_footnote(fig, ps.reps_phrase(ntrials) + "; error bars = IQR (25th-75th pct).")
    return ps.save_figure(fig, FIGURES_ROOT / board, f"{circuit}_exec_time_vs_n")


def _outcome_category(status):
    if status == "ok":
        return "ok"
    if rs.is_wall_status(status):
        return "wall"
    if status.startswith("runtime_hang_or_reset") or status.startswith("watchdog_suspected"):
        return "hang_no_evidence"
    return "failed"  # build_or_upload_fail, build_timeout, skipped_* never reach here (filtered)


def plot_outcomes_vs_n(board, circuit):
    """2. Point outcomes vs n: ok / failed (upload/build) / wall (positive
    evidence, annotated) / hang-no-evidence (distinct marker, flagged for
    review). Title states what was observed, never just "Memory Wall", so a
    build/upload failure can never be read as a wall from the chart."""
    wall = [r for r in load_wall(board, circuit) if not r["status"].startswith("skipped_")]
    if not wall:
        print(f"[{circuit}] no point-outcome rows -- skipping outcomes_vs_n")
        return None

    cat_style = {
        "ok": dict(marker="o", color="#0072B2", label="ok"),
        "wall": dict(marker="X", color="#D55E00", label="wall (positive RAM evidence)"),
        "hang_no_evidence": dict(marker="^", color="#8c8c8c",
                                  label="hang, no wall evidence, needs review"),
        "failed": dict(marker="s", color="#555555", label="build/upload failure (not a wall)"),
    }

    fig, ax = plt.subplots(figsize=(7, 4.5), layout="constrained")
    seen = set()
    for r in sorted(wall, key=lambda r: int(r["n"])):
        n = int(r["n"])
        cat = _outcome_category(r["status"])
        style = cat_style[cat]
        label = style["label"] if cat not in seen else None
        seen.add(cat)
        ax.scatter([n], [1], marker=style["marker"], color=style["color"], s=110,
                   edgecolor="white", linewidth=0.8, label=label, zorder=3)
        if cat == "wall":
            ram_pct = r.get("compile_ram_pct", "")
            used = r.get("compile_ram_used_bytes", "")
            total = _board_sram_bytes(board)
            ax.annotate(f"compile_ram_pct={ram_pct}%\n{used}/{total} bytes",
                        (n, 1), xytext=(0, 22), textcoords="offset points",
                        ha="center", fontsize=8, color=ps.INK_PRIMARY)

    ax.set_yticks([])
    ax.set_ylim(0.5, 1.7)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ps.style_axes(ax, log_y=False)
    ax.grid(False, axis="y")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2)

    commit_note = f"commit {collection_commit(board, circuit)}"
    _finish(fig, ax, board, circuit, "point outcomes and RAM-overflow wall", commit_note)
    return ps.save_figure(fig, FIGURES_ROOT / board, f"{circuit}_outcomes_vs_n")


def plot_time_per_point(board, circuit):
    """3. Time per point vs n: compile_s + upload_s stacked (summed across
    every attempt for that n, so a retried point's true reflash cost shows),
    with the number of upload attempts annotated per n so retries stay
    visible."""
    pts = load_points(board, circuit)
    # every real attempt has a row -- "retrying" is a non-terminal attempt that still
    # consumed real compile/upload time and must count; only skip_* rows (status
    # skipped_resume/skipped_known_wall/skipped_compute_infeasible/skipped_sim_cost_infeasible,
    # which never touched hardware) are excluded
    pts = [r for r in pts if r["status"] in ("ok", "failed", "retrying")]
    if not pts:
        print(f"[{circuit}] no telemetry points -- skipping time_per_point")
        return None

    by_n = {}
    for r in pts:
        n = int(r["n"])
        d = by_n.setdefault(n, {"compile_s": 0.0, "upload_s": 0.0, "attempts": 0})
        d["compile_s"] += float(r["build_compile_s"] or 0.0)
        d["upload_s"] += float(r["upload_s"] or 0.0)
        d["attempts"] += 1

    ns = sorted(by_n)
    compile_s = [by_n[n]["compile_s"] for n in ns]
    upload_s = [by_n[n]["upload_s"] for n in ns]
    attempts = [by_n[n]["attempts"] for n in ns]

    fig, ax = plt.subplots(figsize=(7, 4.8), layout="constrained")
    ax.bar(ns, compile_s, color=ps.BOARD_COLOR[board], label="compile time (s)", zorder=3)
    ax.bar(ns, upload_s, bottom=compile_s, color=ps.INK_MUTED, label="upload time (s)", zorder=3)
    for n, c, u, a in zip(ns, compile_s, upload_s, attempts):
        label = f"{a} attempt" + ("s" if a != 1 else "")
        ax.annotate(label, (n, c + u), xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=8, color=ps.INK_PRIMARY)

    ps.style_axes(ax, log_y=False)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Time per point, summed across all attempts (s)")
    # headroom for the "N attempts" annotations above the tallest bar, and the legend
    # moved outside the plot area entirely -- with only 2 series the extra vertical
    # space this costs is small, and it can never collide with a bar/annotation
    # regardless of which n ends up tallest (unlike a fixed "upper left"/"upper right")
    ax.set_ylim(0, max(c + u for c, u in zip(compile_s, upload_s)) * 1.18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)

    commit_note = f"commit {collection_commit(board, circuit)}"
    _finish(fig, ax, board, circuit, "reflash time per point (compile+upload, attempts labelled)",
            commit_note)
    return ps.save_figure(fig, FIGURES_ROOT / board, f"{circuit}_time_per_point")


def plot_cumulative(board):
    """4. figures/phase2/<board>/all_algorithms_so_far.png -- median per-rep
    time vs n for every algorithm completed so far on this board, one colour
    per algorithm, wall n marked. Regenerated after each algorithm."""
    wall = load_wall(board)
    circuits = [c for c in ps.CIRCUIT_ORDER if any(r["circuit"] == c for r in wall)]
    if not circuits:
        print(f"[{board}] no data at all -- skipping cumulative chart")
        return None

    fig, ax = plt.subplots(figsize=(8, 5.5), layout="constrained")
    for circuit in circuits:
        raw = load_raw(board, circuit)
        c_wall = [r for r in wall if r["circuit"] == circuit]
        ok_ns = sorted({int(r["n"]) for r in c_wall if r["status"] == "ok"})
        wall_ns = sorted({int(r["n"]) for r in c_wall if rs.is_wall_status(r["status"])})
        if not ok_ns:
            continue
        medians = []
        for n in ok_ns:
            vals = [float(r["exec_time_us"]) for r in raw
                    if int(r["n"]) == n and not is_warmup(int(r["rep"]))]
            medians.append(float(np.median(vals)) if vals else float("nan"))
        ax.plot(ok_ns, medians, marker=ps.CIRCUIT_MARKER[circuit], color=ps.CIRCUIT_INK[circuit],
                linewidth=1.6, markersize=6, markeredgecolor="white", markeredgewidth=0.6,
                label=ps.CIRCUIT_LABEL[circuit], zorder=3)
        if wall_ns:
            # wall point itself has no raw trials (no exec_time_us to plot) -- anchor
            # the annotation to the last ok point instead, on that circuit's own line
            last_ok_n, last_ok_med = ok_ns[-1], medians[-1]
            ax.annotate(f"wall n={wall_ns[0]}", (last_ok_n, last_ok_med),
                        xytext=(8, 0), textcoords="offset points", fontsize=8,
                        color=ps.CIRCUIT_INK[circuit])

    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Median execution time per rep (µs, log scale)")
    ax.legend(loc="upper left", fontsize=8)

    fig.suptitle(f"{ps.BOARD_LABEL[board]} -- all algorithms completed so far "
                 f"(REPS={tm.REPS}, generated at commit {current_head()})")
    ax.text(0.0, 1.06, SUBTITLE, transform=ax.transAxes, fontsize=8.5,
            color=ps.INK_SECONDARY, ha="left")
    ps.add_footnote(fig, "One colour per algorithm; wall n annotated where a positive-evidence "
                     "wall was hit; steane_encode is a single fixed-n point (n=7).")
    return ps.save_figure(fig, FIGURES_ROOT / board, "all_algorithms_so_far")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="uno")
    ap.add_argument("--circuit", required=True, help="the algorithm that just finished")
    args = ap.parse_args()

    ps.apply_style()
    generated = []
    for fn in (plot_exec_time_vs_n, plot_outcomes_vs_n, plot_time_per_point):
        paths = fn(args.board, args.circuit)
        if paths:
            generated.extend(paths)
    paths = plot_cumulative(args.board)
    if paths:
        generated.extend(paths)

    print(f"\n{len(generated)} figure file(s) written under {FIGURES_ROOT / args.board}/")


if __name__ == "__main__":
    main()
