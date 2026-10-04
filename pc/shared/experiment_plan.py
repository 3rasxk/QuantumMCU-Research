# experiment_plan.py -- the restarted experiment's plan as data (2026-10-03).
#
# Scope: circuits h_all, bell_ghz, qft, grover; boards uno, esp8266, esp32;
# phases 2 and 3. Pure data + pure functions, no I/O, no hardware. Consumed by
# pc/shared/eta.py (run-time estimates), analysis/phase1_compare.py (which n to
# validate) and docs/experiment_plan.md.
#
# Nothing here changes what a sweep script collects: the sweeps still climb n
# from --n-start until their own wall logic stops them (pc/shared/resume.py).
# This module only PREDICTS where that stops, for planning and ETA display.

from shared.circuit_ids import EXPERIMENT_CIRCUITS

BOARDS = ("uno", "esp8266", "esp32")
PHASES = (2, 3)

# Minimum meaningful n per circuit -- same table as pc/run.py MIN_VALID_N
# (kept in sync by pc/shared/eta_test.py).
MIN_N = {"h_all": 1, "bell_ghz": 2, "qft": 1, "grover": 2}

# Predicted memory wall per board: the first n that is expected to FAIL (and
# is still attempted, because the failure itself is the evidence).
#   uno:     state is a static array, 8 * 2^n B vs 2048 B RAM -> the linker
#            overflows at n=8 (firmware/uno/src/main.cpp:30).
#   esp8266: malloc'ed state (firmware/esp8266/src/main.cpp:67), 64 KiB at n=13
#            cannot fit in 81 920 - 29 200 B static = 52 720 B (arithmetic, no measurement).
#   esp32:   malloc'ed (firmware/esp32/src/main.cpp:65), 128 KiB at n=14; prediction rests on a
#            ~110 KB largest free block seen in retired data (docs/experiment_plan.md,
#            'Prior observations'); the new run records its own.
# All three are re-verified only when the restarted run reaches them.
# docs/experiment_plan.md has the full derivation (UNVERIFIED values marked).
WALL_PREDICTION = {
    "uno": {"wall_n": 8, "evidence": "build_overflow"},
    "esp8266": {"wall_n": 13, "evidence": "malloc_failed"},
    "esp32": {"wall_n": 14, "evidence": "malloc_failed"},
}

# Phase 3 offloads the state to the PC, so no board memory wall applies; the
# plan keeps the same n range as Phase 2 (so the two phases compare at equal
# n, as docs/run/phase3.md already did) and caps grover by PC-side Aer cost.
PHASE3_GROVER_N_MAX = 10

# A point is FLAGGED time-limited above this device time. This is a display
# threshold only, NOT a ceiling: nothing is skipped. The ceiling is an owner
# decision (docs/experiment_plan.md, "Time ceiling").
TIME_FLAG_S = 3600.0


def wall_n(board):
    return WALL_PREDICTION[board]["wall_n"]


def wall_evidence(board):
    return WALL_PREDICTION[board]["evidence"]


def plan_n_values(board, circuit, phase):
    """n values the plan expects to be attempted, in order. For Phase 2 this
    includes the predicted wall point (attempted as evidence)."""
    lo = MIN_N[circuit]
    hi = wall_n(board)
    if phase == 3 and circuit == "grover":
        hi = min(hi, PHASE3_GROVER_N_MAX)
    return list(range(lo, hi + 1))


def is_wall_point(board, circuit, n, phase):
    """True for the one Phase 2 point where a wall is predicted."""
    return phase == 2 and n == wall_n(board)


def all_rows():
    """Every (board, circuit, phase) row of the plan, in table order."""
    return [(b, c, p) for p in PHASES for b in BOARDS for c in EXPERIMENT_CIRCUITS]


def phase1_n_values(circuit):
    """Union of n over every board and phase: what Phase 1 (C++ vs Qiskit)
    must validate for this circuit."""
    ns = set()
    for b in BOARDS:
        for p in PHASES:
            ns.update(plan_n_values(b, circuit, p))
    return sorted(ns)
