#!/usr/bin/env python3
# phase2_all_in_one.py  (Phase 2 default; --phase 3 draws the Phase 3 offload round trip)
#
# One chart with every board and every circuit: median time vs n, log-y. Phase 2 = per-rep micros() execution time;
# Phase 3 = e2e offload round trip per request (only points whose session_log status is ok).
# One line, one colour: 12 (board, circuit) series, solid lines, no markers; legend is read per board.
# Reads data/raw/phase2/<board>/<circuit>/with_ref/ read-only. Output: data/figures/phase<N>/all_boards_all_circuits.png
#
# Use:  .venv/bin/python analysis/phase2_all_in_one.py [--phase 2|3] [--no-ref]

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _graph_data as gd  # noqa: E402
from _graph_data import OK, OK_CAPPED  # noqa: E402
from shared import plot_style as ps  # noqa: E402

# 12 colours, one tone family per board, one per (board, circuit); order = BOARD_ORDER x CIRCUIT_ORDER
COLORS = ["#1f77b4", "#8e5bd0", "#56b4e9", "#0b2a6b",     # uno (cool): h_all blue, bell_ghz purple, qft sky, grover navy
          "#ff7f0e", "#d62728", "#f2c230", "#7a3b12",     # esp8266 (warm): orange, red, yellow, brown
          "#2ca02c", "#8bd450", "#00a99d", "#0b4d2a"]     # esp32 (green): green, lime, teal, dark green

# Phase 3 only: last n drawn per board (the Uno runs past n=10 are left out of the chart)
PHASE3_MAX_N = {"uno": 10}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ref", action="store_true", help="read the no_ref bucket (default with_ref)")
    ap.add_argument("--phase", type=int, choices=(2, 3), default=2)
    a = ap.parse_args()
    ref, phase = not a.no_ref, a.phase
    ps.apply_style()
    fig, ax = plt.subplots(figsize=(9.4, 6.2), layout="constrained")
    handles = []
    for bi, b in enumerate(ps.BOARD_ORDER):
        for ci, c in enumerate(ps.CIRCUIT_ORDER):
            col = COLORS[bi * len(ps.CIRCUIT_ORDER) + ci]
            S = gd.PointSet(b, c, phase, ref)
            if not S.raw:
                continue
            if phase == 2:
                out = gd.outcomes_phase2(S)
                vals = gd.values_by_n(S.raw, "exec_time_us")
                ns = [n for n in sorted(vals) if not out or out.get(n, {}).get("cat") in (OK, OK_CAPPED)]
            else:
                ok = {(int(r["n"]), int(r["baud_rate"])): r["status"] == "ok" for r in S.log}
                vals = {}
                for r in S.raw:
                    n = int(r["n"])
                    if ok.get((n, int(r["baud_rate"]))):
                        vals.setdefault(n, []).append(float(r["e2e_latency_us"]))
                ns = [n for n in sorted(vals) if n <= PHASE3_MAX_N.get(b, n)]
            if not ns:
                continue
            ax.plot(ns, [gd.stats(vals[n])[0] for n in ns], color=col, linestyle="-", linewidth=1.8, zorder=2)
            handles.append(Line2D([], [], color=col, linewidth=2, label=f"{ps.BOARD_SHORT[b]} {c}"))
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Median execution time per rep (µs, log scale)" if phase == 2
                  else "Median offload round trip per request (µs, log scale)")
    ax.legend(handles=handles, loc="upper left", fontsize=8.5, ncol=3)
    ps.suptitle(fig, ("Phase 2 -- all boards, all circuits (micros() timing)" if phase == 2
                    else "Phase 3 -- all boards, all circuits (offload round trip, 115200 baud)"), fontsize=10.5)
    path = ps.save_figure_png_only(fig, gd.REPO_ROOT / "data" / "figures" / f"phase{phase}", "all_boards_all_circuits")
    print(path)


if __name__ == "__main__":
    main()
