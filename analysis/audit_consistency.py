"""Consistency audit helpers (read-only): per-point statistics and outliers for Phase 2 and Phase 3, Phase 3 reference-counter status.
Writes data/derived/phase2_phase3_point_stats.csv (every ok point) and prints the flagged ones."""
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "data", "raw")
BOARDS = ["uno", "esp8266", "esp32"]
CIRCUITS = ["h_all", "bell_ghz", "qft", "grover"]
IQR_FLAG = 0.20


def stats(x):
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return med, q1, q3, ((q3 - q1) / med if med else np.nan)


rows = []
for b in BOARDS:
    for c in CIRCUITS:
        base = lambda ph: os.path.join(RAW, f"phase{ph}", b, c, "with_ref")
        r2 = pd.read_csv(f"{base(2)}/raw.csv")
        ok2 = set(pd.read_csv(f"{base(2)}/memory_wall.csv").query("status == 'ok'").n)
        for n, g in r2[r2.n.isin(ok2)].groupby("n"):
            med, q1, q3, rel = stats(g.exec_time_us.to_numpy(float))
            rows.append(dict(phase=2, board=b, circuit=c, n=n, reps=len(g), median_us=med, q1_us=q1, q3_us=q3,
                             iqr_over_median=rel, crc_error=0, timed_out=0, unit="exec_time_us"))
        r3 = pd.read_csv(f"{base(3)}/raw.csv")
        ok3 = set(pd.read_csv(f"{base(3)}/session_log.csv").query("status == 'ok'").n)
        for n, g in r3[r3.n.isin(ok3)].groupby("n"):
            med, q1, q3, rel = stats(g.e2e_latency_us.to_numpy(float))
            rows.append(dict(phase=3, board=b, circuit=c, n=n, reps=len(g), median_us=med, q1_us=q1, q3_us=q3,
                             iqr_over_median=rel, crc_error=int(g.crc_error.sum()), timed_out=int(g.timed_out.sum()),
                             unit="e2e_latency_us"))
df = pd.DataFrame(rows)
df["flag_iqr_gt_20pct"] = df.iqr_over_median > IQR_FLAG
df["flag_err"] = (df.crc_error > 0) | (df.timed_out > 0)
df["flag_median_below_20us"] = (df.phase == 2) & (df.median_us < 20)
out = os.path.join(ROOT, "data", "derived", "phase2_phase3_point_stats.csv")
df.to_csv(out, index=False)
pd.set_option("display.width", 220, "display.max_columns", 30)
print("points:", df.groupby("phase").size().to_dict())
print("IQR/median > 20%:", df.groupby("phase").flag_iqr_gt_20pct.sum().to_dict(), "| crc/timeouts > 0:", int(df.flag_err.sum()))
print(df[df.flag_iqr_gt_20pct][["phase", "board", "circuit", "n", "reps", "median_us", "iqr_over_median", "flag_median_below_20us"]].round(3).to_string())
print("\nP3 reps<100:"); print(df[(df.phase == 3) & (df.reps < 100)][["board", "circuit", "n", "reps", "median_us", "iqr_over_median"]].round(3).to_string())
print("\nP3 median IQR/median by board:", df[df.phase == 3].groupby("board").iqr_over_median.max().round(3).to_dict())
