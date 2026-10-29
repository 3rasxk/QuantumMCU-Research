"""Phase 4 item 2: counter validity table, per-point flag explanation (Uno, ESP8266) and the micros()-vs-counter agreement from
USABLE points only.  Writes data/derived/counter_validity.csv, data/derived/counter_flag_explanation.csv,
data/processed/phase4/counter_agreement.csv, counter_summary.csv (replacing the earlier unfiltered versions)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
from common import counter_validity as cv  # noqa: E402
from common import weak  # noqa: E402

DERIVED = os.path.join(ROOT, "data", "derived")
PROC = os.path.join(ROOT, "data", "processed", "phase4")
CM = "firmware/counter_esp32/src/main.cpp"
# where each counter-side anomaly code is raised (line numbers at this commit)
CODE_RULE = {
    "missing": f"{CM}:236 (falls < reps armed)", "extra": f"{CM}:237 (falls > reps armed)",
    "glitch": f"{CM}:221 (pulse < min_width_ns)", "stuck_high": f"{CM}:234,:471-473 (still high at END / above max_width_s)",
    "count_mismatch": f"{CM}:210,:214,:239 (two rises without a fall / a fall without a rise / PCNT count differs from the edge count)",
    "seq_gap": f"{CM}:402 (frame sequence gap, REPLAY requested)", "never_started": f"{CM}:235,:477 (no pulse seen)",
    "clock_fault": f"{CM}:347 (clock vs PC > 50 ppm)", "ring_overflow": f"{CM}:201,:240 (frame or edge ring overflow)"}
HOST_RULES = ("pc/counter/session.py:192-199 sets ref_status (no_target_run / count_mismatch if clean pulses != reps / anomaly if any code); "
              "pc/counter/crosscheck.py:83-111 refuses a join (refused_*), :140 sets host_flagged = |median diff %| > 5 and > 1 micros() tick")


def explanation_table(vt):
    rows = []
    for _, r in vt[vt.board.isin(["uno", "esp8266"])].iterrows():
        codes = [c for c in str(r.counter_codes).split("+") if c and c != "nan"]
        fired = [f"{c}: {CODE_RULE.get(c, '?')}" for c in codes]
        note = ""
        if "extra" in codes and r.usable:
            note = ("extra pulses are the cut-short run before the restart after upload/DTR reset; the join takes the LAST run only "
                    "(pc/counter/crosscheck.py:split_runs), and all reps were paired")
        rows.append(dict(phase=r.phase, board=r.board, circuit=r.circuit, n=r.n, ref_status=r.ref_status, counter_codes=r.counter_codes,
                         counter_side_rules=" | ".join(fired), host_side_rule=("crosscheck.py:140 flagged" if r.host_flagged else ""),
                         pulses_received=r.pulses_received, n_pairs=r.n_pairs, reps_in_raw=r.reps_in_raw, usable=r.usable,
                         reason=r.reason, note=note))
    return pd.DataFrame(rows)


def agreement(vt):
    """micros() vs counter per usable Phase 2 point (ratio = micros/counter), with the weak flag of item 5"""
    rows = []
    for _, r in vt[(vt.phase == 2) & vt.usable].iterrows():
        g = cv.usable_pairs(2, r.board, r.circuit, vt)
        g = g[g.n == r.n]
        g = g[(g.counter_us > 0) & (g.micros_us > 0)]
        ratio = g.micros_us / g.counter_us
        rows.append(dict(board=r.board, circuit=r.circuit, n=int(r.n), n_pairs=len(g), ref_status=r.ref_status,
                         median_micros_us=float(g.micros_us.median()), median_counter_us=float(g.counter_us.median()),
                         median_ratio=float(ratio.median()), ratio_q1=float(np.percentile(ratio, 25)), ratio_q3=float(np.percentile(ratio, 75)),
                         weak=weak.is_weak(len(g))))
    return pd.DataFrame(rows)


def summary(a, floor_us=100.0):
    out = []
    for b in cv.BOARDS:
        for sub, f in (("all usable", lambda g: g), (f"median>={floor_us:.0f}us", lambda g: g[g.median_micros_us >= floor_us]),
                       ("median>=100us, not weak", lambda g: g[(g.median_micros_us >= floor_us) & (~g.weak)])):
            g = f(a[a.board == b])
            if len(g):
                out.append(dict(board=b, subset=sub, n_points=len(g), median_of_median_ratio=float(g.median_ratio.median()),
                                ratio_min=float(g.median_ratio.min()), ratio_max=float(g.median_ratio.max()),
                                iqr_of_point_medians=float(np.percentile(g.median_ratio, 75) - np.percentile(g.median_ratio, 25)),
                                longest_micros_us=float(g.median_micros_us.max())))
    return pd.DataFrame(out)


def main():
    os.makedirs(DERIVED, exist_ok=True)
    os.makedirs(PROC, exist_ok=True)
    vt = cv.validity_table()
    vt.rename(columns={"T_max_s": "T_max_s"}).to_csv(os.path.join(DERIVED, "counter_validity.csv"), index=False)
    ex = explanation_table(vt)
    ex.to_csv(os.path.join(DERIVED, "counter_flag_explanation.csv"), index=False)
    a = agreement(vt)
    a.to_csv(os.path.join(PROC, "counter_agreement.csv"), index=False)
    s = summary(a)
    s.to_csv(os.path.join(PROC, "counter_summary.csv"), index=False)
    return vt, ex, a, s


if __name__ == "__main__":
    vt, ex, a, s = main()
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(vt.groupby(["phase", "board"]).usable.agg(["sum", "count"]))
    print(s.round(4).to_string())
