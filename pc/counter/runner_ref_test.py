#!/usr/bin/env python3
# runner_ref_test.py -- pc/run.py with --ref counter / --counter-port: argument validation, dry-run for every
# board x circuit (phase 2), refusals, counter-port preflight. subprocess.run is mocked; no hardware, no ports.
import contextlib
import io
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pc"))
import run as run_mod  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


@contextlib.contextmanager
def capture():
    out, err = io.StringIO(), io.StringIO()
    so, se = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        yield out, err
    finally:
        sys.stdout, sys.stderr = so, se


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, *a, **k):
        self.calls.append(list(argv) if isinstance(argv, (list, tuple)) else argv)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()


def main():
    ledger = Path(tempfile.mkdtemp(prefix="runner_ref_ledger_")) / "l.jsonl"
    saved_ledger, saved_run = run_mod.rh.LEDGER_PATH, run_mod.subprocess.run
    run_mod.rh.LEDGER_PATH = ledger
    rec = Rec()
    run_mod.subprocess.run = rec
    try:
        n_ok = 0
        all_ok = True
        for board in run_mod.BOARDS:
            for circuit in run_mod.ALGORITHMS:
                with capture() as (o, e):
                    code = run_mod.main(["--board", board, "--algorithm", circuit, "--phase", "2", "--port", "/dev/cu.TARGET",
                                         "--ref", "counter", "--counter-port", "/dev/cu.COUNTER", "--dry-run"])
                t = o.getvalue()
                ok = (code == 0 and "--ref counter --counter-port /dev/cu.COUNTER" in t and "with_ref" in t
                      and "timing reference: ESP32 counter" in t)
                all_ok = all_ok and ok
                n_ok += ok
        check("dry-run --ref counter is clean for every board x circuit (phase 2)", all_ok, f"{n_ok}/12")
        hw = [c for c in rec.calls if isinstance(c, list) and any(m in c for m in ("pio",) + tuple(str(p) for p in run_mod.PHASE2_SCRIPTS.values()))]
        check("dry-runs never touch hardware (no sweep script, no pio)", not hw, f"{len(rec.calls)} subprocess calls")

        with capture() as (o, e):
            code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2", "--port", "/dev/cu.T", "--dry-run"])
        t = o.getvalue()
        check("--ref none is allowed for a dry-run but warned: no_ref bucket, not valid for official runs",
              code == 0 and "WARNING: --ref none" in t and "--ref" not in t.split("command:")[1].split("\n")[0])

        for argv, why in ((["--ref", "counter"], "missing --counter-port"),
                          (["--ref", "counter", "--counter-port", "/dev/cu.T"], "same port for counter and target"),
                          (["--counter-port", "/dev/cu.C"], "--counter-port without --ref counter")):
            with capture() as (o, e):
                code = run_mod.main(["--board", "esp32", "--algorithm", "h_all", "--phase", "2", "--port", "/dev/cu.T", "--dry-run"] + argv)
            check(f"refused: {why}", code == 1 and "error:" in e.getvalue(), e.getvalue().strip()[:90])
        with capture() as (o, e):
            code = run_mod.main(["--board", "esp32", "--algorithm", "h_all", "--phase", "3", "--port", "/dev/cu.T",
                                 "--ref", "counter", "--counter-port", "/dev/cu.C", "--dry-run"])
        check("accepted: --ref counter in Phase 3 (the offload firmware toggles the timing pin around each round trip)", code == 0, e.getvalue().strip()[:90])
        with capture() as (o, e):
            code = run_mod.main(["--board", "esp8266", "--algorithm", "h_all", "--phase", "3", "--port", "/dev/cu.T",
                                 "--ref", "counter", "--dry-run"])
        check("refused: Phase 3 --ref counter without --counter-port", code == 1 and "error:" in e.getvalue())
        with capture() as (o, e):
            code = run_mod.main(["--board", "uno", "--algorithm", "qpe", "--phase", "2", "--port", "/dev/cu.T",
                                 "--ref", "counter", "--counter-port", "/dev/cu.C", "--dry-run"])
        check("removed circuits are still refused with the counter flags", code == 1 and "removed from the experiment plan" in e.getvalue())

        # counter-port preflight (read-only checks, mocked)
        saved = (run_mod.port_exists, run_mod.port_holder_pids, run_mod.glob.glob)
        try:
            run_mod.port_exists = lambda p: p != "/dev/cu.GONE"
            run_mod.port_holder_pids = lambda p: ["99"] if p == "/dev/cu.BUSY" else []
            run_mod.glob.glob = lambda pat: ["/dev/cu.usbserial-1", "/dev/cu.usbserial-2"] if "usbserial" in pat else []
            for cport, want in (("/dev/cu.GONE", "does not exist"), ("/dev/cu.BUSY", "already held"), ("/dev/cu.T", "must differ")):
                try:
                    run_mod.check_counter_port(cport, "/dev/cu.T"); ok = False; msg = ""
                except run_mod.RunnerError as ex:
                    msg = str(ex); ok = want in msg
                check(f"counter-port preflight refuses ({want})", ok, msg[:70])
            with capture() as (o, e):
                run_mod.check_counter_port("/dev/cu.usbserial-1", "/dev/cu.usbserial-2")
            check("two ESP32-like ports present: runner lists both and does NOT guess which is the counter",
                  "confirm by hand" in o.getvalue() and "/dev/cu.usbserial-1" in o.getvalue() and "/dev/cu.usbserial-2" in o.getvalue())
        finally:
            run_mod.port_exists, run_mod.port_holder_pids, run_mod.glob.glob = saved
        try:
            run_mod.check_counter_port("tcp:8080", "/dev/cu.T"); ok = False
        except run_mod.RunnerError as ex:
            ok = "dashboard" in str(ex) and "tcp:5055" in str(ex)
        check("tcp:8080 (the dashboard port) is refused with a hint to use tcp:5055", ok)
        argv = run_mod.build_command("py", "esp32", "grover", 2, port="/dev/cu.T", ref=True, counter_port="/dev/cu.C", counter_cal="cal.json")
        check("build_command passes --ref counter, --counter-port, --counter-cal to the delegated sweep",
              argv[-6:] == ["--ref", "counter", "--counter-port", "/dev/cu.C", "--counter-cal", "cal.json"])
        argv0 = run_mod.build_command("py", "esp32", "grover", 2, port="/dev/cu.T")
        check("build_command without --ref is exactly the pre-counter command", "--ref" not in argv0 and "--counter-port" not in argv0)
        argvf = run_mod.build_command("py", "esp8266", "grover", 3, port="/dev/cu.T", n_max=15, force_infeasible=True)
        check("build_command passes --force-infeasible to the Phase 3 sweep, and only when asked",
              "--force-infeasible" in argvf and "--force-infeasible" not in run_mod.build_command("py", "esp8266", "grover", 3, port="/dev/cu.T"))
        with capture() as (o, e):
            code = run_mod.main(["--board", "esp8266", "--algorithm", "grover", "--phase", "2", "--port", "/dev/cu.T",
                                 "--force-infeasible", "--dry-run"])
        check("refused: --force-infeasible in Phase 2", code == 1 and "Phase 3" in e.getvalue())
    finally:
        run_mod.rh.LEDGER_PATH, run_mod.subprocess.run = saved_ledger, saved_run
    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
