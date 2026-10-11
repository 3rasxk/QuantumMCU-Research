#!/usr/bin/env python3
# phase2_uno_run_plots.py
#
# Per-run PNG charts for one Phase 2 algorithm on one board (despite the file name, every board), generated
# right after that algorithm's sweep finishes (pc/run.py calls it) and re-runnable by hand. Read-only against
# data/raw/phase2/<board>/<circuit>/<bucket>/: raw.csv (per-rep micros() time), memory_wall.csv (terminal
# outcome + evidence per n), points.csv (per-attempt telemetry), env/*.json (git commit of each session) and,
# with --ref, ref/ref_compare*.csv (micros() vs the ESP32 counter).
#
# Output: data/figures/phase2/<board>/<circuit>/*.png and data/figures/phase2/<board>/all_algorithms_so_far.png
# (PNG only, via pc/shared/plot_style.save_figure_png_only; nothing else is written).
#
#   exec_time_vs_n.png     per-rep time vs n: median line + light IQR band (25th-75th) over every rep (single-rep points: no band; reps as faint dots only with ps.SHOW_REPS),
#                          timing_model line labelled ESTIMATE (never data), log y
#   outcomes_vs_n.png      point outcomes and memory limit: ok / ok but time-capped / wall (only with recorded
#                          evidence, values annotated) / failed / watchdog-reset / hang-no-evidence / time-limited;
#                          failed attempts before the final outcome are a second row, so a reset never looks like a wall
#   memory_vs_n.png        state-vector bytes vs the board's RAM; Uno: compile RAM %, ESP: free heap and largest block
#   time_per_point.png     compile + upload time per point (all attempts), attempts and hang budget labelled
#   scaling.png            ratio of successive-n medians and log2(time) vs n with a fit (fit range on the chart)
#   micros_vs_counter.png  (--ref, physical counter only) micros() minus counter, median + IQR, per n
#   all_algorithms_so_far.png (per board) every completed circuit, walls / time limits marked as in outcomes_vs_n
#
# Use:  .venv/bin/python analysis/phase2_uno_run_plots.py --board uno --circuit h_all [--ref]

import argparse
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _graph_data as gd  # noqa: E402
from _graph_data import OK, OK_CAPPED, WALL, FAILED, WATCHDOG, HANG, TIME_LIMITED  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import paths as sp  # noqa: E402

REPO_ROOT = gd.REPO_ROOT
CAP_TEXT = f"{tm.POINT_TIME_CAP_S / 3600:g} h"
LINE_W = 1.8          # colour-only series: solid lines, no markers

# one marker per outcome category; non-ok categories never reuse the circuit/board data markers
CAT_KIND = {OK: "ok", OK_CAPPED: "capped", WALL: "wall", FAILED: "failed", WATCHDOG: "watchdog", HANG: "hang",
            TIME_LIMITED: "time_limited"}
CAT_LABEL = {
    OK: "ok (100 reps)",
    OK_CAPPED: f"< 100 reps ({CAP_TEXT} cap)",
    WALL: "memory wall",
    FAILED: "build/upload failed (not a wall)",
    WATCHDOG: "watchdog / reset (not a wall)",
    HANG: "hang, no evidence (review)",
    TIME_LIMITED: "time-limited, not run",
}


def subtitle(S):
    return (f"{ps.BOARD_SHORT[S.board]}, Phase 2, micros() timing, "
            f"{'counter reference collected (see micros_vs_counter)' if S.ref else 'no counter reference'}")


def finish(fig, ax, S, what):
    ps.suptitle(fig, f"{ps.BOARD_LABEL[S.board]} -- {ps.CIRCUIT_LABEL.get(S.circuit, S.circuit)} -- {what} "
                     f"(target REPS={tm.REPS}, {S.commit_note()})", fontsize=10)
    axes = list(np.ravel(ax)) if isinstance(ax, (list, tuple, np.ndarray)) else [ax]
    axes[0].text(0.0, 1.06, subtitle(S), transform=axes[0].transAxes, fontsize=8.5, color=ps.INK_SECONDARY, ha="left")


def out_dir(S):
    return sp.figures_dir(S.board, S.circuit, S.ref)


def save(fig, S, stem):
    return ps.save_figure_png_only(fig, out_dir(S), stem)


def marker_kwargs(cat, color=None):
    """Every point status is a round dot (ps.dot_kwargs): filled = ok, half-filled = < 100 reps, black-rimmed = wall,
    open ring = time-limited; failed / watchdog / hang differ by fill colour."""
    return ps.dot_kwargs(CAT_KIND[cat], color)


def ok_series(S):
    """(ns, outcomes) of the points that have timing data: every n with raw rows and a final ok / capped outcome
    (or, when the dataset has no memory_wall.csv rows at all, every n with raw rows)."""
    out = gd.outcomes_phase2(S)
    vals = gd.values_by_n(S.raw, "exec_time_us")
    ns = [n for n in sorted(vals) if not out or out.get(n, {}).get("cat") in (OK, OK_CAPPED)]
    return ns, vals, out


def strip_events(ax, out, board_ymax_axes=0.95):
    """Walls and time-limited points have no timing value: marked on a strip at the top of the axes, never on
    the data curve, so they cannot be read as measured values."""
    tr = ax.get_xaxis_transform()
    for n, o in sorted(out.items()):
        if o["cat"] in (WALL, TIME_LIMITED):
            ax.plot([n], [board_ymax_axes], linestyle="none", transform=tr, clip_on=False, markersize=9,
                    **marker_kwargs(o["cat"]))


def legend_for(ax, cats, extra=()):
    h = [Line2D([], [], linestyle="none", markersize=8, **marker_kwargs(c)) for c in cats]
    ax.legend(h + list(extra), [CAT_LABEL[c] for c in cats] + [e.get_label() for e in extra],
              loc="best", fontsize=8.5)


# --------------------------------------------------------------------------- 1. time vs n

def plot_exec_time_vs_n(S):
    ns, vals, out = ok_series(S)
    if not ns:
        print(f"[{S.circuit}] no ok points -- skipping exec_time_vs_n")
        return None
    st = {n: gd.stats(vals[n]) for n in ns}
    col = ps.BOARD_COLOR[S.board]
    fig, ax = plt.subplots(figsize=(7.4, 5.4), layout="constrained")
    if ps.SHOW_REPS:
        for n in ns:
            ax.plot(np.full(len(vals[n]), n), vals[n], linestyle="none", marker=".", markersize=3.2,
                    color=ps.INK_MUTED, alpha=0.28, zorder=1, rasterized=True)
    ps.iqr_band(ax, ns, [st[n][1] for n in ns], [st[n][2] for n in ns], col)
    ax.plot(ns, [st[n][0] for n in ns], linestyle="-", color=col, linewidth=LINE_W, zorder=2)
    for n in ns:                       # colour-only series; only a time-capped point (< 100 reps) gets an open marker
        if out.get(n, {}).get("cat") == OK_CAPPED:
            ax.plot([n], [st[n][0]], linestyle="none", markersize=7, zorder=4, **marker_kwargs(OK_CAPPED, col))
    tl = [n for n, o in out.items() if o["cat"] == TIME_LIMITED]
    model_ns = sorted(set(ns) | set(tl))
    try:
        ax.plot(model_ns, [tm.expected_exec_time_us(S.board, S.circuit, n) for n in model_ns], linestyle="--",
                color=ps.INK_SECONDARY, linewidth=ps.REF_LINE_WIDTH, zorder=2)
    except Exception as e:  # noqa: BLE001
        print(f"[{S.circuit}] no timing_model estimate ({e})")
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    lo, hi = min(min(v) for v in vals.values() if v), max(max(v) for v in vals.values() if v)
    ax.set_ylim(lo / 2.5, hi * 10 ** (0.75 if any(o["cat"] in (WALL, TIME_LIMITED) for o in out.values()) else 0.3))
    strip_events(ax, out)
    ax.set_xticks(sorted(set(ns) | {n for n, o in out.items() if o["cat"] in (WALL, TIME_LIMITED)}))
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Execution time per rep (µs, log scale)")
    cats = [c for c in (OK_CAPPED, WALL, TIME_LIMITED) if any((o["cat"] == c) for o in out.values())]
    est = Line2D([], [], linestyle="--", color=ps.INK_SECONDARY, linewidth=ps.REF_LINE_WIDTH,
                 label="timing model (estimate)")
    band = Line2D([], [], linestyle="-", color=col, linewidth=6, alpha=ps.BAND_ALPHA * 1.6,
                  label="IQR band")
    extra = [est, band]
    if ps.SHOW_REPS:
        extra.append(Line2D([], [], linestyle="none", marker=".", color=ps.INK_MUTED, alpha=0.6, label="individual rep"))
    ok_line = Line2D([], [], linestyle="-", color=col, linewidth=LINE_W, label="median (100 reps)")
    legend_for(ax, cats, extra=(ok_line,) + tuple(extra))
    finish(fig, ax, S, "per-rep execution time vs n")
    gd.footnote(fig, gd.reps_text(len(vals[n]) for n in ns) + "; line = median, band = IQR (25th-75th pct), "
                    "no band where a point has one rep; all reps used (WARMUP_REPS=0).")
    return save(fig, S, "exec_time_vs_n")


# --------------------------------------------------------------------------- 2. outcomes

def evidence_text(S, o):
    r = o["row"]
    if S.board == "uno":
        used, pct = r.get("compile_ram_used_bytes", ""), r.get("compile_ram_pct", "")
        if used and pct:
            return f"{o['status']}\ncompile RAM {pct}% ({used} / {gd.BOARD_SRAM_BYTES[S.board]} B)"
    tb = r.get("theoretical_bytes", "")
    return f"{o['status']}\nstate {tb} B" + (f"\nhang budget {r['timeout_budget_s']} s" if r.get("timeout_budget_s") else "")


def plot_outcomes_vs_n(S):
    out = gd.outcomes_phase2(S)
    if not out:
        print(f"[{S.circuit}] no point-outcome rows -- skipping outcomes_vs_n")
        return None
    attempts = gd.failed_attempts(S)
    fig, ax = plt.subplots(figsize=(7.4, 4.8), layout="constrained")
    k_cap = 0
    for n, o in sorted(out.items()):
        ax.plot([n], [1.0], linestyle="none", markersize=11, zorder=3, **marker_kwargs(o["cat"]))
        if o["cat"] == OK_CAPPED:
            k_cap += 1
            ax.annotate(f"{o['reps']}/{tm.REPS} reps", (n, 1.0), xytext=(0, -17 - 11 * (k_cap % 2)),
                        textcoords="offset points",
                        ha="center", fontsize=8.5, color=ps.INK_SECONDARY)
        if o["cat"] == WALL:
            ax.annotate(evidence_text(S, o), (n, 1.0), xytext=(0, 14), textcoords="offset points", ha="center",
                        fontsize=8.5, color=ps.INK_PRIMARY)
    for i, (n, kinds) in enumerate(sorted(attempts.items())):
        cat = WATCHDOG if any(k.startswith("watchdog") for k in kinds) else FAILED
        ax.plot([n], [0.55], linestyle="none", markersize=9, zorder=3, **marker_kwargs(cat))
        short = kinds[0].replace("_suspected", "")
        ax.annotate(f"{len(kinds)}x {short}" if len(set(kinds)) == 1 else f"{len(kinds)} failed",
                    (n, 0.55), xytext=(0, -17 - 11 * (i % 2)), textcoords="offset points", ha="center",
                    fontsize=8.5, color=ps.INK_SECONDARY)
    if attempts:
        ax.set_yticks([1.0, 0.55])
        ax.set_yticklabels(["final outcome", "failed attempts\nbefore it"], fontsize=9)
        ax.set_ylim(0.2, 1.55)
    else:
        ax.set_yticks([1.0])
        ax.set_yticklabels(["final outcome"], fontsize=9)
        ax.set_ylim(0.6, 1.55)
    ax.set_xticks(sorted(out))
    ax.set_xlabel("Number of qubits, $n$")
    ps.style_axes(ax, log_y=False)
    ax.grid(False, axis="y")
    cats = [c for c in (OK, OK_CAPPED, WALL, FAILED, WATCHDOG, HANG, TIME_LIMITED)
            if any(o["cat"] == c for o in out.values()) or (c in (WATCHDOG, FAILED) and any(
                (WATCHDOG if any(k.startswith("watchdog") for k in v) else FAILED) == c for v in attempts.values()))]
    legend_for(ax, cats)
    finish(fig, ax, S, "point outcomes and memory limit")
    gd.footnote(fig, "A wall is drawn only where build_overflow / malloc_failed was recorded; resets, hangs and "
                    "build/upload failures are separate markers. Source: memory_wall.csv, points.csv.")
    return save(fig, S, "outcomes_vs_n")


# --------------------------------------------------------------------------- 3. memory

def plot_memory_vs_n(S):
    rows = sorted(S.wall, key=lambda r: int(r["n"]))
    rows = [r for r in rows if gd.f(r.get("theoretical_bytes")) is not None]
    if not rows:
        print(f"[{S.circuit}] no memory_wall rows -- skipping memory_vs_n")
        return None
    out = gd.outcomes_phase2(S)
    sram = gd.BOARD_SRAM_BYTES[S.board]
    ns = [int(r["n"]) for r in rows]
    col = ps.BOARD_COLOR[S.board]
    fig, ax = plt.subplots(figsize=(7.4, 5.0), layout="constrained")
    ax.plot(ns, [float(r["theoretical_bytes"]) for r in rows], linestyle="-",
            color=col, linewidth=LINE_W, label="state vector (8 B x 2^n)", zorder=3)
    ax.axhline(sram, color=ps.INK_PRIMARY, linestyle="--", linewidth=ps.REF_LINE_WIDTH, zorder=2)
    ax.annotate(f"100% of board RAM = {sram} B", (ns[0], sram), xytext=(0, 4), textcoords="offset points",
                fontsize=8, color=ps.INK_PRIMARY)
    heap = gd.values_by_n(S.raw, "free_heap_before")
    if heap:
        hn = sorted(heap)
        ax.plot(hn, [float(np.median(heap[n])) for n in hn], linestyle="-", color=ps.EXTRA_COLOR["purple"], linewidth=LINE_W,
                label="free heap (median)", zorder=2)
    blocks = gd.values_by_n(S.raw, "largest_block")
    if blocks:
        bn = sorted(blocks)
        ax.plot(bn, [float(np.median(blocks[n])) for n in bn], linestyle="-", color=ps.EXTRA_COLOR["brown"], linewidth=LINE_W,
                label="largest free block (median)", zorder=2)
    used = [(int(r["n"]), float(r["compile_ram_used_bytes"])) for r in rows if gd.f(r.get("compile_ram_used_bytes"))]
    if used:
        ax.plot([u[0] for u in used], [u[1] for u in used], linestyle="-", color=ps.EXTRA_COLOR["dark"],
                linewidth=LINE_W, label="compile RAM used", zorder=2)
    for n, o in sorted(out.items()):
        if o["cat"] == WALL:
            y = next(float(r["theoretical_bytes"]) for r in rows if int(r["n"]) == n)
            ax.plot([n], [y], linestyle="none", markersize=11, zorder=5, **marker_kwargs(WALL))
            ax.annotate(evidence_text(S, o).replace("\n", ", "), (n, y), xytext=(-6, 12), textcoords="offset points",
                        ha="right", fontsize=9)
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    sec = ax.secondary_yaxis("right", functions=(lambda y: y / sram * 100, lambda p: p * sram / 100))
    sec.set_ylabel("% of board RAM")
    ax.set_xticks(ns)
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Bytes (log scale)")
    h, lab = ax.get_legend_handles_labels()
    wall_h = Line2D([], [], linestyle="none", markersize=9, **marker_kwargs(WALL))
    if any(o["cat"] == WALL for o in out.values()):
        h.append(wall_h)
        lab.append(CAT_LABEL[WALL])
    ax.legend(h, lab, loc="best", fontsize=8.5)
    finish(fig, ax, S, "memory vs n")
    gd.footnote(fig, "The wall marker only appears where the sweep recorded build_overflow / malloc_failed; "
                    "the board RAM line is the plan's figure, not a measurement.")
    return save(fig, S, "memory_vs_n")


# --------------------------------------------------------------------------- 4. overhead per point

def plot_time_per_point(S):
    pts = [r for r in S.points if r["status"] in ("ok", "failed", "retrying")]
    if not pts:
        print(f"[{S.circuit}] no telemetry points -- skipping time_per_point")
        return None
    by_n = {}
    for r in pts:
        d = by_n.setdefault(int(r["n"]), {"c": 0.0, "u": 0.0, "a": 0, "fail": 0})
        d["c"] += gd.f(r.get("build_compile_s"), 0.0)
        d["u"] += gd.f(r.get("upload_s"), 0.0)
        d["a"] += 1
        d["fail"] += r["status"] == "failed"
    ns = sorted(by_n)
    comp, upl = [by_n[n]["c"] for n in ns], [by_n[n]["u"] for n in ns]
    fig, ax = plt.subplots(figsize=(7.4, 4.8), layout="constrained")
    ax.bar(ns, comp, color=ps.BOARD_COLOR[S.board], label="compile time (s)", zorder=3)
    ax.bar(ns, upl, bottom=comp, color=ps.INK_MUTED, hatch="//", edgecolor="white", label="upload time (s)", zorder=3)
    walls = {int(r["n"]): r for r in S.wall if gd.rs.is_wall_status(r["status"])}
    for n, c, u in zip(ns, comp, upl):
        d = by_n[n]
        txt = f"{d['a']} attempt" + ("s" if d["a"] != 1 else "")
        if d["fail"]:
            txt += f"\n({d['fail']} failed)"
        if n in walls and walls[n].get("timeout_budget_s"):
            txt += f"\nwall run, hang budget {walls[n]['timeout_budget_s']} s"
        ax.annotate(txt, (n, c + u), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)
    ps.style_axes(ax, log_y=False)
    ax.set_xticks(ns)
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Compile + upload time per point, all attempts (s)")
    ax.set_ylim(0, max(c + u for c, u in zip(comp, upl)) * 1.6)
    ax.legend(loc="best", fontsize=8.5)
    finish(fig, ax, S, "reflash overhead per point (compile + upload)")
    gd.footnote(fig, "Summed over every attempt of a point (a retried or failed attempt still costs reflash time); "
                    "device run time is not part of this chart. Source: points.csv.")
    return save(fig, S, "time_per_point")


# --------------------------------------------------------------------------- 5. scaling

FIT_POINTS = 5     # the fit uses the largest FIT_POINTS ok points that have 100 reps (stated on the chart)


def plot_scaling(S):
    ns, vals, out = ok_series(S)
    full = [n for n in ns if out.get(n, {}).get("cat", OK) == OK or not out]
    if len(full) < 3:
        print(f"[{S.circuit}] fewer than 3 complete points -- skipping scaling")
        return None
    med = {n: float(np.median(vals[n])) for n in full}
    fit_ns = full[-FIT_POINTS:]
    slope, icpt = np.polyfit(fit_ns, [np.log2(med[n]) for n in fit_ns], 1)
    col = ps.BOARD_COLOR[S.board]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.8), layout="constrained")
    a1.plot(full, [np.log2(med[n]) for n in full], linestyle="-", color=col, linewidth=LINE_W,
            label="measured median", zorder=3)
    xs = np.array([fit_ns[0], fit_ns[-1]])
    a1.plot(xs, slope * xs + icpt, linestyle="--", color=ps.INK_PRIMARY, linewidth=1.3, zorder=2,
            label=f"fit n={fit_ns[0]}..{fit_ns[-1]}, slope {slope:.2f}")
    a1.plot(xs, 1.0 * (xs - xs[0]) + (slope * xs[0] + icpt), linestyle=":", color=ps.INK_MUTED, linewidth=1.3,
            zorder=1, label="slope 1 (reference)")
    a1.set_xticks(full)
    a1.set_xlabel("Number of qubits, $n$")
    a1.set_ylabel("log2 of median time per rep (µs)")
    ps.style_axes(a1)
    a1.legend(loc="best", fontsize=8.5)
    rn = [n for n in full if n - 1 in med]
    a2.plot(rn, [med[n] / med[n - 1] for n in rn], linestyle="-", color=col, linewidth=LINE_W,
            label="t(n) / t(n-1)")
    a2.axhline(2.0, color=ps.INK_PRIMARY, linestyle="--", linewidth=1.1, label="2x per qubit (reference)")
    a2.set_xticks(rn)
    a2.set_xlabel("Number of qubits, $n$")
    a2.set_ylabel("Ratio of successive medians")
    ps.style_axes(a2)
    a2.legend(loc="best", fontsize=8.5)
    finish(fig, [a1, a2], S, "scaling of time per rep with n")
    gd.footnote(fig, "Points with 100 reps only; a fit of the median curve, not a model of the device. "
                    "Source: raw.csv.")
    return save(fig, S, "scaling")


# --------------------------------------------------------------------------- 8. micros() vs counter

def plot_micros_vs_counter(S):
    if not S.ref:
        return None
    okc, why = S.physical_counter()
    if not okc:
        print(f"[{S.circuit}] counter reference not established as physical ({why}) -- skipping micros_vs_counter")
        return None
    cmp_ = gd.need(gd.read_rows(S.dir / "ref" / "ref_compare.csv"),
                   ["n", "rep", "micros_us", "counter_us", "diff_us", "diff_pct"], "ref_compare.csv")
    pts = {int(r["n"]): r for r in gd.read_rows(S.dir / "ref" / "ref_compare_points.csv")}
    by_n = {}
    for r in cmp_:
        by_n.setdefault(int(r["n"]), []).append(r)
    rows = []
    for n in sorted(by_n):
        st = pts.get(n, {}).get("ref_status", "")
        if st not in ("ok", "anomaly", "count_mismatch") or len(by_n[n]) < gd.MIN_PAIRS:
            continue
        us = [float(r["diff_us"]) for r in by_n[n]]
        pc = [float(r["diff_pct"]) for r in by_n[n]]
        rows.append((n, st, gd.stats(us), gd.stats(pc), len(us)))
    if not rows:
        print(f"[{S.circuit}] no joined counter comparison with >= {gd.MIN_PAIRS} pairs -- skipping micros_vs_counter")
        return None
    col = ps.BOARD_COLOR[S.board]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.4, 7.2), sharex=True, layout="constrained")
    for ax, k, unit in ((a1, 2, "µs"), (a2, 3, "%")):
        ax.axhline(0, color=ps.INK_PRIMARY, linewidth=1.0, zorder=1)
        ps.iqr_band(ax, [r[0] for r in rows], [r[k][1] for r in rows], [r[k][2] for r in rows], col)
        ax.plot([r[0] for r in rows], [r[k][0] for r in rows], linestyle="-", color=col, linewidth=LINE_W, zorder=2)
        for r in rows:                 # only a point the counter flagged gets an open marker
            if r[1] != "ok":
                ax.plot([r[0]], [r[k][0]], linestyle="none", markersize=5.5, zorder=4, marker="o",
                        markerfacecolor="white", markeredgecolor=col, markeredgewidth=1.4)
        ax.set_yscale("symlog", linthresh=1.0 if unit == "µs" else 0.1)
        ax.set_ylabel(f"micros() minus counter ({unit}, symlog)")
        ax.yaxis.set_major_formatter(ps.plain_number_formatter())
        ps.style_axes(ax)
    a2.set_xticks([r[0] for r in rows])
    a2.set_xlabel("Number of qubits, $n$")
    h = [Line2D([], [], linestyle="-", color=col, linewidth=LINE_W, label="median"),
         Line2D([], [], linestyle="none", marker="o", markerfacecolor="white", markeredgecolor=col,
                markersize=6, markeredgewidth=1.4, label="counter flagged anomaly")]
    a2.legend(h, [x.get_label() for x in h], loc="best", fontsize=8.5)
    ps.suptitle(fig, f"{ps.BOARD_LABEL[S.board]} -- {ps.CIRCUIT_LABEL.get(S.circuit, S.circuit)} -- micros() vs counter "
                     f"(target REPS={tm.REPS}, {S.commit_note()})", fontsize=10)
    a1.text(0.0, 1.05, f"{ps.BOARD_SHORT[S.board]}, Phase 2, micros() and ESP32 counter (self-loopback tested only, "
            "NOT externally calibrated)", transform=a1.transAxes, fontsize=8.5, color=ps.INK_SECONDARY)
    gd.footnote(fig, f"Line = median, band = IQR of the per-rep difference; only points with >= {gd.MIN_PAIRS} paired reps. "
                    "Differences are relative to this counter, not to a traceable reference.")
    return save(fig, S, "micros_vs_counter")


# --------------------------------------------------------------------------- 7. cumulative

def plot_cumulative(board, ref=False):
    circuits = gd.known_circuits(board, 2, ref)
    if not circuits:
        print(f"[{board}] no data in the {'with_ref' if ref else 'no_ref'} bucket -- skipping cumulative chart")
        return None
    sets = {c: gd.PointSet(board, c, 2, ref) for c in circuits}
    fig, ax = plt.subplots(figsize=(8.4, 6.0), layout="constrained")
    lo = hi = None
    walls, tls = {}, {}
    for c, S in sets.items():
        ns, vals, out = ok_series(S)
        if not ns:
            continue
        med = [float(np.median(vals[n])) for n in ns]
        lo = min(med + [lo or med[0]])
        hi = max(med + [hi or med[0]])
        ink = ps.CIRCUIT_COLOR[c]
        ax.plot(ns, med, linestyle="-", color=ink, linewidth=LINE_W, zorder=2)
        capped = [n for n in ns if out.get(n, {}).get("cat") == OK_CAPPED]
        ax.plot(capped, [m for n, m in zip(ns, med) if n in capped], linestyle="none", markersize=7, zorder=3,
                **marker_kwargs(OK_CAPPED, ink))
        walls[c] = [n for n, o in out.items() if o["cat"] == WALL]
        tls[c] = [n for n, o in out.items() if o["cat"] == TIME_LIMITED]
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    ax.set_ylim(lo / 2.5, hi * 10 ** 1.0)
    tr = ax.get_xaxis_transform()
    for i, c in enumerate(circuits):
        y = 0.95 - 0.05 * i
        for n in walls.get(c, []):
            ax.plot([n], [y], transform=tr, linestyle="none", markersize=8, color=ps.CIRCUIT_COLOR[c], **{
                k: v for k, v in marker_kwargs(WALL, ps.CIRCUIT_COLOR[c]).items()})
        for n in tls.get(c, []):
            ax.plot([n], [y], transform=tr, linestyle="none", markersize=9, **marker_kwargs(TIME_LIMITED,
                                                                                         ps.CIRCUIT_COLOR[c]))
    h = [Line2D([], [], linestyle="-", color=ps.CIRCUIT_COLOR[c], linewidth=LINE_W,
                label=c) for c in circuits]
    h += [Line2D([], [], linestyle="none", markersize=8, **marker_kwargs(OK_CAPPED), label=CAT_LABEL[OK_CAPPED]),
          Line2D([], [], linestyle="none", markersize=8, **marker_kwargs(WALL), label=CAT_LABEL[WALL]),
          Line2D([], [], linestyle="none", markersize=8, **marker_kwargs(TIME_LIMITED), label=CAT_LABEL[TIME_LIMITED])]
    ax.legend(handles=h, loc="best", fontsize=8.5)
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Median execution time per rep (µs, log scale)")
    commits = list(dict.fromkeys(c for S in sets.values() for c in S.commits()))
    note = gd.commit_phrase(commits)
    ps.suptitle(fig, f"{ps.BOARD_LABEL[board]} -- all algorithms completed so far (target REPS={tm.REPS}, {note})", fontsize=10)
    ax.text(0.0, 1.04, f"{ps.BOARD_SHORT[board]}, Phase 2, micros() timing", transform=ax.transAxes, fontsize=8.5,
            color=ps.INK_SECONDARY)
    gd.footnote(fig, "Median per point (IQR is in each circuit's own exec_time_vs_n chart). Wall / time-limited "
                    "markers are on the top strip, one row per circuit, never on a curve.")
    return ps.save_figure_png_only(fig, sp.figures_dir(board, ref=ref), "all_algorithms_so_far")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="uno", choices=list(ps.BOARD_ORDER))
    ap.add_argument("--circuit", required=True, help="the algorithm that just finished")
    ap.add_argument("--ref", action="store_true",
                    help="read the with_ref bucket (run collected with --ref counter); omit for no_ref")
    args = ap.parse_args()
    ps.apply_style()
    try:
        S = gd.PointSet(args.board, args.circuit, 2, args.ref)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
    generated = []
    for fn in (plot_exec_time_vs_n, plot_outcomes_vs_n, plot_memory_vs_n, plot_time_per_point, plot_scaling,
               plot_micros_vs_counter):
        paths = fn(S)
        if paths:
            generated.extend(paths)
    paths = plot_cumulative(args.board, args.ref)
    if paths:
        generated.extend(paths)
    print(f"\n{len(generated)} figure file(s) written under {sp.figures_dir(args.board)} (PNG only)")


if __name__ == "__main__":
    main()
