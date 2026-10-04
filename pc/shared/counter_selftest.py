#!/usr/bin/env python3
# counter_selftest.py -- host side of the counter's S1 self-test (self-LOOPBACK ONLY:
# GPIO25 generator -> GPIO35 input on the SAME ESP32, one crystal, so this says nothing
# about clock accuracy). Opens the counter's serial port, sends SELFTEST, collects frames,
# and reports error per generated width, observed resolution and anomaly codes.
#   .venv/bin/python pc/shared/counter_selftest.py --port /dev/cu.usbserial-XXXX
# analyze() is pure (tested in counter_test.py); only run() touches a serial port.

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import counter_proto as cp  # noqa: E402

# same table as firmware/counter_esp32/src/main.cpp `groups`
GROUPS = [(100, 20), (1000, 20), (100000, 10), (1000000, 3), (10000000, 2), (60000000, 1)]
WRAP_S = (1 << 32) / 80e6   # 53.69 s capture-timer wrap at 80 MHz

ANOMALY_NAMES = {1: "missing pulse", 2: "extra pulse", 3: "glitch", 4: "still high", 5: "count mismatch",
                 6: "sequence gap", 7: "never started", 8: "clock fault", 9: "ring overflow"}


def analyze(frames):
    """frames: list of (type, fields) in arrival order. Splits by REPORT (one per scenario)."""
    scen, cur = [], {"pulses": [], "anomalies": []}
    results, hb = [], 0
    for t, f in frames:
        if t == cp.T_PULSE:
            cur["pulses"].append(f)
        elif t == cp.T_ANOMALY:
            cur["anomalies"].append(f[1])
        elif t == cp.T_SELFTEST_RESULT:
            results.append(f)
        elif t == cp.T_HEARTBEAT:
            hb += 1
        elif t == cp.T_REPORT:
            cur["report"] = f
            scen.append(cur)
            cur = {"pulses": [], "anomalies": []}
    out = {"scenarios": scen, "group_results": results, "heartbeats": hb, "groups": []}
    if scen:
        w = [p[2] for p in scen[0]["pulses"]]
        i = 0
        for width_us, count in GROUPS:
            chunk = w[i:i + count]
            i += count
            exp = width_us * 1000
            if not chunk:
                out["groups"].append({"width_us": width_us, "n": 0})
                continue
            mean = statistics.fmean(chunk)
            out["groups"].append({
                "width_us": width_us, "n": len(chunk), "expected_ns": exp, "mean_ns": mean,
                "err_ns": mean - exp, "err_ppm": (mean - exp) / exp * 1e6,
                "min_ns": min(chunk), "max_ns": max(chunk),
                "jitter_ns": (max(chunk) - min(chunk)),
                "stdev_ns": statistics.pstdev(chunk) if len(chunk) > 1 else 0.0,
                "exceeds_wrap": exp / 1e9 > WRAP_S,
            })
    return out


def report_text(a):
    L = ["SELF-LOOPBACK TEST ONLY: generator and counter share one crystal; clock accuracy is NOT tested.",
         f"{'width':>10s} {'n':>3s} {'mean err':>12s} {'err ppm':>10s} {'min..max spread':>16s} {'stdev':>9s}  note"]
    for g in a["groups"]:
        if not g["n"]:
            L.append(f"{g['width_us']:>8d}us {0:>3d}  (no pulses)")
            continue
        L.append(f"{g['width_us']:>8d}us {g['n']:>3d} {g['err_ns']:>10.0f}ns {g['err_ppm']:>10.1f} "
                 f"{g['jitter_ns']:>14.0f}ns {g['stdev_ns']:>7.0f}ns  {'> wrap period (overflow path)' if g['exceeds_wrap'] else ''}")
    for i, s in enumerate(a["scenarios"], 1):
        r = s.get("report")
        codes = sorted(set(s["anomalies"]))
        L.append(f"scenario {i}: pulses={len(s['pulses'])} report.pulses={r[2] if r else '?'} "
                 f"anomaly codes={[str(c) + ' (' + ANOMALY_NAMES.get(c, '?') + ')' for c in codes]}")
    L.append(f"heartbeats seen: {a['heartbeats']}")
    return "\n".join(L)


def run(port, baud=921600, timeout_s=240):
    import serial
    d = cp.Decoder()
    frames = []
    with serial.Serial(port, baud, timeout=0.2) as s:
        time.sleep(0.3)
        s.reset_input_buffer()
        s.write(cp.encode(cp.T_SELFTEST, 0))
        t0 = time.time()
        reports = 0
        while time.time() - t0 < timeout_s and reports < 3:
            data = s.read(512)
            for t, f in d.feed(data):
                frames.append((t, f))
                if t == cp.T_REPORT:
                    reports += 1
    return frames, d.bad_frames


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", default=None, help="write the text report here")
    args = ap.parse_args()
    frames, bad = run(args.port)
    a = analyze(frames)
    txt = report_text(a) + f"\nframes={len(frames)} bad_crc_frames={bad}"
    print(txt)
    if args.out:
        Path(args.out).write_text(txt + "\n")
