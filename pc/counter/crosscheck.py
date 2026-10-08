# crosscheck.py -- micros() vs counter comparison (successor of analysis/la_crosscheck.py: the
# sequence join, the refuse-rather-than-guess rule and the two-part "flagged" threshold are kept).
#
# Join: counter pulse i pairs with raw.csv rep i of the same point (sequence order, no timestamps).
# Glitch-flagged pulses (flags bit 0) are dropped from the pairing. The remaining pulse count must
# equal the expected reps and raw.csv must hold at least that many reps, otherwise the point is
# REFUSED for comparison: micros() data and the point status are never touched.
#
# diff_us  = micros_us - counter_us   (positive: the board's own timer reads longer)
# diff_pct = diff_us / counter_us * 100
# flagged  = |median diff %| > max_relative_pct AND |median diff us| > the board's micros() tick
#            (a one-tick difference is quantisation, not error; same rule as la_crosscheck.py)

import csv
import statistics
from pathlib import Path

from counter import ref_schema as rs

DEFAULT_MAX_RELATIVE_PCT = 5.0


def load_micros(raw_csv, circuit, n):
    """exec_time_us per rep (ordered by rep) for one point from raw.csv; None if absent."""
    p = Path(raw_csv)
    if not p.exists():
        return None
    rows = []
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                if r.get("circuit") == circuit and int(r["n"]) == n:
                    rows.append((int(r["rep"]), float(r["exec_time_us"])))
            except (KeyError, ValueError):
                continue
    if not rows:
        return None
    rows.sort(key=lambda t: t[0])
    return [v for _, v in rows]


def _iqr(xs):
    if len(xs) < 4:
        return 0.0
    q = statistics.quantiles(xs, n=4)
    return q[2] - q[0]


def split_runs(pulses, min_gap_s=0.2, gap_factor=50):
    """The Uno restarts its firmware when the sweep opens the serial port (DTR reset) after the restart caused by the
    upload, so the counter can see two runs (the first one usually cut short). Pulses are split where the idle gap
    between the end of one pulse and the next rise is longer than `min_gap_s` AND `gap_factor` times the median in-run
    gap. min_gap_s is 0.2 s since 2026-10-06: the ESP8266 restart gap measured in data/raw/phase2/esp8266 is ~0.318 s
    (reset to first pulse), below the old 0.5 s, so its runs were never split (129, 105, 156 ... pulses for 100 reps). The sweep reads the rows of the LAST run, so only the last run is paired. -> list of runs (lists of PULSE tuples)."""
    if len(pulses) < 3:
        return [list(pulses)]
    gaps = []
    for a, b in zip(pulses, pulses[1:]):
        gaps.append(b[1] - (a[1] + a[3] // 1000))      # rise_us(next) - (rise_us + width_us)
    med = sorted(gaps)[len(gaps) // 2]
    thr = max(min_gap_s * 1e6, gap_factor * max(med, 1))
    runs, cur = [], [pulses[0]]
    for g, p in zip(gaps, pulses[1:]):
        if g > thr:
            runs.append(cur); cur = []
        cur.append(p)
    runs.append(cur)
    return runs


MAX_PARTIAL_SLOTS = 2   # at most this many glitch-occupied rep slots may be skipped in a join
ALIGN_MIN_MATCHED = 0.5  # width alignment must pair at least this fraction of the reps, else the point is refused (noise can destroy some real pulses; each match is by exact width, so a partial join is still sound and says so)


def align_by_width(pulses, micros_us, reps, tol_us=200.0, tol_rel=2e-4):
    """Phase 3 only. The counter may see extra pulses (noise bursts: width ~0 or a stale 2^32-tick width, observed on the
    ESP8266 grover n=10 run) that make the plain sequence join impossible. The board's own round trips are long and
    distinct, so walk the reps in order and take, for each, the next clean counter pulse whose width is within
    max(tol_us, tol_rel x latency) of the board's e2e_latency_us (observed micros()-counter difference: 2-1100 us, under 0.01 %).
    Pulses that match no rep are ignored; reps with no match are skipped. -> [(rep, pulse)] in rep order."""
    cand = [p for p in pulses if not (p[5] & 1)]
    out, j = [], 0
    for rep, m in enumerate(micros_us[:reps]):
        tol = max(tol_us, tol_rel * m)
        for k in range(j, len(cand)):
            if abs(cand[k][3] / 1000.0 - m) <= tol:
                out.append((rep, cand[k]))
                j = k + 1
                break
    return out


def join_point(pulses, micros_us, reps, board, max_relative_pct=DEFAULT_MAX_RELATIVE_PCT, align_widths=False):
    """pulses: list of PULSE field tuples (seq, rise_us, width_ticks, width_ns, wraps, flags) in seq order.
    -> {"status", "pairs": [(rep, micros_us, counter_us, diff_us, diff_pct)], "summary": {...}, "notes"}"""
    used = [p for p in pulses if not (p[5] & 1)]
    glitches = len(pulses) - len(used)
    base = {"pairs": [], "summary": {}, "pulses_used": len(used), "glitches": glitches}
    if micros_us is None:
        return {**base, "status": "refused_no_micros", "notes": "no raw.csv rows for this point"}
    if len(micros_us) < reps:
        return {**base, "status": "refused_short_raw", "notes": f"raw.csv has {len(micros_us)} reps, need {reps}"}
    partial = ""
    aligned = None
    if align_widths:
        # Phase 3: match every board round trip to a counter pulse of the same width (see align_by_width). A clean join
        # (all reps matched, no counter pulse left over) is not 'partial'; anything else is, and says so.
        aligned = align_by_width(pulses, micros_us, reps)
        if len(aligned) < ALIGN_MIN_MATCHED * reps:
            return {**base, "status": "refused_count_mismatch",
                    "notes": f"{len(used)} usable pulses ({glitches} glitch) for {reps} reps; width alignment matched only "
                             f"{len(aligned)}/{reps}"}
        if len(aligned) != reps:
            partial = (f"partial: aligned by width, {len(aligned)}/{reps} reps matched, {len(used) - len(aligned)} extra/unmatched "
                       "counter pulses ignored")
        elif len(used) != reps:
            partial = f"aligned by width, all {reps} reps matched, {len(used) - len(aligned)} extra counter pulse(s) ignored"
    elif len(used) != reps:
        # a glitch pulse that took the place of one rep's pulse: the pulse COUNT is still `reps`, only flagged slots are
        # unusable. Pair by slot and skip them (n_pairs < reps, noted); any other count mismatch stays refused.
        if len(pulses) == reps and 1 <= glitches <= MAX_PARTIAL_SLOTS:
            slots = [i for i, p in enumerate(pulses) if p[5] & 1]
            partial = (f"partial: rep slot(s) {slots} skipped (glitch pulse in place of the rep's pulse); "
                       "slot alignment assumes the glitch replaced that rep")
        else:
            return {**base, "status": "refused_count_mismatch",
                    "notes": f"{len(used)} usable pulses ({glitches} glitch) for {reps} reps; refusing rep-order join"}
    pairs = []
    src = aligned if aligned is not None else ([(i, p) for i, p in enumerate(pulses) if not (p[5] & 1)] if partial else list(enumerate(used)))
    for rep, p in src:
        m = micros_us[rep]
        c_us = p[3] / 1000.0
        d = m - c_us
        pairs.append((rep, m, c_us, d, (d / c_us * 100.0) if c_us > 0 else float("nan")))
    diffs = [x[3] for x in pairs]
    pcts = [x[4] for x in pairs if x[4] == x[4]]
    q = rs.MICROS_QUANTIZATION_US.get(board, 1.0)
    med_pct = statistics.median(pcts) if pcts else float("nan")
    med_d = statistics.median(diffs)
    flagged = bool(pcts) and abs(med_pct) > max_relative_pct and abs(med_d) > q
    summary = {"n_pairs": len(pairs), "median_diff_us": med_d, "mean_diff_us": statistics.fmean(diffs),
               "std_diff_us": statistics.pstdev(diffs) if len(diffs) > 1 else 0.0, "iqr_diff_us": _iqr(diffs),
               "max_abs_diff_us": max(abs(x) for x in diffs), "median_diff_pct": med_pct,
               "flagged": flagged, "micros_quantization_us": q}
    return {**base, "status": "joined", "pairs": pairs, "summary": summary,
            "notes": "; ".join(x for x in (partial, "" if not flagged else
                     f"median diff {med_pct:.2f} % and {med_d:.1f} us exceed threshold ({max_relative_pct} %, {q} us)") if x)}


def write_compare(ref_dir, session_id, board, circuit, n, result, ref_status):
    """Append ref_compare.csv rows (joined points only) and the ref_compare_points.csv row."""
    ref_dir = Path(ref_dir)
    if result["status"] == "joined":
        rs.append_rows(ref_dir / "ref_compare.csv", [
            {"session_id": session_id, "board": board, "circuit": circuit, "n": n, "rep": rep,
             "micros_us": m, "counter_us": round(c, 3), "diff_us": round(d, 3), "diff_pct": round(pc, 4)}
            for rep, m, c, d, pc in result["pairs"]])
    s = result["summary"]
    rs.append_rows(ref_dir / "ref_compare_points.csv", [{
        "session_id": session_id, "board": board, "circuit": circuit, "n": n,
        "n_pairs": s.get("n_pairs", 0), "median_diff_us": _r(s.get("median_diff_us")), "mean_diff_us": _r(s.get("mean_diff_us")),
        "std_diff_us": _r(s.get("std_diff_us")), "iqr_diff_us": _r(s.get("iqr_diff_us")),
        "max_abs_diff_us": _r(s.get("max_abs_diff_us")), "median_diff_pct": _r(s.get("median_diff_pct"), 4),
        "ref_status": ref_status if result["status"] == "joined" else result["status"],
        "flagged": s.get("flagged", True if result["status"] != "joined" else False),
        "micros_quantization_us": s.get("micros_quantization_us", rs.MICROS_QUANTIZATION_US.get(board, "")),
        "notes": result.get("notes", "")}])


def _r(x, nd=3):
    return "" if x is None else round(x, nd)
