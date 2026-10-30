#!/usr/bin/env python3
"""The run-history ledger must be redirectable, and a test must never reach the real data/run_history.jsonl.
Run:  .venv/bin/python pc/shared/run_history_env_test.py"""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REAL = REPO_ROOT / "data" / "run_history.jsonl"
FAILS = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def sha():
    return hashlib.sha256(REAL.read_bytes()).hexdigest() if REAL.exists() else "absent"


def main():
    before = sha()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "ledger.jsonl"
        code = ("import sys; sys.path.insert(0, %r); from shared import run_history as rh; "
                "print(rh.LEDGER_PATH); rh.start_invocation(['x'], 'uno', 'h_all', 2, dry_run=True)"
                % str(REPO_ROOT / "pc"))
        env = dict(os.environ, QLAB_RUN_HISTORY=str(tmp))
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        check("QLAB_RUN_HISTORY redirects LEDGER_PATH", r.stdout.strip().splitlines()[0] == str(tmp) if r.stdout else False)
        check("an event written under the override lands in the temp file", tmp.exists() and tmp.read_text().count("\n") >= 1)
    check("the real ledger is byte-identical after the redirected write", sha() == before)
    # importing the test helper redirects too (this is what every ledger-capable test does first)
    code2 = ("import sys; sys.path.insert(0, %r); import shared.test_ledger; from shared import run_history as rh; print(rh.LEDGER_PATH)"
             % str(REPO_ROOT / "pc"))
    env2 = {k: v for k, v in os.environ.items() if k != "QLAB_RUN_HISTORY"}
    out = subprocess.run([sys.executable, "-c", code2], env=env2, capture_output=True, text=True).stdout.strip()
    check("pc/shared/test_ledger.py alone moves the ledger off data/run_history.jsonl", out and Path(out) != REAL and "qlab_ledger_" in out)
    print(f"\n{len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
