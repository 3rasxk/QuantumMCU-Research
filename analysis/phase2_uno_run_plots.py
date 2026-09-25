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
# and need that one circuit's own raw.csv (per-rep, for the model overlay and
# warm-up exclusion), memory_wall.csv (per-point outcome + evidence), AND
# points.csv (per-attempt compile/upload time and retry counts) all three
# together (pc/shared/paths.py resolves all three under the same
# data/raw/phase2/<board>/<circuit>/ directory) -- phase2_plot.py touches only
# the first two, pre-aggregated across every board/circuit, and never
# per-attempt. Forcing this into phase2_plot.py would mean two incompatible
# calling conventions (once-at-the-end vs once-per-algorithm) and two
# incompatible output trees in one file.
#
# Read-only against data/raw/ -- every function here only ever opens raw/
# telemetry files for reading. Output: data/figures/<board>/<algorithm>/<bucket>/*.png
# (PNG only, via pc/shared/plot_style.save_figure_png_only) plus
# data/figures/<board>/<bucket>/all_algorithms_so_far.png, and nothing else,
# where <bucket> is no_la or with_la (see 2026-09-22 entry below).
#
# 2026-09-20: moved from figures/phase2/<board>/ (with .svg siblings) to
# data/figures/<board>/<algorithm>/ (PNG only) -- see run_log.md "per-board
# per-algorithm layout". Also moved from reading one shared
# data/raw/phase2/<board>_raw.csv (filtered by circuit in Python) to reading
# each circuit's own raw.csv/memory_wall.csv/points.csv/sessions.csv directly
# via pc/shared/paths.py -- no more in-script filtering needed for a single
# circuit's charts; the cumulative chart globs across every circuit directory
# for one board instead.
#
# 2026-09-22: every path gained a no_la/with_la bucket (--la flag on this
# script, matching pc/shared/paths.py's split) -- a chart never mixes
# timing-only and LA-cross-checked points. Default (no --la) reads/writes
# no_la/, matching every point collected so far.
#
# ใช้:
#   .venv/bin/python analysis/phase2_uno_run_plots.py --board uno --circuit h_all
# (สร้างกราฟ 3 อันของ h_all + กราฟสะสม all_algorithms_so_far ใหม่ทั้งหมด, no_la bucket)

import argparse
import csv
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
from shared import paths as sp  # noqa: E402
from shared.telemetry import is_warmup  # noqa: E402

FIGURES_ROOT = REPO_ROOT / "data" / "figures"

def SUBTITLE(la=False, board="uno"):
    """2026-09-22: text now reflects which bucket the figure's data actually
    came from (pc/shared/paths.py's no_la/with_la split) instead of a
    hardcoded "no Logic Analyzer data" that was only ever true because --la
    had never been run for real when this line was first written."""
    name = {"uno": "Uno R3", "esp8266": "ESP8266", "esp32": "ESP32"}.get(board, board)
    return (f"{name}, Phase 2, micros() timing + Logic Analyzer cross-check"
            if la else f"{name}, Phase 2, micros() timing (no Logic Analyzer data)")


def _board_sram_bytes(board):
    return {"uno": 2048, "esp8266": 81920, "esp32": 327680}[board]


def _known_circuits(board, la=False):
    """Every circuit this board has a raw.csv for in the given no_la/with_la
    bucket, discovered by listing data/raw/phase2/<board>/*/<bucket>/ --
    used only by plot_cumulative to find what to include, since circuits are
    no longer listed anywhere centrally."""
    base = REPO_ROOT / "data" / "raw" / "phase2" / board
    if not base.exists():
        return []
    bucket = "with_la" if la else "no_la"
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and (p / bucket / "raw.csv").exists())


def load_raw(board, circuit, la=False):
    path = sp.raw_csv_path(board, circuit, phase=2, la=la)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_wall(board, circuit, la=False):
    path = sp.memory_wall_csv_path(board, circuit, phase=2, la=la)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_points(board, circuit, la=False):
    path = sp.points_csv_path(board, circuit, phase=2, la=la)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def collection_commit(board, circuit, la=False):
    """git commit these points were collected under, per this circuit's own
    sessions.csv -- more accurate than the script's own current HEAD, which
    may have moved on by the time this is run."""
    path = sp.sessions_csv_path(board, circuit, phase=2, la=la)
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


def _finish(fig, ax_or_axes, board, circuit, title_extra, commit_note, la=False):
    fig.suptitle(_title(board, circuit, title_extra, commit_note))
    axes = ax_or_axes if isinstance(ax_or_axes, (list, tuple, np.ndarray)) else [ax_or_axes]
    axes = list(np.ravel(axes))
    axes[0].text(0.0, 1.10, SUBTITLE(la, board), transform=axes[0].transAxes,
                 fontsize=8.5, color=ps.INK_SECONDARY, ha="left")


def plot_exec_time_vs_n(board, circuit, la=False):
    """1. Per-rep execution time vs n: median + IQR from the raw trials of
    each ok point (warm-up reps excluded per telemetry.is_warmup), log y,
    with the timing_model per-rep estimate overlaid as its own series."""
    raw = load_raw(board, circuit, la)
    wall = load_wall(board, circuit, la)
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
    # legend moved outside the plot area (as with outcomes_vs_n/time_per_point) --
    # a fixed "upper left" collided with the data for steane_encode's single-point
    # chart, where the narrow x/y range put the model marker directly under the
    # legend box (found via the required visual self-check, not code review)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)

    commit_note = f"commit {collection_commit(board, circuit, la)}"
    _finish(fig, ax, board, circuit, "per-rep execution time vs n", commit_note, la)
    ps.add_footnote(fig, ps.reps_phrase(ntrials) + "; error bars = IQR (25th-75th pct).")
    return ps.save_figure_png_only(fig, sp.figures_dir(board, circuit, la), "exec_time_vs_n")


def _outcome_category(status):
    if status == "ok":
        return "ok"
    if rs.is_wall_status(status):
        return "wall"
    if status.startswith("runtime_hang_or_reset") or status.startswith("watchdog_suspected"):
        return "hang_no_evidence"
    return "failed"  # build_or_upload_fail, build_timeout, skipped_* never reach here (filtered)


def plot_outcomes_vs_n(board, circuit, la=False):
    """2. Point outcomes vs n: ok / failed (upload/build) / wall (positive
    evidence, annotated) / hang-no-evidence (distinct marker, flagged for
    review). Title states what was observed, never just "Memory Wall", so a
    build/upload failure can never be read as a wall from the chart."""
    wall = [r for r in load_wall(board, circuit, la) if not r["status"].startswith("skipped_")]
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

    commit_note = f"commit {collection_commit(board, circuit, la)}"
    _finish(fig, ax, board, circuit, "point outcomes and RAM-overflow wall", commit_note, la)
    return ps.save_figure_png_only(fig, sp.figures_dir(board, circuit, la), "outcomes_vs_n")


def plot_time_per_point(board, circuit, la=False):
    """3. Time per point vs n: compile_s + upload_s stacked (summed across
    every attempt for that n, so a retried point's true reflash cost shows),
    with the number of upload attempts annotated per n so retries stay
    visible."""
    pts = load_points(board, circuit, la)
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

    commit_note = f"commit {collection_commit(board, circuit, la)}"
    _finish(fig, ax, board, circuit, "reflash time per point (compile+upload, attempts labelled)",
            commit_note, la)
    return ps.save_figure_png_only(fig, sp.figures_dir(board, circuit, la), "time_per_point")


def plot_cumulative(board, la=False):
    """4. data/figures/<board>/{no_la,with_la}/all_algorithms_so_far.png --
    median per-rep time vs n for every algorithm completed so far on this
    board IN THIS BUCKET, one colour per algorithm, wall n marked.
    Regenerated after each algorithm. Never mixes no_la and with_la data into
    one chart -- timing-only and LA-cross-checked points measure different
    things (see pc/shared/paths.py)."""
    all_circuits = _known_circuits(board, la)
    circuits = [c for c in ps.CIRCUIT_ORDER if c in all_circuits]
    if not circuits:
        print(f"[{board}] no data at all in the "
              f"{'with_la' if la else 'no_la'} bucket -- skipping cumulative chart")
        return None

    fig, ax = plt.subplots(figsize=(8, 5.5), layout="constrained")
    for circuit in circuits:
        raw = load_raw(board, circuit, la)
        c_wall = load_wall(board, circuit, la)
        ok_ns = sorted({int(r["n"]) for r in c_wall if r["status"] == "ok"})
        wall_ns = sorted({int(r["n"]) for r in c_wall if rs.is_wall_status(r["status"])})
        if not ok_ns:
            continue
        medians = []
        for n in ok_ns:
            vals = [float(r["exec_time_us"]) for r in raw
                    if int(r["n"]) == n and not is_warmup(int(r["rep"]))]
            medians.append(float(np.median(vals)) if vals else float("nan"))
        # circuits deliberately don't borrow board hues (colour means board everywhere
        # else in this project) -- grey ink + marker + linestyle is the established
        # secondary encoding for telling circuits apart (see plot_style.py), so both
        # CIRCUIT_MARKER and CIRCUIT_LINESTYLE must be used together, not just marker
        ax.plot(ok_ns, medians, marker=ps.CIRCUIT_MARKER[circuit], color=ps.CIRCUIT_INK[circuit],
                linestyle=ps.CIRCUIT_LINESTYLE[circuit], linewidth=1.6, markersize=6,
                markeredgecolor="white", markeredgewidth=0.6,
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
    ax.text(0.0, 1.06, SUBTITLE(la, board), transform=ax.transAxes, fontsize=8.5,
            color=ps.INK_SECONDARY, ha="left")
    ps.add_footnote(fig, "One colour per algorithm; wall n annotated where a positive-evidence "
                     "wall was hit; steane_encode is a single fixed-n point (n=7).")
    return ps.save_figure_png_only(fig, sp.figures_dir(board, la=la), "all_algorithms_so_far")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="uno")
    ap.add_argument("--circuit", required=True, help="the algorithm that just finished")
    ap.add_argument("--la", action="store_true",
                     help="this run's points were collected with --la (sigrok capture actually "
                          "active, not just requested) -- selects the with_la bucket for both "
                          "reading raw/wall/points data and writing figures; omit for the "
                          "default no_la bucket. Must match how the data was actually collected "
                          "(see pc/phase2_sweep/uno_sweep.py's la_active, not args.la).")
    args = ap.parse_args()

    ps.apply_style()
    generated = []
    for fn in (plot_exec_time_vs_n, plot_outcomes_vs_n, plot_time_per_point):
        paths = fn(args.board, args.circuit, args.la)
        if paths:
            generated.extend(paths)
    paths = plot_cumulative(args.board, args.la)
    if paths:
        generated.extend(paths)

    bucket = "with_la" if args.la else "no_la"
    print(f"\n{len(generated)} figure file(s) written under "
          f"{FIGURES_ROOT / args.board}/*/{bucket}/ (PNG only)")


if __name__ == "__main__":
    main()
