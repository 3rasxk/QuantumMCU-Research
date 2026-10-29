#!/usr/bin/env python3
"""Runs every other *_test.py in the repo and asserts data/run_history.jsonl is byte-identical before and after (item 6).
Each test is started with QLAB_RUN_HISTORY pointing at a temp file AND with the real ledger made read-only for the duration, so a test
that tries to append to it would fail loudly instead of silently polluting it. Slow (the whole suite): run it last.
Run:  .venv/bin/python pc/suite_ledger_guard_test.py"""
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "data" / "run_history.jsonl"


def sha():
    return hashlib.sha256(LEDGER.read_bytes()).hexdigest()


def main():
    tests = sorted(p for p in REPO_ROOT.rglob("*_test.py")
                   if ".venv" not in p.parts and "data" not in p.parts and p.name != Path(__file__).name
                   and "suite_ledger_guard" not in p.name)
    before, mode = sha(), LEDGER.stat().st_mode
    bad = []
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, QLAB_RUN_HISTORY=str(Path(td) / "ledger.jsonl"))
        os.chmod(LEDGER, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        try:
            for t in tests:
                r = subprocess.run([sys.executable, str(t)], cwd=REPO_ROOT, env=env, capture_output=True, text=True)
                print(("ok   " if r.returncode == 0 else "FAIL ") + str(t.relative_to(REPO_ROOT)))
                if r.returncode != 0:
                    bad.append(str(t.relative_to(REPO_ROOT)))
        finally:
            os.chmod(LEDGER, mode)
    same = sha() == before
    print(f"\n{len(tests)} test files run, {len(bad)} failed, real ledger byte-identical: {same}")
    if not same:
        print("FAIL: data/run_history.jsonl changed during the suite")
    # the verdict of THIS test is only about the ledger; individual test failures are listed above and judged by the suite run
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
