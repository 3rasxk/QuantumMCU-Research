"""Predicted values for points that are not run because one rep exceeds the per-point time cap
(reason 1_rep_exceeds_time_cap) or that cannot finish a rep because the watchdog resets the board
(reason watchdog_reset_loop).

Owner rule 2026-10-05: board run time per point <= timing_model.POINT_TIME_CAP_S. A point whose single
rep is predicted above the cap is skipped on the board; instead of leaving a hole, this module
computes what the rep time would be and appends one row to predicted.csv beside raw.csv.

Everything here is an ESTIMATE (column `kind`), never a measurement, and is never written to raw.csv.

Two estimates per point:
  model      timing_model.expected_exec_time_us (prior fit, UNVERIFIED)
  calibrated model x median(measured / model) over the largest measured n of the same circuit on the
             same board (up to 3 points from raw.csv); blank when nothing is measured yet
`per_rep_used_us` is the calibrated value when it exists, else the model value.
"""
import csv
import statistics
from datetime import datetime, timezone
from pathlib import Path

from shared import timing_model as tm

FIELDS = [
    "board", "circuit", "n", "kind", "reason", "cap_s", "state_bytes", "ram_pct",
    "per_rep_model_us", "per_rep_calibrated_us", "calibration_ratio", "calibration_n",
    "per_rep_used_us", "per_rep_human", "reps_100_total_human", "watchdog_risk", "max_reps_in_cap",
    "ts_utc",
]
CALIBRATION_POINTS = 3


def measured_medians(raw_path):
    """{n: median exec_time_us} from a raw.csv (empty dict when absent)."""
    raw_path = Path(raw_path)
    if not raw_path.exists():
        return {}
    by_n = {}
    with open(raw_path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                by_n.setdefault(int(r["n"]), []).append(float(r["exec_time_us"]))
            except (KeyError, ValueError):
                continue
    return {n: statistics.median(v) for n, v in by_n.items() if v}


def predict_point(board, circuit, n, medians, cap_s=tm.POINT_TIME_CAP_S, reason="1_rep_exceeds_time_cap"):
    model_us = tm.expected_exec_time_us(board, circuit, n)
    ratios, used_n = [], []
    for m in sorted(medians, reverse=True):
        if m >= n:
            continue
        base = tm.expected_exec_time_us(board, circuit, m)
        if base > 0:
            ratios.append(medians[m] / base)
            used_n.append(m)
        if len(ratios) == CALIBRATION_POINTS:
            break
    ratio = statistics.median(ratios) if ratios else None
    calibrated_us = model_us * ratio if ratio is not None else None
    used_us = calibrated_us if calibrated_us is not None else model_us
    state = 8 << n
    thr = tm.WDT_PER_REP_THRESHOLD_S.get(board)
    return {
        "board": board, "circuit": circuit, "n": n, "kind": "ESTIMATE_not_measured",
        "reason": reason, "cap_s": cap_s,
        "state_bytes": state, "ram_pct": round(state / tm.TOTAL_RAM_BYTES[board] * 100, 1),
        "per_rep_model_us": round(model_us),
        "per_rep_calibrated_us": round(calibrated_us) if calibrated_us is not None else "",
        "calibration_ratio": round(ratio, 4) if ratio is not None else "",
        "calibration_n": " ".join(str(m) for m in sorted(used_n)),
        "per_rep_used_us": round(used_us),
        "per_rep_human": tm.human_duration(used_us / 1e6),
        "reps_100_total_human": tm.human_duration(used_us / 1e6 * tm.REPS),
        "watchdog_risk": bool(thr is not None and used_us / 1e6 > thr),
        "max_reps_in_cap": tm.max_reps_under_cap(used_us / 1e6, cap_s=cap_s),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }


def drop_row(predicted_path, circuit, n):
    """Remove the prediction for (circuit, n) once the point has real measured data (superseded)."""
    predicted_path = Path(predicted_path)
    if not predicted_path.exists():
        return 0
    with open(predicted_path, newline="") as f:
        rows = list(csv.DictReader(f))
    keep = [r for r in rows if not (r["circuit"] == circuit and r["n"] == str(n))]
    if len(keep) != len(rows):
        with open(predicted_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(keep)
    return len(rows) - len(keep)


def record_skipped_point(board, circuit, n, raw_path, predicted_path, cap_s=tm.POINT_TIME_CAP_S,
                         reason="1_rep_exceeds_time_cap"):
    """Append the prediction for (circuit, n) to predicted_path unless it is already there; return the row."""
    predicted_path = Path(predicted_path)
    row = predict_point(board, circuit, n, measured_medians(raw_path), cap_s, reason)
    if row["ram_pct"] > 100:
        return row  # state larger than RAM: a memory wall, not a time problem; no time estimate is stored
    predicted_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if predicted_path.exists():
        with open(predicted_path, newline="") as f:
            existing = {(r["circuit"], r["n"]) for r in csv.DictReader(f)}
    if (circuit, str(n)) in existing:
        return row
    new = not predicted_path.exists()
    with open(predicted_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def summary_line(row):
    if row["ram_pct"] > 100:
        return f"state {row['state_bytes']} B > RAM ({row['ram_pct']}%): memory wall, no time estimate stored"
    cal = (f", calibrated from n={row['calibration_n']} (x{row['calibration_ratio']})"
           if row["per_rep_calibrated_us"] != "" else ", timing model only (nothing measured yet)")
    return (f"predicted (ESTIMATE): 1 rep ~{row['per_rep_human']}, 100 reps ~{row['reps_100_total_human']}"
            f"{cal} -> predicted.csv")


# --------------------------------------------------------------------------------------------------------------
# Phase 3 (offload): points skipped because the PC cannot do them (a single request passes the 2 h per-point cap, or
# the request's circuit does not fit in the PC's memory). Same idea as above: compute, never measure.
FIELDS_P3 = [
    "board", "circuit", "n", "kind", "reason", "gates", "per_request_model_s", "per_request_calibrated_s",
    "calibration_ratio", "calibration_n", "reps_100_total_human", "pc_circuit_gb_est", "pc_ram_gb", "ts_utc",
]


def record_skipped_point_phase3(board, circuit, n, raw_path, predicted_path):
    """Append the prediction for a skipped Phase 3 point (once). Per-request time: the model (PC Aer simulation + the
    board's per-rep overhead), and the same x median(measured e2e latency / model) over the largest measured n of this
    circuit (up to 3). ESTIMATE_not_measured: never written to raw.csv."""
    predicted_path = Path(predicted_path)
    if predicted_path.exists():
        with open(predicted_path, newline="") as f:
            for r in csv.DictReader(f):
                if int(r["n"]) == n and r["circuit"] == circuit:
                    return r
    model_s = tm.phase3_rep_time_s(circuit, n)
    meas = {}
    raw_path = Path(raw_path)
    if raw_path.exists():
        by_n = {}
        with open(raw_path, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("timed_out") == "0" and r.get("crc_error") == "0":
                    by_n.setdefault(int(r["n"]), []).append(float(r["e2e_latency_us"]) / 1e6)
        meas = {k: statistics.median(v) for k, v in by_n.items() if v}
    ns = sorted(meas)[-CALIBRATION_POINTS:]
    ratio = statistics.median(meas[k] / tm.phase3_rep_time_s(circuit, k) for k in ns) if ns else None
    gates = sum(tm.gate_counts(circuit, n))
    row = {
        "board": board, "circuit": circuit, "n": n, "kind": "ESTIMATE_not_measured",
        "reason": tm.phase3_skip_reason(circuit, n) or "skipped", "gates": gates,
        "per_request_model_s": round(model_s, 2),
        "per_request_calibrated_s": round(model_s * ratio, 2) if ratio else "",
        "calibration_ratio": round(ratio, 3) if ratio else "", "calibration_n": " ".join(map(str, ns)),
        "reps_100_total_human": tm.human_duration(model_s * (ratio or 1) * tm.REPS),
        "pc_circuit_gb_est": round(tm.phase3_pc_memory_bytes(circuit, n) / 1e9, 1),
        "pc_ram_gb": round(tm.pc_physical_ram_bytes() / 1e9, 1), "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    predicted_path.parent.mkdir(parents=True, exist_ok=True)
    new = not predicted_path.exists()
    with open(predicted_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS_P3)
        if new:
            w.writeheader()
        w.writerow(row)
    return row
