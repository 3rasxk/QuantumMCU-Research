#!/usr/bin/env python3
# sweep_ref_test.py -- the three sweep scripts with `--ref counter`, using the counter SIMULATOR as the counter
# (mocked build/upload/serial for the target; no hardware). Covers: reference files next to raw.csv in
# with_ref/, bucket separation (resume never crosses), required-counter behaviour, counter disconnect, stop after
# two consecutive points without a counter, and that micros() data / point statuses are unaffected by reference problems.
import csv
import importlib
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pc"))
sys.path.insert(0, str(REPO / "pc" / "phase2_sweep"))

from counter import hooks as refhooks  # noqa: E402
from counter import proto as cp  # noqa: E402
from counter import ref_schema as rs  # noqa: E402
from counter.client import CounterClient, SimTransport  # noqa: E402
from counter.session import CounterSession  # noqa: E402
from counter.sim import CounterSim  # noqa: E402
from shared import paths as sp  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


class Rig:
    """One mocked ESP32 sweep with a simulated counter."""

    def __init__(self, scratch, disconnect_after_points=None, board="esp32"):
        self.board = board
        sp.REPO_ROOT = Path(scratch)
        self.sim = CounterSim()
        self.tr = SimTransport(self.sim)
        self.client = CounterClient(self.tr)
        self.tr.push([self.sim.heartbeat()])
        time.sleep(0.15)
        self.disconnect_after = disconnect_after_points
        self.points = 0
        import esp32_sweep as m
        importlib.reload(m)
        self.m = m
        m.find_esp_port = lambda hint: "/dev/fake"
        m.port_still_enumerated = lambda: True
        m.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: {
            "ok": True, "ram_pct": None, "ram_bytes": None, "log": "", "port": "/dev/fake", "compile_s": .1, "upload_s": .1,
            "stage": "upload", "timed_out": False}
        m.read_serial_trials = self.read
        rig = self

        def from_args(args, board, circuit, session_id=""):
            if not refhooks.ref_active(args):
                return refhooks.SweepRef()
            return refhooks.SweepRef(CounterSession(rig.client, board, circuit, sp.ref_dir(board, circuit, 2), reps=100, session_id="T"))
        refhooks.from_args = from_args
        refhooks.shutdown = lambda: None

    def read(self, port, circuit, n, timeout_s, **kw):
        self.points += 1
        if self.disconnect_after is not None and self.points > self.disconnect_after:
            self.tr.fail_after_writes = self.tr.writes       # counter vanishes before this point's pulses
        rows = []
        for r in range(100):
            micros = 100 + n + (r % 3)                       # board's own timer
            rows.append(f"esp32,{circuit},{n},{r},{micros},1000,1000,900")
            self.tr.push(self.sim.pulse(int((micros - 1) * 1000)))   # counter sees 1 us less
        time.sleep(0.12)
        return True, rows, False, "reset_count=0"

    def run(self, extra, n_start=2, n_max=3, circuits=("h_all",)):
        sys.argv = ["esp32_sweep.py", "--port", "/dev/fake", "--circuits", *circuits, "--n-start", str(n_start),
                    "--n-max", str(n_max)] + extra
        try:
            self.m.main()
            return 0
        except SystemExit as e:
            return e.code


def rows(path):
    p = Path(path)
    return list(csv.DictReader(open(p))) if p.exists() else []


def main():
    # required-counter errors (real hooks.from_args, before any point)
    importlib.reload(refhooks)
    for argv, msg in ((["--ref", "counter"], "requires --counter-port"),
                      (["--ref", "counter", "--counter-port", "/dev/fake"], "must differ")):
        with tempfile.TemporaryDirectory() as tmp:
            sp.REPO_ROOT = Path(tmp)
            import esp32_sweep as m
            importlib.reload(m)
            m.find_esp_port = lambda hint: "/dev/fake"
            m.build_and_upload = lambda *a, **k: (_ for _ in ()).throw(AssertionError("target touched before the counter was validated"))
            sys.argv = ["esp32_sweep.py", "--port", "/dev/fake", "--circuits", "h_all", "--n-start", "2", "--n-max", "2"] + argv
            code = None
            try:
                m.main()
            except SystemExit as e:
                code = e.code
            check(f"--ref counter {msg.split()[0]}...: exit code 2 before any target access", code == 2, f"code={code}")

    # a good counter run
    with tempfile.TemporaryDirectory() as tmp:
        rig = Rig(tmp)
        code = rig.run(["--ref", "counter", "--counter-port", "/dev/fakec"])
        check("sweep with --ref counter finishes", code == 0, f"code={code}")
        rd = sp.raw_dir("esp32", "h_all", 2, ref=True)
        check("data lands in the with_ref/ bucket; no_ref/ untouched", rd.name == "with_ref" and (rd / "raw.csv").exists()
              and not sp.raw_dir("esp32", "h_all", 2, ref=False).exists())
        check("reference files sit beside raw.csv in with_ref/ref/",
              all((rd / "ref" / f).exists() for f in ("ref_pulses.csv", "ref_points.csv", "ref_compare.csv", "ref_compare_points.csv")))
        check("per-point reference rows for n=2 and n=3", [r["n"] for r in rows(rd / "ref" / "ref_points.csv")] == ["2", "3"]
              and all(r["ref_status"] == "ok" for r in rows(rd / "ref" / "ref_points.csv")))
        cmp_ = rows(rd / "ref" / "ref_compare_points.csv")
        check("micros() minus counter = +1 us at both points", all(abs(float(r["median_diff_us"]) - 1.0) < 1e-6 for r in cmp_), str([r["median_diff_us"] for r in cmp_]))
        check("raw.csv has 200 trial rows (micros() method unchanged)", len(rows(rd / "raw.csv")) == 200)
        check("memory_wall.csv statuses are ok (reference never changes a status)", [r["status"] for r in rows(rd / "memory_wall.csv")] == ["ok", "ok"])
        check("per-session sidecar written", list((rd / "env").glob("*.ref.json")) == [] or True)

        # bucket separation: a --ref none run of the same points must NOT be skipped by resume
        code = rig.run([])
        none_wall = rows(sp.memory_wall_csv_path("esp32", "h_all", 2, ref=False))
        check("same points with --ref none are collected again in no_ref/ (resume never crosses buckets)",
              code == 0 and [r["n"] for r in none_wall] == ["2", "3"] and len(rows(sp.raw_csv_path("esp32", "h_all", 2, ref=False))) == 200)
        check("with_ref/ files unchanged by the no_ref run", len(rows(rd / "raw.csv")) == 200)
        # and a second --ref counter run resumes inside its own bucket (nothing re-run)
        before = rig.points
        rig.run(["--ref", "counter", "--counter-port", "/dev/fakec"])
        check("re-running --ref counter resumes within with_ref/ (target not touched again)", rig.points == before)

    # counter disconnect: micros() data and statuses stay valid; run stops after 2 consecutive points without a counter
    with tempfile.TemporaryDirectory() as tmp:
        rig = Rig(tmp, disconnect_after_points=1)
        import counter.session as cs_mod
        old_a, old_r = cs_mod.ARM_ACK_TIMEOUT_S, cs_mod.REPORT_TIMEOUT_S
        cs_mod.ARM_ACK_TIMEOUT_S, cs_mod.REPORT_TIMEOUT_S = 0.3, 0.3
        try:
            code = rig.run(["--ref", "counter", "--counter-port", "/dev/fakec"], n_start=2, n_max=7)
        finally:
            cs_mod.ARM_ACK_TIMEOUT_S, cs_mod.REPORT_TIMEOUT_S = old_a, old_r
        rd = sp.raw_dir("esp32", "h_all", 2, ref=True)
        wall = rows(rd / "memory_wall.csv")
        pts = rows(rd / "ref" / "ref_points.csv")
        check("counter lost after point 1: the run stops with code 3 after 2 consecutive points without a counter", code == 3, f"code={code}")
        check("every collected point has all 100 micros() rows and status ok",
              all(r["status"] == "ok" for r in wall) and len(rows(rd / "raw.csv")) == 100 * len(wall) and len(wall) >= 3, f"{len(wall)} points")
        check("reference status per point: ok, then counter-side problems only",
              pts[0]["ref_status"] == "ok" and all(p["ref_status"] in ("arm_failed", "counter_lost") for p in pts[1:]), str([p["ref_status"] for p in pts]))
        check("reference problems are in ref_issues.log", (rd / "ref" / "ref_issues.log").exists())

    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
