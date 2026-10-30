#!/usr/bin/env python3
# phase2_gate_cost_fit.py
# Fit the per-gate-type cost of the analytical time model from the Phase 2 (on-device) data:
#
#   model A (the timing_model.py form):
#     exec_time_us = (n_H * k_H + n_CNOT * k_CNOT + n_CPHASE * k_CPHASE) * 2^n
#   model B (A + a fixed cost per gate call, independent of n: loop set-up, function call, trig):
#     exec_time_us = (n_H * k_H + n_CNOT * k_CNOT + n_CPHASE * k_CPHASE) * 2^n + (n_H + n_CNOT + n_CPHASE) * a
#
# k_* = microseconds per gate per amplitude (pc/shared/timing_model.py: gate_counts and
# BOARD_GATE_COST use the same definition as model A, so its result can replace the prior constants).
#
# Method
#   * training circuits: h_all, bell_ghz, qft. grover is NOT used for the fit, so it is a genuine
#     out-of-sample test of the model (its gate mix is mostly mc-phase = H + CNOT + CPHASE).
#   * only points whose median is >= MIN_MEDIAN_US are used (micros() has 1 us resolution on the ESP
#     boards and 4 us on the Uno, so below ~100 us the quantisation alone is above 1 %).
#   * non-negative least squares on the RELATIVE error (each row divided by the measured median),
#     so a 10^8 us point does not outweigh a 10^2 us point.
#   * 95 % interval: bootstrap over the reps of every point (BOOTSTRAP draws, fixed seed).
#
# Output: data/processed/gate_cost_fit.csv, data/processed/gate_cost_validation.csv
# (read-only on data/raw; never touches the timing model, the owner decides whether to adopt it).

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "pc" / "shared"))
import timing_model as tm  # noqa: E402

BOARDS = ("uno", "esp8266", "esp32")
TRAIN_CIRCUITS = ("h_all", "bell_ghz", "qft")
ALL_CIRCUITS = TRAIN_CIRCUITS + ("grover",)
MIN_MEDIAN_US = 100.0
BOOTSTRAP = 500
SEED = 20261010
OUT_DIR = REPO_ROOT / "data" / "processed"


def load_reps(board):
    """{(circuit, n): np.array of exec_time_us} from the with_ref Phase 2 raw.csv."""
    out = {}
    for circuit in ALL_CIRCUITS:
        df = pd.read_csv(REPO_ROOT / "data" / "raw" / "phase2" / board / circuit / "with_ref" / "raw.csv")
        for n, g in df.groupby("n"):
            out[(circuit, int(n))] = g["exec_time_us"].to_numpy(dtype=float)
    return out


def design_row(circuit, n, model):
    """model A: (n_H, n_CNOT, n_CPHASE) * 2^n; model B appends the total gate count."""
    counts = np.array(tm.gate_counts(circuit, n), dtype=float)
    row = counts * (1 << n)
    return row if model == "A" else np.append(row, counts.sum())


def fit(points, model):
    """points: list of (circuit, n, median_us). Relative-error NNLS -> (k_H, k_CNOT, k_CPHASE[, a])."""
    a = np.array([design_row(c, n, model) / t for c, n, t in points])
    k, _ = nnls(a, np.ones(len(points)))
    return k


PARAMS = {"A": ("k_H_us", "k_CNOT_us", "k_CPHASE_us"),
          "B": ("k_H_us", "k_CNOT_us", "k_CPHASE_us", "a_per_gate_us")}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    fit_rows, val_rows = [], []
    for board in BOARDS:
        reps = load_reps(board)
        med = {key: float(np.median(v)) for key, v in reps.items()}
        train_keys = sorted(k for k in med if k[0] in TRAIN_CIRCUITS and med[k] >= MIN_MEDIAN_US)
        boot_meds = [{key: float(np.median(rng.choice(reps[key], size=len(reps[key]), replace=True)))
                      for key in train_keys} for _ in range(BOOTSTRAP)]
        for model in ("A", "B"):
            k = fit([(c, n, med[(c, n)]) for c, n in train_keys], model)
            boots = np.array([fit([(c, n, bm[(c, n)]) for c, n in train_keys], model) for bm in boot_meds])
            lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
            errs = {"train": [], "grover": []}
            for (circuit, n), t in sorted(med.items()):
                pred = float(design_row(circuit, n, model) @ k)
                err = 100.0 * (pred - t) / t
                in_train = (circuit, n) in train_keys
                usable = t >= MIN_MEDIAN_US
                val_rows.append(dict(model=model, board=board, circuit=circuit, n=n,
                                     n_reps=len(reps[(circuit, n)]), measured_median_us=t,
                                     predicted_us=pred, error_pct=err, in_fit=in_train,
                                     above_min_median=usable))
                if in_train:
                    errs["train"].append(abs(err))
                elif circuit == "grover" and usable:
                    errs["grover"].append(abs(err))
            prior = tm.BOARD_GATE_COST[board]
            for i, name in enumerate(PARAMS[model]):
                fit_rows.append(dict(model=model, board=board, parameter=name, value_us=k[i],
                                     ci95_low_us=lo[i], ci95_high_us=hi[i],
                                     prior_estimate_us=prior[i] if i < 3 else np.nan,
                                     ratio_fit_over_prior=k[i] / prior[i] if i < 3 else np.nan))
            fit_rows.append(dict(model=model, board=board, parameter="fit_quality",
                                 n_points_fit=len(train_keys),
                                 mape_train_pct=float(np.mean(errs["train"])),
                                 max_abs_err_train_pct=float(np.max(errs["train"])),
                                 n_points_grover=len(errs["grover"]),
                                 mape_grover_oos_pct=float(np.mean(errs["grover"])),
                                 max_abs_err_grover_oos_pct=float(np.max(errs["grover"]))))

    fit_df = pd.DataFrame(fit_rows)
    val_df = pd.DataFrame(val_rows)
    fit_df.to_csv(OUT_DIR / "gate_cost_fit.csv", index=False)
    val_df.to_csv(OUT_DIR / "gate_cost_validation.csv", index=False)

    pd.set_option("display.width", 220)
    print(f"NNLS on relative error, training circuits {TRAIN_CIRCUITS}, medians >= {MIN_MEDIAN_US:g} us, "
          f"{BOOTSTRAP} bootstrap draws over reps (the CI covers rep-to-rep noise only, NOT model error)\n")
    print(fit_df[fit_df.parameter != "fit_quality"].dropna(axis=1, how="all").round(5).to_string(index=False))
    print()
    print(fit_df[fit_df.parameter == "fit_quality"].dropna(axis=1, how="all").drop(columns="parameter")
          .round(1).to_string(index=False))
    print(f"\nwritten: {OUT_DIR / 'gate_cost_fit.csv'}, {OUT_DIR / 'gate_cost_validation.csv'}")


if __name__ == "__main__":
    main()
