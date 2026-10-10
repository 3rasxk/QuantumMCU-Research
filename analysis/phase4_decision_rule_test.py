#!/usr/bin/env python3
# phase4_decision_rule_test.py -- tests for analysis/phase4_decision_rule.py on SYNTHETIC data in a temp dir.
# No pytest. Run: .venv/bin/python analysis/phase4_decision_rule_test.py

import math
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import phase4_decision_rule as p4  # noqa: E402
import audit_data_test as adt  # noqa: E402

PASSED = FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"FAIL: {name} {extra}")


def main():
    # Step 1
    check("n_max 2048-202 B (Uno) is 7", p4.n_max(1846) == 7)
    check("n_max 110612 B (ESP32 block) is 13", p4.n_max(110612) == 13)
    check("n_max 52240 B (ESP8266) is 12", p4.n_max(52240) == 12)
    check("n_max exact power of two: 8 * 2^5 bytes -> 5", p4.n_max(8 * 2 ** 5) == 5)
    check("n_max below one amplitude is 0", p4.n_max(7) == 0)
    # crossover
    loc = {n: 10.0 * 2 ** n for n in range(2, 10)}
    off = {n: 400.0 for n in range(2, 10)}
    ns, flag = p4.crossover(loc, off)
    check("crossover interpolated where local = offload (10*2^n = 400 -> n=log2(40))", flag == "ok" and abs(ns - math.log2(40)) < 1e-9, f"{ns} {flag}")
    ns, flag = p4.crossover({n: 1e9 for n in range(2, 6)}, {n: 1.0 for n in range(2, 6)})
    check("local slower already at the first n -> at_or_below_first_n", flag == "at_or_below_first_n" and ns == 2.0)
    ns, flag = p4.crossover({n: 1.0 for n in range(2, 6)}, {n: 1e9 for n in range(2, 6)})
    check("local faster everywhere -> none_in_range, no n*", flag == "none_in_range" and ns is None)
    check("no common n -> no_common_n", p4.crossover({1: 1.0}, {2: 1.0})[1] == "no_common_n")
    # speed ratio ignores quantized points
    r = p4.log2_speed_ratio({3: 800.0, 4: 1600.0, 5: 50.0}, {3: 100.0, 4: 200.0, 5: 25.0})
    check("log2 speed ratio uses only n with both medians >= 100 us", r is not None and abs(r - 3.0) < 1e-9, str(r))
    check("log2 speed ratio is None with no usable n", p4.log2_speed_ratio({3: 10.0}, {3: 5.0}) is None)
    # end to end on synthetic data
    tmp = Path(tempfile.mkdtemp(prefix="p4_test_"))
    try:
        root = adt.make_data(tmp)
        raw = root / "data" / "raw"
        out, fig = root / "out", root / "figures"
        before = adt.tree_hash(raw)
        rc = p4.main(["--raw", str(raw), "--out", str(out), "--figures", str(fig)])
        check("main exits 0 on synthetic data", rc == 0)
        check("raw tree untouched", adt.tree_hash(raw) == before)
        names = {p.name for p in out.iterdir()}
        check("tables written", {"n_max_check.csv", "crossover.csv", "rule_eval.csv", "adjustments.csv", "offload_floor.csv"} <= names, str(names))
        check("no non-PNG file under the figures dir", all(p.suffix == ".png" for p in fig.rglob("*") if p.is_file()))
        try:
            p4.main(["--raw", str(raw), "--out", str(raw / "x"), "--figures", str(fig)])
            check("refuses --out under raw", False)
        except p4.ad.AuditError:
            check("refuses --out under raw", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{PASSED} checks, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
