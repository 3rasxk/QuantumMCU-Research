#!/usr/bin/env python3
# audit_data_test.py -- tests for analysis/audit_data.py on SYNTHETIC data in a temp dir (never the real data/).
# No pytest (same style as pc/shared/*_test.py). Run: .venv/bin/python analysis/audit_data_test.py

import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit_data as ad  # noqa: E402

PASSED = FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"FAIL: {name} {extra}")


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


WALL_HDR = ["board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes", "compile_ram_pct", "status",
            "timestamp_utc", "retry_count", "timeout_budget_s", "expected_point_s", "retry_policy"]
PTS_HDR = ["schema_version", "session_id", "phase", "board", "circuit", "n", "baud", "attempt_index", "start_utc",
           "end_utc", "wall_s", "build_compile_s", "upload_s", "boot_wait_s", "device_exec_s", "pc_sim_s_total",
           "pc_sim_s_median", "serial_transfer_s_total", "avg_round_trip_latency_s", "crc_error_count",
           "bytes_transferred", "retry_count", "timeout_hit", "failure_type", "failure_message", "status"]
SESSION = "20261005T000000-aaaaaaaa"


def make_data(tmp):
    """Valid synthetic data for uno/h_all, phase 2 (n=1..7 ok, n=8 build_overflow) and phase 3 (n=1..8 ok)."""
    root = Path(tmp) / "repo"
    raw = root / "data" / "raw"
    d2 = raw / "phase2" / "uno" / "h_all" / "with_ref"
    raws, wall, pts = [], [], []
    for n in range(1, 8):
        for rep in range(100):
            raws.append(["uno", "h_all", n, rep, 280 * 2 ** (n - 1) + rep % 3, 1700, 1700, 90])
        wall.append(["uno", "h_all", n, 8 * 2 ** n, 200 + 8 * 2 ** n, round((200 + 8 * 2 ** n) / 2048 * 100, 1), "ok",
                     f"2026-10-05T00:00:{n:02d}+00:00", 0, 90, 0.1, "allowed"])
        pts.append([2, SESSION, 2, "uno", "h_all", n, 115200, 0, f"2026-10-05T00:00:{n:02d}+00:00", "", 1, 5.0, 3.0, 1, 2.5, "", "",
                    "", "", "", "", 0, False, "none", "", "ok"])
    wall.append(["uno", "h_all", 8, 2048, 2250, 109.9, "build_overflow", "2026-10-05T00:01:00+00:00", 0, 90, 6.0, "allowed"])
    pts.append([2, SESSION, 2, "uno", "h_all", 8, 115200, 0, "2026-10-05T00:01:00+00:00", "", 1, 5.0, 0, 0, "", "", "", "", "", "", "",
                0, False, "build", "x", "failed"])
    write_csv(d2 / "raw.csv", ["board", "circuit", "n", "rep", "exec_time_us", "free_heap_before", "free_heap_after",
                               "timeout_budget_s"], raws)
    write_csv(d2 / "memory_wall.csv", WALL_HDR, wall)
    write_csv(d2 / "points.csv", PTS_HDR, pts)
    env = {"schema_version": 2, "session_id": SESSION, "board": "uno", "git_commit": "abcdef1234567", "git_dirty": True,
           "firmware_source_hash": "00ff", "recorded_utc": "2026-10-05T00:00:00+00:00", "ref_used": True,
           "ref_dir_bucket": "with_ref", "ref_dir_matches_flag": True, "serial_port": "PORT", "host_os": "x",
           "sleep_prevention": {"prevented": True}}
    (d2 / "env").mkdir(parents=True, exist_ok=True)
    (d2 / "env" / f"{SESSION}.json").write_text(json.dumps(env))
    (d2 / "env" / f"{SESSION}.ref.json").write_text(json.dumps({"counter_port": "tcp:5055", "counter_fw_sha256": "ab" * 32,
                                                                "counter_proto": 2, "calibration": {}, "selftest": "loopback"}))
    cmp_rows = []
    for n in range(1, 8):
        for rep in range(100):
            m = 280 * 2 ** (n - 1) + rep % 3
            cmp_rows.append([1, "", "uno", "h_all", n, rep, m, m + 4.0, -4.0, -4.0 / m * 100])
    write_csv(d2 / "ref" / "ref_compare.csv", ["schema_version", "session_id", "board", "circuit", "n", "rep", "micros_us",
                                               "counter_us", "diff_us", "diff_pct"], cmp_rows)
    write_csv(d2 / "ref" / "ref_compare_points.csv", ["board", "circuit", "n", "n_pairs", "median_diff_us", "iqr_diff_us",
                                                     "median_diff_pct", "ref_status"],
              [["uno", "h_all", n, 100, -4.0, 0.0, -4.0 / (280 * 2 ** (n - 1) + 1) * 100, "ok"] for n in range(1, 8)])
    write_csv(d2 / "ref" / "ref_points.csv", ["schema_version", "session_id", "board", "circuit", "n", "reps_expected",
                                              "pulses_received", "pulses_used", "ref_status"],
              [[1, "", "uno", "h_all", n, 100, 100, 100, "ok"] for n in range(1, 8)])
    # phase 3
    d3 = raw / "phase3" / "uno" / "h_all" / "with_ref"
    r3, log, p3 = [], [], []
    for n in range(1, 9):
        for rep in range(100):
            r3.append(["uno", "h_all", n, 115200, rep, 3000 + 10 * n, 0, 0])
        log.append(["uno", "h_all", n, 115200, "ok", 100, 0, 100, "", "t", 300, 8, 0.01])
        sim = 0.01 * 100
        p3.append([2, SESSION, 3, "uno", "h_all", n, 115200, 0, f"2026-10-05T01:00:{n:02d}+00:00", "", 10, 5, 3, 1.5, 5.0, sim,
                   0.01, 5.0 - sim, (3000 + 10 * n) / 1e6, 0, 1000, 0, False, "none", "", "ok"])
    write_csv(d3 / "raw.csv", ["board", "circuit", "n", "baud_rate", "rep", "e2e_latency_us", "crc_error", "timed_out"], r3)
    write_csv(d3 / "session_log.csv", ["board", "circuit", "n", "baud_rate", "status", "frames_served", "frames_dropped_bad_crc",
                                       "rows_captured", "last_sim_error", "timestamp_utc", "session_timeout_budget_s",
                                       "expected_session_s", "pc_sim_s_per_request"], log)
    write_csv(d3 / "points.csv", PTS_HDR, p3)
    s3 = "20261005T010000-bbbbbbbb"
    (d3 / "env").mkdir(parents=True, exist_ok=True)
    (d3 / "env" / f"{s3}.json").write_text(json.dumps(dict(env, session_id=s3, ref_used=False, recorded_utc="2026-10-05T01:00:00+00:00")))
    ledger = root / "data" / "run_history.jsonl"
    ledger.write_text("\n".join(json.dumps(e) for e in [
        {"event": "started", "source": "live", "board": "uno", "dry_run": False, "invocation_id": "inv1",
         "timestamp_utc": "2026-10-05T00:00:05+00:00"},
        {"event": "completed", "source": "live", "invocation_id": "inv1", "timestamp_utc": "2026-10-05T00:02:00+00:00"},
        {"event": "started", "source": "live", "board": "uno", "dry_run": False, "invocation_id": "inv2",
         "timestamp_utc": "2026-10-05T01:00:05+00:00"}]) + "\n")
    return root


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def run(root, docs=None):
    raw = root / "data" / "raw"
    ledger = root / "data" / "run_history.jsonl"
    out = root / "audit_out"
    res = ad.run_all(raw, root, ledger, out, docs_dir=docs, use_git=False)
    return {c["id"]: c for c in res["checks"]}, res, out


def main():
    tmp = Path(tempfile.mkdtemp(prefix="audit_test_"))
    try:
        root = make_data(tmp)
        before = tree_hash(root / "data" / "raw")
        checks, res, out = run(root)
        check("raw tree untouched by a full audit", tree_hash(root / "data" / "raw") == before)
        for cid in ("A1", "A2a", "A2b", "A3", "A4a", "A4b", "B1a", "B1b", "B1d", "D1", "D2", "E1", "E2", "E3", "S1", "B2a", "B2b", "B2d", "S6"):
            check(f"clean data: {cid} passes", checks[cid]["result"] == "PASS", checks[cid]["evidence"])
        check("clean data: nothing planned is missing", checks["B1c"]["result"] == "PASS", checks["B1c"]["evidence"])
        for f in ("sessions", "completeness", "checks", "recompute", "point_stats", "slopes", "limits", "memory_model",
                  "reference_diff", "phase3_link", "prediction", "prediction_summary"):
            check(f"{f}.csv written", (out / f"{f}.csv").exists())
        sess = pd.read_csv(out / "sessions.csv")
        check("two sessions inventoried, both ledger-matched", len(sess) == 2 and set(sess.ledger_status) == {"MATCHED"})
        check("phase 3 session without --ref has no reference", "NO_REFERENCE" in set(sess.reference_state))
        check("phase 2 session has a physical counter", any(s.startswith("REFERENCE-PHYSICAL") for s in sess.reference_state))

        # --- refuses to write under data/raw; missing column refused
        try:
            ad.run_all(root / "data" / "raw", root, root / "data" / "run_history.jsonl", root / "data" / "raw" / "audit")
            check("refuses --out under raw", False)
        except ad.AuditError:
            check("refuses --out under raw", True)
        rc = ad.main(["--raw", str(root / "data" / "raw"), "--repo", str(root), "--ledger", str(root / "data" / "run_history.jsonl"),
                      "--out", str(root / "data" / "raw" / "x"), "--no-git"])
        check("main exits 2 for --out under raw", rc == 2)

        # --- missing point
        root2 = make_data(tmp / "m1")
        d = root2 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        w = pd.read_csv(d / "memory_wall.csv")
        w[w.n != 4].to_csv(d / "memory_wall.csv", index=False)
        r = pd.read_csv(d / "raw.csv")
        r[r.n != 4].to_csv(d / "raw.csv", index=False)
        c2, res2, _ = run(root2)
        check("missing planned point is reported", c2["B1c"]["result"] == "FAIL" and "n=4" in c2["B1c"]["evidence"], c2["B1c"]["evidence"])
        comp = pd.DataFrame(res2["completeness"])
        check("completeness marks it MISSING", ((comp.phase == 2) & (comp.n == 4) & (comp.category == "MISSING")).any())

        # --- wrong rep count
        root3 = make_data(tmp / "m2")
        d = root3 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        r = pd.read_csv(d / "raw.csv")
        r = r[~((r.n == 5) & (r.rep >= 90))]
        r.to_csv(d / "raw.csv", index=False)
        c3, _, _ = run(root3)
        check("ok point with 90 reps and no cap note fails B1a", c3["B1a"]["result"] == "FAIL" and "n=5" in c3["B1a"]["evidence"], c3["B1a"]["evidence"])

        # --- wall without evidence
        root4 = make_data(tmp / "m3")
        d = root4 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        w = pd.read_csv(d / "memory_wall.csv")
        w.loc[w.status == "build_overflow", "compile_ram_pct"] = 90.0
        w.to_csv(d / "memory_wall.csv", index=False)
        c4, _, _ = run(root4)
        check("build_overflow with compile_ram_pct <= 100 fails D1", c4["D1"]["result"] == "FAIL", c4["D1"]["evidence"])
        root5 = make_data(tmp / "m4")
        d = root5 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        w = pd.read_csv(d / "memory_wall.csv")
        w.loc[w.status == "build_overflow", "status"] = "malloc_failed"
        w.to_csv(d / "memory_wall.csv", index=False)
        p = pd.read_csv(d / "points.csv")
        p.loc[p.failure_type == "build", "failure_type"] = "hang"
        p.to_csv(d / "points.csv", index=False)
        c5, _, _ = run(root5)
        check("malloc_failed without a malloc attempt fails D1", c5["D1"]["result"] == "FAIL", c5["D1"]["evidence"])
        # a watchdog terminal row is not a wall
        root6 = make_data(tmp / "m5")
        d = root6 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        w = pd.read_csv(d / "memory_wall.csv")
        w.loc[w.status == "build_overflow", "status"] = "watchdog_suspected(x)"
        w.to_csv(d / "memory_wall.csv", index=False)
        c6, res6, _ = run(root6)
        comp = pd.DataFrame(res6["completeness"])
        check("watchdog terminal row is categorised watchdog_suspected, not wall",
              (comp[(comp.phase == 2) & (comp.n == 8)].category == "watchdog_suspected").all() and c6["D2"]["result"] == "PASS")

        # --- mixed buckets
        root7 = make_data(tmp / "m6")
        src = root7 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        shutil.copytree(src, root7 / "data" / "raw" / "phase2" / "uno" / "h_all" / "no_ref")
        c7, _, _ = run(root7)
        check("both buckets present fails A3", c7["A3"]["result"] == "FAIL", c7["A3"]["evidence"])

        # --- mismatching summary numbers
        root8 = make_data(tmp / "m7")
        d = root8 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref" / "ref"
        cp = pd.read_csv(d / "ref_compare_points.csv")
        cp.loc[cp.n == 3, "median_diff_us"] = -9.0
        cp.to_csv(d / "ref_compare_points.csv", index=False)
        docs = root8 / "docs" / "analysis"
        (docs / "uno").mkdir(parents=True)
        (docs / "uno" / "h_all.md").write_text("- Median time per rep: 999 us at n=1, 5 ms at n=7 (x1).\n")
        c8, res8, _ = run(root8, docs)
        check("stored median differing from recomputation fails B2a", c8["B2a"]["result"] == "FAIL", c8["B2a"]["evidence"])
        check("docs number differing from raw fails B2c", c8["B2c"]["result"] == "FAIL", c8["B2c"]["evidence"])
        root9 = make_data(tmp / "m8")
        docs9 = root9 / "docs" / "analysis"
        (docs9 / "uno").mkdir(parents=True)
        (docs9 / "uno" / "h_all.md").write_text("- Median time per rep: 281 us at n=1, 17.9 ms at n=7 (x1).\n")
        c9, _, _ = run(root9, docs9)
        check("docs numbers equal to raw medians pass B2c", c9["B2c"]["result"] == "PASS", c9["B2c"]["evidence"])

        # --- ledger / counter provenance
        root10 = make_data(tmp / "m9")
        (root10 / "data" / "run_history.jsonl").write_text("")
        c10, _, _ = run(root10)
        check("sessions without a ledger entry fail S1", c10["S1"]["result"] == "FAIL")
        root11 = make_data(tmp / "m10")
        ref = root11 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref" / "env" / f"{SESSION}.ref.json"
        ref.write_text(json.dumps({"counter_port": "SIM", "counter_fw_sha256": "00"}))
        c11, _, _ = run(root11)
        check("simulated counter port is REFERENCE-INVALID (E2 fails)", c11["E2"]["result"] == "FAIL", c11["E2"]["evidence"])

        # --- schema / enum
        root12 = make_data(tmp / "m11")
        d = root12 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        p = pd.read_csv(d / "points.csv")
        p.loc[0, "status"] = "bogus"
        p["schema_version"] = [2] * (len(p) - 1) + [1]
        p.to_csv(d / "points.csv", index=False)
        c12, _, _ = run(root12)
        check("unknown status fails A2a", c12["A2a"]["result"] == "FAIL")
        check("mixed schema_version fails A1", c12["A1"]["result"] == "FAIL")
        root13 = make_data(tmp / "m12")
        d = root13 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        pd.read_csv(d / "raw.csv").drop(columns=["exec_time_us"]).to_csv(d / "raw.csv", index=False)
        try:
            run(root13)
            check("missing exec_time_us column is refused", False)
        except ad.AuditError as e:
            check("missing exec_time_us column is refused", "exec_time_us" in str(e) or "missing" in str(e))

        # --- duplicates
        root14 = make_data(tmp / "m13")
        d = root14 / "data" / "raw" / "phase2" / "uno" / "h_all" / "with_ref"
        r = pd.read_csv(d / "raw.csv")
        pd.concat([r, r[r.n == 2].head(3)]).to_csv(d / "raw.csv", index=False)
        c14, _, _ = run(root14)
        check("duplicated rep rows fail A4a", c14["A4a"]["result"] == "FAIL")

        # --- model helpers
        check("gate count feature h_all n=3: 3 gates x 2^3", ad.predictor("h_all", 3, "M1") == 24.0)
        check("touched-amplitude feature h_all n=3 equals M1 (H touches all)", ad.predictor("h_all", 3, "M2") == 24.0)
        pts = [(f, 2.5 * f) for f in (10.0, 20.0, 40.0)]
        c, t0 = ad.fit_c(pts, False)
        check("fit_c recovers an exact coefficient", abs(c - 2.5) < 1e-9 and t0 == 0.0)
        c, t0 = ad.fit_c([(f, 2.5 * f + 7.0) for f in (10.0, 20.0, 40.0, 80.0)], True)
        check("fit_c with constant recovers coefficient and constant", abs(c - 2.5) < 1e-6 and abs(t0 - 7.0) < 1e-6, f"{c} {t0}")
        mm = pd.DataFrame(ad.memory_model_rows(root / "data" / "raw"))
        row = mm[(mm.board == "uno") & (mm.circuit == "h_all")].iloc[0]
        check("memory model predicts the Uno wall at n=8", row.predicted_wall_n == 8 and row.observed_wall_n == 8)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{PASSED} checks, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
