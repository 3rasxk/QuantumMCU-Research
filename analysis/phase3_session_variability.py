"""Phase 3 session-to-session variability (read-only on data/raw). For every board x circuit x n that exists in the original bucket (with_ref) and in a
repeat bucket (with_ref_<TAG>), split the per-request round trip into the parts the logs allow and compare the two sessions.

Parts per point (points.csv ok row, raw.csv): e2e = median of raw.csv e2e_latency_us; pc_sim = pc_sim_s_median (Aer build+run+sample on the PC, per request);
wire = bytes per request * 10 bit / baud (frame bytes from bytes_transferred / requests); residual = e2e - pc_sim - wire (board compute, USB-serial latency,
host scheduling). cold = latency of request 0 minus the median of the rest. Writes data/derived/phase3_session_variability.csv.
Usage: .venv/bin/python analysis/phase3_session_variability.py [board]
"""
import csv
import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data", "raw", "phase3")
OUT = os.path.join(ROOT, "data", "derived", "phase3_session_variability.csv")


def rd(p):
    return list(csv.DictReader(open(p, newline=""))) if os.path.exists(p) else []


def point_stats(base):
    pts = {}
    for r in rd(os.path.join(base, "points.csv")):
        if r["status"] == "ok":
            pts.setdefault(int(r["n"]), []).append(r)     # several ok rows = several sessions for one n
    lat = {}
    for r in rd(os.path.join(base, "raw.csv")):
        try:
            lat.setdefault(int(r["n"]), []).append(float(r["e2e_latency_us"]))
        except ValueError:
            pass
    out = {}
    for n, rows in pts.items():
        v = lat.get(n, [])
        if len(v) < 5:
            continue
        p = rows[-1]
        req = max(len(v), 1)
        baud = float(p["baud"])
        wire = float(p["bytes_transferred"]) / req * 10 / baud * 1e6
        sim = float(p["pc_sim_s_median"]) * 1e6
        med = st.median(v)
        out[n] = dict(session=p["session_id"], n_sessions_ok=len(rows), requests=len(v), e2e=med, pc_sim=sim, wire=wire, resid=med - sim - wire,
                      cold=v[0] - st.median(v[1:]), mean_rtt=float(p["avg_round_trip_latency_s"]) * 1e6,
                      wall_s=float(p["wall_s"]), start=p["start_utc"])
    return out


def env_of(base, session):
    f = os.path.join(base, "env", session + ".json")
    return json.load(open(f)) if os.path.exists(f) else {}


def main():
    boards = sys.argv[1:] or sorted(os.listdir(RAW))
    rows = []
    for b in boards:
        for cdir in sorted(glob.glob(os.path.join(RAW, b, "*"))):
            circ = os.path.basename(cdir)
            old = os.path.join(cdir, "with_ref")
            for rb in sorted(glob.glob(os.path.join(cdir, "with_ref_*"))):
                new = point_stats(rb)
                o = point_stats(old)
                for n in sorted(set(o) & set(new)):
                    a, c = o[n], new[n]
                    eo, en = env_of(old, a["session"]), env_of(rb, c["session"])
                    rows.append(dict(board=b, circuit=circ, bucket=os.path.basename(rb), n=n,
                                     e2e_old=round(a["e2e"], 1), e2e_new=round(c["e2e"], 1), ratio=round(c["e2e"] / a["e2e"], 3),
                                     sim_old=round(a["pc_sim"], 1), sim_new=round(c["pc_sim"], 1),
                                     wire_old=round(a["wire"], 1), wire_new=round(c["wire"], 1),
                                     resid_old=round(a["resid"], 1), resid_new=round(c["resid"], 1),
                                     d_e2e=round(c["e2e"] - a["e2e"], 1), d_sim=round(c["pc_sim"] - a["pc_sim"], 1), d_resid=round(c["resid"] - a["resid"], 1),
                                     cold_old=round(a["cold"], 1), cold_new=round(c["cold"], 1),
                                     requests_old=a["requests"], requests_new=c["requests"], sessions_ok_old=a["n_sessions_ok"],
                                     fw_old=eo.get("firmware_source_hash", ""), fw_new=en.get("firmware_source_hash", ""),
                                     start_old=a["start"][:16], start_new=c["start"][:16]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if rows:
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(rows)} points -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
