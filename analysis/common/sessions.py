"""Session selection: which collection session (raw-data bucket) feeds the analysis, per board x circuit x phase x n.

Buckets under data/raw/phase<N>/<board>/<circuit>/: `with_ref` = original collection, `with_ref_<TAG>` = repeat sessions made with
`pc/run.py --rerun TAG` (a whole new sample per point, never merged). Decision of the owner, 2026-10-31 (proposal of 2026-10-31 step 6):

  Uno (all)                                   original
  ESP8266 Phase 2 h_all, bell_ghz, qft        original
  ESP8266 Phase 2 grover n=2-8                r2 (one firmware source hash 5413c474786bad15); the counter pairs of n=7 come from r2b
  ESP8266 Phase 2 grover n>=9                 original (same source hash; weak: 37 and 4 reps)
  ESP32 Phase 2, all but grover n=9-10        original
  ESP32 Phase 2 grover n=9-10                 r2 (r2b is a replicate of n=9); the counter pairs of n=9 come from r2c (r2 and r2b have none;
                                              r2c was collected after the decision, same rule as for ESP8266 n=7)
  ESP8266 Phase 3 (all circuits)              r2 (one firmware hash e33508351a496315)
  ESP32 Phase 3 (all)                         original

Scope: n >= 2; Phase 3 up to the Phase 2 memory-wall n of the board (config/sweep_ranges.toml [wall.<board>]); Phase 2 has no data at or
beyond its wall. Replaced and replicate sessions are used only for the reproducibility table (`replicates()`).
Every analysis script that needs raw data of the final dataset goes through this module (analysis/common/sessions_test.py checks it).
"""
import glob
import os
import tomllib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "data", "raw")
ORIGINAL = "with_ref"
BOARDS = ["uno", "esp8266", "esp32"]
CIRCUITS = ["h_all", "bell_ghz", "qft", "grover"]
N_MIN = 2

# (phase, board, circuit or "*") -> [(n_lo, n_hi, bucket)] in order; the first match wins; anything unmatched = original
RULES = {
    (2, "esp8266", "grover"): [(2, 8, "with_ref_r2")],
    (2, "esp32", "grover"): [(9, 10, "with_ref_r2")],
    (3, "esp8266", "*"): [(0, 10 ** 6, "with_ref_r2")],
}
# bucket whose counter pairs are used for a point when the selected bucket has none (pairs only; timer data stay in the selected bucket)
COUNTER_RULES = {
    (2, "esp8266", "grover"): [(7, 7, "with_ref_r2b")],
    (2, "esp32", "grover"): [(9, 9, "with_ref_r2c")],
}


def _match(table, phase, board, circuit, n):
    for key in ((phase, board, circuit), (phase, board, "*")):
        for lo, hi, bucket in table.get(key, []):
            if lo <= n <= hi:
                return bucket
    return None


def wall_n(board):
    cfg = tomllib.load(open(os.path.join(ROOT, "config", "sweep_ranges.toml"), "rb"))
    return int(cfg["wall"][board]["n"])


def in_scope(phase, board, circuit, n):
    """n >= 2 and, in Phase 3, n <= the board's Phase 2 wall n (Phase 2 data stop before the wall by construction)"""
    return n >= N_MIN and (phase != 3 or n <= wall_n(board))


def select_session(phase, board, circuit, n):
    """bucket name of the session whose data are the primary evidence for this point"""
    return _match(RULES, phase, board, circuit, n) or ORIGINAL


def counter_session(phase, board, circuit, n):
    """bucket name whose counter pairs are used for this point (the selected session unless COUNTER_RULES names another one)"""
    return _match(COUNTER_RULES, phase, board, circuit, n) or select_session(phase, board, circuit, n)


def bucket_dir(phase, board, circuit, bucket):
    return os.path.join(RAW, f"phase{phase}", board, circuit, bucket)


def buckets(phase, board, circuit):
    """every bucket that exists for the series: original first, then the repeat sessions in name order"""
    base = os.path.join(RAW, f"phase{phase}", board, circuit)
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(base, "with_ref*")) if os.path.isdir(p))
    return ([ORIGINAL] if ORIGINAL in names else []) + [x for x in names if x != ORIGINAL]


def selected_dirs(phase, board, circuit, counter=False):
    """{bucket: bucket_dir} of the buckets that supply at least one selected point of the series, each with the predicate of its n"""
    out = {}
    for b in buckets(phase, board, circuit):
        out[b] = bucket_dir(phase, board, circuit, b)
    return out


def is_selected(phase, board, circuit, n, bucket, counter=False):
    """True if the rows of `bucket` for this n are the selected ones (timer data by default, counter pairs with counter=True)"""
    if not in_scope(phase, board, circuit, n):
        return False
    pick = counter_session if counter else select_session
    return pick(phase, board, circuit, n) == bucket


def read_selected(phase, board, circuit, filename, counter=False):
    """DataFrame of `filename` (raw.csv, points.csv, memory_wall.csv, session_log.csv, ref/ref_compare.csv, ...) with only the rows of the selected
    session of each n; rows without an `n` column are not supported. Adds a `session` column."""
    import pandas as pd
    frames = []
    for b, d in selected_dirs(phase, board, circuit).items():
        p = os.path.join(d, filename)
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p)
        if "n" not in df.columns or not len(df):
            continue
        keep = [is_selected(phase, board, circuit, int(n), b, counter) for n in df["n"]]
        df = df[keep].copy()
        df["session"] = b
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def replicates(phase, board, circuit):
    """{n: [buckets]} of the points measured in more than one session (for the reproducibility table), n in scope only"""
    import pandas as pd
    seen = {}
    for b, d in selected_dirs(phase, board, circuit).items():
        p = os.path.join(d, "raw.csv")
        if os.path.exists(p):
            for n in sorted(set(pd.read_csv(p)["n"])):
                if in_scope(phase, board, circuit, int(n)):
                    seen.setdefault(int(n), []).append(b)
    return {n: v for n, v in seen.items() if len(v) > 1}
