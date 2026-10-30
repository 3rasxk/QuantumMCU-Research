"""Item 1: summary of data/derived/grover_diagnosis.csv -> data/derived/grover_findings.csv (one row per n) with the mechanism check.

Mechanism: qsim_h multiplies both amplitudes of a pair by the float32 constant c = float32(1/sqrt 2) = 0.70710677 (relative error -1.7e-8), so
one H gate multiplies the norm^2 of the whole state by 2 c^2 = 1 - 3.4e-8 (a bias, not noise). After N_H H gates: norm^2 = (2 c^2)^N_H.
Grover at n has N_H gates (gatecount.counts), so the float32 state keeps its direction but loses norm. The constant alone predicts about 1.16 times
the measured log norm loss for n >= 8 (it over-predicts; some other float32 effect, not analysed, partly compensates); Phase 1 reports 1 - |<a|b>|^2 WITHOUT
renormalising and P(marked) = |psi[-1]|^2 raw, so both inherit the norm loss.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
C32 = float(np.float32(0.70710678118654752))
THRESHOLD = 1e-3


def build():
    d = pd.read_csv(os.path.join(ROOT, "data", "derived", "grover_diagnosis.csv"))
    d["predicted_norm2_from_H_constant"] = (2 * C32 * C32) ** d.n_H
    d["f32_norm2_over_predicted"] = d.f32_norm2 / d.predicted_norm2_from_H_constant
    with np.errstate(divide="ignore", invalid="ignore"):
        d["f32_predicted_over_measured_log_loss"] = np.log(d.predicted_norm2_from_H_constant) / np.log(d.f32_norm2)   # > 1: the constant alone predicts MORE loss than measured
    d["f32_direction_infidelity"] = d.f32_infid_vs_ideal_normalised
    d["f32_raw_passes_1e-3"] = d.f32_infid_vs_ideal_raw <= THRESHOLD
    d["f32_direction_passes_1e-3"] = d.f32_direction_infidelity <= THRESHOLD
    d["f32_p_marked_raw_over_theory"] = d.f32_p_marked_raw / d.p_theory_firmware_k
    return d


def main():
    d = build()
    d.to_csv(os.path.join(ROOT, "data", "derived", "grover_findings.csv"), index=False)
    return d


if __name__ == "__main__":
    pd.set_option("display.width", 220, "display.max_columns", 30)
    d = main()
    print(d[["n", "k_firmware_float32", "p_theory_firmware_k", "n_H", "f32_norm2", "predicted_norm2_from_H_constant", "f32_norm2_over_predicted",
             "f32_infid_vs_ideal_raw", "f32_direction_infidelity", "f64_infid_vs_ideal_raw"]].to_string())
