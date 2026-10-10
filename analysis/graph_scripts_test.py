#!/usr/bin/env python3
# graph_scripts_test.py -- tests for the Phase 2 / Phase 3 PNG chart scripts (phase2_uno_run_plots.py,
# phase2_cross_board_plots.py, phase3_run_plots.py, _graph_data.py) on SYNTHETIC data in a temp copy of the repo.
# Nothing here reads or writes the real data/. No pytest (same style as pc/shared/*_test.py).
# Run: .venv/bin/python analysis/graph_scripts_test.py

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REAL = Path(__file__).resolve().parent.parent
PASSED = FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"FAIL: {name} {extra}")


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


WALL_HDR = ["board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes", "compile_ram_pct", "status",
            "timestamp_utc", "retry_count", "timeout_budget_s", "expected_point_s", "retry_policy"]
PTS_HDR = ["schema_version", "session_id", "phase", "board", "circuit", "n", "baud", "attempt_index", "start_utc",
           "end_utc", "wall_s", "build_compile_s", "upload_s", "boot_wait_s", "device_exec_s", "pc_sim_s_total",
           "pc_sim_s_median", "serial_transfer_s_total", "avg_round_trip_latency_s", "crc_error_count",
           "bytes_transferred", "retry_count", "timeout_hit", "failure_type", "failure_message", "status"]


def p2_dir(root, bucket, board, circuit):
    return root / "data" / "raw" / "phase2" / board / circuit / bucket


def make_phase2(root, board, circuit, bucket="with_ref", scale=1.0, extra_status=False, physical=True):
    d = p2_dir(root, bucket, board, circuit)
    raw, wall, pts = [], [], []
    for n in range(2, 8):
        reps = 100 if not (extra_status and n == 6) else 1       # one-rep point (time-capped)
        for rep in range(reps):
            raw.append([board, circuit, n, rep, int(scale * 280 * 2 ** (n - 2) + rep % 3), 1700, 1700, 90])
        wall.append([board, circuit, n, 8 * 2 ** n, 200 + 8 * 2 ** n, 11.0, "ok", "2026-10-01T00:00:00+00:00", 0, 90, 0.1,
                     "allowed"])
        pts.append([2, "s1", 2, board, circuit, n, 115200, 0, "", "", 1, 5.0, 3.0, 1, 1, "", "", "", "", "", "", 0, False,
                    "none", "", "ok"])
    if extra_status:
        # a watchdog attempt before n=7 finally ran, a reset / hang / upload failure with no wall evidence, a skip
        pts.append([2, "s1", 2, board, circuit, 7, 115200, 0, "", "", 1, 5.0, 3.0, 1, 1, "", "", "", "", "", "", 0, False,
                    "watchdog_suspected", "reset", "failed"])
        for n, st in ((8, "runtime_hang_or_reset"), (9, "build_or_upload_fail"), (10, "watchdog_suspected(x)"),
                      (11, "skipped_compute_infeasible")):
            wall.append([board, circuit, n, 8 * 2 ** n, "", "", st, "2026-10-01T00:00:00+00:00", 0, 90, 0.1, "allowed"])
    else:
        wall.append([board, circuit, 8, 2048, 2250, 109.9, "build_overflow", "2026-10-01T00:00:00+00:00", 0, 90, 6.0,
                     "allowed"])
        pts.append([2, "s1", 2, board, circuit, 8, 115200, 0, "", "", 1, 5.0, 3.0, 1, 1, "", "", "", "", "", "", 0, False,
                    "build", "x", "failed"])
    write_csv(d / "raw.csv", ["board", "circuit", "n", "rep", "exec_time_us", "free_heap_before", "free_heap_after",
                              "timeout_budget_s"], raw)
    write_csv(d / "memory_wall.csv", WALL_HDR, wall)
    write_csv(d / "points.csv", PTS_HDR, pts)
    (d / "env").mkdir(parents=True, exist_ok=True)
    (d / "env" / "s1.json").write_text(json.dumps({"git_commit": "abcdef1234567", "recorded_utc": "2026-10-01T00:00:00"}))
    if bucket == "with_ref":
        (d / "env" / "s1.ref.json").write_text(json.dumps(
            {"counter_port": "tcp:5055" if physical else "SIM", "counter_fw_sha256": "00ff"}))
        cmp_rows = []
        for n in range(2, 8):
            for rep in range(100 if not (extra_status and n == 6) else 1):
                m = 280 * 2 ** (n - 2)
                cmp_rows.append([1, "", board, circuit, n, rep, m, m + 3.0, -3.0, -3.0 / m * 100])
        write_csv(d / "ref" / "ref_compare.csv", ["schema_version", "session_id", "board", "circuit", "n", "rep",
                                                  "micros_us", "counter_us", "diff_us", "diff_pct"], cmp_rows)
        write_csv(d / "ref" / "ref_compare_points.csv", ["board", "circuit", "n", "n_pairs", "ref_status"],
                  [[board, circuit, n, 100 if not (extra_status and n == 6) else 1, "ok"] for n in range(2, 8)])


def make_phase3(root, board, circuit, bucket="with_ref"):
    d = root / "data" / "raw" / "phase3" / board / circuit / bucket
    raw, log, pts = [], [], []
    for n in range(2, 7):
        for rep in range(100):
            raw.append([board, circuit, n, 115200, rep, 3000 + 400 * n + rep % 5, 0, 0])
        log.append([board, circuit, n, 115200, "ok", 100, 0, 100, "", "t", 300, 8, 0.01])
        sim = 0.3 * n
        pts.append([2, "s3", 3, board, circuit, n, 115200, 0, "", "", 10, 5, 3, 1.5, 12.0, sim, 0.003, 12 - sim,
                    0.005, 0, 1000, 0, False, "none", "", "ok"])
    log.append([board, circuit, 9, 115200, "skipped_sim_cost_infeasible", 0, 0, 0, "", "t", 300, 8, 0.01])
    write_csv(d / "raw.csv", ["board", "circuit", "n", "baud_rate", "rep", "e2e_latency_us", "crc_error", "timed_out"], raw)
    write_csv(d / "session_log.csv", ["board", "circuit", "n", "baud_rate", "status", "frames_served",
                                      "frames_dropped_bad_crc", "rows_captured", "last_sim_error", "timestamp_utc",
                                      "session_timeout_budget_s", "expected_session_s", "pc_sim_s_per_request"], log)
    write_csv(d / "points.csv", PTS_HDR, pts)
    (d / "env").mkdir(parents=True, exist_ok=True)
    (d / "env" / "s3.json").write_text(json.dumps({"git_commit": "1234567abcdef", "recorded_utc": "2026-10-02T00:00:00"}))
    # reference files next to the data: must be ignored by every Phase 3 chart
    write_csv(d / "ref" / "ref_compare_points.csv", ["n", "median_diff_us"], [[2, 1.0]])


def make_repo(tmp):
    root = Path(tmp) / "repo"
    shutil.copytree(REAL / "pc" / "shared", root / "pc" / "shared", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REAL / "analysis", root / "analysis", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data" / "figures").mkdir(parents=True)
    make_phase2(root, "uno", "h_all")
    make_phase2(root, "esp32", "h_all", scale=0.1)
    make_phase2(root, "esp32", "grover", extra_status=True)
    make_phase3(root, "uno", "h_all")
    make_phase3(root, "esp32", "h_all")
    return root


def run(root, script, *args):
    return subprocess.run([sys.executable, str(root / "analysis" / script), *args], cwd=root, capture_output=True,
                          text=True, timeout=300)


def snippet(root, code):
    """Run python in the temp repo with analysis/ and pc/ on the path; returns stdout."""
    pre = (f"import sys; sys.path.insert(0, {str(root / 'analysis')!r}); sys.path.insert(0, {str(root / 'pc')!r});"
           "import matplotlib; matplotlib.use('Agg');")
    r = subprocess.run([sys.executable, "-c", pre + code], cwd=root, capture_output=True, text=True, timeout=300)
    return r.stdout + r.stderr


def main():
    tmp = Path(tempfile.mkdtemp(prefix="graph_test_"))
    try:
        root = make_repo(tmp)
        (root / "data" / "archive" / "x").mkdir(parents=True)
        (root / "data" / "archive" / "x" / "keep.txt").write_text("sentinel")
        before_raw, before_arc = tree_hash(root / "data" / "raw"), tree_hash(root / "data" / "archive")

        # --- full run on synthetic data
        for b, c in (("uno", "h_all"), ("esp32", "h_all"), ("esp32", "grover")):
            r = run(root, "phase2_uno_run_plots.py", "--board", b, "--circuit", c, "--ref")
            check(f"phase 2 {b}/{c} exits 0", r.returncode == 0, r.stderr[-300:])
        for b in ("uno", "esp32"):
            r = run(root, "phase3_run_plots.py", "--board", b, "--circuit", "h_all", "--ref")
            check(f"phase 3 {b}/h_all exits 0", r.returncode == 0, r.stderr[-300:])
        r = run(root, "phase2_cross_board_plots.py", "--circuit", "h_all", "--ref")
        check("cross-board exits 0", r.returncode == 0, r.stderr[-300:])

        fig = root / "data" / "figures"
        names = {p.relative_to(fig).as_posix() for p in fig.rglob("*") if p.is_file()}
        check("only PNG files under data/figures", all(n.endswith(".png") for n in names), str(sorted(names)))
        for stem in ("exec_time_vs_n", "outcomes_vs_n", "memory_vs_n", "time_per_point", "scaling", "micros_vs_counter"):
            check(f"phase 2 {stem}.png written", f"phase2/uno/h_all/{stem}.png" in names)
        check("cumulative chart written", "phase2/uno/all_algorithms_so_far.png" in names)
        check("cross-board chart written", "phase2/compare_h_all.png" in names)
        for stem in ("time_breakdown", "latency_vs_n", "reliability", "offload_vs_local"):
            check(f"phase 3 {stem}.png written", f"phase3/uno/h_all/{stem}.png" in names)
        check("phase 3 never draws a counter chart", not any("phase3" in n and "counter" in n for n in names))
        check("raw data untouched by a full run", tree_hash(root / "data" / "raw") == before_raw)
        check("archive untouched by a full run", tree_hash(root / "data" / "archive") == before_arc)

        # --- no wall marker without evidence; single-value point handled; categories
        out = snippet(root, """
import _graph_data as gd
S = gd.PointSet('esp32', 'grover', 2, True)
o = gd.outcomes_phase2(S)
print({n: v['cat'] for n, v in sorted(o.items())})
st = gd.stats([5.0]); print('single', st)
print('attempts', gd.failed_attempts(S))
""")
        check("watchdog/hang/upload-failure rows are never a wall",
              "'wall'" not in out.split("single")[0], out)
        check("one-rep point is ok_capped", "6: 'ok_capped'" in out, out)
        check("time-limited skip recognised", "11: 'time_limited'" in out, out)
        check("single value has no IQR", "single (5.0, None, None)" in out, out)
        check("watchdog attempt listed, not hidden", "7: ['watchdog_suspected']" in out, out)
        out = snippet(root, """
import _graph_data as gd, phase2_uno_run_plots as p2
from shared import plot_style as ps
caps = {}
ps.save_figure_png_only = lambda fig, d, stem: caps.setdefault(stem, fig) and []
S = gd.PointSet('esp32', 'grover', 2, True)
p2.plot_outcomes_vs_n(S); p2.plot_exec_time_vs_n(S); p2.plot_memory_vs_n(S)
for stem, f in caps.items():
    print(stem, 'X-markers', sum(1 for ax in f.axes for l in ax.lines if l.get_marker() == 'X'))
""")
        check("no X (wall) marker drawn on a dataset without recorded wall evidence",
              "outcomes_vs_n X-markers 0" in out and "exec_time_vs_n X-markers 0" in out and
              "memory_vs_n X-markers 0" in out, out)
        out = snippet(root, """
import _graph_data as gd, phase2_uno_run_plots as p2
from shared import plot_style as ps
caps = {}
ps.save_figure_png_only = lambda fig, d, stem: caps.setdefault(stem, fig) and []
p2.plot_outcomes_vs_n(gd.PointSet('uno', 'h_all', 2, True))
print('X', sum(1 for ax in caps['outcomes_vs_n'].axes for l in ax.lines if l.get_marker() == 'X'))
""")
        check("recorded build_overflow IS drawn as a wall", "X 1" in out, out)

        # --- with_ref and no_ref never mixed
        make_phase2(root, "uno", "h_all", bucket="no_ref", scale=7.0)
        out = snippet(root, """
import _graph_data as gd, phase2_uno_run_plots as p2, numpy as np
from shared import plot_style as ps
caps = {}
ps.save_figure_png_only = lambda fig, d, stem: caps.setdefault(stem, fig) and []
p2.plot_exec_time_vs_n(gd.PointSet('uno', 'h_all', 2, True))
ys = [float(l.get_ydata()[0]) for ax in caps['exec_time_vs_n'].axes for l in ax.lines
      if l.get_marker() == 'o' and len(l.get_ydata()) == 1 and l.get_linestyle() == 'None']
print('count', len(ys), 'max', max(ys))
""")
        check("with_ref chart uses only the with_ref bucket (no no_ref values)", "count 6" in out and
              float(out.split("max")[1].split()[0]) < 10000, out)
        r = run(root, "phase2_uno_run_plots.py", "--board", "uno", "--circuit", "h_all")
        check("no_ref run succeeds on the no_ref bucket", r.returncode == 0, r.stderr[-200:])

        # --- counter chart only for a physical counter
        d = p2_dir(root, "with_ref", "esp32", "h_all")
        (fig / "phase2" / "esp32" / "h_all" / "micros_vs_counter.png").unlink()
        (d / "env" / "s1.ref.json").write_text(json.dumps({"counter_port": "SIM", "counter_fw_sha256": "00"}))
        r = run(root, "phase2_uno_run_plots.py", "--board", "esp32", "--circuit", "h_all", "--ref")
        check("simulator-port session: no micros_vs_counter chart",
              not (fig / "phase2" / "esp32" / "h_all" / "micros_vs_counter.png").exists() and r.returncode == 0)

        # --- missing columns refused (exit 2, nothing plotted around)
        d = p2_dir(root, "with_ref", "esp32", "h_all")
        rows = list(csv.DictReader(open(d / "raw.csv")))
        write_csv(d / "raw.csv", ["board", "circuit", "n", "rep"], [[r["board"], r["circuit"], r["n"], r["rep"]] for r in rows])
        r = run(root, "phase2_uno_run_plots.py", "--board", "esp32", "--circuit", "h_all", "--ref")
        check("phase 2 refuses raw.csv without exec_time_us", r.returncode == 2 and "exec_time_us" in r.stderr, r.stderr[-200:])
        d3 = root / "data" / "raw" / "phase3" / "uno" / "h_all" / "with_ref"
        rows = list(csv.DictReader(open(d3 / "raw.csv")))
        write_csv(d3 / "raw.csv", ["board", "circuit", "n", "baud_rate", "rep"], [[r["board"], r["circuit"], r["n"],
                                                                                     r["baud_rate"], r["rep"]] for r in rows])
        r = run(root, "phase3_run_plots.py", "--board", "uno", "--circuit", "h_all", "--ref")
        check("phase 3 refuses raw.csv without e2e_latency_us", r.returncode == 2 and "e2e_latency_us" in r.stderr,
              r.stderr[-200:])

        # --- phase 3 ignores the counter files completely
        make_phase3(root, "uno", "h_all")
        shutil.rmtree(d3 / "ref")
        r = run(root, "phase3_run_plots.py", "--board", "uno", "--circuit", "h_all", "--ref")
        check("phase 3 charts do not need ref/ files", r.returncode == 0, r.stderr[-200:])
        check("phase 3 never opens a ref file (source check)", "ref_compare" not in
              (REAL / "analysis" / "phase3_run_plots.py").read_text().replace("ref_compare*", ""))

        # --- raw / archive untouched after all runs, still PNG-only
        names = {p.relative_to(fig).as_posix() for p in fig.rglob("*") if p.is_file()}
        check("only PNG files under data/figures at the end", all(n.endswith(".png") for n in names))
        check("archive untouched at the end", tree_hash(root / "data" / "archive") == before_arc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{PASSED} checks, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
