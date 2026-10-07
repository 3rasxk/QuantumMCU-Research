#!/usr/bin/env python3
# rejoin.py -- redo the micros-vs-counter comparison of a finished Phase 3 --ref counter run from the files it left:
# ref/ref_pulses.csv (every pulse the counter reported) and raw.csv (the board's e2e_latency_us). Uses the current join
# (counter/crosscheck.py, width alignment). Only the derived ref_compare.csv / ref_compare_points.csv are rewritten; the old
# ones are kept as *.pre-rejoin (an earlier *.pre-rejoin is not overwritten). raw.csv, ref_pulses.csv and ref_points.csv are not touched.
#   .venv/bin/python pc/counter/rejoin.py --board esp8266 --circuit grover
import argparse
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import crosscheck as cc  # noqa: E402
from shared import paths as sp  # noqa: E402


def rejoin(board, circuit, ref_dir=None, raw_csv=None, out=print):
    ref_dir = Path(ref_dir) if ref_dir else sp.ref_dir(board, circuit, phase=3)
    raw_csv = Path(raw_csv) if raw_csv else sp.raw_csv_path(board, circuit, phase=3, ref=True)
    pulses, raw = {}, {}
    with open(ref_dir / "ref_pulses.csv", newline="") as f:
        for r in csv.DictReader(f):
            pulses.setdefault(int(r["n"]), set()).add((int(r["seq"]), int(r["rise_us"]), int(r["width_ticks"]),
                                                       round(float(r["width_us"]) * 1000), int(r["wraps"]), int(r["flags"])))
    for line in raw_csv.read_text().splitlines()[1:]:
        p = line.split(",")
        raw.setdefault(int(p[2]), []).append(float(p[5]))
    for name in ("ref_compare.csv", "ref_compare_points.csv"):
        src = ref_dir / name
        if src.exists():
            bak = ref_dir / (name + ".pre-rejoin")
            if bak.exists():
                src.unlink()
            else:
                shutil.move(src, bak)
    results = {}
    for n in sorted(set(pulses) & set(raw)):
        res = cc.join_point(sorted(pulses[n]), raw[n], len(raw[n]), board, align_widths=True)
        ok = res["status"] == "joined"
        cc.write_compare(ref_dir, "", board, circuit, n, res, ("ok" if not res["notes"].startswith("partial") else "anomaly") if ok else res["status"])
        s = res["summary"]
        out(f"n={n:2d} pulses={len(pulses[n]):4d} {res['status']:24s} pairs={s.get('n_pairs')} "
            f"median diff {s.get('median_diff_us', float('nan')):+.1f} us ({s.get('median_diff_pct', float('nan')):+.4f} %) {res['notes'][:60]}")
        results[n] = res
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--circuit", required=True)
    a = ap.parse_args()
    rejoin(a.board, a.circuit)
