#!/usr/bin/env python3
# phase3_run_plots.py
#
# Per-run PNG charts for one Phase 3 (offload) algorithm on one board, generated right after its sweep
# (pc/run.py calls it) and re-runnable by hand. Read-only against data/raw/phase3/<board>/<circuit>/<bucket>/
# (raw.csv, session_log.csv, points.csv, env/*.json) and data/raw/phase2/ (for the local comparison only).
# NO counter reference is read or drawn: Phase 3 is decided to run without the counter, so any ref/ files that
# exist next to the data are ignored and only counted in the console summary.
#
# Output: data/figures/phase3/<board>/<circuit>/*.png (PNG only)
#   time_breakdown.png   where the time of a point goes: share (%) and absolute per request of PC simulation,
#                        the rest of the board-timed round trip, and time outside the timed round trip
#   latency_vs_n.png     round trip per request vs n: median + IQR + every request, one line per baud rate,
#                        with the PC's measured simulation time per request
#   reliability.png      CRC error rate and timeouts per (n, baud), requests per point, failed/retried points listed
#   offload_vs_local.png Phase 2 local time per rep vs Phase 3 round trip per request at the same n (same board and
#                        circuit, only where both exist), crossover n marked or "none in the measured range"
#
# Units (read from pc/phase3_offload/sweep.py): points.csv columns are TOTALS over the point's requests --
#   device_exec_s (sweep.py:547) = wall time of the whole request loop of the point;
#   pc_sim_s_total (:595)        = sum of the PC's Qiskit Aer simulation times, one per request;
#   serial_transfer_s_total (:597) = max(device_exec_s - pc_sim_s_total, 0): a remainder, not a measured transfer.
# raw.csv e2e_latency_us is the board's own micros() round trip PER REQUEST.
#
# Use:  .venv/bin/python analysis/phase3_run_plots.py --board esp8266 --circuit h_all [--ref]

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _graph_data as gd  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import paths as sp  # noqa: E402

CAP_TEXT = f"{tm.POINT_TIME_CAP_S / 3600:g} h"
BAUD_LS = ["-", "--", ":", "-."]
NOTE = "PC simulates the circuit (Qiskit Aer); the board times only the round trip and frame integrity."


def subtitle(S):
    return f"{ps.BOARD_SHORT[S.board]}, Phase 3 (offload), board micros() round trip, no counter reference"


def finish(fig, ax, S, what):
    fig.suptitle(f"{ps.BOARD_LABEL[S.board]} -- {ps.CIRCUIT_LABEL.get(S.circuit, S.circuit)} -- {what} "
                 f"(target REPS={tm.REPS}, {S.commit_note()})", fontsize=10.5)
    axes = list(np.ravel(ax)) if isinstance(ax, (list, tuple, np.ndarray)) else [ax]
    axes[0].text(0.0, 1.06, subtitle(S), transform=axes[0].transAxes, fontsize=8.5, color=ps.INK_SECONDARY)


def out_dir(S):
    return sp.figures_dir(S.board, S.circuit, S.ref, phase=3)


def save(fig, S, stem):
    return ps.save_figure_png_only(fig, out_dir(S), stem)


def load(board, circuit, ref):
    S = gd.PointSet(board, circuit, 3, ref)
    gd.need(S.raw, ["n", "baud_rate", "rep", "e2e_latency_us", "crc_error", "timed_out"], "phase 3 raw.csv")
    S.ok_log = {}                       # {(n, baud): row}, later rows of one key win (a re-run appends a newer row)
    for r in S.log:
        S.ok_log[(int(r["n"]), int(r["baud_rate"]))] = r
    S.ok_points = {}
    for r in S.points:
        if r.get("status") == "ok":
            S.ok_points[(int(r["n"]), int(r["baud"]))] = r
    S.bauds = sorted({int(r["baud_rate"]) for r in S.raw})
    return S


def lat_by_key(S):
    out = {}
    for r in S.raw:
        out.setdefault((int(r["n"]), int(r["baud_rate"])), []).append(float(r["e2e_latency_us"]))
    return out


def not_run(S):
    """n values of points that were not run (PC simulation predicted over the cap / the PC's memory)."""
    return sorted({int(r["n"]) for r in S.log if r["status"].startswith("skipped")} - {k[0] for k in lat_by_key(S)})


# --------------------------------------------------------------------------- time breakdown

def breakdown(S, baud):
    """[(n, reps, pc_sim_us, rt_rest_us, outside_us, clipped)] per request, from totals over the point."""
    lat = lat_by_key(S)
    rows = []
    for (n, b), v in sorted(lat.items()):
        if b != baud or (n, b) not in S.ok_points:
            continue
        p = S.ok_points[(n, b)]
        sim, dev = gd.f(p.get("pc_sim_s_total")), gd.f(p.get("device_exec_s"))
        if sim is None or dev is None:
            continue
        k = len(v)
        rt = sum(v) / 1e6
        rest = rt - sim
        clipped = rest < 0
        rows.append((n, k, sim / k * 1e6, max(rest, 0.0) / k * 1e6, max(dev - rt, 0.0) / k * 1e6, clipped))
    return rows


def plot_time_breakdown(S):
    paths = []
    for baud in S.bauds:
        rows = breakdown(S, baud)
        if not rows:
            print(f"[{S.circuit}] no ok points with telemetry at baud {baud} -- skipping time_breakdown")
            continue
        ns = [r[0] for r in rows]
        comp = np.array([[r[2], r[3], r[4]] for r in rows])
        names = ["PC simulation (Qiskit Aer)", "rest of the board-timed round trip", "outside the timed round trip"]
        hatches = [None, "//", ".."]
        greys = [ps.BOARD_COLOR[S.board], ps.INK_MUTED, "#d9d9d9"]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 5.0), layout="constrained")
        share = comp / comp.sum(axis=1, keepdims=True) * 100
        bottom = np.zeros(len(ns))
        for i in range(3):
            a1.bar(ns, share[:, i], bottom=bottom, color=greys[i], hatch=hatches[i], edgecolor="white", label=names[i],
                   zorder=3)
            bottom += share[:, i]
        a1.set_ylim(0, 100)
        a1.set_ylabel("Share of the point's time (%)")
        a1.set_xticks(ns)
        a1.set_xlabel("Number of qubits, n (qubits)")
        ps.style_axes(a1)
        for i, (c, mk) in enumerate(zip(range(3), ("o", "s", "^"))):
            vals = np.where(comp[:, i] > 0, comp[:, i], np.nan)
            a2.plot(ns, vals, linestyle=("-", "--", ":")[i], marker=mk, color=ps.BOARD_COLOR[S.board] if i == 0 else
                    (ps.INK_SECONDARY if i == 1 else ps.INK_MUTED), markersize=5.5, label=names[i], zorder=3)
        a2.set_yscale("log")
        ps.style_axes(a2, log_y=True)
        a2.set_xticks(ns)
        a2.set_xlabel("Number of qubits, n (qubits)")
        a2.set_ylabel("Time per request (µs, log scale)")
        a2.legend(loc="upper left", fontsize=8)
        h, lab = a1.get_legend_handles_labels()
        a1.legend(h, lab, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=1, fontsize=8.5)
        finish(fig, [a1, a2], S, f"time breakdown per request (baud {baud})")
        clipped = [r[0] for r in rows if r[5]]
        gd.footnote(fig, "Per request = point totals / requests. PC simulation = pc_sim_s_total; rest of round trip = "
                        "sum of the board's own round trips - PC simulation; outside = device_exec_s - sum of round "
                        "trips (wall time of the loop; includes the board's pacing between requests). The points.csv "
                        "column serial_transfer_s_total is only wall - PC simulation and is not used."
                        + (f" At n={clipped} the PC time exceeds the board's round-trip sum (clock difference); "
                           "that remainder is drawn as 0." if clipped else ""))
        paths += save(fig, S, "time_breakdown" if len(S.bauds) == 1 else f"time_breakdown_{baud}")
    return paths


# --------------------------------------------------------------------------- latency

def plot_latency_vs_n(S):
    lat = lat_by_key(S)
    ok_keys = [k for k in sorted(lat) if S.ok_log.get(k, {}).get("status") == "ok"]
    if not ok_keys:
        print(f"[{S.circuit}] no ok points -- skipping latency_vs_n")
        return None
    col = ps.BOARD_COLOR[S.board]
    fig, ax = plt.subplots(figsize=(7.6, 5.4), layout="constrained")
    all_vals = []
    for bi, baud in enumerate(S.bauds):
        keys = [k for k in ok_keys if k[1] == baud]
        if not keys:
            continue
        ls = BAUD_LS[bi % 4]
        ns = [k[0] for k in keys]
        st = {k: gd.stats(lat[k]) for k in keys}
        for k in keys:
            ax.plot(np.full(len(lat[k]), k[0]), lat[k], linestyle="none", marker=".", markersize=3, color=ps.INK_MUTED,
                    alpha=0.25, zorder=1, rasterized=True)
            all_vals += lat[k]
        ax.plot(ns, [st[k][0] for k in keys], linestyle=ls, color=col, linewidth=1.5, zorder=2,
                label=f"board round trip, baud {baud} (median, IQR bars)")
        for k in keys:
            med, q1, q3 = st[k]
            if q1 is not None:
                ax.errorbar([k[0]], [med], yerr=[[med - q1], [q3 - med]], color=col, linewidth=1.6, capsize=2.5, zorder=3)
            capped = len(lat[k]) < tm.REPS
            ax.plot([k[0]], [med], linestyle="none", marker=ps.BOARD_MARKER[S.board], markersize=6.5, zorder=4,
                    markerfacecolor="white" if capped else col, markeredgecolor=col if capped else "white",
                    markeredgewidth=1.3 if capped else 0.6)
    sim = {n: float(p["pc_sim_s_median"]) * 1e6 for (n, b), p in S.ok_points.items()
           if gd.f(p.get("pc_sim_s_median")) is not None and (n, b) in lat}
    if sim:
        sn = sorted(sim)
        ax.plot(sn, [sim[n] for n in sn], linestyle="--", marker="x", color=ps.INK_SECONDARY, linewidth=1.1,
                label="PC simulation time per request (measured median)", zorder=2)
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    nr = not_run(S)
    lo, hi = min(all_vals), max(all_vals)
    ax.set_ylim(lo / 2.5, hi * 10 ** (0.8 if nr else 0.3))
    tr = ax.get_xaxis_transform()
    for n in nr:
        ax.plot([n], [0.95], transform=tr, linestyle="none", marker="*", markersize=10, markerfacecolor="white",
                markeredgecolor=ps.INK_PRIMARY, markeredgewidth=1.2, clip_on=False)
    ax.set_xticks(sorted({k[0] for k in ok_keys} | set(nr)))
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Round trip per request (µs, log scale)")
    h, lab = ax.get_legend_handles_labels()
    if any(len(lat[k]) < tm.REPS for k in ok_keys):
        h.append(Line2D([], [], linestyle="none", marker="o", markerfacecolor="white", markeredgecolor=ps.INK_PRIMARY,
                        markeredgewidth=1.3))
        lab.append(f"< 100 requests ({CAP_TEXT} per-point cap)")
    h.append(Line2D([], [], linestyle="none", marker=".", color=ps.INK_MUTED, alpha=0.6))
    lab.append("individual request")
    if nr:
        h.append(Line2D([], [], linestyle="none", marker="*", markerfacecolor="white", markeredgecolor=ps.INK_PRIMARY))
        lab.append("not run (PC simulation predicted over the cap or the PC's memory), top strip")
    ax.legend(h, lab, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=1, fontsize=8.5)
    finish(fig, ax, S, "offload round-trip latency vs n")
    gd.footnote(fig, gd.reps_text(len(lat[k]) for k in ok_keys).replace("repetitions", "requests") +
                    "; bar = IQR (25th-75th pct); all requests used (rep 0 included).")
    return save(fig, S, "latency_vs_n")


# --------------------------------------------------------------------------- reliability

def plot_reliability(S):
    lat = lat_by_key(S)
    if not lat:
        print(f"[{S.circuit}] no raw rows -- skipping reliability")
        return None
    crc, tout, reqs = {}, {}, {}
    for r in S.raw:
        k = (int(r["n"]), int(r["baud_rate"]))
        reqs[k] = reqs.get(k, 0) + 1
        crc[k] = crc.get(k, 0) + (r["crc_error"] == "1")
        tout[k] = tout.get(k, 0) + (r["timed_out"] == "1")
    dropped = {k: int(gd.f(S.ok_log.get(k, {}).get("frames_dropped_bad_crc"), 0)) for k in reqs}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.6, 6.4), sharex=True, layout="constrained",
                                 height_ratios=[1, 1])
    col = ps.BOARD_COLOR[S.board]
    for bi, baud in enumerate(S.bauds):
        keys = sorted(k for k in reqs if k[1] == baud)
        ns = [k[0] for k in keys]
        ls = BAUD_LS[bi % 4]
        a1.plot(ns, [100 * (crc[k] + dropped[k]) / reqs[k] for k in keys], linestyle=ls, marker="o", color=ps.INK_PRIMARY,
                markersize=6, label=f"CRC errors incl. dropped frames, baud {baud}", zorder=3)
        a1.plot(ns, [100 * tout[k] / reqs[k] for k in keys], linestyle=ls, marker="s", color=ps.INK_MUTED,
                markerfacecolor="white", markersize=6, label=f"timeouts, baud {baud}", zorder=3)
        a2.bar(ns, [reqs[k] for k in keys], color=col, hatch=None, label="requests answered", zorder=3)
    top = max([100 * (crc[k] + dropped[k]) / reqs[k] for k in reqs] + [100 * tout[k] / reqs[k] for k in reqs] + [1.0])
    a1.set_ylim(-0.05 * top, top * 1.1)
    a1.set_ylabel("Rate (% of requests)")
    ps.style_axes(a1)
    a1.legend(loc="center right", fontsize=8.5)
    a2.axhline(tm.REPS, color=ps.INK_PRIMARY, linestyle="--", linewidth=1.0)
    a2.set_ylabel("Requests per point")
    a2.set_xlabel("Number of qubits, n (qubits)")
    a2.set_xticks(sorted({k[0] for k in reqs}))
    ps.style_axes(a2)
    tot, tcrc, tto = sum(reqs.values()), sum(crc.values()) + sum(dropped.values()), sum(tout.values())
    bad = [(int(r["n"]), r.get("failure_type", "")) for r in S.points if r.get("status") == "failed"]
    retried = [(int(r["n"]), int(r["retry_count"])) for r in S.points
               if r.get("status") == "ok" and gd.f(r.get("retry_count"), 0) > 0]
    listing = (f"{len(reqs)} points, {tot} requests: {tcrc} CRC errors, {tto} timeouts. "
               f"Failed points: {bad if bad else 'none'}; retried points: {retried if retried else 'none'}.")
    finish(fig, [a1, a2], S, "link reliability per n")
    gd.footnote(fig, listing + (" Points below 100 requests were stopped by the per-point time cap."
                                     if any(v < tm.REPS for v in reqs.values()) else ""))
    return save(fig, S, "reliability")


# --------------------------------------------------------------------------- offload vs local

def plot_offload_vs_local(S):
    L = gd.PointSet(S.board, S.circuit, 2, S.ref)
    lout = gd.outcomes_phase2(L)
    lvals = gd.values_by_n(L.raw, "exec_time_us")
    lns = {n for n in lvals if not lout or lout.get(n, {}).get("cat") in (gd.OK, gd.OK_CAPPED)}
    lat = lat_by_key(S)
    bauds = S.bauds
    if not lns or not lat:
        print(f"[{S.circuit}] Phase 2 or Phase 3 data missing -- skipping offload_vs_local")
        return None
    baud = max(bauds)                                    # the highest baud with data (only one in this dataset)
    ons = {k[0] for k in lat if k[1] == baud and S.ok_log.get(k, {}).get("status") == "ok"}
    common = sorted(lns & ons)
    if not common:
        print(f"[{S.circuit}] no n with both local and offload data -- skipping offload_vs_local")
        return None
    col = ps.BOARD_COLOR[S.board]
    fig, ax = plt.subplots(figsize=(7.8, 5.6), layout="constrained")
    series = (("local: board runs the circuit, time per rep (Phase 2)", lvals, "-", ps.BOARD_MARKER[S.board], True),
              (f"offload: round trip per request, baud {baud} (Phase 3)", {n: lat[(n, baud)] for n in ons}, "--",
               "D", False))
    meds = {}
    for label, vals, ls, mk, filled in series:
        ns = [n for n in common if n in vals]
        st = {n: gd.stats(vals[n]) for n in ns}
        meds[label[:5]] = {n: st[n][0] for n in ns}
        ax.plot(ns, [st[n][0] for n in ns], linestyle=ls, color=col, linewidth=1.4, zorder=2)
        for n in ns:
            med, q1, q3 = st[n]
            if q1 is not None:
                ax.errorbar([n], [med], yerr=[[med - q1], [q3 - med]], color=col, linewidth=1.5, capsize=2.5, zorder=3)
            ax.plot([n], [med], linestyle="none", marker=mk, markersize=6.5, zorder=4,
                    markerfacecolor=col if filled else "white", markeredgecolor="white" if filled else col,
                    markeredgewidth=0.6 if filled else 1.3)
    local, off = meds["local"], meds["offlo"]
    cross = next((n for n in common if off[n] < local[n]), None)
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    if cross is not None:
        ax.axvline(cross, color=ps.INK_PRIMARY, linestyle=":", linewidth=1.1, zorder=1)
        ax.annotate(f"crossover: offload median first below local at n={cross}", (cross, 0.10),
                    xycoords=("data", "axes fraction"), xytext=(5, 0), textcoords="offset points", ha="left",
                    fontsize=8.5)
        verdict = f"Crossover at n={cross} (first n where the offload median is below the local median)."
    else:
        verdict = (f"No crossover in the measured range n={common[0]}..{common[-1]}: the offload round trip is "
                   "slower than local execution at every n measured in both phases.")
    ax.set_xticks(common)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Time (µs, log scale)")
    h = [Line2D([], [], linestyle="-", marker=ps.BOARD_MARKER[S.board], color=col, label=series[0][0]),
         Line2D([], [], linestyle="--", marker="D", markerfacecolor="white", color=col, markeredgewidth=1.3,
                label=series[1][0])]
    ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1, fontsize=8.5)
    ax.text(0.5, 0.02, NOTE, transform=ax.transAxes, ha="center", va="bottom", fontsize=7.5, color=ps.INK_SECONDARY)
    note = f"Phase 2 {L.commit_note()}; Phase 3 {S.commit_note()}"
    fig.suptitle(f"{ps.BOARD_LABEL[S.board]} -- {ps.CIRCUIT_LABEL.get(S.circuit, S.circuit)} -- local vs offload "
                 f"(target REPS={tm.REPS}, {note})", fontsize=10)
    ax.text(0.0, 1.06, f"{ps.BOARD_SHORT[S.board]}, micros() timing on the board in both phases, no counter reference",
            transform=ax.transAxes, fontsize=8.5, color=ps.INK_SECONDARY)
    gd.footnote(fig, verdict + " Different quantities: local = the board computes one circuit run; offload = "
                    "serial request, PC simulation and reply. Only n measured in both phases are drawn.")
    return save(fig, S, "offload_vs_local")


def ignored_reference_summary(S):
    ref = Path(S.dir) / "ref"
    n = len(list(ref.glob("*.csv"))) if ref.exists() else 0
    if n:
        print(f"[{S.circuit}] note: {n} reference file(s) in {ref.relative_to(gd.REPO_ROOT)} ignored "
              "(Phase 3 charts do not use the counter)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=list(ps.BOARD_ORDER))
    ap.add_argument("--circuit", required=True)
    ap.add_argument("--ref", action="store_true", help="read the with_ref bucket (run collected with --ref counter)")
    args = ap.parse_args()
    ps.apply_style()
    try:
        S = load(args.board, args.circuit, args.ref)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
    generated = []
    for fn in (plot_time_breakdown, plot_latency_vs_n, plot_reliability, plot_offload_vs_local):
        r = fn(S)
        if r:
            generated.extend(r)
    ignored_reference_summary(S)
    print(f"\n{len(generated)} figure file(s) written under {out_dir(S)} (PNG only)")


if __name__ == "__main__":
    main()
