#!/usr/bin/env python3
"""plan_collection.py -- dry run (no hardware, no writes): what is planned by config/sweep_ranges.toml, what data/raw already holds,
what is MISSING, how long collecting only the missing points takes, and the exact pc/run.py commands to do it.

  .venv/bin/python pc/plan_collection.py                 # full list + per-board estimate + commands
  .venv/bin/python pc/plan_collection.py --board esp32   # one board
  .venv/bin/python pc/plan_collection.py --list          # every planned (board, circuit, n, baud), done or not

A point counts as DONE when its terminal record exists (Phase 2: memory_wall.csv, Phase 3: session_log.csv) with a status the
resume logic skips: ok, a wall with positive evidence, or a skipped_* point recorded with its computed reason. Anything else is MISSING.
Collection is additive: the commands resume (skip done points) and append to the existing with_ref files; nothing is overwritten.
"""
import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import eta, sweep_ranges, timing_model as tm  # noqa: E402
from shared import paths as sp  # noqa: E402
from shared.circuit_ids import EXPERIMENT_CIRCUITS  # noqa: E402

BOARDS = sweep_ranges.BOARDS
DONE_STATUSES = {"ok", "build_overflow", "malloc_failed", "skipped_compute_infeasible", "skipped_sim_cost_infeasible"}
COUNTER_FLAGS = "--ref counter --counter-port tcp:5055"   # every existing point is in the with_ref bucket; resume never crosses buckets


def recorded_n(board, circuit, phase):
    """n values that already have a terminal record in the with_ref bucket"""
    path = (sp.memory_wall_csv_path(board, circuit, ref=True) if phase == 2
            else sp.session_log_csv_path(board, circuit, ref=True))
    if not Path(path).exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {int(r["n"]) for r in csv.DictReader(f) if r["status"] in DONE_STATUSES}


def build_plan(boards):
    rows = []
    for b in boards:
        for c in EXPERIMENT_CIRCUITS:
            for ph in (2, 3):
                done = recorded_n(b, c, ph)
                for n in sweep_ranges.planned_n(b, c, ph):
                    for baud in ([None] if ph == 2 else sweep_ranges.baud_rates()):
                        rows.append(dict(board=b, circuit=c, phase=ph, n=n, baud=baud, done=n in done))
    return rows


def contiguous(ns):
    ns = sorted(ns)
    out, s, p = [], ns[0], ns[0]
    for x in ns[1:]:
        if x != p + 1:
            out.append((s, p))
            s = x
        p = x
    out.append((s, p))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", choices=BOARDS, default=None)
    ap.add_argument("--list", action="store_true", help="print every planned point, not only the missing ones")
    args = ap.parse_args(argv)
    boards = [args.board] if args.board else list(BOARDS)
    problems = sweep_ranges.validate()
    if problems:
        print("CONFIG PROBLEMS:", *problems, sep="\n  ")
        return 2
    plan = build_plan(boards)
    miss = [r for r in plan if not r["done"]]
    print(f"config/sweep_ranges.toml: reps={sweep_ranges.reps()}, statistic={sweep_ranges.meta('statistic')}, "
          f"bauds={sweep_ranges.baud_rates()}, Phase 3 = Phase 2 wall + {sweep_ranges.meta('offload_beyond_wall')}")
    print(f"planned points: {len(plan)}   already recorded: {len(plan) - len(miss)}   MISSING: {len(miss)}\n")
    print(f"{'ph':>2} {'board':8} {'circuit':9} {'n':>3} {'baud':>7}  state")
    for r in (plan if args.list else miss):
        print(f"{r['phase']:>2} {r['board']:8} {r['circuit']:9} {r['n']:>3} {str(r['baud'] or '-'):>7}  {'done' if r['done'] else 'MISSING'}")
    # estimates and commands for the missing points only
    print("\n=== estimate for collecting ONLY the missing points (sequential, one operator; pc/shared/eta.py) ===")
    grand = 0.0
    cmds = []
    for b in boards:
        total = 0.0
        notes = []
        for c in EXPERIMENT_CIRCUITS:
            for ph in (2, 3):
                ns = [r["n"] for r in miss if r["board"] == b and r["circuit"] == c and r["phase"] == ph]
                if not ns:
                    continue
                meas = eta.load_measured(b, ph)
                for n in ns:
                    e = eta.estimate_point(b, c, n, ph, meas)
                    total += e.total_s
                    if e.reps and e.reps < tm.REPS:
                        notes.append(f"{c} phase {ph} n={n}: {e.reps}/{tm.REPS} reps under the 2 h cap")
                    if e.skipped:
                        notes.append(f"{c} phase {ph} n={n}: SKIPPED by the model (one rep > cap)")
                for lo, hi in contiguous(ns):
                    cmds.append((b, ph, c, lo, hi))
        grand += total
        print(f"  {b:8s} {tm.human_duration(total):>10s}" + ("   | " + "; ".join(notes) if notes else ""))
    print(f"  {'TOTAL':8s} {tm.human_duration(grand):>10s}   (build + upload + boot + device/PC time; does not include operator delays)\n")
    if cmds:
        print("=== commands (additive: resume skips done points, appends to the existing with_ref files; add --yes to skip the prompt) ===")
        for b, ph, c, lo, hi in cmds:
            print(f".venv/bin/python pc/run.py --board {b} --algorithm {c} --phase {ph} --port <{b.upper()}_PORT> "
                  f"--n-start {lo} --n-max {hi} {COUNTER_FLAGS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
