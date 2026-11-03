#!/usr/bin/env python3
"""Tests for analysis/phase4/data_freeze.py. Run: .venv/bin/python analysis/phase4/data_freeze_test.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data_freeze as F  # noqa: E402

FAILS = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def main():
    check("manifest matches data/raw and data/derived", F.check_manifest())
    ent = F.manifest_entries()
    names = [r for _, r, _ in ent]
    check("manifest does not list itself", "data/derived/MANIFEST.sha256" not in names)
    check("manifest covers raw and derived", any(n.startswith("data/raw/") for n in names) and any(n.startswith("data/derived/") for n in names))
    check("manifest sorted", names == sorted(names, key=lambda x: x.encode()))
    check("docs/DATA_FREEZE.md equals a fresh build", open(F.DOC).read() == F.build_doc(ent))
    r = subprocess.run(["shasum", "-a", "256", "-c", F.MANIFEST], cwd=F.ROOT, capture_output=True, text=True)
    check("shasum -c accepts the manifest", r.returncode == 0)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
