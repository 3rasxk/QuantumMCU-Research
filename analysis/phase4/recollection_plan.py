"""Item 9: re-collection PROPOSALS (nothing is run). Every time estimate is computed from data on disk: per-point overhead = median
(build_compile_s + upload_s + boot_wait_s) of the board's ok points in the same phase, device time = reps x measured median per rep (Phase 2,
raw.csv) or reps x measured median round trip + 20 ms firmware delay (Phase 3). Reps follow the existing 2 h per-point cap unless the proposal says
the cap must be raised for that run (pc/shared/timing_model.py:404, not changed here). Writes data/derived/recollection_proposals.csv.
deadline = needed for the 20 Nov paper: it fixes a weakness the abstract claims rest on."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import p4common as C  # noqa: E402

CAP_S = 7200
COUNTER = "--ref counter --counter-port tcp:5055"
PORT = {b: f"<{b.upper()}_PORT>" for b in C.BOARDS}


def overhead(board, phase):
    tot = []
    for c in C.CIRCUITS:
        p = pd.read_csv(os.path.join(C.series_dir(phase, board, c), "points.csv"))
        p = p[p.status == "ok"]
        tot.append((p.build_compile_s + p.upload_s + p.boot_wait_s).median())
    return float(np.median(tot))


def p2_point_s(loc, board, circuit, n, reps):
    r = loc[(loc.board == board) & (loc.circuit == circuit) & (loc.n == n)].iloc[0]
    return overhead(board, 2) + reps * r.median_us / 1e6


def p3_point_s(off, board, circuit, n, reps):
    r = off[(off.board == board) & (off.circuit == circuit) & (off.n == n)].iloc[0]
    return overhead(board, 3) + reps * (r.median_us / 1e6 + 0.020)


def hours(s):
    return f"{s / 3600:.2f} h"


def build():
    loc, off = C.load_local(), C.load_offload()
    X = pd.read_csv(os.path.join(C.PROC, "offload_crossover.csv"))
    rows = []

    def add(pid, prio, why, board, phase, points, reps, secs, cmd, note=""):
        rows.append(dict(id=pid, priority=prio, weakness=why, board=board, phase=phase, points=points, reps=reps, est_seconds=secs,
                         est_time=hours(secs), commands=cmd, note=note))

    # R1: ESP8266 grover Phase 2 under ONE committed firmware (hash classes X, B vs A): n = 2..10, reps as capped by 2 h
    reps = {n: min(100, int(CAP_S // (loc[(loc.board == "esp8266") & (loc.circuit == "grover") & (loc.n == n)].median_us.iloc[0] / 1e6))) for n in range(2, 11)}
    secs = sum(p2_point_s(loc, "esp8266", "grover", n, r) for n, r in reps.items())
    add("R1", "deadline", "ESP8266 grover n=8, 9, 10 ran under uncommitted firmware (classes X, B) while n=2-7 ran under the committed one",
        "esp8266", 2, "grover n=2..10", ";".join(f"n={n}:{r}" for n, r in reps.items()), secs,
        f".venv/bin/python pc/run.py --board esp8266 --algorithm grover --phase 2 --port {PORT['esp8266']} --fresh {COUNTER}",
        "commit the firmware first; --fresh moves the existing files aside (never deletes); n=10 stays weak (4 reps) under the 2 h cap")
    # R2: Phase 3 repeat of the series that contain a crossover. pc/run.py --fresh moves the WHOLE (board, circuit, phase) series aside (never
    # deletes) and resume skips done n, so a single n cannot be repeated without code changes: the whole series is re-run.
    for r in X[X.first_n_offload_faster.notna() & X.n_star_interpolated.notna() & (X.circuit != "grover")].itertuples():
        ns = sorted(off[(off.board == r.board) & (off.circuit == r.circuit)].n)
        secs = sum(p3_point_s(off, r.board, r.circuit, n, 100) for n in ns)
        add("R2", "deadline", "every crossover n* rests on ONE Phase 3 session per point and Phase 3 round trips have IQR/median > 20 % in most points",
            r.board, 3, f"{r.circuit} n={ns[0]}..{ns[-1]} (whole series; the crossover is at n*={r.n_star_interpolated:.2f})", "100", secs,
            f".venv/bin/python pc/run.py --board {r.board} --algorithm {r.circuit} --phase 3 --port {PORT[r.board]} --fresh {COUNTER}",
            "second session of the series; the first is moved aside by --fresh, then compare the two medians per n")
    # R3: ESP8266 grover with the cap raised: n=9 100 reps, n=10 30 reps
    reps3 = dict(reps)
    reps3[9], reps3[10] = 100, 30
    s = sum(p2_point_s(loc, "esp8266", "grover", n, r) for n, r in reps3.items())
    add("R3", "nice-to-have", "ESP8266 grover n=10 has 4 reps and n=9 37 (n=10 weak)", "esp8266", 2, "grover n=2..10 (R1 with more reps)",
        ";".join(f"n={n}:{r}" for n, r in reps3.items()), s,
        f".venv/bin/python pc/run.py --board esp8266 --algorithm grover --phase 2 --port {PORT['esp8266']} --fresh {COUNTER}",
        "same command as R1 but POINT_TIME_CAP_S raised above 7200 s for this run (pc/shared/timing_model.py:404; a code change in pc/, not made here); replaces R1")
    # R4: ESP32 grover Phase 2 series: n=11 at 30 reps, n=12 1 rep, counter checked (also gives usable counter values for n=10, 12)
    reps4 = {n: 100 for n in range(2, 11)}
    reps4[11], reps4[12] = 30, 1
    s = sum(p2_point_s(loc, "esp32", "grover", n, r) for n, r in reps4.items())
    add("R4", "nice-to-have", "ESP32 grover n=11 has 13 reps and n=12 one (weak); no usable counter value at n=10 and n=12", "esp32", 2,
        "grover n=2..12 (whole series)", ";".join(f"n={n}:{r}" for n, r in reps4.items()), s,
        f".venv/bin/python pc/run.py --board esp32 --algorithm grover --phase 2 --port {PORT['esp32']} --fresh {COUNTER}",
        f"POINT_TIME_CAP_S raised for this run; check the counter WiFi link first; n=12 at 30 reps would need {hours(p2_point_s(loc, 'esp32', 'grover', 12, 30))} (not proposed)")
    # R5: Phase 3 grover series on the ESP boards with 30 requests at n=12
    for b in ("esp8266", "esp32"):
        ns = sorted(off[(off.board == b) & (off.circuit == "grover")].n)
        rq = {n: (30 if n == 12 else int(off[(off.board == b) & (off.circuit == "grover") & (off.n == n)].reps.iloc[0])) for n in ns}
        s = sum(p3_point_s(off, b, "grover", n, r) for n, r in rq.items())
        add("R5", "nice-to-have", "Phase 3 grover n=12 has 9 requests (weak) on the ESP boards", b, 3, f"grover n={ns[0]}..{ns[-1]} (whole series)",
            f"n=12:30, other n as now", s,
            f".venv/bin/python pc/run.py --board {b} --algorithm grover --phase 3 --port {PORT[b]} --fresh {COUNTER}",
            "POINT_TIME_CAP_S raised for this run; the PC simulation dominates and is identical for every board")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(ROOT, "data", "derived", "recollection_proposals.csv"), index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 220, "display.max_colwidth", 70, "display.max_columns", 20)
    d = build()
    print(d[["id", "priority", "board", "phase", "points", "reps", "est_time"]].to_string())
