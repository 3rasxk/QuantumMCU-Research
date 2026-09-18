CIRCUIT_IDS = {
    "h_all": 0,
    "bell_ghz": 1,
    "qft": 2,
    "grover": 3,
    "qpe": 4,
    "steane_encode": 5,
}
CIRCUIT_NAMES = {v: k for k, v in CIRCUIT_IDS.items()}

# steane_encode is fixed at exactly 7 physical qubits (Steane [[7,1,3]] code) — it does
# not scale with n. Every sweep/plot script must special-case this circuit instead of
# looping n the way it does for the other five.
FIXED_N_CIRCUITS = {"steane_encode": 7}


def n_values_for_sweep(circuit, n_start, n_max):
    """n values a Phase 2/3 sweep should actually test for this circuit.

    Fixed-n circuits (steane_encode) ignore n_start/n_max except to decide whether
    their one valid n falls inside the requested range at all — if it doesn't, the
    caller gets an empty list (skip this circuit) instead of silently testing the
    wrong n or crashing on a range() that assumes every circuit scales with n."""
    fixed = FIXED_N_CIRCUITS.get(circuit)
    if fixed is not None:
        return [fixed] if n_start <= fixed <= n_max else []
    return list(range(n_start, n_max + 1))
