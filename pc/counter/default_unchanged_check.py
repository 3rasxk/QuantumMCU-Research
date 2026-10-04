#!/usr/bin/env python3
# default_unchanged_check.py -- proof that the three Phase 2 sweep scripts behave IDENTICALLY with the default
# `--ref none` before and after the counter hooks were added (no hardware, mocked build/upload/serial).
#
# It runs the same mocked scenario (an upload failure + retry, ok points, a wall point) against two code trees:
#   baseline = a git commit before the counter hooks (default 422216c), checked out into a temp worktree
#   current  = this working tree
# and compares sha256 of the NORMALISED result files (raw.csv, memory_wall.csv without its timestamp column,
# points.csv reduced to its deterministic columns). Directory bucket names differ between the trees
# (no_la -> no_ref) so files are located through pc/shared/paths.py of each tree, not by name.
#   .venv/bin/python pc/counter/default_unchanged_check.py [--baseline 422216c]
# Exit 0 = identical for every board.

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def dump(tree, board, out):
    """Run inside a tree: mocked sweep, then print normalised file contents as JSON."""
    sys.path.insert(0, str(tree / "pc"))
    sys.path.insert(0, str(tree / "pc" / "phase2_sweep"))
    import importlib
    from shared import paths as sp
    scratch = Path(tempfile.mkdtemp(prefix="dflt_"))
    sp.REPO_ROOT = scratch
    state = {"n2_calls": 0}
    if board == "uno":
        import uno_sweep as m
        m.find_uno_port = lambda hint: "/dev/fake"
        m.port_still_enumerated = lambda: True

        def build(circuit, n, port_hint, build_timeout_s=None):
            if n == 2 and state["n2_calls"] == 0:
                state["n2_calls"] += 1
                return {"ok": False, "ram_pct": 11.3, "ram_bytes": 232, "log": "avrdude: stk500_getsync(): not in sync",
                        "port": "/dev/fake", "compile_s": 4.0, "upload_s": 6.3, "stage": "upload", "timed_out": False}
            return {"ok": True, "ram_pct": 110.0 if n == 4 else 12.0, "ram_bytes": 2250 if n == 4 else 234, "log": "",
                    "port": "/dev/fake", "compile_s": 0.5, "upload_s": 0.5, "stage": "upload", "timed_out": False}
        m.build_and_upload = build
        m.read_serial_trials = lambda port, circuit, n, t, **k: (True, [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(100)], "reset_count=0")
    else:
        m = importlib.import_module(f"{board}_sweep")
        m.find_esp_port = lambda hint: "/dev/fake"
        m.port_still_enumerated = lambda: True

        def build(circuit, n, port_hint, build_timeout_s=None):
            if n == 2 and state["n2_calls"] == 0:
                state["n2_calls"] += 1
                return {"ok": False, "ram_pct": None, "ram_bytes": None, "log": "Failed to connect: No serial data received.",
                        "port": "/dev/fake", "compile_s": 3.0, "upload_s": 5.0, "stage": "upload", "timed_out": False}
            return {"ok": True, "ram_pct": None, "ram_bytes": None, "log": "", "port": "/dev/fake",
                    "compile_s": 0.5, "upload_s": 0.5, "stage": "upload", "timed_out": False}
        m.build_and_upload = build
        extra = ",900" if board == "esp32" else ""

        def read(port, circuit, n, t, **k):
            if n == 4:
                return False, [], True, "MALLOC_FAILED"
            return True, [f"{board},{circuit},{n},{r},100,1000,1000{extra}" for r in range(100)], False, "reset_count=0"
        m.read_serial_trials = read
    sys.argv = [f"{board}_sweep.py", "--port", "/dev/fake", "--circuits", "h_all", "bell_ghz", "--n-start", "2",
                "--n-max", "5", "--upload-retry-settle-s", "0"] if board == "uno" else \
               [f"{board}_sweep.py", "--port", "/dev/fake", "--circuits", "h_all", "bell_ghz", "--n-start", "2", "--n-max", "5"]
    try:
        m.main()
    except SystemExit as e:
        print(f"exit {e.code}", file=sys.stderr)
    res = {}
    for circuit in ("h_all", "bell_ghz"):
        raw = Path(sp.raw_csv_path(board, circuit))
        wall = Path(sp.memory_wall_csv_path(board, circuit))
        pts = Path(sp.points_csv_path(board, circuit))
        res[circuit] = {
            "raw": raw.read_text() if raw.exists() else None,
            "wall": [{k: v for k, v in r.items() if k != "timestamp_utc"} for r in csv.DictReader(open(wall))] if wall.exists() else None,
            "points": [{k: r.get(k) for k in ("circuit", "n", "status", "failure_type", "retry_count", "attempt_index")}
                       for r in csv.DictReader(open(pts))] if pts.exists() else None,
        }
    Path(out).write_text(json.dumps(res, sort_keys=True))


def run_tree(tree, board):
    out = Path(tempfile.mkdtemp()) / "o.json"
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--dump", str(tree), board, str(out)],
                   cwd=tree, check=True, capture_output=True, text=True, timeout=600)
    return json.loads(out.read_text())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--dump":
        dump(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="422216c")
    args = ap.parse_args()
    wt = Path(tempfile.mkdtemp(prefix="baseline_")) / "wt"
    subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt), args.baseline], cwd=ROOT, check=True)
    ok_all = True
    try:
        for board in ("uno", "esp8266", "esp32"):
            a, b = run_tree(wt, board), run_tree(ROOT, board)
            ha = hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()
            hb = hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest()
            n_rows = sum(len(a[c]["raw"].splitlines()) for c in a if a[c]["raw"])
            same = ha == hb and n_rows > 0
            ok_all = ok_all and same
            print(f"[{'SAME' if same else 'DIFF'}] {board}: baseline {args.baseline} sha256 {ha[:16]}  current {hb[:16]}  ({n_rows} raw lines compared)")
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
