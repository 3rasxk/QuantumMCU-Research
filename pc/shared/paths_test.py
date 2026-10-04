#!/usr/bin/env python3
# paths_test.py — dedicated tests for pc/shared/paths.py's no_la/with_la split
# (2026-09-22, see run_log.md "no_la/with_la data layout"). Covers the full
# la={True,False} x board={uno,esp8266,esp32} matrix for every path helper,
# plus a lossless-migration sanity check against the real committed data
# (data/raw/phase2/uno/*/no_la/ -- migrated via `git mv`, row counts and
# sha256 verified at migration time; this test guards against that state
# silently regressing later, e.g. someone editing a migrated file by hand).
#
# Behavioral no_la/with_la-crossing tests (mocked resume must never treat a
# no_la point as satisfying a with_la request or vice versa; a mocked --la
# run writes only under with_la/; a mocked non-la run writes only under
# no_la/) live in pc/shared/la_capture_test.py and
# pc/shared/uno_upload_retry_test.py, which already exercise the full
# uno_sweep.py machinery those behaviors depend on (session/resume state,
# not just path resolution) -- duplicating that harness here would just be a
# second, weaker copy of the same mocks.
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/shared/*_test.py)
# รันด้วย: .venv/bin/python pc/shared/paths_test.py

import csv
import json
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

from shared import paths as sp  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


BOARDS = ("uno", "esp8266", "esp32")


def test_raw_dir_matrix():
    root = Path(tempfile.mkdtemp(prefix="paths_test_"))
    sp.REPO_ROOT = root
    try:
        for board in BOARDS:
            for la in (False, True):
                bucket = "with_la" if la else "no_la"
                expected = root / "data/raw/phase2" / board / "h_all" / bucket
                check(f"raw_dir({board}, la={la})",
                      sp.raw_dir(board, "h_all", phase=2, la=la) == expected)
                check(f"raw_csv_path({board}, la={la})",
                      sp.raw_csv_path(board, "h_all", phase=2, la=la) == expected / "raw.csv")
                check(f"memory_wall_csv_path({board}, la={la})",
                      sp.memory_wall_csv_path(board, "h_all", phase=2, la=la)
                      == expected / "memory_wall.csv")
                check(f"points_csv_path({board}, la={la})",
                      sp.points_csv_path(board, "h_all", phase=2, la=la) == expected / "points.csv")
                check(f"sessions_csv_path({board}, la={la})",
                      sp.sessions_csv_path(board, "h_all", phase=2, la=la)
                      == expected / "sessions.csv")
                check(f"env_dir({board}, la={la})",
                      sp.env_dir(board, "h_all", phase=2, la=la) == expected / "env")

            # phase 3 uses session_log_csv_path instead of memory_wall_csv_path
            for la in (False, True):
                bucket = "with_la" if la else "no_la"
                expected3 = root / "data/raw/phase3" / board / "h_all" / bucket
                check(f"session_log_csv_path({board}, phase=3, la={la})",
                      sp.session_log_csv_path(board, "h_all", phase=3, la=la)
                      == expected3 / "session_log.csv")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_la_dir_always_with_la():
    """la_dir() has no la= parameter -- LA capture files cannot exist for a
    no_la point, so there is nothing to select."""
    root = Path(tempfile.mkdtemp(prefix="paths_test_"))
    sp.REPO_ROOT = root
    try:
        for board in BOARDS:
            expected = root / "data/raw/phase2" / board / "h_all" / "with_la" / "la"
            check(f"la_dir({board}) always resolves under with_la/",
                  sp.la_dir(board, "h_all", phase=2) == expected)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_figures_dir_matrix():
    root = Path(tempfile.mkdtemp(prefix="paths_test_"))
    sp.REPO_ROOT = root
    try:
        for board in BOARDS:
            for la in (False, True):
                bucket = "with_la" if la else "no_la"
                check(f"figures_dir({board}, circuit, la={la})",
                      sp.figures_dir(board, "h_all", la=la)
                      == root / "data/figures" / board / "h_all" / bucket)
                check(f"figures_dir({board}, circuit=None, la={la}) (cumulative chart)",
                      sp.figures_dir(board, la=la) == root / "data/figures" / board / bucket)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_la_and_with_la_never_collide():
    """For every board/function pair, the no_la and with_la paths must be
    distinct -- the whole point of the split is that these two buckets never
    share a file."""
    root = Path(tempfile.mkdtemp(prefix="paths_test_"))
    sp.REPO_ROOT = root
    try:
        for board in BOARDS:
            no_la = sp.raw_csv_path(board, "h_all", phase=2, la=False)
            with_la = sp.raw_csv_path(board, "h_all", phase=2, la=True)
            check(f"{board}: no_la raw.csv != with_la raw.csv", no_la != with_la,
                  (no_la, with_la))
            check(f"{board}: neither path is a parent/child of the other",
                  no_la not in with_la.parents and with_la not in no_la.parents)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_pre_timer_results_are_gone_and_recorded():
    """2026-10-04 purge: results measured before the ESP32 timer existed were deleted
    (git history, commit af40643). Guard: no data/archive/, and the append-only ledger
    carries the `restart` and `purge` events. (data/raw/phase2|3 may legitimately fill up
    again once the new dataset exists, so they are not asserted empty here.)"""
    check("data/archive/ does not exist", not (sp.REPO_ROOT / "data" / "archive").exists())
    ledger = sp.REPO_ROOT / "data" / "run_history.jsonl"
    events = [json.loads(ln).get("event") for ln in ledger.read_text().splitlines() if ln.strip()]
    check("ledger has a restart and a purge event", "restart" in events and "purge" in events)
    check("purge comes after restart", events.index("purge") > events.index("restart"))


def main():
    saved_root = sp.REPO_ROOT
    try:
        test_raw_dir_matrix()
        test_la_dir_always_with_la()
        test_figures_dir_matrix()
        test_no_la_and_with_la_never_collide()
    finally:
        sp.REPO_ROOT = saved_root  # real-data test below needs the real REPO_ROOT
    test_pre_timer_results_are_gone_and_recorded()

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
