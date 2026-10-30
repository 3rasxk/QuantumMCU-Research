"""Phase 2 vs Phase 3 coverage audit (read-only on data/raw). Writes
data/derived/phase2_phase3_coverage.csv and the table section of docs/audit/phase2_phase3_coverage.md.

Row = board x circuit. A point is 'ok' when its terminal record (memory_wall.csv in Phase 2, session_log.csv in Phase 3)
says ok. Walls: only build_overflow / malloc_failed. Hangs, resets, timeouts are never walls.
"""
import glob
import json
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data", "raw")
OUT_CSV = os.path.join(ROOT, "data", "derived", "phase2_phase3_coverage.csv")
BOARDS = ["uno", "esp8266", "esp32"]
CIRCUITS = ["h_all", "bell_ghz", "qft", "grover"]
WALL_STATUS = ("build_overflow", "malloc_failed")


def sdir(ph, b, c):
    return os.path.join(RAW, f"phase{ph}", b, c, "with_ref")


def span(ns):
    ns = sorted(set(int(x) for x in ns))
    if not ns:
        return ""
    out, s, p = [], ns[0], ns[0]
    for x in ns[1:]:
        if x != p + 1:
            out.append(f"{s}-{p}" if s != p else str(s))
            s = x
        p = x
    out.append(f"{s}-{p}" if s != p else str(s))
    return ",".join(out)


def fmt(ns):
    return span(ns) or "-"


def hashes_and_schema(base, sessions):
    hs, sc = set(), set()
    for sid in sessions:
        p = os.path.join(base, "env", sid + ".json")
        if os.path.exists(p):
            e = json.load(open(p))
            hs.add(e.get("firmware_source_hash", "?"))
            sc.add(str(e.get("schema_version")))
    return sorted(hs), sorted(sc)


def p2(b, c):
    base = sdir(2, b, c)
    pts = pd.read_csv(f"{base}/points.csv")
    raw = pd.read_csv(f"{base}/raw.csv")
    mw = pd.read_csv(f"{base}/memory_wall.csv")
    okn = sorted(mw[mw.status == "ok"].n)
    wall = mw[mw.status.isin(WALL_STATUS)]
    reps = raw.groupby("n").size()
    ok_reps = reps[reps.index.isin(okn)]
    capped = pts[pts.failure_message.fillna("").str.contains("time_capped")]
    skipped = sorted(set(mw[mw.status == "skipped_compute_infeasible"].n))
    sess = set(pts[(pts.status == "ok")].session_id)
    hs, sc = hashes_and_schema(base, sess)
    failed = pts[pts.status == "failed"].groupby("failure_type").n.apply(lambda s: sorted(set(s))).to_dict()
    return dict(p2_n_range=fmt(set(mw.n)), p2_ok_n=fmt(okn), p2_wall_n=int(wall.n.min()) if len(wall) else "",
                p2_wall_evidence=wall.status.iloc[0] if len(wall) else "none observed",
                p2_time_capped_n=fmt(capped.n), p2_skipped_compute_infeasible_n=fmt(skipped),
                p2_reps_min=int(ok_reps.min()), p2_reps_max=int(ok_reps.max()),
                p2_fw_hashes=" ".join(hs), p2_schema=" ".join(sc),
                p2_failed_attempts="; ".join(f"{k}:{fmt(v)}" for k, v in failed.items()),
                _p2_ok=okn, _p2_wall=int(wall.n.min()) if len(wall) else None)


def p3(b, c):
    base = sdir(3, b, c)
    pts = pd.read_csv(f"{base}/points.csv")
    raw = pd.read_csv(f"{base}/raw.csv")
    sl = pd.read_csv(f"{base}/session_log.csv")
    okn = sorted(sl[sl.status == "ok"].n)
    reps = raw.groupby("n").size()
    ok_reps = reps[reps.index.isin(okn)]
    capped = pts[pts.failure_message.fillna("").str.contains("time_capped")]
    skipped = sorted(set(sl[sl.status.str.startswith("skipped")].n))
    sess = set(pts[(pts.status == "ok")].session_id)
    hs, sc = hashes_and_schema(base, sess)
    return dict(p3_n_range=fmt(set(sl.n)), p3_ok_n=fmt(okn), p3_bauds=" ".join(map(str, sorted(raw.baud_rate.unique()))),
                p3_reps_min=int(ok_reps.min()), p3_reps_max=int(ok_reps.max()),
                p3_time_capped_n=fmt(capped.n), p3_skipped_n=fmt(skipped),
                p3_crc_errors=int(raw.crc_error.sum()), p3_timed_out=int(raw.timed_out.sum()),
                p3_fw_hashes=" ".join(hs), p3_schema=" ".join(sc), _p3_ok=okn)


def build():
    rows = []
    for b in BOARDS:
        for c in CIRCUITS:
            a, d = p2(b, c), p3(b, c)
            ok2, ok3 = set(a["_p2_ok"]), set(d["_p3_ok"])
            wall = a["_p2_wall"]
            r = dict(board=b, circuit=c)
            r.update({k: v for k, v in a.items() if not k.startswith("_")})
            r.update({k: v for k, v in d.items() if not k.startswith("_")})
            r["overlap_n"] = fmt(ok2 & ok3)
            r["gap_p2_ok_missing_in_p3"] = fmt(ok2 - ok3)
            r["gap_p3_ok_missing_in_p2"] = fmt(ok3 - ok2)
            r["p3_n_beyond_p2_wall"] = fmt([n for n in ok3 if wall is not None and n >= wall])
            rows.append(r)
    return pd.DataFrame(rows)


def md_table(df):
    """compact markdown table for docs/audit/phase2_phase3_coverage.md"""
    sh = lambda x: " ".join(h[:6] for h in str(x).split()) if str(x) != "nan" else ""
    cols = ["board", "circuit", "P2 ok n", "P2 wall (evidence)", "P2 time-capped / skipped n", "P2 reps", "P2 fw hashes",
            "P3 ok n", "P3 baud", "P3 reps", "P3 crc / timed out", "P3 fw hashes", "overlap n", "P2 ok missing in P3", "P3 beyond P2 wall"]
    rows = []
    for _, r in df.iterrows():
        wall = f"{r.p2_wall_n} ({r.p2_wall_evidence})" if str(r.p2_wall_n) not in ("", "nan") else "none observed"
        capped = "; ".join(x for x in (f"cap {r.p2_time_capped_n}" if r.p2_time_capped_n != "-" else "",
                                       f"skip {r.p2_skipped_compute_infeasible_n}" if r.p2_skipped_compute_infeasible_n != "-" else "") if x) or "-"
        reps2 = f"{r.p2_reps_min}-{r.p2_reps_max}" if r.p2_reps_min != r.p2_reps_max else str(r.p2_reps_min)
        reps3 = f"{r.p3_reps_min}-{r.p3_reps_max}" if r.p3_reps_min != r.p3_reps_max else str(r.p3_reps_min)
        p3extra = f" (cap {r.p3_time_capped_n}; skip {r.p3_skipped_n})" if r.p3_skipped_n != "-" or r.p3_time_capped_n != "-" else ""
        rows.append([r.board, r.circuit, r.p2_ok_n, wall, capped, reps2, sh(r.p2_fw_hashes), r.p3_ok_n + p3extra, r.p3_bauds, reps3,
                     f"{r.p3_crc_errors} / {r.p3_timed_out}", sh(r.p3_fw_hashes), r.overlap_n, r.gap_p2_ok_missing_in_p3,
                     r.p3_n_beyond_p2_wall])
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(x) for x in row) + " |" for row in rows]
    return "\n".join(out)


def write_doc_table(df, doc):
    begin, end = "<!-- COVERAGE-TABLE:BEGIN -->", "<!-- COVERAGE-TABLE:END -->"
    text = open(doc).read()
    a, b = text.index(begin) + len(begin), text.index(end)
    open(doc, "w").write(text[:a] + "\n" + md_table(df) + "\n" + text[b:])


if __name__ == "__main__":
    df = build()
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    pd.set_option("display.width", 250, "display.max_columns", 50, "display.max_colwidth", 40)
    print(df.T.to_string())
    doc = os.path.join(ROOT, "docs", "audit", "phase2_phase3_coverage.md")
    if os.path.exists(doc):
        write_doc_table(df, doc)
