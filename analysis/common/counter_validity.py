"""Counter validity: ONE place that decides, per (phase, board, circuit, n), whether the ESP32 pulse counter's value may be used.

Every script that reads data/raw/**/ref/ref_compare*.csv for statistics or plots must go through `usable_pairs()` /
`validity_table()` here. Inputs are read-only. Decisions use only information the counter and the join code recorded about the
pulses themselves (status, anomaly codes, pulse flags, counts); they never look at whether counter and micros() AGREE, so the
agreement statistics computed afterwards are not circular.

Rules (a point is usable only if every one holds; the FIRST failing rule is the reason):
  R1 status      the join produced pairs: ref_compare_points.ref_status in {ok, anomaly, count_mismatch}. Refused joins
                 (no_target_run, arm_failed, counter_lost, short_raw, count_mismatch) carry no pairs.
  R2 count       n_pairs equals the number of reps present in raw.csv for that point (a partial join is not used).
  R3 pulse flags no paired counter pulse carries a counter-side flag: pulse `flags` bit 0 (glitch) or `anomaly_code` != 0 in
                 ref_pulses.csv. A flagged pulse is the counter telling us that this width is not a clean rise/fall pair
                 (firmware/counter_esp32/src/main.cpp: A_COUNT_MISMATCH raised in handle_edge when a fall has no rise).
  R5 plausibility (checked after R3, before R4) a counter/micros() pair is implausible if counter/micros() is outside [0.5, 2.0] (inclusive) or the counter value lies within
                 +-1 ms of k x 53.687091 s, k >= 1 (the 2^32-tick wrap at 80 MHz: `unwrap_ticks` in firmware/counter_esp32/src/main.cpp turns a spike
                 of a few ticks with the fall stamped before the rise into 2^32 - 1 ticks). Implausible pairs are removed; the point must then still
                 meet R2 (pairs == reps), which it cannot, so ANY implausible pair makes the point unusable (the count rule is not relaxed). Same rule for
                 every board, phase and session. (Added 2026-10-31; the other rules are unchanged.)
  R4 range       the board's micros() median for the point does not exceed T_MAX_S (below). Not binding for any point on disk.
T_MAX_S: the counter timestamps rise and fall with the 32-bit MCPWM capture counter at the APB clock and recovers whole wraps
from the 64-bit esp_timer (firmware/counter_esp32/src/main.cpp:184-189, `unwrap_ticks`); the wrap count is a uint16_t (:188, :217).
So the largest REPRESENTABLE width is (2^16 - 1) wraps of 2^32 ticks at apb_hz = 80 MHz (width_us = width_ticks x 0.0125 in the
data: 2441 ticks = 30.513 us). The unwrap additionally needs the esp_timer stamps of the two edges to be within 2^31 ticks
(26.8 s) of the true width; the data show no violation. Whether the counter is CORRECT at long widths is a separate, measured
question: the longest clean agreement in the data is reported by `validated_max_us()`. T_max is a representation limit, not a guarantee: the firmware also
flags any pulse longer than the host-armed `max_width_s` (default 130 s, :81, :304; checked at :471-473) as stuck-high (anomaly code 4), which rule R3 then rejects.
"""
import glob
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "data", "raw")
BOARDS = ["uno", "esp8266", "esp32"]
CIRCUITS = ["h_all", "bell_ghz", "qft", "grover"]
APB_HZ = 80_000_000
T_MAX_S = ((1 << 16) - 1) * (1 << 32) / APB_HZ
T_MAX_US = T_MAX_S * 1e6
WRAP_US = (1 << 32) / APB_HZ * 1e6          # 53 687 091.2 us
WRAP_TOL_US = 1000.0                          # +-1 ms around k x WRAP_US
RATIO_LO, RATIO_HI = 0.5, 2.0                 # counter / micros() must lie in [RATIO_LO, RATIO_HI]
JOINED_STATUSES = ("ok", "anomaly", "count_mismatch")
# firmware/counter_esp32/src/main.cpp:50-51 (enum order starts at 1)
ANOMALY_NAMES = {1: "missing", 2: "extra", 3: "glitch", 4: "stuck_high", 5: "count_mismatch", 6: "seq_gap", 7: "never_started",
                 8: "clock_fault", 9: "ring_overflow"}
ARM_REASONS = {"no_target_run": "no pulse train from the target run was captured (counter saw no run)",
               "arm_failed": "counter could not be armed for this point", "counter_lost": "counter link lost during the point"}


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from common import sessions as SES  # noqa: E402


def _dir(phase, board, circuit, session=SES.ORIGINAL):
    return os.path.join(RAW, f"phase{phase}", board, circuit, session)


def implausible_pairs(micros_us, counter_us):
    """boolean mask over paired (micros(), counter) values: True = rule R5 rejects the pair"""
    m, c = np.asarray(micros_us, float), np.asarray(counter_us, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(m > 0, c / m, np.inf)
    k = np.round(c / WRAP_US)
    wrap = (k >= 1) & (np.abs(c - k * WRAP_US) <= WRAP_TOL_US)
    return (ratio < RATIO_LO) | (ratio > RATIO_HI) | wrap


def _read(path, **kw):
    return pd.read_csv(path, **kw) if os.path.exists(path) else pd.DataFrame()


def codes_text(s):
    if s is None or (isinstance(s, float) and np.isnan(s)) or str(s).strip() == "":
        return ""
    return "+".join(ANOMALY_NAMES.get(int(float(c)), c) for c in str(s).replace(".0", "").split())


def evaluate_point(status, n_pairs, raw_reps, paired_counter_us, pulses, micros_median_us, paired_micros_us=None):
    """-> (usable: bool, reason: str). `pulses`: DataFrame of ref_pulses rows of this point (width_us, flags, anomaly_code).
    `paired_micros_us`: the micros() value of each pair (same order as `paired_counter_us`); enables rule R5."""
    if status not in JOINED_STATUSES:
        base = str(status).replace("refused_", "")
        return False, f"R1 no pairs: {base}" + (f" ({ARM_REASONS[base]})" if base in ARM_REASONS else "")
    if n_pairs != raw_reps:
        return False, f"R2 partial join: {n_pairs} pairs for {raw_reps} reps"
    if len(pulses):
        bad = pulses[(pulses["flags"].astype(int) & 1 != 0) | (pulses["anomaly_code"].fillna(0).astype(int) != 0)]
        if len(bad):
            clean = Counter(np.round(pulses.drop(bad.index)["width_us"].to_numpy(float), 3))
            used = Counter(np.round(np.asarray(paired_counter_us, float), 3))
            badw = Counter(np.round(bad["width_us"].to_numpy(float), 3))
            for w in badw:
                if used.get(w, 0) > clean.get(w, 0):
                    code = int(bad[np.isclose(bad["width_us"], w, atol=5e-4)]["anomaly_code"].iloc[0])
                    return False, (f"R3 paired pulse of {w:.3f} us carries counter flag "
                                   f"{ANOMALY_NAMES.get(code, code)} (code {code}); the join used a pulse the counter marked not-clean")
    if paired_micros_us is not None and len(paired_micros_us) and len(paired_micros_us) == len(paired_counter_us):
        bad = implausible_pairs(paired_micros_us, paired_counter_us)
        if bad.any():
            i = int(np.argmax(bad))
            return False, (f"R5 {int(bad.sum())} implausible pair(s) (e.g. counter {float(np.asarray(paired_counter_us, float)[i]):.1f} us vs micros() "
                           f"{float(np.asarray(paired_micros_us, float)[i]):.1f} us); R2 then fails: {n_pairs - int(bad.sum())} pairs for {raw_reps} reps")
    if micros_median_us > T_MAX_US:
        return False, f"R4 micros() {micros_median_us / 1e6:.0f} s exceeds T_max {T_MAX_S:.3g} s"
    return True, "ok"


def _rows_for_dir(d, ph, b, c, session=SES.ORIGINAL):
    """validity rows of one with_ref directory (empty list if it has no ref_points.csv, i.e. nothing can be decided)"""
    rows = []
    rp = _read(os.path.join(d, "ref", "ref_points.csv"))
    if rp.empty:
        return rows
    cp = _read(os.path.join(d, "ref", "ref_compare_points.csv"))
    cmp_ = _read(os.path.join(d, "ref", "ref_compare.csv"))
    pul = _read(os.path.join(d, "ref", "ref_pulses.csv"))
    raw = _read(os.path.join(d, "raw.csv"))
    for _, r in rp.iterrows():
        n = int(r["n"])
        cprow = cp[cp["n"] == n] if len(cp) else cp
        status = cprow["ref_status"].iloc[0] if len(cprow) else r["ref_status"]
        npairs = int(cprow["n_pairs"].iloc[0]) if len(cprow) else 0
        flagged = bool(cprow["flagged"].iloc[0]) if len(cprow) else True
        reps = int(raw[raw["n"] == n].shape[0]) if len(raw) else 0
        mic = raw[raw["n"] == n]["exec_time_us" if ph == 2 else "e2e_latency_us"] if len(raw) else pd.Series(dtype=float)
        mmed = float(mic.median()) if len(mic) else float("nan")
        paired = cmp_[cmp_["n"] == n]["counter_us"].to_numpy(float) if len(cmp_) else np.array([])
        paired_m = cmp_[cmp_["n"] == n]["micros_us"].to_numpy(float) if len(cmp_) else np.array([])
        usable, why = evaluate_point(status, npairs, reps, paired, pul[pul["n"] == n] if len(pul) else pul, mmed if mmed == mmed else 0.0, paired_m)
        rows.append(dict(phase=ph, board=b, circuit=c, session=session, n=n, usable=usable, reason=why, T_max_s=T_MAX_S,
                         ref_status=status, counter_codes=codes_text(r.get("anomaly_codes")), reps_in_raw=reps, n_pairs=npairs,
                         pulses_received=r.get("pulses_received"), host_flagged=flagged, micros_median_us=mmed,
                         counter_median_us=float(np.median(paired)) if len(paired) else float("nan")))
    return rows


def validity_table(phases=(2, 3), raw_root=None, selected_only=False):
    """One row per (phase, board, circuit, session, n) that has a ref_points.csv row: usable, reason, T_max and the counter-side facts.
    `session` = bucket name (with_ref, with_ref_r2, ...). selected_only=True keeps, per point, only the session whose counter pairs the
    analysis uses (analysis/common/sessions.py `counter_session`) and only in-scope n."""
    root = raw_root or RAW
    rows = []
    for ph in phases:
        for b in BOARDS:
            for c in CIRCUITS:
                base = os.path.join(root, f"phase{ph}", b, c)
                for d in sorted(glob.glob(os.path.join(base, "with_ref*"))):
                    if os.path.isdir(d):
                        rows += _rows_for_dir(d, ph, b, c, os.path.basename(d))
    df = pd.DataFrame(rows)
    # a point recorded twice inside ONE session is usable only if every record of it is (the first failing record gives the reason)
    df["_bad"] = ~df["usable"]
    keys = ["phase", "board", "circuit", "session", "n"]
    df = df.sort_values(keys + ["_bad"], ascending=[True] * 5 + [False], kind="stable")
    df = df.drop_duplicates(keys, keep="first").drop(columns="_bad")
    df = df.sort_values(keys).reset_index(drop=True)
    df["selected"] = [SES.is_selected(int(r.phase), r.board, r.circuit, int(r.n), r.session, counter=True) for r in df.itertuples()]
    if selected_only:
        df = df[df.selected].reset_index(drop=True)
    return df


def usable_n_in_dir(d, phase, board, circuit):
    """set of usable n of one with_ref directory, or None when the directory has no ref_points.csv (validity cannot be decided; real data
    always has it, only hand-made test fixtures do not)"""
    rows = _rows_for_dir(str(d), phase, board, circuit, os.path.basename(str(d)))
    return {r["n"] for r in rows if r["usable"]} if rows else None


def usable_pairs(phase, board, circuit, table=None):
    """ref_compare.csv rows (one per paired rep) of the usable points only, taken from the session whose counter pairs the analysis uses
    (sessions.counter_session). The ONLY sanctioned way to read counter pairs for statistics."""
    t = table if table is not None else validity_table((phase,), selected_only=True)
    t = t[(t.phase == phase) & (t.board == board) & (t.circuit == circuit) & t.usable]
    cmp_ = SES.read_selected(phase, board, circuit, os.path.join("ref", "ref_compare.csv"), counter=True)
    if not len(cmp_) or not len(t):
        return cmp_.iloc[0:0].copy() if len(cmp_) else cmp_
    ok = {(r.session, int(r.n)) for r in t.itertuples()}
    return cmp_[[(s_, int(n)) in ok for s_, n in zip(cmp_["session"], cmp_["n"])]].copy()


def usable_n(table, phase, board, circuit):
    """usable n of the SELECTED counter session (the table may hold every session)"""
    t = table[(table.phase == phase) & (table.board == board) & (table.circuit == circuit) & table.usable]
    return {int(r.n) for r in t.itertuples() if "session" not in t.columns or SES.is_selected(phase, board, circuit, int(r.n), r.session, counter=True)}


def validated_max_us(table, phase=2):
    """longest micros() median among usable points = the longest interval over which counter and micros() were actually compared"""
    t = table[(table.phase == phase) & table.usable]
    if "session" in t.columns:
        t = t[[SES.is_selected(phase, r.board, r.circuit, int(r.n), r.session, counter=True) for r in t.itertuples()]]
    return float(t.micros_median_us.max()) if len(t) else float("nan")
