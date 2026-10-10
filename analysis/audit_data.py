#!/usr/bin/env python3
# audit_data.py -- read-only data audit of data/raw/phase2 and data/raw/phase3 and the analysis tables behind
# docs/data_audit.md and docs/analysis/paper_plan.md.
#
#   sessions.csv         one row per session (env JSON): ledger match, git commit/dirty, tracked-in-git, firmware hash
#                        vs the run commit and vs the working tree, counter sidecar, REFERENCE status
#   completeness.csv     planned vs collected point per (phase, board, circuit, n[, baud]): terminal status, reps,
#                        attempts, duplicates, superseded rows, firmware hash of the session that produced the point
#   checks.csv           automated checks, each PASS / FAIL / UNVERIFIED with evidence
#   recompute.csv        numbers recomputed from raw rows vs the numbers stored/reported elsewhere
#   point_stats.csv      per ok Phase 2 point: median/IQR/min/max, successive ratio, outlier/drift/bimodal/warm-up flags
#   slopes.csv, model_vs_measured.csv, limits.csv, cross_board.csv, crossover.csv, reference_diff.csv,
#   phase3_link.csv, prediction.csv, prediction_summary.csv, loco.csv   (analysis tables)
#
# Reads data/raw read-only (and git read-only); writes only under --out (default data/processed/audit/). It refuses an
# --out under the raw data tree. Nothing here fixes anything: problems are reported.
#
# Conventions stated here so they are fixed before any result is looked at:
#   * median and IQR = numpy percentile (linear interpolation) 25/50/75 over every rep of a point (WARMUP_REPS=0).
#   * outlier = rep outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR] (Tukey); a point is "outlier-heavy" if > 5 % of its reps are.
#   * Tukey collapses when IQR = 0 (most points here): any deviating rep is then an "outlier". The secondary measure
#     dev_frac = share of reps deviating from the median by more than max(1 % of the median, 2 x micros() resolution)
#     is reported next to it. (Added after the first run showed the Tukey rule flags 57 of 113 points mostly because
#     IQR = 0; both numbers are reported.)
#   * drift = |median(last 20 reps) - median(first 20 reps)| / median(all reps) > 0.10 (points with >= 40 reps).
#   * bimodal flag = in the sorted reps the largest gap between neighbours exceeds 50 % of the range and each side holds
#     >= 10 % of the reps (a crude heuristic, not a statistical test).
#   * warm-up flag = rep 0 > 2 x median (reported only; all reps are used).
#   * non-monotonic = the median of a point is below the median of the previous n of the same series.
#   * time model (fixed before fitting): t(board, circuit, n) = c_board * G(circuit, n) * 2^n, G = total gate count
#     (H + CNOT + CPHASE, pc/shared/timing_model.gate_counts), because every gate of firmware/common/qsim.hpp loops over
#     all 2^n state indices (qsim.hpp:65, :86, :107). Variant "c" adds a non-negative constant t0 per point.
#     Fit on the smaller half of the ok points of one (board, circuit) (floor(k/2) points by n), least squares on the
#     relative error; evaluated on every ok point (in-sample / extrapolation labelled).
#     Leave-one-circuit-out: one c per board from the ok points of the other three circuits, predicting the fourth.
#   * memory model: bytes(n) = 8 * 2^n (firmware/common/qsim.hpp Cplx = 2 floats); wall predicted at the first n where
#     bytes(n) + static > available (static = compile RAM used - state on the Uno; available = smallest free heap /
#     largest block seen in an ok point on the ESP boards).

import argparse
import csv
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import experiment_plan as plan  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import telemetry as tel  # noqa: E402
from shared import resume as rs  # noqa: E402

BOARDS = ("uno", "esp8266", "esp32")
CIRCUITS = ("h_all", "bell_ghz", "qft", "grover")
REPS = 100
MICROS_RESOLUTION_US = {"uno": 4, "esp8266": 1, "esp32": 1}   # AVR core wiring.c:100-102 (64 cycles / 16 MHz); ESP: 1 us
BOARD_RAM = {"uno": 2048, "esp8266": 81920, "esp32": 327680}
WALL_PREFIXES = rs.WALL_STATUS_PREFIXES
TERMINAL_OK_PREFIX = ("ok",)
VALID_WALL_TERMINAL = re.compile(r"^(ok|build_overflow|malloc_failed|runtime_hang_or_reset.*|watchdog_suspected.*|"
                                 r"build_or_upload_fail.*|build_timeout.*|skipped_.*)$")
VALID_P3_STATUS = re.compile(r"^(ok|session_incomplete.*|build_or_upload_fail.*|build_timeout.*|skipped_.*|failed.*)$")
PHASE_SRC = {2: "src", 3: "src_offload"}
MIN_FIT_MEDIAN_US = 0.0     # no point is excluded from evaluation; fit uses every point of the smaller half
OUTLIER_FRACTION = 0.05
FRAME_BYTES_PER_REQUEST = 4 + 6          # request 4 B + response 6 B (pc/phase3_offload/sweep.py:245, :262)
BITS_PER_BYTE_ON_WIRE = 10               # 8N1


class AuditError(Exception):
    pass


# --------------------------------------------------------------------------- helpers

def assert_not_raw(out, raw_root):
    out, raw_root = Path(out).resolve(), Path(raw_root).resolve()
    if out == raw_root or raw_root in out.parents:
        raise AuditError(f"refusing to write under the raw data tree: {out}")


def rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def need(df, cols, what):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise AuditError(f"{what}: missing column(s) {miss}")


def readdf(path, cols=(), what=""):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=list(cols))
    df = pd.read_csv(path)
    need(df, cols, what or path.name)
    return df


def point_sets(raw_root):
    out = []
    for phase in (2, 3):
        base = Path(raw_root) / f"phase{phase}"
        if not base.exists():
            continue
        for b in sorted(p for p in base.iterdir() if p.is_dir()):
            for c in sorted(p for p in b.iterdir() if p.is_dir()):
                for bucket in sorted(p for p in c.iterdir() if p.is_dir()):
                    if bucket.name in ("with_ref", "no_ref"):
                        out.append(dict(phase=phase, board=b.name, circuit=c.name, bucket=bucket.name, dir=bucket))
    return out


def git(repo, *args):
    try:
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def tracked_files(repo):
    out = git(repo, "ls-files")
    return None if out is None else set(out.split("\n"))


def fw_hash_tree(read_bytes, list_files):
    """Same recipe as pc/shared/telemetry._firmware_build_hash: firmware/common/*.hpp then <src>/*.cpp, sorted."""
    import hashlib
    h = hashlib.sha256()
    for p in list_files():
        data = read_bytes(p)
        if data is not None:
            h.update(data)
    return h.hexdigest()[:16]


def fw_hash_worktree(repo, board, phase):
    repo = Path(repo)
    src = repo / "firmware" / board / PHASE_SRC[phase]
    files = sorted((repo / "firmware" / "common").rglob("*.hpp")) + sorted(src.rglob("*.cpp"))
    return fw_hash_tree(lambda p: p.read_bytes() if p.exists() else None, lambda: files)


_FW_COMMIT_CACHE = {}


def fw_hash_commit(repo, commit, board, phase):
    key = (commit, board, phase)
    if key in _FW_COMMIT_CACHE:
        return _FW_COMMIT_CACHE[key]
    common = git(repo, "ls-tree", "-r", "--name-only", commit, "firmware/common")
    srcs = git(repo, "ls-tree", "-r", "--name-only", commit, f"firmware/{board}/{PHASE_SRC[phase]}")
    if common is None or srcs is None:
        _FW_COMMIT_CACHE[key] = None
        return None
    files = sorted(p for p in common.split() if p.endswith(".hpp")) + sorted(p for p in srcs.split() if p.endswith(".cpp"))

    def rb(p):
        try:
            return subprocess.run(["git", "show", f"{commit}:{p}"], cwd=repo, capture_output=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
    v = fw_hash_tree(rb, lambda: files)
    _FW_COMMIT_CACHE[key] = v
    return v


def load_ledger(path):
    out = []
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def parse_ts(s):
    from datetime import datetime
    return datetime.fromisoformat(s)


# --------------------------------------------------------------------------- 1. sessions

def inventory(raw_root, repo_root, ledger_path, use_git=True):
    ledger = load_ledger(ledger_path)
    started = [e for e in ledger if e.get("event") == "started" and e.get("source") == "live"]
    ended = {}
    for e in ledger:
        if e.get("event") in ("completed", "failed", "interrupted"):
            ended[e.get("invocation_id")] = e
    tracked = tracked_files(repo_root) if use_git else None
    cur_hash = {}
    out = []
    for ps in point_sets(raw_root):
        envd = ps["dir"] / "env"
        if not envd.exists():
            continue
        for p in sorted(envd.glob("*.json")):
            if p.name.endswith(".ref.json"):
                continue
            j = json.loads(p.read_text())
            rec = parse_ts(j["recorded_utc"])
            match = [e for e in started if e.get("board") == j.get("board")
                     and abs((parse_ts(e["timestamp_utc"]) - rec).total_seconds()) < 30]
            live = [e for e in match if not e.get("dry_run")]
            dry = [e for e in match if e.get("dry_run")]
            ledger_status = "MATCHED" if live else ("DRY_RUN_ONLY" if dry else "UNMATCHED")
            inv = live[0]["invocation_id"] if live else ""
            end = ended.get(inv, {}).get("event", "") if live else ""
            ref = {}
            rp = envd / (p.stem + ".ref.json")
            if rp.exists():
                ref = json.loads(rp.read_text())
            try:
                rel = p.relative_to(repo_root).as_posix()
            except ValueError:
                rel = ""
            key = (j.get("board"), ps["phase"])
            if use_git and key not in cur_hash:
                cur_hash[key] = fw_hash_worktree(repo_root, j["board"], ps["phase"])
            fw_run = fw_hash_commit(repo_root, j.get("git_commit", ""), j["board"], ps["phase"]) if use_git else None
            port = str(ref.get("counter_port", ""))
            if not j.get("ref_used"):
                ref_state = "NO_REFERENCE"
            elif not ref:
                ref_state = "REFERENCE-INVALID (ref_used but no counter sidecar)"
            elif not port or port.upper().startswith("SIM") or not ref.get("counter_fw_sha256"):
                ref_state = "REFERENCE-INVALID (simulated or unknown counter)"
            elif ps["phase"] == 3:
                ref_state = "REFERENCE-EXCLUDED (Phase 3 runs without the counter)"
            else:
                ref_state = "REFERENCE-PHYSICAL (tcp link to the counter)"
            out.append(dict(
                phase=ps["phase"], board=ps["board"], circuit=ps["circuit"], bucket=ps["bucket"],
                session_id=j.get("session_id", ""), recorded_utc=j.get("recorded_utc", ""),
                schema_version=j.get("schema_version", ""), git_commit=j.get("git_commit", "")[:7],
                git_dirty=j.get("git_dirty", ""), firmware_source_hash=j.get("firmware_source_hash", ""),
                fw_matches_run_commit=("" if fw_run is None else fw_run == j.get("firmware_source_hash")),
                fw_matches_worktree=("" if not use_git else cur_hash[key] == j.get("firmware_source_hash")),
                serial_port=j.get("serial_port", ""), host_os=j.get("host_os", ""),
                sleep_prevented=(j.get("sleep_prevention") or {}).get("prevented", ""),
                ref_used=j.get("ref_used", ""), ref_dir_bucket=j.get("ref_dir_bucket", ""),
                ref_dir_matches_flag=j.get("ref_dir_matches_flag", ""),
                counter_port=port, counter_fw_sha=str(ref.get("counter_fw_sha256", ""))[:12],
                counter_proto=ref.get("counter_proto", ""), counter_calibration_empty=(not ref.get("calibration")) if ref else "",
                counter_selftest=ref.get("selftest", ""), reference_state=ref_state,
                ledger_status=ledger_status, invocation_id=inv, ledger_end=end,
                tracked_in_git=("" if tracked is None else rel in tracked), env_path=rel))
    return out


# --------------------------------------------------------------------------- 2. completeness

def cat_of(status):
    if status == "ok":
        return "ok"
    if rs.is_wall_status(status):
        return "wall"
    if status.startswith("watchdog_suspected"):
        return "watchdog_suspected"
    if status.startswith("runtime_hang_or_reset"):
        return "hang_no_evidence"
    if status.startswith("skipped_compute_infeasible"):
        return "time_limited"
    if status.startswith("skipped_sim_cost_infeasible"):
        return "sim_cost_infeasible"
    if status.startswith("skipped_"):
        return "skipped_other"
    return "failed"


def session_fw(raw_root_set):
    """{session_id: firmware_source_hash} from the env JSONs of one point set."""
    out = {}
    envd = raw_root_set / "env"
    if envd.exists():
        for p in envd.glob("*.json"):
            if not p.name.endswith(".ref.json"):
                j = json.loads(p.read_text())
                out[j.get("session_id", p.stem)] = j.get("firmware_source_hash", "")
    return out


def completeness(raw_root):
    out = []
    for ps in point_sets(raw_root):
        phase, board, circuit, d = ps["phase"], ps["board"], ps["circuit"], ps["dir"]
        raw = readdf(d / "raw.csv", ["n", "rep"], f"{board}/{circuit} raw.csv")
        pts = readdf(d / "points.csv", ["n", "status"], f"{board}/{circuit} points.csv")
        fw = session_fw(d)
        planned = set(plan.plan_n_values(board, circuit, phase)) if board in BOARDS and circuit in CIRCUITS else set()
        if phase == 2:
            term = readdf(d / "memory_wall.csv", ["n", "status"], f"{board}/{circuit} memory_wall.csv")
            keyed = {}
            for r in term.to_dict("records"):
                keyed.setdefault((int(r["n"]), 115200), []).append(r)
            bauds = {115200}
        else:
            term = readdf(d / "session_log.csv", ["n", "baud_rate", "status"], f"{board}/{circuit} session_log.csv")
            keyed = {}
            for r in term.to_dict("records"):
                keyed.setdefault((int(r["n"]), int(r["baud_rate"])), []).append(r)
            bauds = {k[1] for k in keyed} | ({int(b) for b in raw["baud_rate"].unique()} if "baud_rate" in raw.columns else set())
            bauds = bauds or {115200}
        reps = {}
        dups = {}
        if len(raw):
            rawc = raw.copy()
            rawc["baud"] = rawc["baud_rate"] if "baud_rate" in rawc.columns else 115200
            for (n, b), g in rawc.groupby(["n", "baud"]):
                reps[(int(n), int(b))] = len(g)
                dups[(int(n), int(b))] = int(g.duplicated("rep").sum())
        keys = set(keyed) | {(n, 115200) for n in planned}
        if phase == 3:
            keys |= {(n, b) for n in planned for b in bauds}
        for (n, b) in sorted(keys):
            trs = keyed.get((n, b), [])
            if phase == 2:
                trs = sorted(trs, key=lambda r: r.get("timestamp_utc", ""))
            term_row = trs[-1] if trs else None
            status = term_row["status"] if term_row else ""
            cat = cat_of(status) if term_row else "MISSING"
            if len(pts):
                pr = pts[(pts["n"] == n) & ((pts["baud"] == b) if (phase == 3 and "baud" in pts.columns) else True)]
            else:
                pr = pts
            attempts = int(pr["status"].isin(["ok", "failed", "retrying"]).sum()) if len(pr) else 0
            fails = [str(x) for x in pr[pr["status"] == "failed"].get("failure_type", pd.Series(dtype=str))]
            okrows = pr[pr["status"] == "ok"]
            sess = okrows.iloc[-1]["session_id"] if len(okrows) else ""
            msg = str(okrows.iloc[-1].get("failure_message", "")) if len(okrows) else ""
            capped = msg.startswith("time_capped")
            n_reps = reps.get((n, b), 0)
            if cat == "ok":
                reps_flag = "OK" if n_reps == REPS else ("CAPPED_RECORDED" if capped and 0 < n_reps < REPS else "REPS_MISMATCH")
            elif n_reps:
                reps_flag = "ROWS_WITHOUT_OK_STATUS"
            else:
                reps_flag = ""
            out.append(dict(
                phase=phase, board=board, circuit=circuit, bucket=ps["bucket"], n=n, baud=b if phase == 3 else "",
                planned=n in planned, terminal_status=status, category=cat, reps=n_reps, reps_flag=reps_flag,
                capped_note=msg if capped else "", attempts=attempts, failed_attempt_types=";".join(fails),
                terminal_rows=len(trs), superseded_rows=max(len(trs) - 1, 0), dup_rep_rows=dups.get((n, b), 0),
                session_id=sess, firmware_hash=fw.get(sess, ""),
                compile_ram_pct=(term_row.get("compile_ram_pct", "") if term_row and phase == 2 else ""),
                theoretical_bytes=(term_row.get("theoretical_bytes", "") if term_row and phase == 2 else "")))
    return out


# --------------------------------------------------------------------------- 3. automated checks

class Checks:
    def __init__(self):
        self.rows = []

    def add(self, cid, desc, result, evidence=""):
        self.rows.append(dict(id=cid, check=desc, result=result, evidence=str(evidence)[:600]))


def run_checks(raw_root, repo_root, sessions, comp, docs_dir=None):
    C = Checks()
    sets = point_sets(raw_root)
    # A1 schema version
    bad = []
    for ps in sets:
        for name in ("points.csv", "sessions.csv"):
            df = readdf(ps["dir"] / name)
            if "schema_version" in df.columns and set(df["schema_version"].unique()) != {tel.SCHEMA_VERSION}:
                bad.append(f"{ps['board']}/{ps['circuit']}/{name}: {sorted(df['schema_version'].unique())}")
            elif len(df) and "schema_version" not in df.columns:
                bad.append(f"{ps['board']}/{ps['circuit']}/{name}: no schema_version column")
    bad += [f"{s['session_id']}: env schema {s['schema_version']}" for s in sessions if str(s["schema_version"]) != str(tel.SCHEMA_VERSION)]
    C.add("A1", f"telemetry files carry SCHEMA_VERSION={tel.SCHEMA_VERSION}, one version per file", "FAIL" if bad else "PASS",
          "; ".join(bad[:5]) or f"{len(sets)} point sets")
    # A2 enums
    badp, badw = [], []
    for ps in sets:
        pts = readdf(ps["dir"] / "points.csv")
        if len(pts):
            for col, allowed in (("status", tel.STATUS_TYPES), ("failure_type", tel.FAILURE_TYPES)):
                if col in pts.columns:
                    extra = set(pts[col].dropna().astype(str)) - set(allowed)
                    if extra:
                        badp.append(f"{ps['board']}/{ps['circuit']} {col}: {sorted(extra)}")
        term = readdf(ps["dir"] / ("memory_wall.csv" if ps["phase"] == 2 else "session_log.csv"))
        pat = VALID_WALL_TERMINAL if ps["phase"] == 2 else VALID_P3_STATUS
        if "status" in term.columns:
            for s in term["status"].astype(str).unique():
                if not pat.match(s):
                    badw.append(f"{ps['board']}/{ps['circuit']}: {s}")
    C.add("A2a", "points.csv status / failure_type are members of telemetry.STATUS_TYPES / FAILURE_TYPES",
          "FAIL" if badp else "PASS", "; ".join(badp[:5]))
    C.add("A2b", "terminal-record statuses (memory_wall.csv / session_log.csv) match the known status vocabulary",
          "FAIL" if badw else "PASS", "; ".join(badw[:5]))
    # A3 buckets
    bk = {ps["bucket"] for ps in sets}
    badb = [s["session_id"] for s in sessions if s["ref_dir_bucket"] != s["bucket"] or s["ref_dir_matches_flag"] is False]
    C.add("A3", "no_ref and with_ref never mixed (one bucket present; env bucket == directory; flag consistent)",
          "FAIL" if (len(bk) > 1 or badb) else "PASS", f"buckets present: {sorted(bk)}; inconsistent sessions: {badb[:3]}")
    # A4 append-only
    dup, nonmono = [], []
    for ps in sets:
        raw = readdf(ps["dir"] / "raw.csv")
        if len(raw) and "rep" in raw.columns:
            keycols = [c for c in ("n", "baud_rate", "rep") if c in raw.columns]
            if raw.duplicated(keycols).any():
                dup.append(f"{ps['board']}/{ps['circuit']} p{ps['phase']}")
        pts = readdf(ps["dir"] / "points.csv")
        if len(pts) and "start_utc" in pts.columns:
            ts = pts["start_utc"].astype(str).tolist()
            if ts != sorted(ts):
                nonmono.append(f"{ps['board']}/{ps['circuit']} p{ps['phase']}")
    C.add("A4a", "no duplicated (n, [baud], rep) rows in any raw.csv (resumed runs only appended)", "FAIL" if dup else "PASS",
          ", ".join(dup[:6]))
    C.add("A4b", "points.csv start_utc non-decreasing (append order = time order)", "FAIL" if nonmono else "PASS",
          ", ".join(nonmono[:6]))
    # B1 reps
    cdf = pd.DataFrame(comp)
    okp = cdf[cdf["category"] == "ok"]
    bad = okp[okp["reps_flag"] == "REPS_MISMATCH"]
    capped = okp[okp["reps_flag"] == "CAPPED_RECORDED"]
    C.add("B1a", "every ok point has exactly 100 reps, or a recorded time_capped note", "FAIL" if len(bad) else "PASS",
          f"{len(okp)} ok points; {len(capped)} capped with a recorded note; mismatches: "
          + "; ".join(f"p{r.phase} {r.board}/{r.circuit} n={r.n} reps={r.reps}" for r in bad.itertuples()))
    rw = cdf[cdf["reps_flag"] == "ROWS_WITHOUT_OK_STATUS"]
    C.add("B1b", "no raw rows for a point whose terminal status is not ok (interrupted points leave no partial rows)",
          "FAIL" if len(rw) else "PASS", "; ".join(f"p{r.phase} {r.board}/{r.circuit} n={r.n}" for r in rw.itertuples()))
    miss = cdf[(cdf["planned"]) & (cdf["category"] == "MISSING")]
    C.add("B1c", "every planned point is collected or explicitly classified", "FAIL" if len(miss) else "PASS",
          "; ".join(f"p{r.phase} {r.board}/{r.circuit} n={r.n}" for r in miss.itertuples()))
    sup = cdf[cdf["superseded_rows"] > 0]
    C.add("B1d", "no point has several terminal rows (superseded)", "FAIL" if len(sup) else "PASS", f"{len(sup)} points")
    # D wall evidence
    badwall = []
    for ps in sets:
        if ps["phase"] != 2:
            continue
        term = readdf(ps["dir"] / "memory_wall.csv", ["n", "status"])
        pts = readdf(ps["dir"] / "points.csv")
        for r in term.to_dict("records"):
            s = str(r["status"])
            if not rs.is_wall_status(s):
                continue
            ev = ""
            if s == "build_overflow":
                pct = r.get("compile_ram_pct")
                ev = "compile_ram_pct>100" if pd.notna(pct) and float(pct) > 100 else "NO compile_ram_pct>100"
            else:
                f = pts[(pts["n"] == r["n"]) & (pts["status"] == "failed")] if len(pts) else pts
                ev = "failed attempt failure_type=malloc" if len(f) and (f["failure_type"] == "malloc").any() else "NO malloc attempt"
            if ev.startswith("NO"):
                badwall.append(f"{ps['board']}/{ps['circuit']} n={r['n']} {s}: {ev}")
    C.add("D1", "every wall row has positive evidence (build_overflow with compile_ram_pct > 100, or a malloc failure attempt)",
          "FAIL" if badwall else "PASS", "; ".join(badwall[:5]))
    walls_wrong = cdf[(cdf["category"].isin(["watchdog_suspected", "hang_no_evidence", "time_limited"])) &
                      (cdf["terminal_status"].astype(str).map(rs.is_wall_status))]
    C.add("D2", "no watchdog / hang / time-limited point is classified as a wall", "FAIL" if len(walls_wrong) else "PASS",
          f"{len(walls_wrong)} offending rows")
    # D3 reasons for watchdog / serial error attempts
    wd = []
    for ps in sets:
        pts = readdf(ps["dir"] / "points.csv")
        if len(pts) and "failure_type" in pts.columns:
            for r in pts[(pts["status"] == "failed") & (pts["failure_type"].isin(["watchdog_suspected", "serial", "hang"]))].itertuples():
                wd.append(f"{ps['board']}/{ps['circuit']} p{ps['phase']} n={r.n} {r.failure_type}: {r.failure_message}")
    C.add("D3", "failed attempts of type watchdog_suspected / serial / hang are recorded as failures (not walls)", "INFO" if wd else "PASS",
          f"{len(wd)} attempts: " + " | ".join(wd[:4]))
    # E reference counter
    e_bad, e_n = [], 0
    for ps in sets:
        if ps["phase"] != 2 or ps["bucket"] != "with_ref":
            continue
        rp = readdf(ps["dir"] / "ref" / "ref_points.csv")
        if not len(rp):
            continue
        okr = rp[rp["ref_status"] == "ok"]
        rawc = readdf(ps["dir"] / "raw.csv", ["n", "rep"])
        have = rawc.groupby("n").size().to_dict() if len(rawc) else {}
        e_n += len(okr)
        for r in okr.itertuples():
            if int(r.pulses_used) != int(have.get(int(r.n), -1)):
                e_bad.append(f"{ps['board']}/{ps['circuit']} n={r.n} pulses_used={r.pulses_used} raw reps={have.get(int(r.n))}")
    C.add("E1", "counter-ok points: pulses used equals the reps present in raw.csv (capped points have fewer than 100)", "FAIL" if e_bad else "PASS", f"{e_n} points; " + "; ".join(e_bad[:4]))
    inv = [s for s in sessions if s["reference_state"].startswith("REFERENCE-INVALID")]
    C.add("E2", "no session with a simulated / unknown / missing counter reference", "FAIL" if inv else "PASS",
          f"{len(inv)} sessions: " + ", ".join(s['session_id'] for s in inv[:3]))
    p3ref = [s for s in sessions if s["phase"] == 3 and s["ref_used"]]
    C.add("E3", "Phase 3 sessions recorded without a counter reference (policy: Phase 3 runs without the counter)",
          "FAIL" if p3ref else "PASS", f"{len(p3ref)} of {len([s for s in sessions if s['phase'] == 3])} Phase 3 sessions used --ref counter")
    # ledger / git
    un = [s for s in sessions if s["ledger_status"] != "MATCHED"]
    C.add("S1", "every session matches a live, non-dry-run 'started' entry of data/run_history.jsonl", "FAIL" if un else "PASS",
          f"{len(un)} unmatched: " + ", ".join(f"{s['session_id']}={s['ledger_status']}" for s in un[:4]))
    ut = [s for s in sessions if s["tracked_in_git"] is False]
    C.add("S2", "session env files are tracked in git", "FAIL" if ut else ("UNVERIFIED" if not sessions or sessions[0]["tracked_in_git"] == "" else "PASS"),
          f"{len(ut)} untracked")
    mm = [s for s in sessions if s["fw_matches_run_commit"] is False]
    C.add("S3", "firmware source hash of every session equals the hash of the run commit's firmware tree",
          "FAIL" if mm else "PASS", f"{len(mm)} sessions differ (uncommitted firmware at run time): "
          + ", ".join(sorted({f"{s['board']}:{s['firmware_source_hash']}" for s in mm})))
    dirty = [s for s in sessions if s["git_dirty"] is True]
    C.add("S4", "git_dirty false (clean working tree at collection)", "FAIL" if dirty else "PASS",
          f"{len(dirty)} of {len(sessions)} sessions dirty (git status --porcelain counts untracked data files, "
          "pc/shared/telemetry.py:369-372, so this flag cannot show code changes alone)")
    hashes = {}
    for s in sessions:
        if s["firmware_source_hash"]:
            hashes.setdefault((s["board"], s["phase"], s["circuit"]), set()).add(s["firmware_source_hash"])
    multi = {k: v for k, v in hashes.items() if len(v) > 1}
    C.add("S5", "one firmware source hash per (board, phase, circuit) series", "FAIL" if multi else "PASS",
          "; ".join(f"{k}: {len(v)} hashes" for k, v in sorted(multi.items())[:6]))
    mis = []
    for ps in sets:
        ses = readdf(ps["dir"] / "sessions.csv")
        pts = readdf(ps["dir"] / "points.csv")
        if len(ses) and "n_points_failed" in ses.columns and len(pts):
            a, b = int(ses["n_points_failed"].sum()), int((pts["status"] == "failed").sum())
            if a != b:
                mis.append(f"p{ps['phase']} {ps['board']}/{ps['circuit']}: sessions.csv n_points_failed={a}, points.csv failed rows={b}")
    C.add("S6", "failed points counted in sessions.csv equal the failed rows in points.csv (every failure has a row)", "FAIL" if mis else "PASS",
          "; ".join(mis[:4]))
    rep = repeat_rows(raw_root)
    C.add("F1", "repeat data: points collected more than once (points.csv ok rows); agreement of the totals", "INFO",
          f"{len(rep)} repeated points; max device_exec_s ratio " + (f"{max(float(r['device_exec_s_max_over_min'] if 'device_exec_s_max_over_min' in r else r['device_exec_max_over_min']) for r in rep):.2f}" if rep else "n/a")
          + "; raw.csv keeps only the last run's reps, so per-rep repeatability cannot be assessed")
    # recompute counter points
    rc = recompute_counter(raw_root)
    badrc = [r for r in rc if r["status"] == "MISMATCH"]
    alt = [r for r in rc if r["status"] == "OK_ALT_CONVENTION"]
    C.add("B2a", "ref_compare_points.csv medians/IQR equal a recomputation from ref_compare.csv rows", "FAIL" if badrc else "PASS",
          f"{len(rc)} values compared; {len(alt)} IQR values equal the 'exclusive' quantile convention "
          "(pc/counter/crosscheck.py:42-45 statistics.quantiles) instead of numpy linear used by the charts; true mismatches: "
          + "; ".join(f"{r['where']} {r['quantity']} {r['stored']} vs {r['recomputed']}" for r in badrc[:3]))
    # units: Phase 3 avg_round_trip_latency_s is per request; Phase 2/3 device_exec_s is a total over the point's reps
    badu, ratios, nu = [], [], 0
    for ps in sets:
        pts = readdf(ps["dir"] / "points.csv")
        raw = readdf(ps["dir"] / "raw.csv")
        if not len(pts) or not len(raw):
            continue
        col = "exec_time_us" if ps["phase"] == 2 else "e2e_latency_us"
        if col not in raw.columns:
            continue
        okp = pts[pts["status"] == "ok"]
        okp = okp.drop_duplicates(["n", "baud"] if ps["phase"] == 3 and "baud" in okp.columns else ["n"], keep="last")  # raw keeps the last run
        for r in okp.to_dict("records"):
            g = raw[raw["n"] == r["n"]]
            if ps["phase"] == 3 and "baud_rate" in g.columns:
                g = g[g["baud_rate"] == r["baud"]]
            if not len(g) or pd.isna(r.get("device_exec_s")):
                continue
            nu += 1
            tot = g[col].sum() / 1e6
            if float(r["device_exec_s"]) + 0.05 < tot:
                badu.append(f"p{ps['phase']} {ps['board']}/{ps['circuit']} n={r['n']}: device_exec_s={r['device_exec_s']} < sum of reps {tot:.3f}")
            if ps["phase"] == 3 and pd.notna(r.get("avg_round_trip_latency_s")):
                if abs(float(r["avg_round_trip_latency_s"]) - g[col].mean() / 1e6) > 2e-6 + 1e-4 * abs(float(r["avg_round_trip_latency_s"])):
                    badu.append(f"p3 {ps['board']}/{ps['circuit']} n={r['n']}: avg_round_trip_latency_s={r['avg_round_trip_latency_s']} vs mean(e2e)={g[col].mean() / 1e6:.6f}")
    C.add("B2d", "units: device_exec_s is a total over the point's reps (>= sum of the board-timed reps); Phase 3 avg_round_trip_latency_s "
          "equals the per-request mean of e2e_latency_us (pc/phase3_offload/sweep.py:547,598)", "FAIL" if badu else "PASS",
          f"{nu} points; " + "; ".join(badu[:3]))
    # compile_ram_pct
    badpct = []
    for ps in sets:
        if ps["phase"] == 2 and ps["board"] == "uno":
            for r in readdf(ps["dir"] / "memory_wall.csv", ["n", "status"]).to_dict("records"):
                try:
                    used, pct = float(r["compile_ram_used_bytes"]), float(r["compile_ram_pct"])
                except (TypeError, ValueError, KeyError):
                    continue
                if abs(used / BOARD_RAM["uno"] * 100 - pct) > 0.06:
                    badpct.append(f"{ps['circuit']} n={r['n']}: {used}/{BOARD_RAM['uno']} -> {used / BOARD_RAM['uno'] * 100:.2f} vs {pct}")
    C.add("B2b", "Uno compile_ram_pct equals compile_ram_used_bytes / 2048 (rounded to 0.1)", "FAIL" if badpct else "PASS", "; ".join(badpct[:3]))
    return C.rows


# --------------------------------------------------------------------------- recompute

def recompute_counter(raw_root):
    out = []
    for ps in point_sets(raw_root):
        if ps["phase"] != 2 or ps["bucket"] != "with_ref":
            continue
        cmp_ = readdf(ps["dir"] / "ref" / "ref_compare.csv")
        pts = readdf(ps["dir"] / "ref" / "ref_compare_points.csv")
        if not len(cmp_) or not len(pts):
            continue
        for r in pts.to_dict("records"):
            g = cmp_[cmp_["n"] == r["n"]]
            if not len(g) or pd.isna(r.get("median_diff_us")):
                continue
            vals = {"median_diff_us": float(np.median(g["diff_us"])), "iqr_diff_us": float(np.percentile(g["diff_us"], 75) - np.percentile(g["diff_us"], 25)),
                    "median_diff_pct": float(np.median(g["diff_pct"])), "n_pairs": float(len(g))}
            qx = statistics.quantiles(list(g["diff_us"]), n=4) if len(g) >= 2 else [0, 0, 0]
            alt = qx[2] - qx[0]
            for q, v in vals.items():
                if q in r and pd.notna(r[q]):
                    tol = 1e-3 + 1e-3 * abs(v)
                    st = "OK" if abs(float(r[q]) - v) <= tol else "MISMATCH"
                    if st == "MISMATCH" and q == "iqr_diff_us" and abs(float(r[q]) - alt) <= tol:
                        st = "OK_ALT_CONVENTION"      # stored with statistics.quantiles(n=4) 'exclusive', not numpy linear
                    out.append(dict(where=f"{ps['board']}/{ps['circuit']} n={r['n']}", quantity=q, stored=float(r[q]),
                                    recomputed=v, status=st))
    return out


def recompute_docs(raw_root, docs_dir):
    """Compare 'Median time per rep: X at n=N' lines of docs/analysis/<board>/<circuit>.md with a recomputation."""
    out = []
    docs_dir = Path(docs_dir)
    if not docs_dir.exists():
        return out
    unit = {"us": 1.0, "ms": 1e3, "s": 1e6}
    for f in sorted(docs_dir.glob("*/*.md")):
        if f.stem == "comparison":
            continue
        board, circuit = f.parent.name, f.stem
        d = Path(raw_root) / "phase2" / board / circuit / "with_ref"
        raw = readdf(d / "raw.csv")
        if not len(raw):
            continue
        for m in re.finditer(r"Median time per rep: ([\d.e+-]+) (us|ms|s) at n=(\d+), ([\d.e+-]+) (us|ms|s) at n=(\d+)", f.read_text()):
            for val, u, n in ((m.group(1), m.group(2), m.group(3)), (m.group(4), m.group(5), m.group(6))):
                rep = float(val) * unit[u]
                true = float(np.median(raw[raw["n"] == int(n)]["exec_time_us"]))
                ok = abs(rep - true) <= 0.006 * max(abs(true), 1) + 0.5   # 3-4 significant digits printed
                out.append(dict(where=f"{f.relative_to(docs_dir).as_posix()} n={n}", quantity="median_exec_time_us", stored=rep,
                                recomputed=true, status="OK" if ok else "MISMATCH"))
    return out


# --------------------------------------------------------------------------- point statistics

def repeat_rows(raw_root):
    """Points with more than one 'ok' row in points.csv (collected more than once). raw.csv keeps only the last run's reps,
    so only the points.csv totals of the earlier runs remain comparable."""
    out = []
    for ps in point_sets(raw_root):
        pts = readdf(ps["dir"] / "points.csv", ["n", "status"])
        if not len(pts):
            continue
        ok = pts[pts["status"] == "ok"]
        key = ["n", "baud"] if ps["phase"] == 3 and "baud" in ok.columns else ["n"]
        for k, g in ok.groupby(key):
            if len(g) < 2:
                continue
            dev = g["device_exec_s"].astype(float).tolist()
            row = dict(phase=ps["phase"], board=ps["board"], circuit=ps["circuit"], n=int(k[0] if isinstance(k, tuple) else k),
                       runs=len(g), sessions=";".join(g["session_id"].astype(str).str[:15]), device_exec_s=";".join(map(str, dev)),
                       device_exec_max_over_min=max(dev) / min(dev) if min(dev) else "")
            if ps["phase"] == 3 and "avg_round_trip_latency_s" in g.columns:
                a = g["avg_round_trip_latency_s"].astype(float).tolist()
                row.update(avg_round_trip_s=";".join(f"{x:.4f}" for x in a), avg_rt_max_over_min=max(a) / min(a) if min(a) else "")
            out.append(row)
    return out


def point_stat_rows(raw_root):
    out = []
    for ps in point_sets(raw_root):
        if ps["phase"] != 2:
            continue
        raw = readdf(ps["dir"] / "raw.csv", ["n", "rep", "exec_time_us"])
        term = readdf(ps["dir"] / "memory_wall.csv", ["n", "status"])
        okn = set(term[term["status"] == "ok"]["n"].astype(int))
        prev = None
        for n in sorted(okn):
            g = raw[raw["n"] == n].sort_values("rep")
            v = g["exec_time_us"].to_numpy(float)
            if not len(v):
                continue
            q1, med, q3 = np.percentile(v, [25, 50, 75])
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            n_out = int(((v < lo) | (v > hi)).sum())
            drift = ""
            if len(v) >= 40:
                drift = abs(np.median(v[-20:]) - np.median(v[:20])) / med > 0.10
            s = np.sort(v)
            bimodal = False
            if len(s) >= 10 and s[-1] > s[0]:
                gaps = np.diff(s)
                k = int(np.argmax(gaps))
                bimodal = bool(gaps[k] > 0.5 * (s[-1] - s[0]) and (k + 1) >= 0.1 * len(s) and (len(s) - k - 1) >= 0.1 * len(s))
            res = MICROS_RESOLUTION_US[ps["board"]]
            out.append(dict(board=ps["board"], circuit=ps["circuit"], n=n, reps=len(v), median_us=med, q1_us=q1, q3_us=q3,
                            iqr_us=iqr, min_us=v.min(), max_us=v.max(), ratio_to_prev_n=(med / prev) if prev else "",
                            non_monotonic=(prev is not None and med < prev), outliers=n_out, outlier_frac=n_out / len(v),
                            outlier_heavy=n_out / len(v) > OUTLIER_FRACTION,
                            dev_frac=float((np.abs(v - med) > max(0.01 * med, 2 * MICROS_RESOLUTION_US[ps["board"]])).mean()),
                            max_over_median=float(v.max() / med), drift=drift, bimodal=bimodal,
                            rep0_over_median=float(v[0] / med) if len(v) else "", warmup_flag=bool(v[0] > 2 * med),
                            resolution_us=res, median_below_20x_resolution=bool(med < 20 * res),
                            iqr_over_median=iqr / med if med else ""))
            prev = med
    return out


# --------------------------------------------------------------------------- analysis tables

def ok_series(raw_root, board, circuit, phase=2):
    d = Path(raw_root) / f"phase{phase}" / board / circuit / "with_ref"
    raw = readdf(d / "raw.csv")
    if not len(raw):
        return {}
    col = "exec_time_us" if phase == 2 else "e2e_latency_us"
    if phase == 2:
        term = readdf(d / "memory_wall.csv", ["n", "status"])
        okn = set(term[term["status"] == "ok"]["n"].astype(int))
    else:
        term = readdf(d / "session_log.csv", ["n", "status"])
        okn = set(term[term["status"] == "ok"]["n"].astype(int))
    return {int(n): g[col].to_numpy(float) for n, g in raw.groupby("n") if int(n) in okn}


def slope_rows(raw_root, fit_points=5):
    out, mv = [], []
    for b in BOARDS:
        for c in CIRCUITS:
            s = ok_series(raw_root, b, c)
            full = sorted(n for n, v in s.items() if len(v) == REPS)
            if len(full) < 3:
                continue
            med = {n: float(np.median(s[n])) for n in full}
            fit = full[-fit_points:]
            slope = float(np.polyfit(fit, [np.log2(med[n]) for n in fit], 1)[0])
            ratios = [med[n] / med[n - 1] for n in full if n - 1 in med]
            out.append(dict(board=b, circuit=c, n_first=full[0], n_last=full[-1], fit_range=f"{fit[0]}..{fit[-1]}", slope_doublings_per_qubit=slope,
                            ratio_min=min(ratios), ratio_median=float(np.median(ratios)), ratio_max=max(ratios), ratio_last=ratios[-1]))
            for n in sorted(s):
                est = tm.expected_exec_time_us(b, c, n)
                m = float(np.median(s[n]))
                mv.append(dict(board=b, circuit=c, n=n, reps=len(s[n]), measured_median_us=m, timing_model_estimate_us=est,
                               measured_over_estimate=m / est if est else ""))
    return out, mv


def limits_rows(raw_root):
    out = []
    for b in BOARDS:
        for c in CIRCUITS:
            d = Path(raw_root) / "phase2" / b / c / "with_ref"
            term = readdf(d / "memory_wall.csv", ["n", "status"])
            if not len(term):
                continue
            term = term.sort_values("timestamp_utc") if "timestamp_utc" in term.columns else term
            last = term.drop_duplicates("n", keep="last")
            ok = last[last["status"] == "ok"]
            nlast = int(ok["n"].max()) if len(ok) else None
            wall = last[last["status"].map(lambda s: rs.is_wall_status(str(s)))]
            tl = last[last["status"].astype(str).str.startswith("skipped_compute_infeasible")]
            pts = readdf(d / "points.csv")
            wd = pts[(pts["status"] == "failed") & (pts["failure_type"] == "watchdog_suspected")] if len(pts) and "failure_type" in pts.columns else pts
            if len(wall):
                w = wall.sort_values("n").iloc[0]
                kind = "memory"
                ev = f"{w['status']}" + (f", compile_ram_pct={w['compile_ram_pct']}" if pd.notna(w.get("compile_ram_pct")) else "")
                wn = int(w["n"])
            elif len(tl):
                kind, ev, wn = "time ceiling", f"skipped_compute_infeasible from n={int(tl['n'].min())} (1 rep > {tm.POINT_TIME_CAP_S} s)", int(tl["n"].min())
            else:
                kind, ev, wn = "none reached", "", ""
            pred = plan.wall_n(b)
            out.append(dict(board=b, circuit=c, last_ok_n=nlast, limit_n=wn, limit_kind=kind, evidence=ev,
                            predicted_wall_n=pred, predicted_evidence=plan.wall_evidence(b),
                            matches_prediction=(wn == pred) if wn != "" and kind == "memory" else "",
                            watchdog_attempts=int(len(wd)), capped_points=int(((last["status"] == "ok") & False).sum())))
    return out


def cross_board_rows(raw_root):
    out = []
    for c in CIRCUITS:
        ser = {b: ok_series(raw_root, b, c) for b in BOARDS}
        for n in sorted(set().union(*[set(s) for s in ser.values()])):
            m = {b: float(np.median(ser[b][n])) for b in BOARDS if n in ser[b]}
            if len(m) < 2:
                continue
            row = dict(circuit=c, n=n)
            for b in BOARDS:
                row[f"{b}_median_us"] = m.get(b, "")
            for a, bb in (("uno", "esp8266"), ("uno", "esp32"), ("esp8266", "esp32")):
                row[f"{a}_over_{bb}"] = m[a] / m[bb] if a in m and bb in m else ""
            out.append(row)
    return out


def reference_rows(raw_root, sessions):
    valid = {(s["board"], s["circuit"]) for s in sessions if s["phase"] == 2 and s["reference_state"].startswith("REFERENCE-PHYSICAL")}
    invalid = {(s["board"], s["circuit"]) for s in sessions if s["phase"] == 2 and not s["reference_state"].startswith("REFERENCE-PHYSICAL")}
    out = []
    for b in BOARDS:
        for c in CIRCUITS:
            if (b, c) not in valid or (b, c) in invalid:
                continue
            d = Path(raw_root) / "phase2" / b / c / "with_ref" / "ref"
            cmp_ = readdf(d / "ref_compare.csv")
            pts = readdf(d / "ref_compare_points.csv")
            for r in pts.to_dict("records") if len(pts) else []:
                g = cmp_[cmp_["n"] == r["n"]]
                if not len(g):
                    continue
                us, pc = g["diff_us"].to_numpy(float), g["diff_pct"].to_numpy(float)
                q = MICROS_RESOLUTION_US[b]
                out.append(dict(board=b, circuit=c, n=int(r["n"]), pairs=len(g), ref_status=r.get("ref_status", ""),
                                median_diff_us=float(np.median(us)), iqr_diff_us=float(np.percentile(us, 75) - np.percentile(us, 25)),
                                median_diff_pct=float(np.median(pc)), micros_resolution_us=q,
                                within_resolution=bool(abs(np.median(us)) <= q)))
    return out


def phase3_rows(raw_root):
    out = []
    for b in BOARDS:
        for c in CIRCUITS:
            d = Path(raw_root) / "phase3" / b / c / "with_ref"
            raw = readdf(d / "raw.csv")
            pts = readdf(d / "points.csv")
            if not len(raw):
                continue
            ok = {}
            for r in pts.to_dict("records") if len(pts) else []:
                if r["status"] == "ok":
                    ok[(int(r["n"]), int(r["baud"]))] = r
            for (n, baud), g in raw.groupby(["n", "baud_rate"]):
                r = ok.get((int(n), int(baud)))
                lat = g["e2e_latency_us"].to_numpy(float)
                frame_us = FRAME_BYTES_PER_REQUEST * BITS_PER_BYTE_ON_WIRE / baud * 1e6
                row = dict(board=b, circuit=c, n=int(n), baud=int(baud), requests=len(g), median_rt_us=float(np.median(lat)),
                           min_rt_us=float(lat.min()), frame_time_us=frame_us, crc_rows=int((g["crc_error"] == 1).sum()),
                           timeout_rows=int((g["timed_out"] == 1).sum()))
                if r:
                    sim_total, dev, k = float(r["pc_sim_s_total"]), float(r["device_exec_s"]), len(g)
                    row.update(pc_sim_per_request_us=sim_total / k * 1e6, wall_per_request_us=dev / k * 1e6,
                               sum_rt_s=float(lat.sum() / 1e6), pc_sim_total_s=sim_total, device_exec_s=dev,
                               pc_sim_share_of_rt=sim_total / (lat.sum() / 1e6),
                               overhead_us=float(np.median(lat)) - frame_us - sim_total / k * 1e6,
                               retry_count=r.get("retry_count", ""))
                out.append(row)
    return out


def crossover_rows(raw_root):
    out = []
    for b in BOARDS:
        for c in CIRCUITS:
            loc, off = ok_series(raw_root, b, c, 2), ok_series(raw_root, b, c, 3)
            common = sorted(set(loc) & set(off))
            if not common:
                continue
            ratio = {n: float(np.median(off[n]) / np.median(loc[n])) for n in common}
            cross = next((n for n in common if ratio[n] < 1), None)
            out.append(dict(board=b, circuit=c, common_n=f"{common[0]}..{common[-1]}", crossover_n=cross if cross is not None else "none in range",
                            offload_over_local_at_first=ratio[common[0]], offload_over_local_at_last=ratio[common[-1]],
                            offload_over_local_min=min(ratio.values()), offload_over_local_max=max(ratio.values())))
    return out


# --------------------------------------------------------------------------- prediction accuracy

def gates_total(circuit, n):
    return sum(tm.gate_counts(circuit, n))


def predictor(circuit, n, variant="M1"):
    """Predictor feature f(circuit, n) in 'amplitude updates'.
    M1 (declared before the first look at results): total gates x 2^n  (every gate loops over all 2^n indices).
    M2 (POST-HOC): touched amplitudes: H 2^n, CNOT 2^(n-1) (pairs control=1,target=0 swapped), CPHASE 2^(n-2)
       (qsim.hpp:65, :86, :107)."""
    h, c, p = tm.gate_counts(circuit, n)
    if variant == "M2":
        return h * 2.0 ** n + c * 2.0 ** (n - 1) + p * 2.0 ** (n - 2)
    return (h + c + p) * 2.0 ** n


def feature3(circuit, n):
    h, c, p = tm.gate_counts(circuit, n)
    return [h * 2.0 ** n, c * 2.0 ** n, p * 2.0 ** n]


def fit_c(points, with_const=False):
    """points: list of (f, t). Relative-error least squares for t = c*f (+ t0 >= 0). Returns (c, t0)."""
    f = np.array([p[0] for p in points], float)
    t = np.array([p[1] for p in points], float)
    if not with_const:
        c = float(np.sum(f / t) / np.sum((f / t) ** 2))     # argmin sum((c f - t)/t)^2
        return c, 0.0
    from scipy.optimize import nnls
    A = np.vstack([f / t, 1.0 / t]).T
    sol, _ = nnls(A, np.ones(len(t)))
    return float(sol[0]), float(sol[1])


DECLARED = {"M1": "pre", "M1c": "pre", "M2": "post-hoc", "M2c": "post-hoc", "M3": "post-hoc"}


def prediction_rows(raw_root):
    rows, loco = [], []
    series = {(b, c): ok_series(raw_root, b, c) for b in BOARDS for c in CIRCUITS}
    for (b, c), s in series.items():
        ns = sorted(s)
        if len(ns) < 4:
            continue
        half = len(ns) // 2
        for variant, base, wc in (("M1", "M1", False), ("M1c", "M1", True), ("M2", "M2", False), ("M2c", "M2", True)):
            pts = [(n, predictor(c, n, base), float(np.median(s[n]))) for n in ns]
            cc, t0 = fit_c([(f, t) for _, f, t in pts[:half]], wc)
            for i, (n, f, t) in enumerate(pts):
                pred = cc * f + t0
                rows.append(dict(board=b, circuit=c, n=n, variant=variant, declared=DECLARED[variant],
                                 set="fit (smaller half)" if i < half else "extrapolation", measured_us=t, predicted_us=pred,
                                 measured_over_predicted=t / pred, c_us=cc, t0_us=t0))
    from scipy.optimize import nnls
    for b in BOARDS:
        for held in CIRCUITS:
            if not series[(b, held)]:
                continue
            for variant, base in (("M1", "M1"), ("M2", "M2"), ("M3", None)):
                train = []
                for c in CIRCUITS:
                    if c == held:
                        continue
                    for n, v in series[(b, c)].items():
                        train.append((c, n, float(np.median(v))))
                if len(train) < 3:
                    continue
                if base:
                    cc, _ = fit_c([(predictor(c, n, base), t) for c, n, t in train], False)
                    predf = lambda cn, nn, cc=cc, base=base: cc * predictor(cn, nn, base)
                    ncoef = 1
                else:
                    A = np.array([[x / t for x in feature3(c, n)] for c, n, t in train])
                    k, _ = nnls(A, np.ones(len(train)))
                    predf = lambda cn, nn, k=k: float(np.dot(k, feature3(cn, nn)))
                    ncoef = 3
                for n, v in sorted(series[(b, held)].items()):
                    pred = predf(held, n)
                    loco.append(dict(board=b, held_out=held, n=n, variant=variant, declared=DECLARED[variant],
                                     measured_us=float(np.median(v)), predicted_us=pred, measured_over_predicted=float(np.median(v)) / pred,
                                     train_points=len(train), coefficients=ncoef))
    return rows, loco


def summarize_ratios(df, group, col="measured_over_predicted"):
    out = []
    for key, g in df.groupby(group):
        r = g[col].to_numpy(float)
        key = key if isinstance(key, tuple) else (key,)
        out.append(dict(zip(group, key), points=len(r), median_ratio=float(np.median(r)), q1=float(np.percentile(r, 25)), q3=float(np.percentile(r, 75)),
                        min_ratio=float(r.min()), max_ratio=float(r.max()), within_25pct=float(((r > 0.75) & (r < 1.25)).mean()),
                        within_2x=float(((r > 0.5) & (r < 2.0)).mean())))
    return out


def memory_model_rows(raw_root):
    out = []
    for b in BOARDS:
        for c in CIRCUITS:
            d = Path(raw_root) / "phase2" / b / c / "with_ref"
            term = readdf(d / "memory_wall.csv", ["n", "status"])
            raw = readdf(d / "raw.csv")
            if not len(term):
                continue
            ok = term[term["status"] == "ok"]
            if b == "uno":
                st = [float(r.compile_ram_used_bytes) - 8 * 2 ** int(r.n) for r in ok.itertuples() if pd.notna(r.compile_ram_used_bytes)]
                static = float(np.median(st)) if st else float("nan")
                avail = BOARD_RAM["uno"]
                basis = f"static {static:.0f} B (compile RAM used - state), RAM {avail} B"
            else:
                # free_heap_before / largest_block are read with the state already allocated: add it back, taken at the
                # smallest ok n where the state is tiny (the allocation that fails at the wall needs this much room)
                col = "largest_block" if "largest_block" in raw.columns else "free_heap_before"
                n0 = int(raw["n"].min()) if len(raw) else 0
                avail = float(raw[raw["n"] == n0][col].median()) + 8 * 2 ** n0 if len(raw) else float("nan")
                static = 0.0
                basis = f"{col} at n={n0} + its state = {avail:.0f} B"
            pred_n = next((n for n in range(1, 40) if 8 * 2 ** n + static > avail), None)
            walls = term[term["status"].map(lambda s: rs.is_wall_status(str(s)))]
            out.append(dict(board=b, circuit=c, model_basis=basis, predicted_wall_n=pred_n,
                            observed_wall_n=int(walls["n"].min()) if len(walls) else "none reached",
                            agree=(pred_n == int(walls["n"].min())) if len(walls) else ""))
    return out


# --------------------------------------------------------------------------- driver

def write_csv(path, rows_, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_ = list(rows_)
    if not fields:
        fields = []
        for r in rows_:
            for k in r:
                if k not in fields:
                    fields.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows_:
            w.writerow(r)


def run_all(raw_root, repo_root, ledger_path, out_dir, docs_dir=None, use_git=True):
    assert_not_raw(out_dir, raw_root)
    out_dir = Path(out_dir)
    sessions = inventory(raw_root, repo_root, ledger_path, use_git)
    comp = completeness(raw_root)
    checks = run_checks(raw_root, repo_root, sessions, comp, docs_dir)
    recompute = recompute_counter(raw_root) + (recompute_docs(raw_root, docs_dir) if docs_dir else [])
    bad_docs = [r for r in recompute if r["status"] == "MISMATCH" and r["quantity"] == "median_exec_time_us"]
    checks.append(dict(id="B2c", check="medians quoted in docs/analysis/**/*.md equal a recomputation from raw.csv",
                       result="FAIL" if bad_docs else "PASS", evidence=f"{len([r for r in recompute if r['quantity'] == 'median_exec_time_us'])} values; "
                       + "; ".join(f"{r['where']} {r['stored']} vs {r['recomputed']}" for r in bad_docs[:3])))
    write_csv(out_dir / "sessions.csv", sessions)
    write_csv(out_dir / "completeness.csv", comp)
    write_csv(out_dir / "checks.csv", checks)
    write_csv(out_dir / "recompute.csv", recompute, ["where", "quantity", "stored", "recomputed", "status"])
    write_csv(out_dir / "point_stats.csv", point_stat_rows(raw_root))
    write_csv(out_dir / "repeats.csv", repeat_rows(raw_root))
    slopes, mv = slope_rows(raw_root)
    write_csv(out_dir / "slopes.csv", slopes)
    write_csv(out_dir / "model_vs_measured.csv", mv)
    write_csv(out_dir / "limits.csv", limits_rows(raw_root))
    write_csv(out_dir / "memory_model.csv", memory_model_rows(raw_root))
    write_csv(out_dir / "cross_board.csv", cross_board_rows(raw_root))
    write_csv(out_dir / "crossover.csv", crossover_rows(raw_root))
    write_csv(out_dir / "reference_diff.csv", reference_rows(raw_root, sessions))
    write_csv(out_dir / "phase3_link.csv", phase3_rows(raw_root))
    pr, lo = prediction_rows(raw_root)
    write_csv(out_dir / "prediction.csv", pr)
    write_csv(out_dir / "loco.csv", lo)
    if pr:
        df = pd.DataFrame(pr)
        summ = []
        for r in summarize_ratios(df, ["variant", "declared", "set"]):
            summ.append(dict(scope="all points", **r))
        ex = df[df["set"] == "extrapolation"]
        for r in summarize_ratios(ex, ["variant", "declared", "board"]):
            summ.append(dict(scope="extrapolation by board", **r))
        for r in summarize_ratios(ex, ["variant", "declared", "circuit"]):
            summ.append(dict(scope="extrapolation by circuit", **r))
        if lo:
            ldf = pd.DataFrame(lo)
            for r in summarize_ratios(ldf, ["variant", "declared", "board"]):
                summ.append(dict(scope="leave-one-circuit-out by board", **r))
            for r in summarize_ratios(ldf, ["variant", "declared", "held_out"]):
                summ.append(dict(scope="leave-one-circuit-out by circuit", **r))
            for r in summarize_ratios(ldf, ["variant", "declared"]):
                summ.append(dict(scope="leave-one-circuit-out overall", **r))
        write_csv(out_dir / "prediction_summary.csv", summ)
    return dict(sessions=sessions, completeness=comp, checks=checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="read-only data audit")
    ap.add_argument("--raw", type=Path, default=REPO_ROOT / "data" / "raw")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT)
    ap.add_argument("--ledger", type=Path, default=REPO_ROOT / "data" / "run_history.jsonl")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "processed" / "audit")
    ap.add_argument("--docs", type=Path, default=REPO_ROOT / "docs" / "analysis")
    ap.add_argument("--no-git", action="store_true", help="skip git lookups (tests)")
    a = ap.parse_args(argv)
    try:
        res = run_all(a.raw, a.repo, a.ledger, a.out, a.docs, use_git=not a.no_git)
    except AuditError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    cnt = pd.Series([c["result"] for c in res["checks"]]).value_counts().to_dict()
    print(f"sessions={len(res['sessions'])} points={len(res['completeness'])} checks={cnt}")
    for c in res["checks"]:
        if c["result"] in ("FAIL", "UNVERIFIED"):
            print(f"  {c['result']} {c['id']}: {c['check']} -- {c['evidence'][:140]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
