# Experiment plan scope: h_all, bell_ghz, qft, grover only. qpe and steane_encode
# were removed from the plan on 2026-10-03 (full restart). Their code stays in
# firmware/common/circuits.hpp (firmware source hash unchanged; circuit ids 4 and
# 5 stay reserved there) but no PC script runs, plans, or analyses them.
CIRCUIT_IDS = {
    "h_all": 0,
    "bell_ghz": 1,
    "qft": 2,
    "grover": 3,
}
CIRCUIT_NAMES = {v: k for k, v in CIRCUIT_IDS.items()}
EXPERIMENT_CIRCUITS = tuple(CIRCUIT_IDS)

REMOVED_CIRCUITS = {"qpe": 4, "steane_encode": 5}
REMOVED_DATE = "2026-10-03"


def removed_message(circuit):
    return f"{circuit} removed from the experiment plan on {REMOVED_DATE}"


def reject_removed_circuits(circuits):
    """Exit with a clear message if any requested circuit was removed from the
    plan. Shared by pc/run.py and every sweep script's --circuits."""
    for c in circuits:
        if c in REMOVED_CIRCUITS:
            raise SystemExit(f"error: {removed_message(c)}")


# No circuit in the plan is fixed-n any more (steane_encode was the only one).
FIXED_N_CIRCUITS = {}


def n_values_for_sweep(circuit, n_start, n_max):
    """n values a Phase 2/3 sweep should test for this circuit."""
    fixed = FIXED_N_CIRCUITS.get(circuit)
    if fixed is not None:
        return [fixed] if n_start <= fixed <= n_max else []
    return list(range(n_start, n_max + 1))
