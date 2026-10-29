# sweep_ranges.py -- loader for config/sweep_ranges.toml, the single source of truth for the n range of every
# (board, circuit, phase). Pure functions plus one file read; no hardware, no network.
#
# Used by the four sweep scripts (default --n-start/--n-max), pc/run.py (preflight and --dry-run), pc/shared/experiment_plan.py
# (ETA / plan tables) and pc/plan_collection.py. The rules the numbers follow are written at the top of the TOML and checked in
# pc/shared/sweep_ranges_test.py.

import functools
import tomllib
from pathlib import Path

from shared.circuit_ids import EXPERIMENT_CIRCUITS

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sweep_ranges.toml"
BOARDS = ("uno", "esp8266", "esp32")
PHASES = (2, 3)


@functools.lru_cache(maxsize=None)
def load(path=None):
    with open(path or CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def meta(key, path=None):
    return load(path)["meta"][key]


def reps(path=None):
    return meta("reps", path)


def baud_rates(path=None):
    return list(meta("baud_rates", path))


def circuit_min_n(circuit, path=None):
    return load(path)["circuit_min_n"][circuit]


def wall_n(board, path=None):
    return load(path)["wall"][board]["n"]


def wall_evidence(board, path=None):
    return load(path)["wall"][board]["evidence"]


def phase3_circuit_limit(circuit, path=None):
    """largest n the PC time / memory budget allows for this circuit in Phase 3, or None (only the safety cap applies)"""
    lim = load(path).get("phase3_limit", {}).get(circuit)
    return None if lim is None else lim["n_max"]


def n_range(board, circuit, phase, path=None):
    """(first n, last n) of the plan for this (board, circuit, phase)"""
    lo = circuit_min_n(circuit, path)
    wall = wall_n(board, path)
    if phase == 2:
        return lo, wall
    hi = wall + meta("offload_beyond_wall", path)
    lim = phase3_circuit_limit(circuit, path)
    if lim is not None:
        hi = min(hi, lim)
    return lo, min(hi, meta("pc_safety_cap_n", path), meta("protocol_n_max", path))


def planned_n(board, circuit, phase, path=None):
    lo, hi = n_range(board, circuit, phase, path)
    return list(range(lo, hi + 1))


def n_values(board, circuit, phase, n_start=None, n_max=None, path=None):
    """n values a sweep tests: the config range, where an explicit operator --n-start / --n-max (None = not given) replaces that
    bound as given. The operator may deliberately probe past a limit (e.g. --force-infeasible), as with the old fixed defaults."""
    lo, hi = n_range(board, circuit, phase, path)
    return list(range(n_start if n_start is not None else lo, (n_max if n_max is not None else hi) + 1))


def phase3_gaps(board, circuit, phase2_ok_n, path=None):
    """n values at which Phase 2 has ok data but the Phase 3 plan does not run (must be empty: a crossover needs both phases at the
    same n)"""
    planned = set(planned_n(board, circuit, 3, path))
    return sorted(n for n in phase2_ok_n if n not in planned)


def validate(path=None):
    """list of rule violations in the config itself (empty = consistent)"""
    problems = []
    cfg = load(path)
    for c in EXPERIMENT_CIRCUITS:
        if c not in cfg["circuit_min_n"]:
            problems.append(f"circuit_min_n missing {c}")
    for b in BOARDS:
        if b not in cfg["wall"]:
            problems.append(f"wall missing {b}")
    if problems:
        return problems
    for b in BOARDS:
        for c in EXPERIMENT_CIRCUITS:
            lo2, hi2 = n_range(b, c, 2, path)
            lo3, hi3 = n_range(b, c, 3, path)
            if lo2 != lo3:
                problems.append(f"{b}/{c}: phase 2 starts at {lo2}, phase 3 at {lo3}")
            if hi3 < hi2 and phase3_circuit_limit(c, path) is None:
                problems.append(f"{b}/{c}: phase 3 ends at {hi3}, before phase 2 at {hi2}")
            if hi3 > meta("protocol_n_max", path) or hi3 > meta("pc_safety_cap_n", path):
                problems.append(f"{b}/{c}: phase 3 n {hi3} above a protocol/PC cap")
    return problems
