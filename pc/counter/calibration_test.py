#!/usr/bin/env python3
# calibration_test.py -- calibration fit and JSON, driven by the counter simulator (no hardware).
import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import calibration as cal  # noqa: E402
from counter import proto as cp  # noqa: E402
from counter.sim import CounterSim  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def simulate(ppm, minutes, jitter_us, seed=1, hb_period_s=1.0):
    rnd = random.Random(seed)
    sim = CounterSim()
    sim.clock_ppm_error = ppm
    pairs = []
    t_us = 0
    for _ in range(int(minutes * 60 / hb_period_s)):
        t_us += int(hb_period_s * 1e6)
        sim.t_us = t_us                       # true elapsed time; the sim applies its ppm error
        counter_us = cp.decode(sim.heartbeat())[1][1]
        pairs.append((t_us + rnd.gauss(0, jitter_us), counter_us))
    return pairs


def main():
    r = cal.fit(simulate(0.0, 10, 1000.0))
    check("0 ppm clock, 1 ms jitter, 10 min: estimate within 3 ppm", abs(r["ppm"]) < 3.0, f"{r['ppm']:+.2f} +- {r['ppm_stderr']:.2f}")
    r = cal.fit(simulate(+20.0, 30, 1000.0))
    check("+20 ppm recovered within its stated error band (30 min)", abs(r["ppm"] - 20.0) < 3 * r["ppm_stderr"] + 0.5, f"{r['ppm']:+.2f} +- {r['ppm_stderr']:.2f}")
    r2 = cal.fit(simulate(-35.0, 30, 1000.0, seed=2))
    check("-35 ppm recovered", abs(r2["ppm"] + 35.0) < 3 * r2["ppm_stderr"] + 0.5, f"{r2['ppm']:+.2f}")
    short = cal.fit(simulate(20.0, 2, 1000.0))
    check("uncertainty shrinks with duration (30 min vs 2 min)", r["ppm_stderr"] < short["ppm_stderr"], f"{r['ppm_stderr']:.2f} < {short['ppm_stderr']:.2f}")
    try:
        cal.fit([(0, 0)] * 5); ok = False
    except ValueError:
        ok = True
    check("fewer than 10 pairs refused", ok)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "cal.json"
        doc = cal.write_json(p, r, port="/dev/cu.SIM")
        back = json.loads(p.read_text())
        check("calibration JSON has its own schema version, ppm, error, limitation",
              back["schema_version"] == cal.CAL_SCHEMA_VERSION and "ppm" in back and "ppm_stderr" in back and "limitation" in back)
        check("within_50ppm flag follows the estimate", back["within_50ppm"] is True)
        bad = cal.write_json(Path(tmp) / "bad.json", cal.fit(simulate(120.0, 10, 1000.0)))
        check("a 120 ppm clock is flagged as outside tolerance", bad["within_50ppm"] is False)
    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
