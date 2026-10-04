#!/usr/bin/env python3
# selftest.py -- host side of the counter's S1 self-test (self-LOOPBACK ONLY: GPIO25 generator ->
# GPIO35 input on the SAME ESP32, one crystal for generating and measuring). It does NOT prove
# clock accuracy and does NOT exercise the GPIO34 pad the target is wired to.
# Opens the counter's serial port, sends SELFTEST, runs five scenarios, and reports error per
# generated width, observed resolution, anomaly codes, frame/CRC errors and dropped records.
#   .venv/bin/python pc/counter/selftest.py --port /dev/cu.usbserial-XXXX --out results.txt
# analyze()/report_text() are pure (tested in selftest_test.py); only run() touches a serial port.

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import proto as cp  # noqa: E402
from counter.sim import SeqTracker  # noqa: E402

# same table as firmware/counter_esp32/src/main.cpp `groups`
GROUPS = [(100, 20), (1000, 20), (100000, 10), (1000000, 3), (10000000, 2), (60000000, 1)]
WRAP_S = (1 << 32) / 80e6   # 53.69 s capture-timer wrap at 80 MHz
APB_HZ = 80_000_000

SCENARIOS = {
    1: ("clean widths", set()),
    2: ("induced glitch (20 us pulse, limit 50 us)", {cp.A_GLITCH}),
    3: ("missing pulse (9 of 10)", {cp.A_MISSING}),
    4: ("still high at end (line held high)", {cp.A_STUCK_HIGH}),   # code 1 also appears (3 of 4 pulses)
    5: ("sequence gap (PC drops one frame, REPLAY)", {cp.A_SEQ_GAP}),
}


def analyze(frames):
    """frames: list of (type, fields) in arrival order. Splits by REPORT (one per scenario)."""
    scen, cur = [], {"pulses": [], "anomalies": []}
    results, hb = [], []
    for t, f in frames:
        if t == cp.T_PULSE:
            cur["pulses"].append(f)
        elif t == cp.T_ANOMALY:
            cur["anomalies"].append(f[1])
        elif t == cp.T_SELFTEST_RESULT:
            results.append(f)
        elif t == cp.T_HEARTBEAT:
            hb.append(f)
        elif t == cp.T_REPORT:
            cur["report"] = f
            scen.append(cur)
            cur = {"pulses": [], "anomalies": []}
    if cur["anomalies"] and scen:           # anomalies that arrive after the last REPORT (REPLAY -> code 6)
        scen[-1]["anomalies"] += cur["anomalies"]
        scen[-1]["pulses"] += cur["pulses"]
    out = {"scenarios": scen, "group_results": results, "heartbeats": hb, "groups": []}
    if scen:
        pulses = scen[0]["pulses"]
        w = [p[3] for p in pulses]
        ticks = [p[2] for p in pulses]
        i = 0
        for width_us, count in GROUPS:
            chunk = w[i:i + count]
            tk = ticks[i:i + count]
            wr = [p[4] for p in pulses[i:i + count]]
            i += count
            exp = width_us * 1000
            if not chunk:
                out["groups"].append({"width_us": width_us, "n": 0})
                continue
            mean = statistics.fmean(chunk)
            out["groups"].append({
                "width_us": width_us, "n": len(chunk), "expected_ns": exp, "mean_ns": mean,
                "err_ns": mean - exp, "err_ppm": (mean - exp) / exp * 1e6,
                "min_ns": min(chunk), "max_ns": max(chunk), "spread_ns": max(chunk) - min(chunk),
                "stdev_ns": statistics.pstdev(chunk) if len(chunk) > 1 else 0.0,
                "wraps": max(wr), "exceeds_wrap": exp / 1e9 > WRAP_S,
            })
        diffs = sorted({abs(a - b) for a in ticks for b in ticks if a != b})
        out["tick_resolution_ns"] = (diffs[0] * 1e9 / APB_HZ) if diffs else None
    return out


def evaluate(a):
    """Pass/fail per scenario: expected anomaly codes present, none unexpected (scenario 4 may also show 1)."""
    rows = []
    for i, s in enumerate(a["scenarios"], 1):
        name, want = SCENARIOS.get(i, ("?", set()))
        got = set(s["anomalies"])
        allowed = want | ({cp.A_MISSING} if i == 4 else set())
        ok = want <= got and got <= allowed
        rows.append((i, name, sorted(got), sorted(want), ok))
    return rows


def report_text(a, bad_frames=0, dropped_records=0, extra=""):
    L = ["SELF-LOOPBACK TEST ONLY: one crystal generates and measures; clock accuracy is NOT tested and the",
         "GPIO34 target pad is NOT exercised (the loopback uses GPIO25 -> GPIO35).", "",
         f"{'width':>10s} {'n':>3s} {'mean err':>12s} {'err ppm':>10s} {'spread':>10s} {'stdev':>9s} {'wraps':>5s}  note"]
    for g in a["groups"]:
        if not g["n"]:
            L.append(f"{g['width_us']:>8d}us {0:>3d}  (no pulses)")
            continue
        L.append(f"{g['width_us']:>8d}us {g['n']:>3d} {g['err_ns']:>10.0f}ns {g['err_ppm']:>10.1f} "
                 f"{g['spread_ns']:>8.0f}ns {g['stdev_ns']:>7.0f}ns {g['wraps']:>5d}  "
                 f"{'> 32-bit wrap period (overflow path)' if g['exceeds_wrap'] else ''}")
    if a.get("tick_resolution_ns") is not None:
        L.append(f"observed tick resolution (smallest width step seen): {a['tick_resolution_ns']:.1f} ns (capture tick 12.5 ns at 80 MHz)")
    L.append("")
    for i, name, got, want, ok in evaluate(a):
        L.append(f"scenario {i} [{'PASS' if ok else 'FAIL'}] {name}: codes raised {[str(c) + ' ' + cp.ANOMALY_NAMES.get(c, '?') for c in got]}, expected {want}")
    hb = a["heartbeats"]
    if len(hb) >= 2:
        span = (hb[-1][1] - hb[0][1]) / 1e6
        L.append(f"heartbeats: {len(hb)} over {span:.1f} s of counter clock (sub-second ticks)")
    L.append(f"frame errors: bad CRC / unparsable frames = {bad_frames}; dropped records detected (sequence gaps outside scenario 5) = {dropped_records}")
    if extra:
        L.append(extra)
    return "\n".join(L)


def run(port, baud=115200, timeout_s=300):
    import serial
    d = cp.Decoder()
    frames = []
    dropped_outside = 0
    scen_idx = 1
    trackers = SeqTracker(0)
    dropped_done = False
    with serial.Serial(port, baud, timeout=0.2) as s:
        time.sleep(0.3)
        s.reset_input_buffer()
        s.write(cp.encode(cp.T_SELFTEST, 0))
        t0 = time.time()
        last_rx = time.time()
        while time.time() - t0 < timeout_s:
            data = s.read(512)
            if data:
                last_rx = time.time()
            for t, f in d.feed(data):
                if t == cp.T_PULSE:
                    if scen_idx == 5 and f[0] == 3 and not dropped_done:   # deliberately lose one frame
                        dropped_done = True
                        continue
                    for req in trackers.feed(cp.encode(cp.T_PULSE, *f)):
                        if scen_idx == 5:
                            s.write(req)                     # the tracker saw the jump: ask for a replay
                        else:
                            dropped_outside += 1
                frames.append((t, f))
                if t == cp.T_REPORT:
                    scen_idx += 1
                    trackers = SeqTracker(0)
            if scen_idx > 5 and time.time() - last_rx > 3.0:
                break
    return frames, d.bad_frames, dropped_outside


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", default=None, help="write the text report here")
    args = ap.parse_args()
    frames, bad, dropped = run(args.port)
    a = analyze(frames)
    txt = report_text(a, bad, dropped) + f"\nframes received: {len(frames)}"
    print(txt)
    if args.out:
        Path(args.out).write_text(txt + "\n")
