#!/usr/bin/env python3
"""Checks for config/sweep_ranges.toml and its consumers. No hardware; reads data/raw (read-only) for the coverage checks.
Run:  .venv/bin/python pc/shared/sweep_ranges_test.py"""
import csv
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
import shared.test_ledger  # noqa: E402,F401  (ledger redirected to a temp file before anything imports run_history)
from shared import sweep_ranges as sr  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import experiment_plan as plan  # noqa: E402
from shared import paths as sp  # noqa: E402
from shared.circuit_ids import EXPERIMENT_CIRCUITS  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def ok_n(board, circuit, phase):
    path = sp.memory_wall_csv_path(board, circuit, ref=True) if phase == 2 else sp.session_log_csv_path(board, circuit, ref=True)
    with open(path, newline="", encoding="utf-8") as f:
        return sorted(int(r["n"]) for r in csv.DictReader(f) if r["status"] == "ok")


def wall_rows(board, circuit):
    with open(sp.memory_wall_csv_path(board, circuit, ref=True), newline="", encoding="utf-8") as f:
        return [int(r["n"]) for r in csv.DictReader(f) if r["status"] in ("build_overflow", "malloc_failed")]


def test_config_rules():
    check("config validates (no rule violation)", sr.validate() == [], str(sr.validate()))
    for b in sr.BOARDS:
        for c in EXPERIMENT_CIRCUITS:
            lo2, hi2 = sr.n_range(b, c, 2)
            lo3, hi3 = sr.n_range(b, c, 3)
            if not (lo2 == sr.circuit_min_n(c) and hi2 == sr.wall_n(b) and lo3 == lo2):
                check(f"{b}/{c}: phase 2 = min n .. wall n, phase 3 starts at the same n", False, f"{(lo2, hi2)} {(lo3, hi3)}")
                continue
            lim = sr.phase3_circuit_limit(c)
            want = min(sr.wall_n(b) + sr.meta("offload_beyond_wall"), lim if lim is not None else 10 ** 6,
                       sr.meta("pc_safety_cap_n"), sr.meta("protocol_n_max"))
            check(f"{b}/{c}: phase 3 = min n .. min(wall + {sr.meta('offload_beyond_wall')}, circuit limit, caps)", hi3 == want, f"phase 3 {(lo3, hi3)}")
    check("reps and statistic are single values shared by both phases", sr.reps() == tm.REPS == 100 and sr.meta("statistic") == "median")
    check("point time cap in config equals timing_model.POINT_TIME_CAP_S", sr.meta("point_time_cap_s") == tm.POINT_TIME_CAP_S)
    check("circuits in config are exactly the four plan circuits", set(sr.load()["circuit_min_n"]) == set(EXPERIMENT_CIRCUITS))


def test_phase3_covers_phase2_data():
    """the check the audit asked for: fails if Phase 3 planned n do not cover every Phase 2 ok n of any board x circuit"""
    for b in sr.BOARDS:
        for c in EXPERIMENT_CIRCUITS:
            p2 = ok_n(b, c, 2)
            gaps = sr.phase3_gaps(b, c, p2)
            check(f"{b}/{c}: Phase 3 plan covers all {len(p2)} Phase 2 ok n ({p2[0]}..{p2[-1]})", gaps == [], f"gaps {gaps}")
            walls = wall_rows(b, c)
            if walls:
                check(f"{b}/{c}: config wall n {sr.wall_n(b)} equals the observed wall n {min(walls)}", min(walls) == sr.wall_n(b))
                check(f"{b}/{c}: Phase 3 plan reaches wall + {sr.meta('offload_beyond_wall')} or its documented circuit limit",
                      sr.n_range(b, c, 3)[1] >= min(sr.wall_n(b) + sr.meta("offload_beyond_wall"), sr.phase3_circuit_limit(c) or 10 ** 6))
    # the checker itself must be able to fail
    hi3 = sr.n_range("uno", "h_all", 3)[1]   # fake Phase 2 data two n beyond the plan must show exactly those two n as gaps
    gaps = sr.phase3_gaps("uno", "h_all", list(range(1, hi3 + 3)))
    check("negative control: a Phase 3 plan that stops early is reported as a gap", gaps == [hi3 + 1, hi3 + 2], str(gaps))


def test_real_limit_is_evidenced():
    lim = sr.phase3_circuit_limit("grover")
    check("grover Phase 3 limit: n_max fits one request in the 2 h cap, n_max + 1 does not (timing model)",
          tm.max_reps_under_cap(tm.phase3_rep_time_s("grover", lim)) >= 1 and tm.max_reps_under_cap(tm.phase3_rep_time_s("grover", lim + 1)) == 0,
          f"n_max={lim}")


def test_consumers_read_the_config():
    run_py = (REPO_ROOT / "pc" / "run.py").read_text()
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_mod", REPO_ROOT / "pc" / "run.py")
    run_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_mod)
    check("run.py MIN_VALID_N and experiment_plan.MIN_N come from the config", run_mod.MIN_VALID_N == plan.MIN_N == {c: sr.circuit_min_n(c) for c in EXPERIMENT_CIRCUITS})
    check("run.py default_n_max == config for every (phase, board, circuit)",
          all(run_mod.default_n_max(ph, b, c) == sr.n_range(b, c, ph)[1] for ph in (2, 3) for b in sr.BOARDS for c in EXPERIMENT_CIRCUITS))
    check("experiment_plan.plan_n_values == config planned_n",
          all(plan.plan_n_values(b, c, ph) == sr.planned_n(b, c, ph) for ph in (2, 3) for b in sr.BOARDS for c in EXPERIMENT_CIRCUITS))
    for f, ph in [("phase2_sweep/uno_sweep.py", 2), ("phase2_sweep/esp8266_sweep.py", 2), ("phase2_sweep/esp32_sweep.py", 2), ("phase3_offload/sweep.py", 3)]:
        src = (REPO_ROOT / "pc" / f).read_text()
        check(f"pc/{f}: --n-start and --n-max default to None (config decides) and n values come from sweep_ranges",
              bool(re.search(r'"--n-start", type=int, default=None', src)) and bool(re.search(r'"--n-max", type=int, default=None', src))
              and f"sweep_ranges.n_values(" in src and "n_values_for_sweep(" not in src.replace("import n_values_for_sweep", ""))
    p3 = (REPO_ROOT / "pc" / "phase3_offload" / "sweep.py").read_text()
    check("phase 3 sweep default bauds come from the config", "default=sweep_ranges.baud_rates()" in p3)
    with open(sr.CONFIG_PATH, "rb") as f:
        check("config file parses as TOML", "meta" in tomllib.load(f))


def main():
    test_config_rules()
    test_phase3_covers_phase2_data()
    test_real_limit_is_evidenced()
    test_consumers_read_the_config()
    n_fail = sum(1 for r in RESULTS if not r)
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
