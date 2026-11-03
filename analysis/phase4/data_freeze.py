#!/usr/bin/env python3
"""Data freeze: writes docs/DATA_FREEZE.md and data/derived/MANIFEST.sha256. Read-only on data/raw/.

    .venv/bin/python analysis/phase4/data_freeze.py            # write both files
    .venv/bin/python analysis/phase4/data_freeze.py --check    # verify the manifest against the files on disk (exit 1 on any difference)

The session-selection tables and every constant in the rule table are read from analysis/common/{sessions,weak,counter_validity}.py,
analysis/phase4/{p4common,timemodel}.py and data/raw/**/sessions.csv; what is written by hand is wording (what a rule means, when it was set relative to
the data). Commit dates come from `git log` (a rule's date is the date of the commit named in the table; 'n/a' when there is no git history).
The manifest covers every file under data/raw/ and data/derived/ except itself, one line per file as `sha256sum -c` / `shasum -a 256 -c` expects it, paths
relative to the repository root, sorted by path (bytewise).
"""
import hashlib
import os
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import p4common as C  # noqa: E402
import timemodel as TM  # noqa: E402
from common import counter_validity as CV  # noqa: E402
from common import sessions as SES  # noqa: E402
from common import weak as W  # noqa: E402

ROOT = C.ROOT
MANIFEST = os.path.join(ROOT, "data", "derived", "MANIFEST.sha256")
DOC = os.path.join(ROOT, "docs", "DATA_FREEZE.md")
TREES = ("data/raw", "data/derived")
PHASES = (2, 3)


# ------------------------------------------------------------------------------------------------ manifest
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def manifest_entries():
    out = []
    for t in TREES:
        for d, _, files in os.walk(os.path.join(ROOT, t)):
            for f in files:
                p = os.path.join(d, f)
                rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
                if rel == "data/derived/MANIFEST.sha256":
                    continue
                out.append((rel, p))
    out.sort(key=lambda x: x[0].encode())
    return [(sha256(p), rel, os.path.getsize(p)) for rel, p in out]


def write_manifest():
    ent = manifest_entries()
    with open(MANIFEST, "w") as f:
        for h, rel, _ in ent:
            f.write(f"{h}  {rel}\n")
    return ent


def check_manifest():
    want = {}
    for line in open(MANIFEST):
        h, rel = line.rstrip("\n").split("  ", 1)
        want[rel] = h
    have = {rel: h for h, rel, _ in manifest_entries()}
    bad = [r for r in want if r in have and want[r] != have[r]]
    missing = [r for r in want if r not in have]
    extra = [r for r in have if r not in want]
    for tag, lst in (("CHANGED", bad), ("MISSING", missing), ("NOT IN MANIFEST", extra)):
        for r in lst:
            print(tag, r)
    print(f"{len(want)} files in manifest; {len(bad)} changed, {len(missing)} missing, {len(extra)} not in manifest")
    return not (bad or missing or extra)


# ------------------------------------------------------------------------------------------------ session table
def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def commit_date(h):
    d = git("log", "-1", "--format=%ad", "--date=format:%Y-%m-%d %H:%M %z", h)
    return d or "n/a"


def ranges(ns):
    ns = sorted(set(ns))
    out, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append(str(ns[i]) if i == j else f"{ns[i]}-{ns[j]}")
        i = j + 1
    return ",".join(out) if out else "-"


def session_ids(d):
    """session ids of a bucket: the env/*.json sidecars (every session has one; sessions.csv misses some)"""
    ed = os.path.join(d, "env")
    return sorted(f[:-5] for f in os.listdir(ed) if f.endswith(".json") and not f.endswith(".ref.json")) if os.path.isdir(ed) else []


def sid_date(sid):
    """UTC date of a session id (`YYYYMMDDTHHMMSS-xxxxxxxx`)"""
    return f"{sid[:4]}-{sid[4:6]}-{sid[6:8]}"


def bucket_info(phase, board, circuit, bucket):
    d = SES.bucket_dir(phase, board, circuit, bucket)
    raw = pd.read_csv(os.path.join(d, "raw.csv")) if os.path.exists(os.path.join(d, "raw.csv")) else pd.DataFrame(columns=["n"])
    ids = session_ids(d)
    ns = sorted(int(n) for n in set(raw["n"]))
    return dict(dir=d, ns=ns, sessions=ids, start=sid_date(ids[0]) if ids else "-", end=sid_date(ids[-1]) if ids else "-")


def selection_tables():
    """-> (series rows, bucket rows)"""
    srows, brows = [], []
    for ph in PHASES:
        for b in C.BOARDS:
            for c in C.CIRCUITS:
                bk = SES.buckets(ph, b, c)
                info = {x: bucket_info(ph, b, c, x) for x in bk}
                allns = sorted({n for x in info.values() for n in x["ns"] if SES.in_scope(ph, b, c, n)})
                sel = {}
                for n in allns:
                    sel.setdefault(SES.select_session(ph, b, c, n), []).append(n)
                cnt = {}
                for n in allns:
                    cs = SES.counter_session(ph, b, c, n)
                    if cs != SES.select_session(ph, b, c, n):
                        cnt.setdefault(cs, []).append(n)
                srows.append((ph, C.BOARD_LABEL[b], c, "; ".join(f"`{k}` n={ranges(v)}" for k, v in sel.items()),
                              "; ".join(f"`{k}` n={ranges(v)}" for k, v in cnt.items()) or "-"))
                for x in bk:
                    i = info[x]
                    inn = [n for n in i["ns"] if SES.in_scope(ph, b, c, n)]
                    used = [n for n in inn if SES.select_session(ph, b, c, n) == x]
                    cused = [n for n in inn if SES.counter_session(ph, b, c, n) == x and SES.select_session(ph, b, c, n) != x]
                    rep = [n for n in inn if n not in used]
                    role = []
                    if used:
                        role.append(f"selected n={ranges(used)}")
                    if cused:
                        role.append(f"counter pairs only n={ranges(cused)}")
                    if rep:
                        role.append(f"replicate/replaced, reproducibility table only n={ranges(rep)}")
                    if not inn:
                        role.append("no in-scope n")
                    brows.append((ph, C.BOARD_LABEL[b], c, x, sess_cell(i["sessions"]),
                                  i["start"] if i["start"] == i["end"] else f"{i['start']}..{i['end']}", ranges(i["ns"]), "; ".join(role)))
    return srows, brows


def sess_cell(ids):
    ids = [x.split("-")[0] for x in ids]
    return ", ".join(ids) if len(ids) <= 3 else f"{len(ids)} sessions, {ids[0]} .. {ids[-1]}" if ids else "-"


def md_table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ document
def build_doc(ent):
    srows, brows = selection_tables()
    nraw = sum(1 for _, rel, _ in ent if rel.startswith("data/raw/"))
    nder = sum(1 for _, rel, _ in ent if rel.startswith("data/derived/"))
    nbytes = sum(s for _, _, s in ent)
    mh = sha256(MANIFEST)
    ids = sorted({x for ph in PHASES for bd in C.BOARDS for c in C.CIRCUITS for bk in SES.buckets(ph, bd, c) for x in session_ids(SES.bucket_dir(ph, bd, c, bk))})
    orig = [x for x in brows if x[3] == SES.ORIGINAL]
    n_ses = len(ids)
    t0, t1 = sid_date(ids[0]), sid_date(ids[-1])
    ph1 = sorted(f for f in os.listdir(os.path.join(ROOT, "data", "raw", "phase1")) if f.startswith("infidelity_tvd."))
    wall = {b: SES.wall_n(b) for b in C.BOARDS}
    cd = commit_date
    L = []
    a = L.append
    a("# Data freeze v1: dataset, selection and analysis rules\n")
    a("Generated by `analysis/phase4/data_freeze.py` (`make freeze`); do not edit by hand. Constants and tables are read from the code and from `data/raw/**/sessions.csv`; "
      "the wording of the rule table and the before/after labels are written by hand from the git history and the Phase 4 report (section 4), and are marked "
      "**OBSERVED** (checkable in the files or in `git log`) or **INTERPRETATION** / **UNVERIFIED**.\n")
    a("## 1. What is frozen\n")
    a(f"- `data/raw/`: {nraw} files; `data/derived/`: {nder} files (the manifest itself excluded); {nbytes / 1e6:.1f} MB together. "
      f"`data/derived/MANIFEST.sha256` lists the sha256 of every one of them (`shasum -a 256 -c data/derived/MANIFEST.sha256` from the repository root; "
      f"`analysis/phase4/data_freeze.py --check` does the same). sha256 of the manifest file: `{mh}`.")
    a(f"- Phase 2 and 3 collection: {n_ses} sessions (one env sidecar each), starting {t0} to {t1} (UTC). Phase 1 (PC build against Qiskit Aer): {len(ph1)} infidelity "
      f"files ({', '.join(f.split('.')[1] for f in ph1)}).")
    a("- Nothing under `data/raw/` or `data/calibration/` is written by any analysis script (`analysis/common/sessions.py` and `analysis/phase4/audit.py` read only). "
      "`data/derived/` is rewritten by `analysis/reproduce.py`, which prints the sha256 of every figure, table and the report so two runs can be compared.")
    a("- What the freeze does **not** claim: that the rules below were set before the data were seen (most were not, section 3), or that the board data are correct "
      "(the reference counter is uncalibrated, section 3).\n")
    a("## 2. Scope and session selection\n")
    a("Scope (`analysis/common/sessions.py`): boards Uno R3, ESP8266, ESP32; circuits h_all, bell_ghz, qft, grover; n >= "
      f"{SES.N_MIN}; Phase 2 has no data at or beyond its wall; Phase 3 is kept up to the Phase 2 wall n of the board "
      f"({', '.join(f'{C.BOARD_LABEL[b]} n={wall[b]}' for b in C.BOARDS)}; `config/sweep_ranges.toml [wall.<board>]`). qpe and steane_encode are not used. "
      "Bucket `with_ref` = original collection; `with_ref_<TAG>` = repeat session (`pc/run.py --rerun TAG`), a whole new sample per point, never merged with another bucket. "
      "Replaced and replicate sessions are used only for the reproducibility table (`SES.replicates()`) and for the Phase 3 PC-simulation band (offload_band.py, in-scope n only).\n")
    a("Selection rules in force (`SES.RULES`, `SES.COUNTER_RULES`; owner's decision of 2026-10-31, after the data and the first scores were known):\n")
    a("**Per series and n (generated from `SES.select_session` / `SES.counter_session` over the n present on disk):**\n")
    a(md_table(["phase", "board", "circuit", "timer data (bucket, n)", "counter pairs from another bucket"], srows))
    a("\n**Every bucket on disk (generated):** session = session-id prefix (UTC timestamp), n = every n with rows in `raw.csv` (before scope), role = what the in-scope n are used for.\n")
    a(md_table(["phase", "board", "circuit", "bucket", "sessions", "dates (UTC)", "n in raw.csv", "role"], brows))
    a(f"\nOBSERVED: {len(orig)} of the {len(srows)} series have an original bucket; the original collection is the primary evidence wherever no rule above names a repeat session.\n")
    a("## 3. Rules in force and when each was set\n")
    a("Reference points: the original data were committed 2026-10-04 to 2026-10-10 (`git log -- data/raw`, Phase 2/3 sessions starting "
      f"{t0}); the first Phase 4 analysis commit is `bf9b692` ({cd('bf9b692')}); the fix round that changed the rules, after the first test scores were known, is `0724ab3`"
      f" (, {cd('0724ab3')}). The repeat sessions r2, r2b, r2c were collected 2026-10-30/31 *after* those scores. "
      "'Before the data were seen' therefore never applies to the Phase 4 rules: the question per rule is whether it was set before the **scores** (the held-out errors) were seen.\n")
    rows = [
        ("Phase 1 gate", f"raw infidelity of the float32 PC build against Aer <= 1e-3 (`INFIDELITY_THRESHOLD`, `analysis/phase1_compare.py`)",
         f"`7a22d20` {cd('7a22d20')}", "**before** the Phase 1 data of 2026-10-03/04 (OBSERVED: the threshold is in the first commit of that script)"),
        ("Phase 1 primary metric", "grover's Phase 1 is judged by the infidelity of the *normalised* state (direction error), raw infidelity secondary; sensitivity at 1e-4 and 1e-2 reported",
         f"`a3a81ce` {cd('a3a81ce')}", "**after** the grover norm loss was seen: post-hoc, disclosed as such in the paper"),
        ("Split and floor", f"held-out = largest {C.N_TEST} ok n of each (board, circuit); a fit point needs median >= {C.FLOOR_US:g} us (`p4common.N_TEST`, `FLOOR_US`)",
         f"`bf9b692` {cd('bf9b692')}", "after collection, **before any test point was scored** (stated in `timemodel.py` and report section 4; not independently verifiable from the history)"),
        ("Model form M1 / M2", "M1 one constant per board; M2 per-gate-kind costs (H, CNOT, CPHASE) + per-call term, NNLS on relative error",
         f"`bf9b692` {cd('bf9b692')}", "after collection and **not blind**: M2 has the form of 'Model B' whose out-of-sample grover errors were known (report section 4)"),
        ("Memory predictor", "wall n = floor(log2(B/8)), B read at n=2 (Uno: compiler RAM figure; ESP8266: free heap; ESP32: total free heap and largest free block, both reported)",
         f"`bf9b692` {cd('bf9b692')}", "after the walls were observed in collection (walls are in `memory_wall.csv`); INTERPRETATION: a consistency test of B, not a blind prediction"),
        ("Weak rule", f"a point with fewer than {W.WEAK_MIN} repetitions (Phase 3: requests) is weak: never fitted, never in the primary MAPE, drawn hollow (`weak.WEAK_MIN`)",
         f"`4581fb3` {cd('4581fb3')}", "**after** the first scores (the first analysis used 10 repetitions)"),
        ("Independent-repetition rule", f"rows after an exact periodic repeat of a block (period >= {W.MIN_PERIOD}, >= {W.MIN_DISTINCT} distinct values, covering >= {W.MIN_COVER:g} of the rows) "
         "are copies and do not count toward the 30 (`weak.effective_reps`)", f"`0724ab3` {cd('0724ab3')}", "**after** the data were seen (found in ESP32 grover n=9, n=10); cause of the copies UNVERIFIED"),
        ("Hash rule", "every grover point carries the firmware source hash of its session; hashes are classed A (reference), B (timing-relevant difference), X (unknown); non-A points are not fitted; "
         "a fit that mixes classes raises (`timemodel.assert_homogeneous`)", f"`1f410f9` {cd('1f410f9')}", "**after** the first scores (classes assigned from `git diff` of the firmware trees; INTERPRETATION for the timing relevance)"),
        ("Identifiability rule", f"an M2 fit is identifiable if n_fit >= params + 2, full column rank, column-scaled condition number <= {TM.COND_MAX:g} and no NNLS coefficient on the zero boundary (<= 1e-12)",
         f"`9a7de1a` {cd('9a7de1a')}", "**after** the first scores; the boundary condition is a knife edge (verdict changes with the held-out size) and has no claim of being set in advance"),
        ("Session selection", "table in section 2 (`SES.RULES`)", f"`765b34a` {cd('765b34a')}", "**after** the data and scores (INTERPRETATION: the repeat sessions replace points whose original session was hash class B or X)"),
        ("Counter-session fallback", "counter pairs of ESP8266 grover n=7 from r2b and ESP32 grover n=9 from r2c when the selected session has none (`SES.COUNTER_RULES`)",
         f"`765b34a` {cd('765b34a')}", "**after**; chosen because those sessions have usable pairs, an availability-conditioned choice"),
        ("Counter validity R1-R4", "R1 join status in {ok, anomaly, count_mismatch}; R2 pairs == reps in raw.csv; R3 no counter-side pulse flag (glitch bit, anomaly code != 0); "
         f"R4 micros() median <= T_MAX = {CV.T_MAX_S:.0f} s (representation limit of the counter firmware, not binding for any point on disk); none of them looks at agreement with micros()",
         f"`09f0a38` {cd('09f0a38')}", "**after** the data were collected; R1-R4 use only what the counter recorded about the pulses"),
        ("Counter validity R5", f"a pair is implausible if counter/micros() is outside [{CV.RATIO_LO}, {CV.RATIO_HI}] or the counter lies within {CV.WRAP_TOL_US:g} us of k x {CV.WRAP_US:.1f} us (32-bit wrap at 80 MHz); "
         "any implausible pair makes the point unusable", f"`0ac49da` {cd('0ac49da')}", "**after** the data were seen, and it **conditions on agreement** with micros(): statistics of the points that pass are not independent of the filter"),
        ("Offload band and brackets", "band = wire + residual + [min, max] observed PC simulation time per circuit x n over every Phase 3 session; crossover = bracket of two measured n for the fast and for the slow bound; "
         f"labels *within noise* (IQRs overlap) and *weak* (< {W.WEAK_MIN})", f"`448f67c` {cd('448f67c')}", "**after** the data and scores (a single offload line hid the ~2x spread of the PC simulation time between sessions)"),
        ("Held-out sensitivity", "held-out = largest 2, 3, 4 reported in full; 3 stays primary", f"`9a7de1a` {cd('9a7de1a')}", "after the first scores; reported so that the primary choice is not the only number"),
    ]
    a(md_table(["rule", "definition (constants read from the code)", "set in commit", "relative to the data / scores"], rows))
    a("\nCounter calibration status (OBSERVED, report section 2): every session sidecar carries `\"calibration\": {}` and `\"selftest\": \"self-loopback only\"`; the counter is **uncalibrated**.\n")
    a("## 4. Tag\n")
    a("The tag is **not** created by the scripts. After committing `docs/DATA_FREEZE.md` and `data/derived/MANIFEST.sha256`:\n")
    a("```\ngit tag -a data-freeze-v1 -m \"data freeze v1: data/raw and data/derived as listed in data/derived/MANIFEST.sha256; rules of docs/DATA_FREEZE.md\" <commit>\n```\n")
    a("`git tag` is local; nothing here is pushed. To verify later: `git checkout data-freeze-v1 && shasum -a 256 -c data/derived/MANIFEST.sha256`.\n")
    return "\n".join(L)


def main():
    if "--check" in sys.argv:
        sys.exit(0 if check_manifest() else 1)
    ent = write_manifest()
    with open(DOC, "w") as f:
        f.write(build_doc(ent))
    print(f"wrote {os.path.relpath(MANIFEST, ROOT)} ({len(ent)} files) and docs/DATA_FREEZE.md")


if __name__ == "__main__":
    main()
