#!/usr/bin/env python3
# make_analysis_docs.py
#
# Writes docs/analysis/<board>/<circuit>.md (one per board and circuit), docs/analysis/<board>/comparison.md
# (circuits against each other on one board) and docs/analysis/cross_board.md (boards against each other), from the
# CSVs in data/raw/phase2 and data/raw/phase3 (with_ref bucket; read-only). Every number in an OBSERVED section is
# computed here from those CSVs; INTERPRETATION sections are labelled as such and only say what the numbers do not
# contradict. The charts they describe are the PNGs written by phase2_uno_run_plots.py, phase2_cross_board_plots.py
# and phase3_run_plots.py.
#
# Use:  .venv/bin/python analysis/make_analysis_docs.py [--ref]      (default: the with_ref bucket)

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _graph_data as gd  # noqa: E402
from _graph_data import OK, OK_CAPPED, WALL, TIME_LIMITED  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import paths as sp  # noqa: E402

FIT_POINTS = 5
LIMITS = """- One unit of each board (one Uno, one ESP8266, one ESP32); no unit-to-unit spread is measured.
- One run per point set (100 reps per point, fewer where the 2 h per-point cap stopped a point); no run-to-run spread.
- `micros()` times the window the firmware defines around the circuit call (see `firmware/*/src/main.cpp`); the
  contents of that window were not re-verified here. The Uno's `micros()` has 4 us resolution.
- The ESP32 counter was only self-loopback tested and is not externally calibrated; a +17.5 +/- 1.9 ppm calibration
  against the PC clock exists (`data/calibration/counter_20261004.json`) but is not stored in the session sidecars.
  Counter differences are relative to this counter.
- Sessions of one point set can come from several git commits (named on each chart); the working tree was dirty during
  collection, so the exact code state of some sessions cannot be reconstructed.
- Phase 3 times include a PC-side Qiskit Aer simulation of the circuit; the board only times the round trip."""


def rel(p):
    return Path(p).relative_to(gd.REPO_ROOT).as_posix()


def fmt_us(v):
    if v is None:
        return "n/a"
    if v >= 1e9:
        return f"{v / 1e6:.4g} s"
    if v >= 1e6:
        return f"{v / 1e6:.3g} s"
    if v >= 1e3:
        return f"{v / 1e3:.3g} ms"
    return f"{v:.4g} us"


def phase2_section(S):
    out = gd.outcomes_phase2(S)
    vals = gd.values_by_n(S.raw, "exec_time_us")
    ns = [n for n in sorted(vals) if out.get(n, {}).get("cat") in (OK, OK_CAPPED)]
    if not ns:
        return ["No ok point."], {}
    med = {n: statistics.median(vals[n]) for n in ns}
    full = [n for n in ns if out[n]["cat"] == OK]
    info = {"ns": ns, "med": med}
    lines = []
    lines.append(f"- Points with timing: n = {ns[0]}..{ns[-1]} ({len(ns)} points; {len(full)} with 100 reps).")
    capped = [(n, out[n]["reps"]) for n in ns if out[n]["cat"] == OK_CAPPED]
    if capped:
        lines.append("- Stopped by the 2 h per-point cap before 100 reps: " +
                     ", ".join(f"n={n} ({k} reps)" for n, k in capped) + ".")
    lines.append(f"- Median time per rep: {fmt_us(med[ns[0]])} at n={ns[0]}, {fmt_us(med[ns[-1]])} at n={ns[-1]} "
                 f"(x{med[ns[-1]] / med[ns[0]]:.3g}).")
    if len(full) >= 3:
        fit = full[-FIT_POINTS:]
        slope = float(np.polyfit(fit, [np.log2(med[n]) for n in fit], 1)[0])
        ratios = [med[n] / med[n - 1] for n in full if n - 1 in med]
        lines.append(f"- Fit of log2(median) vs n over n={fit[0]}..{fit[-1]}: slope {slope:.2f} doublings per qubit "
                     f"(reference 1.00 = cost proportional to the 2^n amplitudes at a fixed gate count). Successive-n ratio of medians: "
                     f"{min(ratios):.2f} to {max(ratios):.2f}, last {ratios[-1]:.2f}.")
        info["slope"] = slope
    walls = [(n, o) for n, o in out.items() if o["cat"] == WALL]
    for n, o in sorted(walls):
        r = o["row"]
        ev = (f"compile RAM {r.get('compile_ram_pct')}% ({r.get('compile_ram_used_bytes')} of "
              f"{gd.BOARD_SRAM_BYTES[S.board]} B)" if S.board == "uno" and r.get("compile_ram_pct")
              else f"state {r.get('theoretical_bytes')} B")
        lines.append(f"- Memory wall at n={n}: `{o['status']}` recorded; {ev}; hang budget {r.get('timeout_budget_s')} s.")
    tl = sorted(n for n, o in out.items() if o["cat"] == TIME_LIMITED)
    if tl:
        lines.append(f"- Not run, time-limited (1 rep predicted over the {tm.POINT_TIME_CAP_S // 3600} h cap): n = "
                     f"{tl[0]}..{tl[-1]}.")
    att = gd.failed_attempts(S)
    if att:
        lines.append("- Failed attempts before the final outcome: " + "; ".join(
            f"n={n}: {len(k)}x {k[0]}" for n, k in sorted(att.items())) + " (not walls).")
    heap = gd.values_by_n(S.raw, "free_heap_before")
    blocks = gd.values_by_n(S.raw, "largest_block")
    if heap:
        h0, h1 = statistics.median(heap[ns[0]]), statistics.median(heap[ns[-1]]) if ns[-1] in heap else None
        txt = f"- Free heap before the run: {h0:.0f} B at n={ns[0]}"
        if h1 is not None:
            txt += f", {h1:.0f} B at n={ns[-1]}"
        if blocks and ns[-1] in blocks:
            txt += f"; largest free block {statistics.median(blocks[ns[-1]]):.0f} B at n={ns[-1]}"
        lines.append(txt + ".")
    pts = [r for r in S.points if r["status"] in ("ok", "failed", "retrying")]
    if pts:
        tot = sum(gd.f(r.get("build_compile_s"), 0.0) + gd.f(r.get("upload_s"), 0.0) for r in pts)
        lines.append(f"- Reflash overhead: {tot:.0f} s of compile + upload over {len(pts)} attempts.")
    ok_c, why = S.physical_counter() if S.ref else (False, "no_ref bucket")
    if ok_c:
        cmp_ = gd.read_rows(S.dir / "ref" / "ref_compare.csv")
        pts_c = {int(r["n"]): r for r in gd.read_rows(S.dir / "ref" / "ref_compare_points.csv")}
        by = {}
        for r in cmp_:
            by.setdefault(int(r["n"]), []).append((float(r["diff_us"]), float(r["diff_pct"])))
        use = [n for n in sorted(by) if len(by[n]) >= gd.MIN_PAIRS and pts_c.get(n, {}).get("ref_status") in
               ("ok", "anomaly", "count_mismatch")]
        if use:
            mu = [statistics.median(d[0] for d in by[n]) for n in use]
            mp = [statistics.median(d[1] for d in by[n]) for n in use]
            flagged = sum(1 for n in use if pts_c[n]["ref_status"] != "ok")
            lines.append(f"- micros() minus counter, per-point median: {min(mu):.4g} to {max(mu):.4g} us "
                         f"({min(mp):.4g} to {max(mp):.4g} %) over {len(use)} points; counter flagged an anomaly on "
                         f"{flagged} of them.")
            info["counter_pct"] = (min(mp), max(mp))
    else:
        lines.append(f"- No counter comparison charted ({why}).")
    return lines, info


def phase3_section(S):
    lat = {}
    for r in S.raw:
        lat.setdefault((int(r["n"]), int(r["baud_rate"])), []).append(float(r["e2e_latency_us"]))
    ok = sorted(k for k in lat if S.ok_log.get(k, {}).get("status") == "ok")
    if not ok:
        return ["No ok point."], {}
    ns = [k[0] for k in ok]
    med = {k[0]: statistics.median(lat[k]) for k in ok}
    lines = [f"- Points: n = {ns[0]}..{ns[-1]} ({len(ok)} points, {sum(len(lat[k]) for k in ok)} requests, baud "
             f"{', '.join(str(b) for b in S.bauds)}).",
             f"- Median round trip per request: {fmt_us(med[ns[0]])} at n={ns[0]}, {fmt_us(med[ns[-1]])} at n={ns[-1]}."]
    capped = [(k[0], len(lat[k])) for k in ok if len(lat[k]) < tm.REPS]
    if capped:
        lines.append("- Stopped by the per-point cap before 100 requests: " + ", ".join(
            f"n={n} ({k})" for n, k in capped) + ".")
    nr = sorted({int(r["n"]) for r in S.log if r["status"].startswith("skipped")} - set(ns))
    if nr:
        lines.append(f"- Not run (PC simulation predicted over the cap or the PC's memory): n = {nr}.")
    rows = p3_breakdown(S)
    if rows:
        last = rows[-1]
        tot = last[2] + last[3] + last[4]
        outside = statistics.median(r[4] for r in rows)
        lines.append(f"- Time per request at n={last[0]}: PC simulation {fmt_us(last[2])} ({100 * last[2] / tot:.0f} % of the "
                     f"point's time), rest of the board-timed round trip {fmt_us(last[3])}, outside the timed round trip "
                     f"{fmt_us(last[4])}; median outside-the-round-trip time over all n: {fmt_us(outside)}."
                     + (" (At this n the PC's simulation time is not below the board's own round-trip sum, "
                        "so the remainder is shown as 0; clock difference between PC and board.)" if last[3] == 0 else ""))
    crc = sum(1 for r in S.raw if r["crc_error"] == "1") + sum(
        int(gd.f(S.ok_log.get(k, {}).get("frames_dropped_bad_crc"), 0)) for k in S.ok_log)
    tout = sum(1 for r in S.raw if r["timed_out"] == "1")
    bad = [int(r["n"]) for r in S.points if r.get("status") == "failed"]
    lines.append(f"- Reliability: {crc} CRC errors (incl. dropped frames), {tout} timeouts, failed points: "
                 f"{bad if bad else 'none'}.")
    L = gd.PointSet(S.board, S.circuit, 2, S.ref)
    lout = gd.outcomes_phase2(L)
    lv = gd.values_by_n(L.raw, "exec_time_us")
    common = [n for n in ns if lout.get(n, {}).get("cat") in (OK, OK_CAPPED)]
    cross = next((n for n in common if med[n] < statistics.median(lv[n])), None)
    if common:
        lines.append(f"- Local (Phase 2) vs offload (Phase 3), n={common[0]}..{common[-1]}: " + (
            f"offload median first below local at n={cross}." if cross else
            "no crossover; offload slower at every common n."))
    return lines, {"med": med, "cross": cross}


def p3_breakdown(S):
    rows = []
    lat = {}
    for r in S.raw:
        lat.setdefault((int(r["n"]), int(r["baud_rate"])), []).append(float(r["e2e_latency_us"]))
    for (n, b), v in sorted(lat.items()):
        p = S.ok_points.get((n, b))
        if not p:
            continue
        sim, dev = gd.f(p.get("pc_sim_s_total")), gd.f(p.get("device_exec_s"))
        if sim is None or dev is None:
            continue
        rt, k = sum(v) / 1e6, len(v)
        rows.append((n, k, sim / k * 1e6, max(rt - sim, 0.0) / k * 1e6, max(dev - rt, 0.0) / k * 1e6))
    return rows


def write_circuit_doc(board, circuit, ref):
    S2 = gd.PointSet(board, circuit, 2, ref)
    p2_lines, i2 = phase2_section(S2) if S2.raw else (["No Phase 2 data."], {})
    S3 = p3_load(board, circuit, ref)
    p3_lines, i3 = phase3_section(S3) if S3.raw else (["No Phase 3 data."], {})
    f2, f3 = sp.figures_dir(board, circuit, ref, phase=2), sp.figures_dir(board, circuit, ref, phase=3)
    interp = []
    if "slope" in i2:
        s = i2["slope"]
        interp.append(f"The fitted slope ({s:.2f} doublings per qubit) is {'above' if s > 1.05 else 'below' if s < 0.95 else 'close to'} "
                      "the 1.00 reference (cost proportional to the 2^n amplitudes at a fixed gate count). For circuits "
                      "whose gate count grows with n (qft, grover) a slope above 1 is what a growing gate count would give; "
                      "a fixed per-call overhead at small n or memory effects at large n would also move it. None of "
                      "these readings was tested here (`analysis/phase2_gate_cost_fit.py` fits a gate-cost model).")
    if i3.get("cross") is not None:
        interp.append(f"Offload overtakes local execution from n={i3['cross']} in the measured range; this compares a "
                      "local run of the circuit with a serial round trip whose cost is dominated by the PC simulation at "
                      "larger n, so it says where offloading pays on this link, not that the board is slower at the "
                      "circuit itself.")
    elif i3:
        interp.append("Offloading did not beat local execution at any n measured in both phases; the offload cost "
                      "contains a fixed serial and pacing part that local execution does not have.")
    if "counter_pct" in i2:
        lo, hi = i2["counter_pct"]
        interp.append(f"Where the counter comparison exists, micros() reads {lo:.3g} to {hi:.3g} % relative to the "
                      "counter; relative to this uncalibrated counter only. Differences of a few microseconds at small n "
                      "are at the resolution of micros() on the board.")
    if not interp:
        interp.append("None beyond what the OBSERVED numbers state.")
    txt = [f"# {ps.BOARD_LABEL[board]} -- {ps.CIRCUIT_LABEL.get(circuit, circuit)}", "",
           f"Generated by `analysis/make_analysis_docs.py` from `data/raw/phase2|3/{board}/{circuit}/with_ref/`. "
           f"Charts: `{rel(f2)}/`, `{rel(f3)}/`. Collected under {S2.commit_note()} (Phase 2), {S3.commit_note()} (Phase 3).",
           "", "## Phase 2 (on-board execution, micros())", "", "### Observed", ""] + p2_lines + [
           "", "Charts: `exec_time_vs_n.png`, `outcomes_vs_n.png`, `memory_vs_n.png`, `time_per_point.png`, `scaling.png`"
           + (", `micros_vs_counter.png`" if ref else "") + ".", "", "## Phase 3 (offload round trip)", "", "### Observed", ""] + p3_lines + [
           "", "Charts: `time_breakdown.png`, `latency_vs_n.png`, `reliability.png`, `offload_vs_local.png`.", "",
           "## Interpretation (not tested)", ""] + [f"- {x}" for x in interp] + ["", "## Limitations", "", LIMITS, ""]
    path = sp.analysis_doc_path(board, circuit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(txt))
    return path, i2, i3


def p3_load(board, circuit, ref):
    import phase3_run_plots as p3
    return p3.load(board, circuit, ref)


def write_comparison(board, infos):
    rows = ["| circuit | Phase 2 n range | median at last n | slope (doublings/qubit) | Phase 3 crossover n |",
            "|---|---|---|---|---|"]
    for c, (i2, i3) in infos.items():
        if not i2:
            continue
        ns = i2["ns"]
        slope = f"{i2['slope']:.2f}" if "slope" in i2 else "n/a"
        cross = i3.get("cross") if i3.get("cross") is not None else "none"
        rows.append(f"| {c} | {ns[0]}..{ns[-1]} | {fmt_us(i2['med'][ns[-1]])} | {slope} | {cross} |")
    txt = [f"# {ps.BOARD_LABEL[board]} -- circuits compared", "",
           "Generated by `analysis/make_analysis_docs.py`; per-circuit detail in the sibling files.", "",
           "## Observed", ""] + rows + ["", f"Chart: `{rel(sp.figures_dir(board, ref=True, phase=2))}/all_algorithms_so_far.png`.",
           "", "## Interpretation (not tested)", "",
           "- Circuits with more gates per qubit cost more per rep at the same n; the table shows the measured order, "
           "not a gate-cost model (`analysis/phase2_gate_cost_fit.py` fits one).", "", "## Limitations", "", LIMITS, ""]
    path = sp.analysis_doc_path(board)
    path.write_text("\n".join(txt))
    return path


def write_cross_board(ref):
    rows = ["| circuit | board | n range | median at last n | wall / limit |", "|---|---|---|---|---|"]
    for c in ps.CIRCUIT_ORDER:
        for b in ps.BOARD_ORDER:
            S = gd.PointSet(b, c, 2, ref)
            if not S.raw:
                continue
            out = gd.outcomes_phase2(S)
            vals = gd.values_by_n(S.raw, "exec_time_us")
            ns = [n for n in sorted(vals) if out.get(n, {}).get("cat") in (OK, OK_CAPPED)]
            lim = ("memory wall n=" + str(min(n for n, o in out.items() if o["cat"] == WALL))) if any(
                o["cat"] == WALL for o in out.values()) else (
                "time-limited from n=" + str(min(n for n, o in out.items() if o["cat"] == TIME_LIMITED))
                if any(o["cat"] == TIME_LIMITED for o in out.values()) else "none recorded")
            rows.append(f"| {c} | {ps.BOARD_SHORT[b]} | {ns[0]}..{ns[-1]} | {fmt_us(statistics.median(vals[ns[-1]]))} | {lim} |")
    order = ["", "Order of the boards at the largest n that all three have ok points for (fastest first):", ""]
    for c in ps.CIRCUIT_ORDER:
        meds = {}
        for b in ps.BOARD_ORDER:
            S = gd.PointSet(b, c, 2, ref)
            out = gd.outcomes_phase2(S)
            vals = gd.values_by_n(S.raw, "exec_time_us")
            meds[b] = {n: statistics.median(vals[n]) for n in vals if out.get(n, {}).get("cat") in (OK, OK_CAPPED)}
        if all(meds.values()):
            n = max(set.intersection(*[set(m) for m in meds.values()]))
            rank = sorted(meds, key=lambda b: meds[b][n])
            order.append(f"- {c}, n={n}: " + " < ".join(f"{ps.BOARD_SHORT[b]} ({fmt_us(meds[b][n])})" for b in rank))
    txt = ["# Boards compared (Phase 2)", "", "Generated by `analysis/make_analysis_docs.py`.", "", "## Observed", ""] + rows + order + [
           "", "Charts: `data/figures/phase2/compare_<circuit>.png`.", "", "## Interpretation (not tested)", "",
           "- The boards differ in clock rate, floating-point hardware and RAM; these runs show the measured order but "
           "do not separate those causes.", "", "## Limitations", "", LIMITS, ""]
    path = gd.REPO_ROOT / "docs" / "analysis" / "cross_board.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(txt))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", action="store_true", help="read the with_ref bucket (all collected data)")
    a = ap.parse_args()
    written = []
    for b in ps.BOARD_ORDER:
        infos = {}
        for c in ps.CIRCUIT_ORDER:
            if not (gd.PointSet(b, c, 2, a.ref).raw or gd.PointSet(b, c, 3, a.ref).raw):
                continue
            path, i2, i3 = write_circuit_doc(b, c, a.ref)
            infos[c] = (i2, i3)
            written.append(path)
        if infos:
            written.append(write_comparison(b, infos))
    written.append(write_cross_board(a.ref))
    print("\n".join(rel(p) for p in written))


if __name__ == "__main__":
    main()
