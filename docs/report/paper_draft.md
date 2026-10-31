# Characterizing Statevector Quantum Circuit Simulation on Microcontrollers: Memory, Time and Offload Limits

*Draft for the KST 2027 submission. Author names, affiliations, e-mail addresses and the repository link are omitted for blind review
(the call asks to remove them). Format: IEEE conference, A4, 10 pt Times; the length limit on the submission page (4-6 pages) and on the
conference home page (8-12 pages) disagree, confirm with the organizers before cutting or expanding. Every number below is produced by
`analysis/paper_draft.py` from the committed analysis outputs; text in [TODO ...] needs the authors.*

## Abstract

We measure how far a dense statevector simulator can be pushed on three microcontrollers (Arduino Uno R3, ESP8266, ESP32) with four circuits
(h_all, bell_ghz, qft, grover), timing every run with an external pulse counter. The largest circuit that fits is set by memory for h_all,
bell_ghz and qft (walls at n = 8, 13 and 14 qubits) and by time for grover on the ESP boards. A
floor(log2(B/8)) rule, with B the free memory read at n = 2, reproduces the three walls (on the ESP32 only when B is the largest free block). A
per-gate-kind timing model predicts held-out largest-n times with 17 % mean absolute percentage error over 32 points against 47 % for
one constant per board; we state that the model was not fixed blind. Offloading the simulation to a PC becomes faster than local execution between n = 2 and n = 13
depending on board and circuit; because the PC simulation time varies about 1.5x between sessions, we report the crossover as brackets, not as one number.

## I. Introduction

Statevector simulation needs 2^n complex amplitudes. On a microcontroller the state competes with the program and the runtime for kilobytes of RAM and
the arithmetic runs on 8-bit or soft-float cores. We ask three questions: (1) which resource ends the experiment first, memory or time; (2) can the
limit be predicted from quantities available before the run; (3) at which n does offloading the simulation to a PC over a serial link pay off. The
contribution is a measurement protocol with an independent timing reference and an analysis whose weak points, firmware versions and session
choices are stated explicitly.

[TODO related work: statevector simulators on classical hardware, embedded quantum-simulation work, timing-measurement practice on microcontrollers.
No reference is invented in this draft.]

## II. Method

**Boards and circuits.** Arduino Uno R3 (16 MHz), ESP8266 NodeMCU (80 MHz) and ESP32 DevKit (240 MHz) run the same C++
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

The wall (first allocation failure with positive evidence) is at n = 8 on the Uno (SRAM, linker overflow), n = 13 on the ESP8266 and n = 14 on the ESP32 (allocation returns NULL).
With B read at n = 2 (static RAM left on the Uno, free heap on the ESP8266, largest free block on the ESP32) the rule floor(log2(B/8)) gives n_max = 7,
12 and 13, each equal to the last n that ran. On the ESP32 the total free heap (256328 B) predicts n = 14, one qubit too many; the
largest free block (110580 B) is the right quantity because the state needs one contiguous block (Fig. 3). Caveat: the test resolves B only to a factor of 2, and the Uno B comes from the same
compiler figure that triggers the overflow, so that confirmation is close to circular.

### B. Time

Fig. 1 shows the median time per run. A per-gate-kind model (M2: cost per H, CNOT and controlled-phase gate times 2^n plus a per-gate call term, fitted on small n by non-negative least squares)
reaches a held-out error of 17 % (ESP32 6 %, ESP8266 17 %, Uno 25 %; 32 non-weak points, the largest three n of each series held out)
against 47 % for one constant per board (M1; ESP32 26 %, ESP8266 67 %, Uno 45 %). Honest status: M2 was written down before the analysis was run
but not blind to grover errors that were already known; the weak-point rule, the firmware-class rule, the identifiability rule and the session selection were fixed after scores were seen;
the identifiability verdict of M2 changes with the held-out size; the fitted constants are fits, not measured gate costs. Every selected ESP8266 grover point
ran firmware with a timer interrupt inside the timed region, so ESP8266 grover is excluded from the fit and the clean scores.

### C. Agreement of the on-board timer with the counter

On points that pass the validity rules and have at least 30 independent repetitions, the median `micros()`/counter ratio is 0.9943 on the Uno (19 points),
0.9974 on the ESP8266 (24) and 0.9995 on the ESP32 (26); the largest compared run is
30 s. Small n shows a constant offset of about 1-2 us (1 us timer resolution), visible as ratios well below 1 at n = 2 (figure
`timer_vs_counter`). The counter could not pair some long points (line noise on its input, cause not established); those points keep their `micros()` data and are listed in the report.
The counter's wrap artefact (53.687 s) is rejected by a plausibility rule that was added after the data had been seen, so agreement statistics are conditional on that coarse filter.

### D. Offload crossover

Offload is faster than local execution from a measured n that depends on board and circuit (Fig. 4, Table I). The Phase 3 floor is 3.4 ms (Uno), 3.7 ms (ESP8266)
and 6.8 ms (ESP32) at n <= 4. The simulation time on the PC differs by a median 1.53x (at most 2.92x) between sessions on the same PC (grover n = 9:
4.1 to 8.8 s), while the board-and-link residual is stable; the offload latency is therefore a band between the fastest and the slowest observed simulation and the
crossover is a bracket of two measured n for each bound, never an interpolated value.

**Table I.** Crossover brackets (measured n between which offload becomes faster and stays faster; fast bound / slow bound of the PC simulation time).

| board | circuit | fast PC | slow PC | label |
|---|---|---|---|---|
| ESP32 | bell_ghz | 12-13 | 12-13 | - |
| ESP32 | grover | 8-9 | 9-10 | weak; weak |
| ESP32 | h_all | 12-13 | none (n <= 13) | within noise; no crossover up to the largest measured n; within noise at the largest measured n |
| ESP32 | qft | 11-12 | 12-13 | - |
| ESP8266 | bell_ghz | 9-10 | 10-11 | within noise; within noise |
| ESP8266 | grover | 3-4 | 4-5 | weak point beyond the bracket; weak point beyond the bracket |
| ESP8266 | h_all | 7-8 | 7-8 | within noise |
| ESP8266 | qft | 6-7 | 7-8 | within noise |
| Uno | bell_ghz | 5-6 | 6-7 | within noise |
| Uno | grover | <= 2 | 2-3 | offload faster at the smallest measured n; within noise at the smallest measured n; within noise |
| Uno | h_all | 4-5 | 4-5 | - |
| Uno | qft | 3-4 | 3-4 | within noise |

### E. Precision

On the PC, the float32 state of grover keeps its direction (normalised infidelity at most 5.5e-05 for n <= 12) but loses norm: the raw infidelity against Aer is 0.109 at n = 12 while the success probability is still 0.89.
The cause is the float32 constant 1/sqrt(2), which is biased and multiplies the norm squared of the state by a constant below 1 at every H gate; the direction error also grows beyond n = 12
(1.1e-03 at n = 13, 1.7e-02 at n = 14). The statement that the constant alone explains the loss holds through n = 13 only. These are PC builds; the microcontroller builds return timing only, so no board-level correctness is claimed.

### F. Reproducibility

Phase 2 board timer medians of 9 repeated points differ by at most 0.0056 % between sessions. Phase 3 round trips of 45 repeated points differ by a median 14 %, almost all of it the PC simulation
time (median 21 %).

## IV. Limitations

One unit per board, one PC, one baud rate (115 200); the counter is uncalibrated and its input was noisy on some long points; some points have fewer than 30 repetitions and are never primary evidence; ESP8266 grover runs a
firmware with a timer interrupt inside the timed region; the model choices above were made after scores were seen; the Phase 3 band reflects the speed of the PC used; correctness on the microcontrollers was not measured.

## V. Conclusion

Memory ends the experiment first for three of the four circuits, and the end can be predicted from the free memory read at n = 2 (largest free block on the ESP32). Time ends grover on the ESP boards. A per-gate-kind model
predicts the largest sizes to about 17 % but is a fit, not a gate cost. Offloading wins from small n; its crossover should be quoted as a bracket tied to the PC.

## Acknowledgments

[TODO funding and thanks.] **AI-use statement (IEEE requires AI-generated content, including text, figures and code, to be disclosed in the acknowledgments; the KST pages state no AI policy of their own):** the measurement and analysis code, the figures
and a first draft of this text were produced with the assistance of an AI coding assistant (Claude Code, Anthropic, model Claude Sonnet 5.5) under the authors' direction; the authors checked the results against the raw data and take responsibility for the content.
[TODO authors confirm wording and the extent of AI involvement.]

## Figures and tables to place (IEEE two-column; files in `figures/phase4/`, `data/figures/phase(2, 3)/timer_vs_counter/`)

Fig. 1 `F1_timing_vs_n` (time per run, walls marked); Fig. 2 `F2_parity` (predicted vs measured, M1 and M2); Fig. 3 `F3_memory_wall` (measured vs predicted largest n); Fig. 4 `F4_offload_crossover`
(local, offload band, crossover brackets); Fig. 5 `F5_phase1_accuracy` (float32 infidelity); optional: `timer_vs_counter/ratio_all_boards` (Phase 2). Tables: Table I above; memory table `tables/phase4_memory_wall.tex`.

## References

[TODO references. None were added automatically.]
