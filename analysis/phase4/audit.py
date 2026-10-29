"""Phase 4 Step 0: data audit. Read-only on data/raw. Writes data/processed/phase4/audit_*.csv.

One row per (phase, board, circuit, n) for the four paper circuits. Statuses come from
memory_wall.csv (phase 2) / session_log.csv (phase 3) plus failed attempts in points.csv.
Firmware hash = firmware_source_hash in the session env JSON (hash of the simulator source at run time).
"""
import glob
import json
import os
import sys
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed", "phase4")
BOARDS = ["uno", "esp8266", "esp32"]
CIRCUITS = ["h_all", "bell_ghz", "qft", "grover"]


def rd(p):
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


def env_of(base, sid):
    p = os.path.join(base, "env", sid + ".json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p))


def audit_series(phase, board, circuit):
    base = os.path.join(RAW, f"phase{phase}", board, circuit, "with_ref")
    pts, raw = rd(f"{base}/points.csv"), rd(f"{base}/raw.csv")
    term = rd(f"{base}/memory_wall.csv" if phase == 2 else f"{base}/session_log.csv")
    if pts.empty or raw.empty:
        return None
    rows = []
    ns = sorted(set(pts["n"]) | set(raw["n"]))
    for n in ns:
        p = pts[pts["n"] == n]
        ok = p[p["status"] == "ok"]
        t = term[term["n"] == n]
        # all terminal-status rows seen for this point (a point can be retried after a failed attempt)
        stat = ";".join(sorted(set(t["status"].astype(str)))) if len(t) else ""
        fails = ";".join(sorted(set(p[p["status"] == "failed"]["failure_type"].astype(str))))
        sids = sorted(set(ok["session_id"]))
        envs = [env_of(base, s) for s in sids]
        hashes = sorted({e.get("firmware_source_hash", "?") for e in envs})
        schemas = sorted({str(v) for v in set(p["schema_version"]) | {e.get("schema_version") for e in envs if e}})
        commits = sorted({e.get("git_commit", "?")[:7] for e in envs})
        r = raw[raw["n"] == n]
        rows.append(dict(
            phase=phase, board=board, circuit=circuit, n=int(n),
            terminal_status=stat, failed_attempts=fails,
            ok_rows=len(ok), reps=int(r["rep"].nunique()) if len(r) else 0,
            n_sessions=len(sids), fw_hashes="|".join(hashes), n_hashes=len(hashes),
            schemas="|".join(schemas), n_schemas=len(schemas), commits="|".join(commits),
            ref_pairs=0))
    df = pd.DataFrame(rows)
    # counter pairs (phase 2 and 3 both ran with the counter)
    cp = rd(f"{base}/ref/ref_compare_points.csv")
    if len(cp):
        m = dict(zip(cp["n"], zip(cp["n_pairs"], cp["ref_status"])))
        df["ref_pairs"] = df["n"].map(lambda n: m.get(n, (0, ""))[0])
        df["ref_status"] = df["n"].map(lambda n: m.get(n, (0, ""))[1])
    else:
        df["ref_status"] = ""
    return df


def phase1():
    """Phase 1 (PC build, float32 C++ vs Qiskit Aer): infidelity per (circuit, n) with the 1e-3 gate.

    The canonical infidelity_tvd.csv is a subset of the 20261003T111917Z run (values identical where they overlap, checked
    below); grover n = 12 exists only in the 20261004T091042Z file. All three files are read, later file wins on a clash.
    """
    d = os.path.join(RAW, "phase1")
    canon = pd.read_csv(f"{d}/infidelity_tvd.csv")
    a = pd.read_csv(f"{d}/infidelity_tvd.20261003T111917Z.csv")
    b = pd.read_csv(f"{d}/infidelity_tvd.20261004T091042Z.csv")
    m = canon.merge(a, on=["circuit", "n"], suffixes=("_c", "_a"))
    assert (m.infidelity_c == m.infidelity_a).all(), "canonical and 20261003 infidelity disagree"
    a["source"] = "infidelity_tvd.20261003T111917Z.csv"
    b["source"] = "infidelity_tvd.20261004T091042Z.csv"
    df = pd.concat([a, b]).drop_duplicates(["circuit", "n"], keep="last")
    df = df[df.circuit.isin(CIRCUITS)].sort_values(["circuit", "n"]).reset_index(drop=True)
    df["pass_1e-3"] = df.infidelity <= 1e-3
    assert (df["pass_1e-3"] == df["pass"]).all()
    df.to_csv(f"{OUT}/phase1_infidelity.csv", index=False)
    return df


def phase3_inventory(df):
    """(board, circuit, n range, baud) of Phase 3; baud read from raw.csv."""
    rows = []
    for b in BOARDS:
        for c in CIRCUITS:
            raw = rd(os.path.join(RAW, "phase3", b, c, "with_ref", "raw.csv"))
            rows.append(dict(board=b, circuit=c, n_min=int(raw.n.min()), n_max=int(raw.n.max()),
                             n_points=raw.n.nunique(), bauds=",".join(map(str, sorted(raw.baud_rate.unique()))),
                             min_requests_per_point=int(raw.groupby("n").size().min())))
    return pd.DataFrame(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    parts = []
    for ph in (2, 3):
        for b in BOARDS:
            for c in CIRCUITS:
                d = audit_series(ph, b, c)
                if d is None:
                    print(f"MISSING phase{ph} {b} {c}")
                    continue
                parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(f"{OUT}/audit_points.csv", index=False)
    # series summary
    s = []
    for (ph, b, c), g in df.groupby(["phase", "board", "circuit"]):
        okn = g[g["terminal_status"].str.contains("ok")]
        s.append(dict(phase=ph, board=b, circuit=c, rows=len(g), n_min=g["n"].min(), n_max=g["n"].max(),
                      n_ok_max=int(okn["n"].max()) if len(okn) else -1,
                      reps_min=int(okn["reps"].min()), reps_max=int(okn["reps"].max()),
                      statuses=";".join(f"{k}:{v}" for k, v in g["terminal_status"].value_counts().items()),
                      mixed_hash_points=int((g["n_hashes"] > 1).sum()),
                      mixed_schema_points=int((g["n_schemas"] > 1).sum()),
                      series_hashes=g["fw_hashes"].nunique(),
                      ref_pts=int((g["ref_pairs"] > 0).sum())))
    ss = pd.DataFrame(s)
    ss.to_csv(f"{OUT}/audit_series.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 80)
    print(ss.to_string())
    inv = phase3_inventory(df)
    inv.to_csv(f"{OUT}/audit_phase3_inventory.csv", index=False)
    print("\nPHASE 3 INVENTORY\n" + inv.to_string())
    p1 = phase1()
    print("\nPHASE 1 (<=1e-3 gate): last passing n and first failing n per circuit")
    for c, g in p1.groupby("circuit"):
        fail = g[~g["pass_1e-3"]]
        print(c, "n", g.n.min(), "-", g.n.max(), "all_pass" if fail.empty else
              f"last_pass_n={int(g[g['pass_1e-3']].n.max())} first_fail_n={int(fail.n.min())} infid@first_fail={fail.infidelity.iloc[0]:.3e}")
    cal = json.load(open(os.path.join(ROOT, "data", "calibration", "counter_20261004.json")))
    print("\nCOUNTER CALIBRATION FILE:", {k: cal[k] for k in ("timestamp_utc", "ppm", "ppm_stderr", "within_50ppm", "limitation")})
    sidecars = glob.glob(os.path.join(RAW, "phase*", "*", "*", "with_ref", "env", "*.ref.json"))
    sc = [json.load(open(f)) for f in sidecars]
    print("ref sidecars:", len(sc), "| calibration empty:", sum(1 for x in sc if not x.get("calibration")),
          "| selftest values:", sorted({x.get("selftest") for x in sc}))
    bad = df[(df["n_hashes"] > 1) | (df["n_schemas"] > 1)]
    print("\nPOINTS WITH MIXED HASH/SCHEMA:", len(bad))
    print(bad[["phase", "board", "circuit", "n", "fw_hashes", "schemas", "n_sessions"]].to_string())
    return 1 if len(bad) else 0


if __name__ == "__main__":
    sys.exit(main())
