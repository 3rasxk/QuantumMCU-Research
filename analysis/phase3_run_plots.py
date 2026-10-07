#!/usr/bin/env python3
# phase3_run_plots.py
#
# Per-run plots for one Phase 3 (offload) algorithm on one board, generated right after its sweep finishes
# (pc/run.py calls it, like phase2_uno_run_plots.py does for Phase 2). Read-only against data/raw/phase3/.
# Output: data/figures/phase3/<board>/<algorithm>/<bucket>/*.png, <bucket> = no_ref or with_ref.
#
#   latency_vs_n.png       round-trip latency per request vs n: median + IQR of e2e_latency_us (log y), the PC's
#                          Aer time per request, and (with_ref) the counter's own median for the same reps
#   outcomes_vs_n.png      per n: reps answered cleanly / CRC errors / timeouts
#   time_per_point.png     per n: compile, upload, boot wait, device run time
#   micros_vs_counter.png  (with_ref) board micros() minus counter, median and IQR per n
#
# Use:  .venv/bin/python analysis/phase3_run_plots.py --board esp8266 --circuit h_all [--ref]

import argparse
import csv
import statistics
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import paths as sp  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared.telemetry import is_warmup  # noqa: E402


def _read(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _last_per_n(rows):
    """Later rows win (a resumed/re-run point appends a newer row for the same n)."""
    out = {}
    for r in rows:
        out[int(r["n"])] = r
    return out


def load(board, circuit, ref):
    d = sp.raw_dir(board, circuit, phase=3, ref=ref)
    data = {
        "raw": _read(sp.raw_csv_path(board, circuit, phase=3, ref=ref)),
        "log": _last_per_n(_read(sp.session_log_csv_path(board, circuit, phase=3, ref=ref))),
        "points": _read(sp.points_csv_path(board, circuit, phase=3, ref=ref)),
        "cmp_points": {}, "cmp": {}}
    if ref:
        data["cmp_points"] = _last_per_n(_read(d / "ref" / "ref_compare_points.csv"))
        for r in _read(d / "ref" / "ref_compare.csv"):   # later rows of one n replace earlier ones
            data["cmp"].setdefault(int(r["n"]), {})[int(r["rep"])] = float(r["counter_us"])
    return data


def _subtitle(board, ref):
    return (f"{ps.BOARD_SHORT[board]}, Phase 3 (offload), board micros() round trip + ESP32 counter" if ref
            else f"{ps.BOARD_SHORT[board]}, Phase 3 (offload), board micros() round trip (no counter)")


def _finish(fig, ax, board, circuit, what, ref):
    fig.suptitle(f"{ps.BOARD_LABEL[board]} -- {ps.CIRCUIT_LABEL.get(circuit, circuit)} -- {what} (REPS={tm.REPS})")
    ax.text(0.0, 1.10, _subtitle(board, ref), transform=ax.transAxes, fontsize=8.5, color=ps.INK_SECONDARY, ha="left")


def _out(board, circuit, ref):
    return sp.figures_dir(board, circuit, ref, phase=3)


def _latencies(raw):
    by_n = {}
    for r in raw:
        if is_warmup(int(r["rep"])):
            continue
        by_n.setdefault(int(r["n"]), []).append(float(r["e2e_latency_us"]))
    return by_n


def plot_latency_vs_n(board, circuit, ref, data):
    by_n = _latencies(data["raw"])
    ok_ns = sorted(n for n in by_n if data["log"].get(n, {}).get("status") == "ok")
    if not ok_ns:
        print(f"[{circuit}] no ok points -- skipping latency_vs_n")
        return None
    med = [float(np.median(by_n[n])) for n in ok_ns]
    q1 = [float(np.percentile(by_n[n], 25)) for n in ok_ns]
    q3 = [float(np.percentile(by_n[n], 75)) for n in ok_ns]
    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    ax.errorbar(ok_ns, med, yerr=[[m - a for m, a in zip(med, q1)], [b - m for m, b in zip(med, q3)]],
                fmt=ps.BOARD_MARKER[board], color=ps.BOARD_COLOR[board], markersize=6, markeredgecolor="white",
                markeredgewidth=0.7, linewidth=1.8, capsize=3, label="board micros() round trip (median, IQR bars)", zorder=3)
    sim_ns = [n for n in ok_ns if data["log"][n].get("pc_sim_s_per_request")]
    if sim_ns:
        ax.plot(sim_ns, [float(data["log"][n]["pc_sim_s_per_request"]) * 1e6 for n in sim_ns], linestyle="--", marker="x",
                color=ps.INK_SECONDARY, linewidth=1.3, label="PC Aer time per request (timing_model estimate)", zorder=2)
    cmp_ns = sorted(n for n in data["cmp"] if n in ok_ns and data["cmp"][n])
    if cmp_ns:
        ax.plot(cmp_ns, [statistics.median(data["cmp"][n].values()) for n in cmp_ns], linestyle="none", marker="+",
                markersize=11, markeredgewidth=1.8, color=ps.INK_PRIMARY, label="ESP32 counter (median, same reps)", zorder=4)
    ps.style_axes(ax, log_y=True)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Round trip per request (µs, log scale)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=1)
    _finish(fig, ax, board, circuit, "offload round-trip latency vs n", ref)
    ps.add_footnote(fig, ps.reps_phrase([len(by_n[n]) for n in ok_ns]) + "; error bars = IQR (25th-75th pct); rep 0 included.")
    return ps.save_figure_png_only(fig, _out(board, circuit, ref), "latency_vs_n")


def plot_outcomes_vs_n(board, circuit, ref, data):
    stats = {}
    for r in data["raw"]:
        s = stats.setdefault(int(r["n"]), [0, 0, 0])
        if r["timed_out"] == "1":
            s[2] += 1
        elif r["crc_error"] == "1":
            s[1] += 1
        else:
            s[0] += 1
    if not stats:
        print(f"[{circuit}] no raw rows -- skipping outcomes_vs_n")
        return None
    ns = sorted(stats)
    ok = np.array([stats[n][0] for n in ns]); crc = np.array([stats[n][1] for n in ns]); to = np.array([stats[n][2] for n in ns])
    fig, ax = plt.subplots(figsize=(7, 4.8), layout="constrained")
    ax.bar(ns, ok, color=ps.BOARD_COLOR[board], label="answered, CRC ok", zorder=3)
    ax.bar(ns, crc, bottom=ok, color="#D55E00", label="CRC error", zorder=3)
    ax.bar(ns, to, bottom=ok + crc, color=ps.INK_MUTED, label="timed out (5 s)", zorder=3)
    ps.style_axes(ax)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Requests per point")
    ax.set_ylim(0, max(ok + crc + to) * 1.18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
    _finish(fig, ax, board, circuit, "request outcomes per n", ref)
    return ps.save_figure_png_only(fig, _out(board, circuit, ref), "outcomes_vs_n")


def plot_time_per_point(board, circuit, ref, data):
    pts = [r for r in data["points"] if r["status"] in ("ok", "failed")]
    if not pts:
        print(f"[{circuit}] no telemetry points -- skipping time_per_point")
        return None
    by_n = {}
    for r in pts:
        d = by_n.setdefault(int(r["n"]), [0.0, 0.0, 0.0, 0.0])
        for i, col in enumerate(("build_compile_s", "upload_s", "boot_wait_s", "device_exec_s")):
            d[i] += float(r[col] or 0.0)
    ns = sorted(by_n)
    cols = [np.array([by_n[n][i] for n in ns]) for i in range(4)]
    labels = ("compile", "upload", "boot wait", "device run (100 requests)")
    colors = (ps.BOARD_COLOR[board], ps.INK_MUTED, "#CC79A7", "#56B4E9")
    fig, ax = plt.subplots(figsize=(7, 4.8), layout="constrained")
    bottom = np.zeros(len(ns))
    for c, lab, col in zip(cols, labels, colors):
        ax.bar(ns, c, bottom=bottom, color=col, label=lab, zorder=3)
        bottom += c
    ps.style_axes(ax)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Time per point (s)")
    ax.set_ylim(0, max(bottom) * 1.12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    _finish(fig, ax, board, circuit, "time per point", ref)
    return ps.save_figure_png_only(fig, _out(board, circuit, ref), "time_per_point")


def plot_micros_vs_counter(board, circuit, ref, data):
    rows = {n: r for n, r in data["cmp_points"].items() if r.get("median_diff_us") not in (None, "")}
    if not rows:
        print(f"[{circuit}] no joined counter comparison -- skipping micros_vs_counter")
        return None
    ns = sorted(rows)
    med = [float(rows[n]["median_diff_us"]) for n in ns]
    iqr = [float(rows[n]["iqr_diff_us"] or 0) / 2 for n in ns]
    pct = [float(rows[n]["median_diff_pct"]) for n in ns]
    q = float(rows[ns[0]].get("micros_quantization_us") or 1.0)
    fig, ax = plt.subplots(figsize=(7, 4.8), layout="constrained")
    ax.axhspan(-q, q, color=ps.GRID_COLOR, alpha=0.7, zorder=1, label=f"micros() resolution (±{q:g} µs)")
    ax.axhline(0, color=ps.REFERENCE_LINE, linewidth=1.0, zorder=2)
    ax.errorbar(ns, med, yerr=iqr, fmt=ps.BOARD_MARKER[board], color=ps.BOARD_COLOR[board], markersize=6,
                markeredgecolor="white", linewidth=1.8, capsize=3, zorder=3, label="micros() minus counter (median, ±IQR/2)")
    for n, m, p in zip(ns, med, pct):
        ax.annotate(f"{p:+.2f}%", (n, m), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=7.5, color=ps.INK_SECONDARY)
    ps.style_axes(ax)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("micros() minus counter, per request (µs)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=1)
    _finish(fig, ax, board, circuit, "board clock vs ESP32 counter, round trip", ref)
    ps.add_footnote(fig, ps.reps_phrase([rows[n]["n_pairs"] for n in ns]).replace("repetitions", "paired requests") + ".")
    return ps.save_figure_png_only(fig, _out(board, circuit, ref), "micros_vs_counter")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=list(ps.BOARD_ORDER))
    ap.add_argument("--circuit", required=True)
    ap.add_argument("--ref", action="store_true", help="read the with_ref bucket (run collected with --ref counter)")
    args = ap.parse_args()
    ps.apply_style()
    data = load(args.board, args.circuit, args.ref)
    generated = []
    fns = [plot_latency_vs_n, plot_outcomes_vs_n, plot_time_per_point] + ([plot_micros_vs_counter] if args.ref else [])
    for fn in fns:
        paths = fn(args.board, args.circuit, args.ref, data)
        if paths:
            generated.extend(paths)
    print(f"\n{len(generated)} figure file(s) written under {_out(args.board, args.circuit, args.ref)} (PNG only)")


if __name__ == "__main__":
    main()
