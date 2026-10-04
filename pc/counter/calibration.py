#!/usr/bin/env python3
# calibration.py -- counter clock calibration against the PC monotonic clock (design
# docs/design/counter_design.md section 15, procedure 1). The counter heartbeat carries its
# 64-bit microsecond clock; this tool pairs each heartbeat with the PC's time.monotonic_ns() on
# arrival, fits counter_us = a + b * pc_us by least squares, and stores ppm = (b - 1) * 1e6 with
# its standard error and the residual jitter in a calibration JSON.
#
# LIMITS (stated in the JSON): the PC clock is itself a quartz clock (typically a few ppm to tens
# of ppm off true time, UNVERIFIED); serial/USB latency jitter (ms) is the dominant noise, so the
# uncertainty falls with duration (1 ms jitter over 30 min gives about 1 ppm). This measures the
# counter's crystal relative to the PC clock, not relative to true time.
#   .venv/bin/python pc/counter/calibration.py --port /dev/cu.usbserial-XXXX --minutes 30 --out cal.json
# fit()/write_json() are pure and tested with the simulator (calibration_test.py).

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import proto as cp  # noqa: E402

CAL_SCHEMA_VERSION = 1   # own constant: calibration JSON files


def fit(pairs, robust=True):
    """pairs: [(pc_us, counter_us)]. -> dict(ppm, ppm_stderr, n, span_s, residual_rms_us, offset_us, dropped).
    robust: WiFi/USB latency has rare long spikes (seen: 1.6 s), so after a first fit the pairs whose residual exceeds
    5 x the median absolute residual are dropped (at most 10 % of the pairs) and the line is refitted."""
    dropped = 0
    if robust and len(pairs) >= 30:
        r0 = _fit(pairs)
        x0 = pairs[0][0]
        res = [abs((y - pairs[0][1]) - (r0["offset_us"] + (r0["ppm"] / 1e6 + 1.0) * (x - x0))) for x, y in pairs]
        mad = sorted(res)[len(res) // 2] or 1.0
        keep = [p for p, e in zip(pairs, res) if e <= 5 * mad]
        if len(pairs) - len(keep) <= 0.1 * len(pairs) and len(keep) >= 10:
            dropped = len(pairs) - len(keep)
            pairs = keep
    out = _fit(pairs)
    out["dropped"] = dropped
    return out


def _fit(pairs):
    n = len(pairs)
    if n < 10:
        raise ValueError(f"need at least 10 heartbeat pairs, got {n}")
    x0 = pairs[0][0]
    xs = [p[0] - x0 for p in pairs]
    ys = [p[1] - pairs[0][1] for p in pairs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    rms = math.sqrt(sum(r * r for r in res) / (n - 2)) if n > 2 else 0.0
    se_b = rms / math.sqrt(sxx)
    return {"ppm": (b - 1.0) * 1e6, "ppm_stderr": se_b * 1e6, "n": n, "span_s": xs[-1] / 1e6,
            "residual_rms_us": rms, "offset_us": a}


def write_json(path, result, port="", counter_fw="", note=""):
    doc = {
        "schema_version": CAL_SCHEMA_VERSION,
        "method": "heartbeat counter clock vs PC time.monotonic_ns, least squares",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "port": port, "counter_fw": counter_fw,
        "ppm": round(result["ppm"], 3), "ppm_stderr": round(result["ppm_stderr"], 3),
        "pairs": result["n"], "dropped_outliers": result.get("dropped", 0), "span_s": round(result["span_s"], 1),
        "residual_rms_us": round(result["residual_rms_us"], 1),
        "limitation": ("Measured relative to the PC clock (itself a quartz clock, UNVERIFIED tolerance), "
                       "dominated by serial latency jitter; says nothing about the target board's own clock. "
                       "The self-loopback self-test is not a calibration."),
        "within_50ppm": abs(result["ppm"]) + 2 * result["ppm_stderr"] <= 50.0,
        "note": note,
    }
    Path(path).write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def collect(port, minutes, baud=115200, out=print):
    """port: a USB serial device path or 'tcp:PORT' (the counter connects over WiFi). Each heartbeat is stamped with the PC
    monotonic clock in the reader thread, at arrival (not when the main loop gets round to it)."""
    from counter.client import CounterClient, make_transport
    pairs = []

    def on_frame(ftype, f):
        if ftype == cp.T_HEARTBEAT:
            pairs.append((time.monotonic_ns() / 1000.0, f[1]))
    cl = CounterClient(make_transport(port, baud), on_frame=on_frame)
    end = time.monotonic() + minutes * 60
    next_report = time.monotonic() + 60
    try:
        while time.monotonic() < end:
            cl.drain()
            time.sleep(0.5)
            if time.monotonic() > next_report and len(pairs) >= 10:
                next_report += 60
                r = fit(list(pairs))
                out(f"  {r['span_s'] / 60:.1f} min: {r['ppm']:+.2f} ppm +- {r['ppm_stderr']:.2f} ({r['n']} pairs, {r['dropped']} outliers dropped)")
    finally:
        cl.close()
    return list(pairs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="USB serial device or tcp:5055 (counter over WiFi; stop the bridge first)")
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--out", required=True, help="calibration JSON to write")
    args = ap.parse_args()
    pairs = collect(args.port, args.minutes)
    res = fit(pairs)
    doc = write_json(args.out, res, port=args.port)
    print(json.dumps(doc, indent=1))
