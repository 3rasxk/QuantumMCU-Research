#!/usr/bin/env python3
"""Draft of the paper (Markdown, IEEE conference structure) from the final Phase 4 outputs. Every number comes from a CSV in data/processed/phase4 or
data/derived (read-only); wording is hand-written. Writes docs/report/paper_draft.md.  Run: .venv/bin/python analysis/paper_draft.py
Placeholders [TODO ...] mark what only the authors can supply (references, affiliations, AI-use statement)."""
import glob
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
P = os.path.join(ROOT, "data", "processed", "phase4")
D = os.path.join(ROOT, "data", "derived")
rd = lambda d, f: pd.read_csv(os.path.join(d, f))
BL = {"uno": "Arduino Uno R3", "esp8266": "ESP8266 (NodeMCU)", "esp32": "ESP32 (DevKit)"}

mem, ts, cs, xo = rd(P, "memory_model.csv"), rd(P, "time_scores.csv"), rd(P, "counter_summary.csv"), rd(P, "offload_crossover.csv")
rng, rep, gf = rd(D, "phase3_pc_sim_range.csv"), rd(D, "reproducibility.csv"), rd(D, "grover_findings.csv")
ovl = rd(P, "offload_vs_local.csv")
cv = rd(D, "counter_validity.csv")
cv = cv[cv.selected.astype(bool)]


def fcpu(board):
    f = sorted(glob.glob(os.path.join(ROOT, "data", "raw", "phase2", board, "h_all", "with_ref", "env", "*.json")))
    f = [x for x in f if not x.endswith(".ref.json")]
    return float(json.load(open(f[0]))["f_cpu"]) / 1e6


def sc(model, board, scope="all", test="primary (non-weak)"):
    r = ts[(ts.model == model) & (ts.scope == scope) & (ts.test_set == test) & (ts.board == board)].iloc[0]
    return float(r.mape_pct), int(r.n_points)


q = mem[mem.circuit == "qft"].set_index(["board", "predictor"])
wall = {b: int(q.loc[(b, p)].wall_n) for b, p in (("uno", "static_ram"), ("esp8266", "total_free_heap"), ("esp32", "largest_block"))}
B = {"uno": q.loc[("uno", "static_ram")].B_bytes, "esp8266": q.loc[("esp8266", "total_free_heap")].B_bytes,
     "esp32_lb": q.loc[("esp32", "largest_block")].B_bytes, "esp32_free": q.loc[("esp32", "total_free_heap")].B_bytes}
pred = {"uno": int(q.loc[("uno", "static_ram")].n_max_pred), "esp8266": int(q.loc[("esp8266", "total_free_heap")].n_max_pred),
        "esp32_lb": int(q.loc[("esp32", "largest_block")].n_max_pred), "esp32_free": int(q.loc[("esp32", "total_free_heap")].n_max_pred)}
m1, m2 = sc("M1", "all")[0], sc("M2", "all")[0]
n_test = sc("M2", "all")[1]
m1b = {b: sc("M1", b)[0] for b in ("uno", "esp8266", "esp32")}
m2b = {b: sc("M2", b)[0] for b in ("uno", "esp8266", "esp32")}
cnt = cs[cs.subset == "median>=100us, not weak"].set_index("board")
fl = ovl[ovl.n <= 4].groupby("board").median_us_offload.median() / 1000
rr = rng[rng.n >= 6].assign(spread=lambda d: d.pc_sim_max_us / d.pc_sim_min_us)
g9 = rng[(rng.circuit == "grover") & (rng.n == 9)].iloc[0]
r2 = rep[rep.phase == 2]
r3 = rep[rep.phase == 3]
r3e, r3s = r3[r3.quantity == "e2e_us"], r3[r3.quantity == "pc_sim_us"]
g12 = gf[gf.n == 12].iloc[0]
g13 = gf[gf.n == 13].iloc[0]
g14 = gf[gf.n == 14].iloc[0]
dir12 = float(gf[gf.n <= 12].f32_direction_infidelity.max())
n_use = {b: int(cv[(cv.phase == 2) & (cv.board == b)].usable.sum()) for b in BL}
n_all = {b: int((cv.phase == 2).sum() * 0 + len(cv[(cv.phase == 2) & (cv.board == b)])) for b in BL}


def brk(r, bound):
    lo, hi, kind = getattr(r, f"n_{bound}_lo"), getattr(r, f"n_{bound}_hi"), getattr(r, f"{bound}_kind")
    return f"{int(lo)}-{int(hi)}" if kind == "bracket" else (f"<= {int(hi)}" if kind == "below" else f"none (n <= {int(r.n_last)})")


rows = "\n".join(f"| {BL[r.board].split(' ')[0] if r.board != 'uno' else 'Uno'} | {r.circuit} | {brk(r, 'fast')} | {brk(r, 'slow')} | "
                 f"{'; '.join(x for x in (r.fast_labels if isinstance(r.fast_labels, str) else '', r.slow_labels if isinstance(r.slow_labels, str) else '') if x) or '-'} |"
                 for r in xo.itertuples())

txt = f"""# Characterizing Statevector Quantum Circuit Simulation on Microcontrollers: Memory, Time and Offload Limits

*Draft for the KST 2027 submission. Author names, affiliations, e-mail addresses and the repository link are omitted for blind review
(the call asks to remove them). Format: IEEE conference, A4, 10 pt Times; the length limit on the submission page (4-6 pages) and on the
conference home page (8-12 pages) disagree, confirm with the organizers before cutting or expanding. Every number below is produced by
`analysis/paper_draft.py` from the committed analysis outputs; text in [TODO ...] needs the authors.*

## Abstract

We measure how far a dense statevector simulator can be pushed on three microcontrollers (Arduino Uno R3, ESP8266, ESP32) with four circuits
(h_all, bell_ghz, qft, grover), timing every run with an external pulse counter. The largest circuit that fits is set by memory for h_all,
bell_ghz and qft (walls at n = {wall['uno']}, {wall['esp8266']} and {wall['esp32']} qubits) and by time for grover on the ESP boards. A
floor(log2(B/8)) rule, with B the free memory read at n = 2, reproduces the three walls (on the ESP32 only when B is the largest free block). A
per-gate-kind timing model predicts held-out largest-n times with {m2:.0f} % mean absolute percentage error over {n_test} points against {m1:.0f} % for
one constant per board; we state that the model was not fixed blind. Offloading the simulation to a PC becomes faster than local execution between n = {int(xo.n_fast_hi.min())} and n = {int(xo.n_slow_hi.max())}
depending on board and circuit; because the PC simulation time varies about {rr.spread.median():.1f}x between sessions, we report the crossover as brackets, not as one number.

## I. Introduction

Statevector simulation needs 2^n complex amplitudes. On a microcontroller the state competes with the program and the runtime for kilobytes of RAM and
the arithmetic runs on 8-bit or soft-float cores. We ask three questions: (1) which resource ends the experiment first, memory or time; (2) can the
limit be predicted from quantities available before the run; (3) at which n does offloading the simulation to a PC over a serial link pay off. The
contribution is a measurement protocol with an independent timing reference and an analysis whose weak points, firmware versions and session
choices are stated explicitly.

[TODO related work: statevector simulators on classical hardware, embedded quantum-simulation work, timing-measurement practice on microcontrollers.
No reference is invented in this draft.]

## II. Method

**Boards and circuits.** Arduino Uno R3 ({fcpu('uno'):.0f} MHz), ESP8266 NodeMCU ({fcpu('esp8266'):.0f} MHz) and ESP32 DevKit ({fcpu('esp32'):.0f} MHz) run the same C++
statevector code (float32 complex amplitudes, `firmware/common`). Circuits: h_all, bell_ghz, qft and grover; every point is 100 repetitions where the
2 h per-point cap allows (otherwise fewer, marked weak below 30).

**Timing reference.** The board raises a pin for the duration of one run; a separate ESP32 timestamps both edges with its hardware capture unit (12.5 ns tick).
The board's own `micros()` value and the counter value are compared per repetition. A loopback self-test of the counter passed 5 of 5 scenarios; one crystal
generates and measures, so clock accuracy is not tested. Pairs are used only if they pass five validity rules (pair count, counter flags, plausibility).

**Phase 3 (offload).** The PC runs a Qiskit Aer statevector simulation per request and the board only answers the framed request over 115 200 baud. The round trip is split into wire time,
PC simulation time and a board-and-link residual.

**Sessions.** Several points were collected more than once. A single selector fixes which session is primary evidence for each point; the other sessions feed only a
reproducibility table.

## III. Results

### A. Memory

The wall (first allocation failure with positive evidence) is at n = {wall['uno']} on the Uno (SRAM, linker overflow), n = {wall['esp8266']} on the ESP8266 and n = {wall['esp32']} on the ESP32 (allocation returns NULL).
With B read at n = 2 (static RAM left on the Uno, free heap on the ESP8266, largest free block on the ESP32) the rule floor(log2(B/8)) gives n_max = {pred['uno']},
{pred['esp8266']} and {pred['esp32_lb']}, each equal to the last n that ran. On the ESP32 the total free heap ({B['esp32_free']:.0f} B) predicts n = {pred['esp32_free']}, one qubit too many; the
largest free block ({B['esp32_lb']:.0f} B) is the right quantity because the state needs one contiguous block (Fig. 3). Caveat: the test resolves B only to a factor of 2, and the Uno B comes from the same
compiler figure that triggers the overflow, so that confirmation is close to circular.

### B. Time

Fig. 1 shows the median time per run. A per-gate-kind model (M2: cost per H, CNOT and controlled-phase gate times 2^n plus a per-gate call term, fitted on small n by non-negative least squares)
reaches a held-out error of {m2:.0f} % (ESP32 {m2b['esp32']:.0f} %, ESP8266 {m2b['esp8266']:.0f} %, Uno {m2b['uno']:.0f} %; {n_test} non-weak points, the largest three n of each series held out)
against {m1:.0f} % for one constant per board (M1; ESP32 {m1b['esp32']:.0f} %, ESP8266 {m1b['esp8266']:.0f} %, Uno {m1b['uno']:.0f} %). Honest status: M2 was written down before the analysis was run
but not blind to grover errors that were already known; the weak-point rule, the firmware-class rule, the identifiability rule and the session selection were fixed after scores were seen;
the identifiability verdict of M2 changes with the held-out size; the fitted constants are fits, not measured gate costs. Every selected ESP8266 grover point
ran firmware with a timer interrupt inside the timed region, so ESP8266 grover is excluded from the fit and the clean scores.

### C. Agreement of the on-board timer with the counter

On points that pass the validity rules and have at least 30 independent repetitions, the median `micros()`/counter ratio is {cnt.loc['uno'].median_of_median_ratio:.4f} on the Uno ({int(cnt.loc['uno'].n_points)} points),
{cnt.loc['esp8266'].median_of_median_ratio:.4f} on the ESP8266 ({int(cnt.loc['esp8266'].n_points)}) and {cnt.loc['esp32'].median_of_median_ratio:.4f} on the ESP32 ({int(cnt.loc['esp32'].n_points)}); the largest compared run is
{cnt.longest_micros_us.max() / 1e6:.0f} s. Small n shows a constant offset of about 1-2 us (1 us timer resolution), visible as ratios well below 1 at n = 2 (figure
`timer_vs_counter`). The counter could not pair some long points (line noise on its input, cause not established); those points keep their `micros()` data and are listed in the report.
The counter's wrap artefact (53.687 s) is rejected by a plausibility rule that was added after the data had been seen, so agreement statistics are conditional on that coarse filter.

### D. Offload crossover

Offload is faster than local execution from a measured n that depends on board and circuit (Fig. 4, Table I). The Phase 3 floor is {fl['uno']:.1f} ms (Uno), {fl['esp8266']:.1f} ms (ESP8266)
and {fl['esp32']:.1f} ms (ESP32) at n <= 4. The simulation time on the PC differs by a median {rr.spread.median():.2f}x (at most {rr.spread.max():.2f}x) between sessions on the same PC (grover n = 9:
{g9.pc_sim_min_us / 1e6:.1f} to {g9.pc_sim_max_us / 1e6:.1f} s), while the board-and-link residual is stable; the offload latency is therefore a band between the fastest and the slowest observed simulation and the
crossover is a bracket of two measured n for each bound, never an interpolated value.

**Table I.** Crossover brackets (measured n between which offload becomes faster and stays faster; fast bound / slow bound of the PC simulation time).

| board | circuit | fast PC | slow PC | label |
|---|---|---|---|---|
{rows}

### E. Precision

On the PC, the float32 state of grover keeps its direction (normalised infidelity at most {dir12:.1e} for n <= 12) but loses norm: the raw infidelity against Aer is {g12.f32_infid_vs_ideal_raw:.3f} at n = 12 while the success probability is still {g12.f32_p_marked_raw:.2f}.
The cause is the float32 constant 1/sqrt(2), which is biased and multiplies the norm squared of the state by a constant below 1 at every H gate; the direction error also grows beyond n = 12
({g13.f32_direction_infidelity:.1e} at n = 13, {g14.f32_direction_infidelity:.1e} at n = 14). The statement that the constant alone explains the loss holds through n = 13 only. These are PC builds; the microcontroller builds return timing only, so no board-level correctness is claimed.

### F. Reproducibility

Phase 2 board timer medians of {len(r2)} repeated points differ by at most {r2.max_rel_diff.max() * 100:.4f} % between sessions. Phase 3 round trips of {len(r3e)} repeated points differ by a median {r3e.max_rel_diff.median() * 100:.0f} %, almost all of it the PC simulation
time (median {r3s.max_rel_diff.median() * 100:.0f} %).

## IV. Limitations

One unit per board, one PC, one baud rate (115 200); the counter is uncalibrated and its input was noisy on some long points; some points have fewer than 30 repetitions and are never primary evidence; ESP8266 grover runs a
firmware with a timer interrupt inside the timed region; the model choices above were made after scores were seen; the Phase 3 band reflects the speed of the PC used; correctness on the microcontrollers was not measured.

## V. Conclusion

Memory ends the experiment first for three of the four circuits, and the end can be predicted from the free memory read at n = 2 (largest free block on the ESP32). Time ends grover on the ESP boards. A per-gate-kind model
predicts the largest sizes to about {m2:.0f} % but is a fit, not a gate cost. Offloading wins from small n; its crossover should be quoted as a bracket tied to the PC.

## Acknowledgments

[TODO funding and thanks.] **AI-use statement (IEEE requires AI-generated content, including text, figures and code, to be disclosed in the acknowledgments; the KST pages state no AI policy of their own):** the measurement and analysis code, the figures
and a first draft of this text were produced with the assistance of an AI coding assistant (Claude Code, Anthropic, model Claude Sonnet 5.5) under the authors' direction; the authors checked the results against the raw data and take responsibility for the content.
[TODO authors confirm wording and the extent of AI involvement.]

## Figures and tables to place (IEEE two-column; files in `figures/phase4/`, `data/figures/phase{2,3}/timer_vs_counter/`)

Fig. 1 `F1_timing_vs_n` (time per run, walls marked); Fig. 2 `F2_parity` (predicted vs measured, M1 and M2); Fig. 3 `F3_memory_wall` (measured vs predicted largest n); Fig. 4 `F4_offload_crossover`
(local, offload band, crossover brackets); Fig. 5 `F5_phase1_accuracy` (float32 infidelity); optional: `timer_vs_counter/ratio_all_boards` (Phase 2). Tables: Table I above; memory table `tables/phase4_memory_wall.tex`.

## References

[TODO references. None were added automatically.]
"""
out = os.path.join(ROOT, "docs", "report", "paper_draft.md")
open(out, "w").write(txt)
print(out, len(txt.split()), "words")
