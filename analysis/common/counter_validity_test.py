#!/usr/bin/env python3
"""Tests for analysis/common/counter_validity.py (item 2g). Run:  .venv/bin/python analysis/common/counter_validity_test.py"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
sys.path.insert(0, os.path.join(ROOT, "analysis", "phase4"))
from common import counter_validity as cv  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def pulses(widths, codes=None, flags=None):
    codes = codes or [0] * len(widths)
    flags = flags or [0] * len(widths)
    return pd.DataFrame({"width_us": widths, "anomaly_code": codes, "flags": flags})


def main():
    # ---- T_max from the firmware's own numbers
    import re
    fw = open(os.path.join(ROOT, "firmware", "counter_esp32", "src", "main.cpp")).read()
    wrap_bits = int(re.search(r"uint(\d+)_t wraps = 0;", fw).group(1))                 # width of the whole-wrap counter in the firmware
    apb = int(re.search(r"static uint32_t apb_hz = (\d+);", fw).group(1))                # APB clock the capture counter runs at
    fine_bits = 32 if re.search(r"uint32_t fine = f32 - r32;", fw) else None            # width of the MCPWM capture counter
    check("firmware: whole-wrap counter is 16 bits, capture counter 32 bits, APB 80 MHz (parsed from main.cpp)", (wrap_bits, fine_bits, apb) == (16, 32, 80_000_000), str((wrap_bits, fine_bits, apb)))
    t_from_firmware = ((1 << wrap_bits) - 1) * (1 << fine_bits) / apb
    check("T_max in the module equals the value derived from the firmware source text", abs(cv.T_MAX_S - t_from_firmware) < 1e-6 and 3.5e6 < cv.T_MAX_S < 3.6e6, str(cv.T_MAX_S))
    check("firmware flags a pulse longer than the armed max_width_s as stuck-high (the extra, host-set limit named in the docstring)", "(esp_timer_get_time() - rise_us) > (int64_t)max_width_s" in fw and "A_STUCK_HIGH" in fw)
    t = cv.validity_table((2,))
    ticks = pd.read_csv(os.path.join(ROOT, "data/raw/phase2/esp32/h_all/with_ref/ref/ref_pulses.csv")).head(200)
    check("80 MHz APB assumption: width_us == width_ticks x 0.0125 in the data (all of 200 pulses)",
          np.allclose(ticks.width_ticks * 0.0125, ticks.width_us, atol=2e-3))

    ok_p = pulses([100.0, 200.0, 300.0])
    # ---- R1
    for st in ("refused_no_target_run", "refused_count_mismatch", "refused_arm_failed", "refused_counter_lost", "refused_short_raw"):
        u, why = cv.evaluate_point(st, 0, 3, [], ok_p, 1000.0)
        check(f"R1 {st} -> unusable", (not u) and why.startswith("R1"), why)
    for st in ("ok", "anomaly", "count_mismatch"):
        u, why = cv.evaluate_point(st, 3, 3, [100.0, 200.0, 300.0], ok_p, 1000.0)
        check(f"R1 joined status {st} with a clean join -> usable", u, why)
    # ---- R2
    u, why = cv.evaluate_point("ok", 2, 3, [100.0, 200.0], ok_p, 1000.0)
    check("R2 2 pairs for 3 reps -> unusable", (not u) and why.startswith("R2"), why)
    # ---- R3: a flagged pulse
    pf = pulses([100.0, 200.0, 999.0], codes=[0, 0, 5])
    u, why = cv.evaluate_point("ok", 3, 3, [100.0, 200.0, 999.0], pf, 1000.0)
    check("R3 join used a pulse with anomaly_code 5 -> unusable", (not u) and why.startswith("R3"), why)
    u, why = cv.evaluate_point("ok", 2, 2, [100.0, 200.0], pf, 1000.0)
    check("R3 the same flagged pulse exists but was NOT used -> usable", u, why)
    pg = pulses([100.0, 200.0, 5.0], flags=[0, 0, 1])
    u, why = cv.evaluate_point("ok", 3, 3, [100.0, 200.0, 5.0], pg, 1000.0)
    check("R3 join used a glitch-flagged pulse (flags bit 0) -> unusable", (not u) and why.startswith("R3"), why)
    pdup = pulses([100.0, 100.0, 100.0], codes=[5, 0, 0])
    u, why = cv.evaluate_point("ok", 2, 2, [100.0, 100.0], pdup, 1000.0)
    check("R3 equal widths: 2 clean pulses cover the 2 used values, the flagged twin is not blamed", u, why)
    # ---- R4 just below / just above T_max
    below, above = cv.T_MAX_US * (1 - 1e-6), cv.T_MAX_US * (1 + 1e-6)
    u1, _ = cv.evaluate_point("ok", 3, 3, [100.0, 200.0, 300.0], ok_p, below)
    u2, why2 = cv.evaluate_point("ok", 3, 3, [100.0, 200.0, 300.0], ok_p, above)
    check("R4 interval just below T_max -> usable", u1)
    check("R4 interval just above T_max -> unusable", (not u2) and why2.startswith("R4"), why2)

    # ---- the two cases that motivated the module, on the real data
    def row(circuit, n, board="esp32", phase=2):
        r = t[(t.board == board) & (t.circuit == circuit) & (t.n == n) & (t.phase == phase)]
        return r.iloc[0]
    r12, r11, r10 = row("grover", 12), row("grover", 11), row("grover", 10)
    check("ESP32 grover n=12 (1.71 s counter vs 4520 s micros) is unusable by R3", (not r12.usable) and r12.reason.startswith("R3"), r12.reason)
    check("... and not because of T_max (micros 4.5e9 us is far below T_max)", r12.micros_median_us < cv.T_MAX_US)
    check("ESP32 grover n=11 (529 s, 13 pairs) is usable", bool(r11.usable) and r11.micros_median_us > 5e8)
    check("ESP32 grover n=10 is unusable by R1 (counter count mismatch, no pairs)", (not r10.usable) and r10.reason.startswith("R1"), r10.reason)
    # the counter's own second pulse at n=12 is a clean 4519 s width: evidence about the counter, kept OUT of the statistics
    pl = pd.read_csv(os.path.join(ROOT, "data/raw/phase2/esp32/grover/with_ref/ref/ref_pulses.csv"))
    p12 = pl[pl.n == 12]
    check("n=12: the counter recorded a clean 4519 s pulse (wraps 84, anomaly 0) next to the flagged 1.71 s one",
          len(p12) == 2 and p12[p12.anomaly_code == 0].width_us.iloc[0] > 4.5e9 and int(p12[p12.anomaly_code == 0].wraps.iloc[0]) == 84)

    # ---- no unusable counter point reaches any plot or statistic
    full = cv.validity_table()
    check("one row per (phase, board, circuit, n) in the validity table", not full.duplicated(["phase", "board", "circuit", "n"]).any())
    usable = {(r.phase, r.board, r.circuit, r.n) for r in full.itertuples() if r.usable}
    for ph in (2, 3):
        d = pd.read_csv(os.path.join(ROOT, "data", "derived", f"phase{ph}_timer_vs_counter.csv"))
        bad = [(r.board, r.circuit, r.n) for r in d.itertuples() if (ph, r.board, r.circuit, r.n) not in usable]
        check(f"phase {ph}_timer_vs_counter.csv (source of the timer_vs_counter figures): every point usable", not bad, str(bad[:5]))
    ag = pd.read_csv(os.path.join(ROOT, "data", "processed", "phase4", "counter_agreement.csv"))
    bad = [(r.board, r.circuit, r.n) for r in ag.itertuples() if (2, r.board, r.circuit, r.n) not in usable]
    check("phase4 counter_agreement.csv: every point usable", not bad, str(bad[:5]))
    import paper_figures_ieee as pf_mod  # noqa: E402
    sys.path.insert(0, os.path.join(ROOT, "analysis"))
    out, _ = pf_mod.load_counter_diff(os.path.join(ROOT, "data", "raw"))
    bad = [(b, c, int(n)) for (b, c), df in out.items() for n in df.n if (2, b, c, int(n)) not in usable]
    check("paper_figures_ieee.load_counter_diff (Fig. micros() - counter): every point usable", not bad, str(bad[:5]))
    print(f"\n{len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
