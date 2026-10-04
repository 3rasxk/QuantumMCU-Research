#!/usr/bin/env python3
# selftest_test.py -- analysis/evaluation of the self-test on synthetic frames (no hardware).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import proto as cp  # noqa: E402
from counter import selftest as st  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def pulse(seq, ns, wraps=0):
    return (cp.T_PULSE, (seq, 0, ns * 80 // 1000, ns, wraps, 0))


def main():
    frames = []
    seq = 0
    for width_us, count in st.GROUPS:
        for _ in range(count):
            ns = width_us * 1000 + 40
            frames.append(pulse(seq, ns, ns * 80 // 1000 >> 32)); seq += 1
    frames.append((cp.T_REPORT, (1, 0, seq, 0, 0, 0, 0, seq, 0)))
    frames += [pulse(0, 10_000_000), (cp.T_ANOMALY, (0, cp.A_GLITCH, 1)), (cp.T_REPORT, (2, 1, 1, 8, 0, 0, 0, 1, 0))]
    frames += [pulse(0, 10_000_000), (cp.T_ANOMALY, (1, cp.A_MISSING, 1)), (cp.T_REPORT, (3, 1, 1, 2, 0, 0, 0, 1, 0))]
    frames += [pulse(0, 10_000_000), (cp.T_ANOMALY, (1, cp.A_STUCK_HIGH, 0)), (cp.T_ANOMALY, (1, cp.A_MISSING, 1)),
               (cp.T_REPORT, (4, 1, 1, 0, 0, 0, 0, 1, 0))]
    frames += [pulse(0, 10_000_000), (cp.T_REPORT, (5, 0, 1, 0, 0, 0, 0, 1, 0)), (cp.T_ANOMALY, (3, cp.A_SEQ_GAP, 0))]
    frames += [(cp.T_HEARTBEAT, (2, 1_000_000, 1, 0, 0, 0, 0, 0)), (cp.T_HEARTBEAT, (2, 2_500_000, 1, 0, 0, 0, 0, 0))]
    a = st.analyze(frames)
    check("five scenarios split at each REPORT", len(a["scenarios"]) == 5)
    check("group sizes", [g["n"] for g in a["groups"]] == [20, 20, 10, 3, 2, 1])
    check("per-width error is the injected 40 ns", all(abs(g["err_ns"] - 40) < 1e-9 for g in a["groups"]))
    check("the 60 s group is flagged as beyond the wrap period and reports wraps >= 1",
          a["groups"][-1]["exceeds_wrap"] and a["groups"][-1]["wraps"] >= 1 and not a["groups"][-2]["exceeds_wrap"])
    check("observed tick resolution is derived from the data", a["tick_resolution_ns"] is not None and a["tick_resolution_ns"] > 0)
    ev = st.evaluate(a)
    check("every scenario passes with the expected codes", all(r[4] for r in ev), str([(r[0], r[2]) for r in ev]))
    check("the late code-6 anomaly is attributed to scenario 5", cp.A_SEQ_GAP in a["scenarios"][4]["anomalies"])
    bad = list(frames)
    bad = [x for x in bad if not (x[0] == cp.T_ANOMALY and x[1][1] == cp.A_GLITCH)]
    check("a missing glitch code makes scenario 2 FAIL", not st.evaluate(st.analyze(bad))[1][4])
    txt = st.report_text(a, bad_frames=0, dropped_records=0)
    check("report carries the self-loopback caveat and the GPIO34 caveat", "SELF-LOOPBACK TEST ONLY" in txt and "GPIO34" in txt)
    check("report lists heartbeat span", "heartbeats: 2" in txt and "1.5 s" in txt)
    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
