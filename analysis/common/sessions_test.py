#!/usr/bin/env python3
"""Tests for analysis/common/sessions.py. Run: .venv/bin/python analysis/common/sessions_test.py"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
from common import sessions as S  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def main():
    sel = S.select_session
    check("Uno, all circuits and phases: original", all(sel(p, "uno", c, n) == "with_ref" for p in (2, 3) for c in S.CIRCUITS for n in (2, 5, 8)))
    check("ESP8266 P2 h_all/bell_ghz/qft: original", all(sel(2, "esp8266", c, n) == "with_ref" for c in ("h_all", "bell_ghz", "qft") for n in (2, 7, 12)))
    check("ESP8266 P2 grover n=2-8 -> r2, n=9-10 -> original", all(sel(2, "esp8266", "grover", n) == "with_ref_r2" for n in range(2, 9))
          and all(sel(2, "esp8266", "grover", n) == "with_ref" for n in (9, 10)))
    check("ESP8266 P2 grover n=7 counter pairs from r2b, n=8 stays r2 (no usable pairs anywhere)", S.counter_session(2, "esp8266", "grover", 7) == "with_ref_r2b"
          and S.counter_session(2, "esp8266", "grover", 8) == "with_ref_r2" and S.counter_session(2, "esp8266", "grover", 6) == "with_ref_r2")
    check("ESP32 P2: original except grover n=9-10 -> r2", all(sel(2, "esp32", "grover", n) == "with_ref" for n in (2, 8, 11, 12))
          and all(sel(2, "esp32", "grover", n) == "with_ref_r2" for n in (9, 10)) and sel(2, "esp32", "qft", 9) == "with_ref")
    check("ESP32 P2 grover n=9 counter pairs from r2c", S.counter_session(2, "esp32", "grover", 9) == "with_ref_r2c" and S.counter_session(2, "esp32", "grover", 10) == "with_ref_r2")
    check("ESP8266 P3: r2 for every circuit; ESP32 P3: original", all(sel(3, "esp8266", c, 5) == "with_ref_r2" for c in S.CIRCUITS) and all(sel(3, "esp32", c, 5) == "with_ref" for c in S.CIRCUITS))
    check("scope: n=1 excluded, P3 beyond the Phase 2 wall excluded (Uno 8, ESP8266 13, ESP32 14), the wall n itself included",
          not S.in_scope(2, "uno", "h_all", 1) and S.in_scope(3, "uno", "h_all", 8) and not S.in_scope(3, "uno", "h_all", 9)
          and S.in_scope(3, "esp8266", "qft", 13) and not S.in_scope(3, "esp8266", "qft", 14) and S.in_scope(3, "esp32", "qft", 14) and not S.in_scope(3, "esp32", "qft", 15))
    # read_selected: each n comes from exactly one session
    g = S.read_selected(2, "esp8266", "grover", "raw.csv")
    per_n = g.groupby("n")["session"].nunique()
    check("read_selected(ESP8266 P2 grover): one session per n, r2 for 2-8 and original for 9-10", (per_n == 1).all()
          and set(g[g.n.between(2, 8)].session) == {"with_ref_r2"} and set(g[g.n.isin([9, 10])].session) == {"with_ref"})
    g3 = S.read_selected(3, "esp8266", "grover", "raw.csv")
    check("read_selected(ESP8266 P3 grover): only r2, n 2-10 (the old n=11-13 points are not selected)", set(g3.session) == {"with_ref_r2"} and g3.n.min() == 2 and g3.n.max() == 10)
    u3 = S.read_selected(3, "uno", "h_all", "raw.csv")
    check("read_selected(Uno P3 h_all): scope cut at the wall n=8", u3.n.max() <= 8 and u3.n.min() >= 2)
    rep = S.replicates(2, "esp8266", "grover")
    check("replicates: ESP8266 P2 grover n=2-8 measured in more than one session", set(range(2, 9)) <= set(rep))
    # no pipeline script builds a raw-data path to an original bucket by itself
    allowed = {"sessions.py", "sessions_test.py", "counter_validity.py", "counter_validity_test.py"}
    offenders = []
    for d in ("analysis/phase4", "analysis/common"):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            if f.endswith(".py") and f not in allowed and f not in AUDIT_ALL_SESSIONS:
                txt = open(os.path.join(ROOT, d, f)).read()
                if re.search(r"""["']with_ref["']|series_dir\(""", txt):
                    offenders.append(f"{d}/{f}")
    check("no Phase 4 pipeline script hard-codes the original bucket or the old series_dir (the selector is the only door)", not offenders, str(offenders))
    print(f"\n{len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


# scripts that audit EVERY session on purpose (provenance, data audit, hash scan, repeat-session summaries): they read all buckets, never pick one as evidence
AUDIT_ALL_SESSIONS = {"audit.py", "provenance.py", "firmware_hash_scan.py", "firmware_hash_audit.py"}

if __name__ == "__main__":
    main()
