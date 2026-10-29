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
    # static part: a test that can reach the ledger but does not import shared.test_ledger would hit the REAL ledger when run standalone
    # (the per-test environment below would hide that), so every such test file must import the helper
    reach = ("run_history", "import run as", "import run\n", "run_mod", "importlib")
    missing = [str(t.relative_to(REPO_ROOT)) for t in tests
               if any(k in t.read_text() for k in reach) and "shared.test_ledger" not in t.read_text() and t.name != "run_history_env_test.py"
               and t.name != "audit_data_test.py"]   # audit_data_test only reads a ledger it builds in its own temp directory (never pc/shared/run_history.py)
    print("tests that can reach the ledger without importing shared.test_ledger:", missing or "none")
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
    # the verdict of THIS test is about the ledger only (byte-identical, and every ledger-capable test imports the redirect helper);
    # failures of individual tests are listed above and judged by the suite run
    sys.exit(0 if same and not missing else 1)


if __name__ == "__main__":
    main()
