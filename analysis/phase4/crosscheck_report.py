"""Item 10: pick random numbers quoted in docs/phase4_report.md and recompute each straight from data/raw with the csv module only
(no pandas, none of the Phase 4 code). Usage: crosscheck_report.py [seed] [count]"""
import csv
import os
import random
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT = open(os.path.join(ROOT, "docs", "phase4_report.md")).read()
rows = lambda p: sel_rows(*p[1:]) if isinstance(p, tuple) else list(csv.DictReader(open(os.path.join(ROOT, p))))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
from common import sessions as SES  # noqa: E402  (pure selection rules; the numbers below are still computed with the csv module only)


def sel_rows(phase, b, c, f):
    """rows of `f` of the SELECTED session of each n (csv module only)"""
    out = []
    for bucket in SES.buckets(phase, b, c):
        p = os.path.join(SES.bucket_dir(phase, b, c, bucket), f)
        if os.path.exists(p):
            out += [x for x in csv.DictReader(open(p)) if SES.is_selected(phase, b, c, int(x["n"]), bucket)]
    return out


S2 = lambda b, c, f: ("sel", 2, b, c, f)
S3 = lambda b, c, f: ("sel", 3, b, c, f)
P1 = "data/raw/phase1/infidelity_tvd.20261003T111917Z.csv"


def c_p1_inf():
    r = [x for x in rows("data/raw/phase1/infidelity_tvd.20261004T091042Z.csv") if x["n"] == "12"][0]
    return "Phase 1 grover n=12 infidelity", f"{float(r['infidelity']):.3f}", "0.109"


def c_p1_marked():
    r = rows("data/raw/phase1/infidelity_tvd.20261004T091042Z.csv")[0]
    return "Phase 1 grover n=12 P(marked)", f"{float(r['grover_marked_prob']):.2f}", "0.89"


def c_reps(board, circuit, n, tok):
    def f():
        k = sum(1 for x in rows(S2(board, circuit, "raw.csv")) if x["n"] == str(n))
        return f"{board} {circuit} n={n} reps (raw rows)", str(k), tok
    return f


def c_pulse():
    p = [x for x in rows(S2("esp32", "grover", "ref/ref_pulses.csv")) if x["n"] == "12"]
    good = [x for x in p if x["anomaly_code"] == "0"][0]
    return "ESP32 grover n=12 clean counter pulse (s)", f"{float(good['width_us']) / 1e6:.3f}", "4519.488"


def c_wraps():
    p = [x for x in rows(S2("esp32", "grover", "ref/ref_pulses.csv")) if x["n"] == "12" and x["anomaly_code"] == "0"][0]
    return "ESP32 grover n=12 clean pulse wraps", p["wraps"], "wraps 84"


def c_tmax():
    return "T_max = (2^16-1) x 2^32 / 80 MHz (s)", f"{65535 * 2 ** 32 / 80e6:.4g}", "3.518e+06"


def c_heap():
    r = [x for x in rows(S2("esp8266", "qft", "raw.csv")) if x["n"] == "2"][0]
    return "ESP8266 B (free_heap_before@n=2 + 8*2^2)", str(int(r["free_heap_before"]) + 32), "52240"


def c_lb():
    r = [x for x in rows(S2("esp32", "h_all", "raw.csv")) if x["n"] == "2"][0]
    return "ESP32 largest_block @n=2", r["largest_block"], "110580"


def _med(v):
    return statistics.median(v)


def c_band():
    """ESP8266 qft crossover brackets recomputed from raw files with the csv module only: selected sessions, pc_sim pooled over every Phase 3 session of every board
    (in-scope n), wire + residual from the selected ESP8266 session; compare with the table row of section 5"""
    wall = {"uno": 8, "esp8266": 13, "esp32": 14}
    pc = {}
    for b in ("uno", "esp8266", "esp32"):
        for bucket in SES.buckets(3, b, "qft"):
            d = SES.bucket_dir(3, b, "qft", bucket)
            for x in csv.DictReader(open(os.path.join(d, "points.csv"))):
                if x["status"] == "ok" and 2 <= int(x["n"]) <= wall[b]:
                    pc.setdefault(int(x["n"]), []).append(float(x["pc_sim_s_median"]) * 1e6)
    loc, off, pts = {}, {}, {}
    for x in rows(S2("esp8266", "qft", "raw.csv")):
        loc.setdefault(int(x["n"]), []).append(float(x["exec_time_us"]))
    for x in rows(S3("esp8266", "qft", "raw.csv")):
        if x["timed_out"] == "0" and x["crc_error"] == "0":
            off.setdefault(int(x["n"]), []).append(float(x["e2e_latency_us"]))
    for x in rows(S3("esp8266", "qft", "points.csv")):
        if x["status"] == "ok":
            pts[int(x["n"])] = x
    ns = sorted(n for n in loc if n in off and n in pts and n in pc and 2 <= n <= 13)
    res = {}
    for bound, f in (("fast", min), ("slow", max)):
        ok = []
        for n in ns:
            e2e = _med(off[n]); p = pts[n]
            wire = float(p["bytes_transferred"]) / len(off[n]) * 10 / float(p["baud"]) * 1e6
            resid = e2e - float(p["pc_sim_s_median"]) * 1e6 - wire
            ok.append(wire + resid + f(pc[n]) < _med(loc[n]))
        first = next(i for i in range(len(ns)) if all(ok[i:]))
        res[bound] = f"{ns[first - 1]}-{ns[first]}"
    tok = f"| ESP8266 | qft | {ns[0]}-{ns[-1]} | {res['fast']} |"
    return "ESP8266 qft fast-bound crossover bracket (table row prefix)", res["fast"] + " / slow " + res["slow"], tok


def c_repro():
    d = lambda bucket: _med([float(x["exec_time_us"]) for x in csv.DictReader(open(os.path.join(SES.bucket_dir(2, "esp8266", "grover", bucket), "raw.csv"))) if x["n"] == "5"])
    a, b = d(SES.ORIGINAL), d(SES.ORIGINAL + "_r2")
    return "ESP8266 grover n=5 Phase 2 medians, original;r2 (reproducibility table)", f"{a:.3f};{b:.3f}", f"{a:.3f};{b:.3f}"


def c_p3reps():
    k = sum(1 for x in rows(S3("esp32", "grover", "raw.csv")) if x["n"] == "13")
    return "ESP32 grover Phase 3 n=13 requests", str(k), "2-42 requests"


def c_floor():
    meds = []
    for c in ("h_all", "bell_ghz", "qft", "grover"):
        for n in range(2, 5):
            v = [float(x["e2e_latency_us"]) for x in rows(S3("esp8266", c, "raw.csv")) if x["n"] == str(n) and x["timed_out"] == "0" and x["crc_error"] == "0"]
            meds.append(statistics.median(v))
    val = f"{statistics.median(meds) / 1000:.1f}"
    return "ESP8266 offload floor (ms)", val, f"{val} ms (ESP8266)"


CHECKS = [c_p1_inf, c_p1_marked, c_reps("esp32", "grover", 11, "ESP32 grover n=11 (13 reps)"), c_reps("esp8266", "grover", 10, "4 reps"), c_reps("esp8266", "grover", 9, "37"),
          c_pulse, c_wraps, c_tmax, c_heap, c_lb, c_band, c_repro, c_p3reps, c_floor]
if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else int.from_bytes(os.urandom(4), "big")
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    random.seed(seed)
    print("seed", seed)
    bad = 0
    for fn in random.sample(CHECKS, k):
        name, raw_val, quoted = fn()
        ok = quoted in REPORT and (raw_val in quoted or quoted.split()[0] == raw_val or raw_val == quoted)
        if "crossover bracket" in name or "reproducibility" in name:
            ok = quoted in REPORT
        print(("OK  " if ok else "BAD ") + f"{name}: raw={raw_val} report-token={quoted!r} in_report={quoted in REPORT}")
        bad += not ok
    sys.exit(1 if bad else 0)
