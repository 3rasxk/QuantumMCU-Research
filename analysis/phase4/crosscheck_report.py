"""Step 4 check: pick random numbers quoted in docs/phase4_report.md and recompute each straight from data/raw with the
csv module only (no pandas, none of the Phase 4 code). Usage: crosscheck_report.py [seed]"""
import csv
import glob
import json
import os
import random
import re
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT = open(os.path.join(ROOT, "docs", "phase4_report.md")).read()
rows = lambda p: list(csv.DictReader(open(os.path.join(ROOT, p))))
S2 = lambda b, c, f: f"data/raw/phase2/{b}/{c}/with_ref/{f}"
S3 = lambda b, c, f: f"data/raw/phase3/{b}/{c}/with_ref/{f}"


def in_report(txt):
    return txt in REPORT


def c_esp8266_B():
    r = [x for x in rows(S2("esp8266", "qft", "raw.csv")) if x["n"] == "2"][0]
    return "ESP8266 B (free_heap_before@n=2 + 8*2^2)", str(int(r["free_heap_before"]) + 32), "52240"


def c_esp32_lb():
    r = [x for x in rows(S2("esp32", "h_all", "raw.csv")) if x["n"] == "2"][0]
    return "ESP32 largest_block @n=2", r["largest_block"], "110580"


def c_uno_over():
    r = [x for x in rows(S2("uno", "qft", "memory_wall.csv")) if x["n"] == "7"][0]
    return "Uno qft static overhead (compile_ram_used - 8*2^7)", str(int(r["compile_ram_used_bytes"]) - 1024), "200"


def c_grover9():
    r = [x for x in rows("data/raw/phase1/infidelity_tvd.20261003T111917Z.csv") if x["circuit"] == "grover" and x["n"] == "9"][0]
    return "grover n=9 infidelity", f"{float(r['infidelity']):.2e}", "1.47e-03"


def c_grover12():
    r = rows("data/raw/phase1/infidelity_tvd.20261004T091042Z.csv")[0]
    return "grover n=12 infidelity", f"{float(r['infidelity']):.3f}", "0.109"


def c_reps():
    n = sum(1 for x in rows(S2("esp8266", "grover", "raw.csv")) if x["n"] == "9")
    return "ESP8266 grover n=9 reps (raw rows)", str(n), "37"


def c_ppm():
    return "counter ppm vs PC clock", f"{json.load(open(os.path.join(ROOT, 'data/calibration/counter_20261004.json')))['ppm']:.1f}", "17.5"


def c_sidecars():
    fs = glob.glob(os.path.join(ROOT, "data/raw/phase*/*/*/with_ref/env/*.ref.json"))
    return "ref sidecars with empty calibration", str(sum(1 for f in fs if not json.load(open(f)).get("calibration"))), "60 session sidecars"


def c_floor():
    meds = []
    for c in ("h_all", "bell_ghz", "qft", "grover"):
        for n in range(2, 5):
            v = [float(x["e2e_latency_us"]) for x in rows(S3("esp8266", c, "raw.csv")) if x["n"] == str(n)
                 and x["timed_out"] == "0" and x["crc_error"] == "0"]
            meds.append(statistics.median(v))
    val = f"{statistics.median(meds) / 1000:.1f}"
    return "ESP8266 offload floor, median of the 12 per-point medians at n<=4 (ms)", val, f"{val} ms (ESP8266)"


def c_cross():
    loc, off = {}, {}
    for x in rows(S2("esp8266", "h_all", "raw.csv")):
        loc.setdefault(int(x["n"]), []).append(float(x["exec_time_us"]))
    for x in rows(S3("esp8266", "h_all", "raw.csv")):
        if x["timed_out"] == "0" and x["crc_error"] == "0":
            off.setdefault(int(x["n"]), []).append(float(x["e2e_latency_us"]))
    first = min(n for n in loc if n in off and statistics.median(off[n]) < statistics.median(loc[n]))
    tok = f"| ESP8266 | h_all | 2-12 | {first} |"
    return "ESP8266 h_all first measured n offload faster (table row)", str(first), tok


def c_ctr():
    r = [x for x in rows(S2("esp32", "grover", "ref/ref_compare.csv")) if x["n"] == "12"]
    return "ESP32 grover n=12 counter value (s) and pairs", f"{float(r[0]['counter_us']) / 1e6:.2f}", "1.71"


CHECKS = [c_esp8266_B, c_esp32_lb, c_uno_over, c_grover9, c_grover12, c_reps, c_ppm, c_sidecars, c_floor, c_cross, c_ctr]
if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else int.from_bytes(os.urandom(4), "big")
    random.seed(seed)
    print("seed", seed)
    bad = 0
    for fn in random.sample(CHECKS, 5):
        name, raw_val, quoted = fn()
        if quoted is None:
            quoted = raw_val
        ok = in_report(quoted) and (quoted.split()[0] == raw_val or raw_val in quoted)
        if fn is c_cross:
            ok = in_report(quoted)
        print(("OK  " if ok else "BAD ") + f"{name}: raw={raw_val} report-token={quoted!r} found={in_report(quoted)}")
        bad += not ok
    sys.exit(1 if bad else 0)
