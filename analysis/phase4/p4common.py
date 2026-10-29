"""Shared loaders and constants for the Phase 4 analysis. Read-only on data/raw/."""
import os

import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.join(ROOT, "data", "raw")
PROC = os.path.join(ROOT, "data", "processed", "phase4")
FIG = os.path.join(ROOT, "figures", "phase4")
TAB = os.path.join(ROOT, "tables")

BOARDS = ["uno", "esp8266", "esp32"]
BOARD_LABEL = {"uno": "Uno R3", "esp8266": "ESP8266", "esp32": "ESP32"}
CIRCUITS = ["h_all", "bell_ghz", "qft", "grover"]
CIRCUIT_LABEL = {"h_all": "h_all", "bell_ghz": "bell_ghz", "qft": "qft", "grover": "grover"}

# Fixed a priori, before any test point was looked at (see docs/phase4_report.md section 4):
N_TEST = 3          # held-out points = the largest N_TEST ok n of each (board, circuit)
FLOOR_US = 100.0    # a fit point needs median >= 100 us = 25 ticks of the coarsest clock (Uno micros(), 4 us)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import weak as _weak  # noqa: E402  (analysis/common/weak.py: the one definition of a weak point)
SMALL_REPS = _weak.WEAK_MIN   # points with fewer reps / requests are weak (item 5)


def series_dir(phase, board, circuit):
    return os.path.join(RAW, f"phase{phase}", board, circuit, "with_ref")


def load_local():
    """Phase 2 per-point statistics from raw.csv (rows exist only for ok points, audit check B1b).

    Columns: board, circuit, n, reps (independent repetitions: recorded rows minus exact copies, analysis/common/weak.py), reps_recorded, median_us, q1_us, q3_us, min_us, max_us.
    """
    rows = []
    for b in BOARDS:
        for c in CIRCUITS:
            raw = pd.read_csv(os.path.join(series_dir(2, b, c), "raw.csv"))
            for n, g in raw.groupby("n"):
                xall = g["exec_time_us"].to_numpy(dtype=float)
                eff = _weak.effective_reps(xall)
                x = xall[:eff]                      # statistics over the independent repetitions only (exact copies dropped)
                rows.append(dict(board=b, circuit=c, n=int(n), reps=eff, reps_recorded=len(xall), median_us=float(np.median(x)),
                                 q1_us=float(np.percentile(x, 25)), q3_us=float(np.percentile(x, 75)),
                                 min_us=float(x.min()), max_us=float(x.max())))
    return pd.DataFrame(rows).sort_values(["board", "circuit", "n"]).reset_index(drop=True)


def load_offload():
    """Phase 3 per-point round-trip statistics (us per request), timed-out and CRC-error requests excluded."""
    rows = []
    for b in BOARDS:
        for c in CIRCUITS:
            raw = pd.read_csv(os.path.join(series_dir(3, b, c), "raw.csv"))
            n_all = raw.groupby("n").size()
            raw = raw[(raw["timed_out"] == 0) & (raw["crc_error"] == 0)]
            for n, g in raw.groupby("n"):
                x = g["e2e_latency_us"].to_numpy(dtype=float)
                rows.append(dict(board=b, circuit=c, n=int(n), baud=int(g["baud_rate"].iloc[0]), reps=_weak.effective_reps(x), reps_recorded=len(x),
                                 reqs_total=int(n_all[n]), median_us=float(np.median(x)),
                                 q1_us=float(np.percentile(x, 25)), q3_us=float(np.percentile(x, 75))))
    return pd.DataFrame(rows).sort_values(["board", "circuit", "n"]).reset_index(drop=True)


def load_walls():
    """Phase 2 memory_wall.csv rows with positive evidence (status build_overflow / malloc_failed)."""
    rows = []
    for b in BOARDS:
        for c in CIRCUITS:
            mw = pd.read_csv(os.path.join(series_dir(2, b, c), "memory_wall.csv"))
            w = mw[mw["status"].isin(["build_overflow", "malloc_failed"])]
            for _, r in w.iterrows():
                rows.append(dict(board=b, circuit=c, n=int(r["n"]), status=r["status"],
                                 theoretical_bytes=int(r["theoretical_bytes"]),
                                 compile_ram_pct=r["compile_ram_pct"],
                                 file=os.path.relpath(os.path.join(series_dir(2, b, c), "memory_wall.csv"), ROOT)))
    return pd.DataFrame(rows)
