# experiment_plan.py -- the restarted experiment's plan as data (2026-10-03).
#
# Scope: circuits h_all, bell_ghz, qft, grover; boards uno, esp8266, esp32;
# phases 2 and 3. Pure data + pure functions, no I/O, no hardware. Consumed by
# pc/shared/eta.py (run-time estimates), analysis/phase1_compare.py (which n to
# validate) and docs/design/experiment_plan.md.
#
# The n ranges are read from config/sweep_ranges.toml (pc/shared/sweep_ranges.py), the same single source the sweep scripts use for
# their default --n-start / --n-max, so this plan, the ETA tables and what a default sweep collects cannot drift apart.

from shared.circuit_ids import EXPERIMENT_CIRCUITS
from shared import sweep_ranges

BOARDS = ("uno", "esp8266", "esp32")
PHASES = (2, 3)

# Every n range below comes from config/sweep_ranges.toml through pc/shared/sweep_ranges.py (the same file the sweep scripts read).
# Minimum meaningful n per circuit -- same table as pc/run.py MIN_VALID_N (kept in sync by pc/shared/eta_test.py).
MIN_N = {c: sweep_ranges.circuit_min_n(c) for c in EXPERIMENT_CIRCUITS}

# Memory wall per board: the first n that FAILS (and is still attempted, because the failure itself is the evidence). Observed in
# data/raw/phase2 for h_all, bell_ghz, qft on every board and for all four circuits on the Uno; grover on the ESP boards never
# reached it (time-limited). Derivation: docs/design/experiment_plan.md.
WALL_PREDICTION = {b: {"wall_n": sweep_ranges.wall_n(b), "evidence": sweep_ranges.wall_evidence(b)} for b in BOARDS}

# Phase 3 offloads the state to the PC, so no board memory wall applies. The plan runs it from the same minimum n up to the Phase 2
# wall PLUS sweep_ranges.meta("offload_beyond_wall") (offload is the only option there), limited per circuit by the PC time / memory
# budget ([phase3_limit.*] in the config) -- so it always covers every n Phase 2 can have.

# A point is FLAGGED time-limited above this device time. This is a display
# threshold only, NOT a ceiling: nothing is skipped. The ceiling is an owner
# decision (docs/design/experiment_plan.md, "Time ceiling").
TIME_FLAG_S = 3600.0


def wall_n(board):
    return WALL_PREDICTION[board]["wall_n"]


def wall_evidence(board):
    return WALL_PREDICTION[board]["evidence"]


def plan_n_values(board, circuit, phase):
    """n values the plan expects to be attempted, in order. For Phase 2 this
    includes the wall point (attempted as evidence)."""
    return sweep_ranges.planned_n(board, circuit, phase)


def is_wall_point(board, circuit, n, phase):
    """True for the one Phase 2 point where a wall is predicted."""
    return phase == 2 and n == wall_n(board)


def all_rows():
    """Every (board, circuit, phase) row of the plan, in table order."""
    return [(b, c, p) for p in PHASES for b in BOARDS for c in EXPERIMENT_CIRCUITS]


def phase1_n_values(circuit):
    """Union of n over every board's Phase 2 range: what Phase 1 (C++ vs Qiskit)
    must validate for this circuit."""
    ns = set()
    for b in BOARDS:
        ns.update(plan_n_values(b, circuit, 2))   # the C++ build runs on the boards in Phase 2 only; Phase 3 uses the Qiskit side alone
    return sorted(ns)
