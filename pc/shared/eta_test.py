#!/usr/bin/env python3
# eta_test.py -- mocked-only tests for pc/shared/eta.py, pc/shared/experiment_plan.py
# and the --plan / table / live-ETA parts of pc/run.py. No hardware, no pio, no
# serial: subprocess.run is replaced wherever a run is simulated.
#
# Same style as the other pc/shared/*_test.py (no pytest):
#   .venv/bin/python pc/shared/eta_test.py

import contextlib
import csv
import io
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

import run as run_mod  # noqa: E402
from shared import eta  # noqa: E402
from shared import experiment_plan as plan  # noqa: E402
from shared import paths as sp  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared.circuit_ids import EXPERIMENT_CIRCUITS  # noqa: E402

RESULTS = []
BKK = eta.BANGKOK
UTC = timezone.utc


def check(name, cond, detail=""):
    RESULTS.append((name, "PASS" if cond else "FAIL"))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


@contextlib.contextmanager
def captured():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- plan data

def test_plan_scope_and_ranges():
    check("plan circuits are exactly the four", EXPERIMENT_CIRCUITS == ("h_all", "bell_ghz", "qft", "grover"))
    check("MIN_N matches pc/run.py MIN_VALID_N", plan.MIN_N == run_mod.MIN_VALID_N, str(plan.MIN_N))
    check("predicted walls: uno 8, esp8266 13, esp32 14",
          [plan.wall_n(b) for b in plan.BOARDS] == [8, 13, 14])
    check("uno phase2 h_all n = 1..8 (wall point included)",
          plan.plan_n_values("uno", "h_all", 2) == list(range(1, 9)))
    check("phase3 grover capped at n=10 on esp32",
          plan.plan_n_values("esp32", "grover", 3) == list(range(2, 11)))
    check("phase1 n union covers n=1 for h_all/qft and odd n up to 14",
          plan.phase1_n_values("h_all")[0] == 1 and plan.phase1_n_values("qft")[0] == 1
          and plan.phase1_n_values("bell_ghz")[0] == 2 and 13 in plan.phase1_n_values("h_all")
          and plan.phase1_n_values("h_all")[-1] == 14)
    check("24 plan rows = 3 boards x 4 circuits x 2 phases", len(plan.all_rows()) == 24)


# ---------------------------------------------------------------- estimates

def _fake_dataset(root, board="uno", phase=2):
    """A tiny NEW-run dataset in a scratch root: points.csv for h_all n=2,3 (ok) -- synthetic
    numbers chosen only to be distinguishable from the model, not measurements of anything."""
    path = sp.points_csv_path(board, "h_all", phase, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["circuit", "n", "status", "build_compile_s", "upload_s", "device_exec_s"])
        w.writerow(["h_all", 2, "ok", 11.0, 5.0, 2.5])
        w.writerow(["h_all", 3, "ok", 13.0, 7.0, 3.5])
        w.writerow(["h_all", 4, "failed", 99.0, 99.0, 99.0])


def test_estimates_and_labels():
    with tempfile.TemporaryDirectory() as tmp:
        saved = sp.REPO_ROOT
        sp.REPO_ROOT = Path(tmp)
        try:
            check("empty tree: nothing measured", eta.load_measured("uno", 2) == {})
            p0 = eta.estimate_point("uno", "h_all", 3, 2)
            check("no data yet: ESTIMATE from timing_model constants only",
                  p0.label == "ESTIMATE" and p0.compile_s == tm.COMPILE_S_ESTIMATE["uno"]
                  and p0.upload_s == tm.UPLOAD_S_ESTIMATE["uno"])
            _fake_dataset(Path(tmp))
            m = eta.load_measured("uno", 2)
            check("new-run medians loaded, failed rows ignored",
                  m["n_ok_points"] == 2 and approx(m["compile_s"], 12.0) and approx(m["upload_s"], 6.0))
            p = eta.estimate_point("uno", "h_all", 3, 2)
            check("(circuit, n) with a measured device time: MEASURED, device = that value",
                  p.label == "MEASURED" and approx(p.device_s, 3.5) and approx(p.compile_s, 12.0))
            p1 = eta.estimate_point("uno", "h_all", 5, 2)
            check("unmeasured n on the same board: ESTIMATE device, but measured compile/upload used",
                  p1.label == "ESTIMATE" and approx(p1.compile_s, 12.0))
            pw = eta.estimate_point("uno", "qft", 8, 2)
            check("wall point: no device time, 90 s hang budget, MEASURED compile+upload",
                  pw.wall and pw.device_s == 0 and pw.hang_s == 90.0 and pw.label == "MEASURED"
                  and approx(pw.total_s, 12.0 + 6.0 + 90.0))
            check("another board stays ESTIMATE (per-board data)",
                  eta.estimate_point("esp32", "h_all", 3, 2).label == "ESTIMATE")
            text = eta.format_table("uno", "h_all", 2, eta.plan_points("uno", "h_all", 2),
                                    datetime(2026, 10, 3, 9, 0, tzinfo=BKK))
            check("table labels both sources", "MEASURED" in text and "ESTIMATE" in text)
        finally:
            sp.REPO_ROOT = saved
    pe = eta.estimate_point("esp8266", "h_all", 6, 2, {})
    check("ESP8266 point is ESTIMATE and uses timing_model constants",
          pe.label == "ESTIMATE" and pe.compile_s == tm.COMPILE_S_ESTIMATE["esp8266"]
          and approx(pe.device_s, tm.expected_point_time_s("esp8266", "h_all", 6)
                     + tm.DEVICE_OVERHEAD_S_ESTIMATE["esp8266"]))
    pg = eta.estimate_point("esp8266", "grover", 9, 2, {})
    check("esp8266 grover n=9 flagged TIME-LIMITED (> 1 h device)", pg.time_limited and pg.device_s > 3600,
          f"{pg.device_s:.0f}s")
    check("esp32 grover n=9 NOT flagged (about 12 min)", not eta.estimate_point("esp32", "grover", 9, 2, {}).time_limited)
    p3 = eta.estimate_point("esp32", "qft", 6, 3, {})
    check("phase 3 point: ESTIMATE, device = PC-sim x reps",
          p3.label == "ESTIMATE" and approx(p3.device_s, tm.pc_sim_time_s("qft", 6) * tm.REPS) and not p3.wall)


def test_plan_points_filters():
    pts = eta.plan_points("esp32", "h_all", 2, n_start=3, n_max=6, completed={4})
    check("plan_points honours n_start/n_max/completed", [p.n for p in pts] == [3, 5, 6])
    pts_all = eta.plan_points("uno", "grover", 2)
    check("sweep list ends at the predicted wall n", pts_all[-1].n == 8 and pts_all[-1].wall)
    pts_cut = eta.plan_points("uno", "grover", 2, n_max=6)
    check("no wall point when --n-max stops short of it", all(not p.wall for p in pts_cut))


# ------------------------------------------------------------ clock / ETA math

def test_clock_arithmetic():
    start = datetime(2026, 10, 3, 10, 0, tzinfo=BKK)
    f = eta.finish_clock(start, 90 * 60)
    check("same day: HH:MM only", eta.format_clock(f, start) == "11:30", eta.format_clock(f, start))
    start2 = datetime(2026, 10, 3, 23, 30, tzinfo=BKK)
    f2 = eta.finish_clock(start2, 45 * 60)
    check("crossing midnight: date is added", eta.format_clock(f2, start2) == "Sun 04 Oct 00:15",
          eta.format_clock(f2, start2))
    start3 = datetime(2026, 10, 3, 17, 30, tzinfo=UTC)  # = 00:30 on 4 Oct in Bangkok
    f3 = eta.finish_clock(start3, 3600)
    check("UTC start is converted to Asia/Bangkok before comparing dates (same Bangkok day)",
          eta.format_clock(f3, start3) == "01:30" and f3.tzinfo is not None, eta.format_clock(f3, start3))
    f4 = eta.finish_clock(start3, 24 * 3600)
    check("exactly +24 h is the next date", eta.format_clock(f4, start3).startswith("Mon 05 Oct"),
          eta.format_clock(f4, start3))
    rows = eta.table_rows(eta.plan_points("uno", "h_all", 2), start2)
    cums = [r["cum_s"] for r in rows]
    check("cumulative column is a running sum of totals",
          all(approx(cums[i], sum(r["p"].total_s for r in rows[:i + 1])) for i in range(len(rows))))
    check("a long table crosses midnight and shows the date",
          any(" Oct " in r["finish"] for r in eta.table_rows(eta.plan_points("esp8266", "grover", 2), start2)))


def test_table_text():
    start = datetime(2026, 10, 3, 9, 0, tzinfo=BKK)
    pts = eta.plan_points("uno", "qft", 2)
    text = eta.format_table("uno", "qft", 2, pts, start)
    for needle in ("device", "compile", "upload", "hang", "total", "cumul", "finish", "MEASURED",
                   "WALL (predicted)", "build_overflow", "Asia/Bangkok", "whole run finishes"):
        check(f"table contains {needle!r}", needle in text)
    check("one line per planned n", sum(1 for ln in text.splitlines() if ln[:3].strip().isdigit()) == len(pts))


# ------------------------------------------------------------------ live ETA

def _mk(n, device, overhead):
    return eta.PointEst("uno", "h_all", 2, n, device, overhead, 0.0, 0.0, "ESTIMATE")


def test_live_eta_arithmetic():
    pts = [_mk(2, 0.0, 10.0), _mk(3, 0.0, 10.0), _mk(4, 100.0, 10.0), _mk(5, 400.0, 10.0)]
    live = eta.LiveEta(pts)
    check("no data: scales are 1.0 and remaining equals the static estimate",
          live.scales() == (1.0, 1.0) and approx(live.remaining_seconds(), sum(p.total_s for p in pts)))
    live.record(2, 20.0)  # overhead twice the estimate
    check("overhead scale fitted from an overhead-only point", approx(live.scales()[0], 2.0), str(live.scales()))
    live.record(3, 20.0)
    live.record(4, 230.0)  # 20 overhead (scaled) + 210 device vs 100 estimated
    s_o, s_d = live.scales()
    check("device scale fitted after removing scaled overhead", approx(s_o, 2.0) and approx(s_d, 2.1), f"{s_o} {s_d}")
    check("remaining = scaled overhead + scaled device of the unfinished points",
          approx(live.remaining_seconds(), 2.0 * 10.0 + 2.1 * 400.0), f"{live.remaining_seconds():.1f}")
    now = datetime(2026, 10, 3, 23, 50, tzinfo=BKK)
    line = live.line(4, "ok", now)
    check("live line names remaining points, ETA and next n", "1 point(s) left" in line and "next n=5" in line,
          line)
    check("live line crosses midnight with a date", "Sun 04 Oct" in line, line)
    live.record(5, 700.0)
    check("last point: 'all planned points done' line", "all planned points done" in live.line(5, "ok", now))


def test_watcher_live_update_with_mock_csv():
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "memory_wall.csv"
        with open(csv_path, "w", newline="") as f:
            csv.writer(f).writerow(["board", "circuit", "n", "status", "timestamp_utc"])
        pts = eta.plan_points("uno", "h_all", 2, n_start=2, n_max=5)
        start = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
        out = []
        w = eta.PointWatcher(csv_path, pts, run_start=start, out=out.append,
                             now_fn=lambda: datetime(2026, 10, 3, 19, 0, tzinfo=BKK))
        check("no new rows: poll prints nothing", w.poll() == [])

        def add(n, status, t):
            with open(csv_path, "a", newline="") as f:
                csv.writer(f).writerow(["uno", "h_all", n, status, t.isoformat()])

        add(2, "ok", start + timedelta(seconds=40))
        lines = w.poll()
        check("one new row -> exactly one ETA line", len(lines) == 1 and "n=2 ok in 40.0s" in lines[0], str(lines))
        check("remaining points counted", "3 point(s) left" in lines[0], lines[0])
        add(3, "ok", start + timedelta(seconds=75))
        add(4, "ok", start + timedelta(seconds=120))
        lines2 = w.poll()
        check("two rows at once -> two lines in order, durations are deltas",
              len(lines2) == 2 and "n=3 ok in 35.0s" in lines2[0] and "n=4 ok in 45.0s" in lines2[1], str(lines2))
        check("poll is idempotent (no duplicate lines)", w.poll() == [])
        w2 = eta.PointWatcher(csv_path, pts, run_start=start, out=out.append, skip_existing=True)
        check("skip_existing ignores rows from earlier runs (resume)", w2.poll() == [])


# ------------------------------------------------------ plan-wide / run.py

def test_plan_report():
    buf = []
    res = eta.plan_report(out=buf.append, start=datetime(2026, 10, 3, 9, 0, tzinfo=BKK))
    text = "\n".join(buf)
    rows = res["rows"]
    check("plan report covers all 24 board x circuit x phase rows", len(rows) == 24)
    check("per-board totals sum to the grand total",
          approx(sum(d["total_s"] for d in res["per_board"].values()), res["grand"]["total_s"], 1e-3))
    check("grand total equals the sum of every row",
          approx(sum(t["total_s"] for _, _, _, _, t in rows), res["grand"]["total_s"], 1e-3))
    check("excluding-time-limited total is smaller and consistent",
          approx(res["grand"]["total_s"] - res["grand"]["limited_s"], res["grand"]["excl_s"], 1e-3)
          and res["grand"]["excl_s"] < res["grand"]["total_s"])
    check("predicted wall n shown per phase-2 row", "build_overflow" in text and "malloc_failed" in text)
    check("no removed circuit appears", "qpe" not in text and "steane" not in text)
    check("GRAND TOTAL line present", "GRAND TOTAL" in text)


def test_run_py_plan_and_dry_run():
    with captured() as out:
        code = run_mod.main(["--plan", "--brief"])
    check("run.py --plan --brief exits 0 and prints the grand total", code == 0 and "GRAND TOTAL" in out.getvalue())
    with captured() as out2:
        code2 = run_mod.main(["--plan", "--board", "uno", "--algorithm", "grover", "--phase", "2"])
    t2 = out2.getvalue()
    check("--plan with filters prints the per-n table for that row only",
          code2 == 0 and "board=uno circuit=grover phase=2" in t2 and "board=esp32" not in t2)
    err = io.StringIO()
    saved = sys.stderr
    sys.stderr = err
    try:
        with captured():
            code3 = run_mod.main(["--plan", "--algorithm", "qpe"])
    finally:
        sys.stderr = saved
    check("--plan with a removed circuit is refused with the removal message",
          code3 == 1 and "qpe removed from the experiment plan on 2026-10-03" in err.getvalue())

    ledger = Path(tempfile.mkdtemp(prefix="eta_test_ledger_")) / "run_history.jsonl"
    saved_ledger = run_mod.rh.LEDGER_PATH
    run_mod.rh.LEDGER_PATH = ledger
    try:
        with captured() as out4:
            code4 = run_mod.main(["--board", "esp32", "--algorithm", "qft", "--phase", "2",
                                  "--port", "/dev/cu.FAKE", "--dry-run"])
    finally:
        run_mod.rh.LEDGER_PATH = saved_ledger
    t4 = out4.getvalue()
    check("--dry-run prints the run-time table before preflight",
          code4 == 0 and "run-time estimate: board=esp32 circuit=qft phase=2" in t4
          and t4.index("run-time estimate") < t4.index("--- preflight ---"))


class _Result:
    returncode = 0
    stdout = ""
    stderr = ""


def test_real_run_prints_live_eta_with_mocked_subprocess():
    """A 'real' (non --dry-run) run in a scratch repo root: the fake delegated
    script appends terminal records the way a sweep does; run.py must print an
    ETA line per recorded point."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        saved = (run_mod.REPO_ROOT, sp.REPO_ROOT, run_mod.git_state, run_mod.port_exists,
                 run_mod.port_matches_board, run_mod.port_holder_pids, run_mod.subprocess.run,
                 run_mod.rh.LEDGER_PATH, run_mod.generate_figures)
        run_mod.REPO_ROOT = root
        sp.REPO_ROOT = root
        run_mod.git_state = lambda: (True, "fake")
        run_mod.port_exists = lambda port: True
        run_mod.port_matches_board = lambda board, port: True
        run_mod.port_holder_pids = lambda port: []
        run_mod.rh.LEDGER_PATH = root / "ledger.jsonl"
        run_mod.generate_figures = lambda *a, **k: None
        calls = []

        def fake_run(argv, *a, **k):
            calls.append(argv)
            if isinstance(argv, list) and "uno_sweep.py" in " ".join(map(str, argv)):
                path = sp.memory_wall_csv_path("uno", "h_all", 2, False)
                path.parent.mkdir(parents=True, exist_ok=True)
                t0 = datetime.now(UTC)
                with open(path, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["board", "circuit", "n", "status", "timestamp_utc"])
                    for i, n in enumerate((2, 3, 4)):
                        w.writerow(["uno", "h_all", n, "ok", (t0 + timedelta(seconds=10 * (i + 1))).isoformat()])
            return _Result()

        run_mod.subprocess.run = fake_run
        try:
            with captured() as out:
                code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                     "--port", "/dev/cu.FAKE", "--yes", "--n-max", "5"])
        finally:
            (run_mod.REPO_ROOT, sp.REPO_ROOT, run_mod.git_state, run_mod.port_exists,
             run_mod.port_matches_board, run_mod.port_holder_pids, run_mod.subprocess.run,
             run_mod.rh.LEDGER_PATH, run_mod.generate_figures) = saved
        text = out.getvalue()
        etas = [ln for ln in text.splitlines() if ln.startswith("[ETA]")]
        check("real run exits 0", code == 0, f"code={code}")
        check("one [ETA] line per recorded point (3 rows written)", len(etas) == 3, str(etas))
        check("last ETA line shows the remaining point count", "point(s) left" in etas[-1] if etas else False,
              etas[-1] if etas else "")


def test_tiers_and_watchdog():
    check("duration tiers", [eta.duration_tier(x) for x in (3600, 7 * 3600, 25 * 3600, 73 * 3600)] == ["", ">6h", ">24h", ">72h"])
    p = eta.estimate_point("esp8266", "grover", 8, 2)
    check("esp8266 grover n=8: per rep 15.6 s > 6.0 s -> watchdog risk", p.wdt_risk and p.per_rep_s > 6.0, f"{p.per_rep_s:.1f}")
    check("esp32 grover n=9: 7.0 s > 5.0 s -> watchdog risk", eta.estimate_point("esp32", "grover", 9, 2).wdt_risk)
    check("esp32 grover n=8: 0.83 s -> no watchdog risk", not eta.estimate_point("esp32", "grover", 8, 2).wdt_risk)
    check("uno has no WDT threshold", not eta.estimate_point("uno", "grover", 7, 2).wdt_risk)
    check("phase 3 and wall points are never watchdog risk",
          not eta.estimate_point("esp8266", "grover", 9, 3).wdt_risk and not eta.estimate_point("esp8266", "grover", 13, 2).wdt_risk)
    text = eta.format_table("esp8266", "grover", 2, eta.plan_points("esp8266", "grover", 2),
                            datetime(2026, 10, 3, 9, 0, tzinfo=BKK))
    check("table shows >72h and WATCHDOG RISK notes and a per-rep column", ">72h" in text and "WATCHDOG RISK" in text and "per-rep" in text)
    buf = []
    eta.plan_report(brief=True, out=buf.append)
    t = "\n".join(buf)
    check("plan report lists tier counts and grover time to wall",
          ">72h 2" in t and "grover, time to complete up to the predicted wall" in t and "n=2..13" in t)


def main():
    test_tiers_and_watchdog()
    test_plan_scope_and_ranges()
    test_estimates_and_labels()
    test_plan_points_filters()
    test_clock_arithmetic()
    test_table_text()
    test_live_eta_arithmetic()
    test_watcher_live_update_with_mock_csv()
    test_plan_report()
    test_run_py_plan_and_dry_run()
    test_real_run_prints_live_eta_with_mocked_subprocess()
    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
