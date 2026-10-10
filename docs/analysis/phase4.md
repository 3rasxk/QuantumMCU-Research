# Phase 4: local vs offload decision rule

Generated from `data/raw/phase2|3` (with_ref bucket, the only one) by `analysis/phase4_decision_rule.py`; tables in
`data/processed/phase4/` (`n_max_check.csv`, `crossover.csv`, `rule_eval.csv`, `adjustments.csv`, `offload_floor.csv`), charts in
`data/figures/phase4/` (`decision_flowchart.png`, `crossover_rule.png`). No hardware was used: Phase 4 is an analysis of the Phase 2
(local, `micros()`) and Phase 3 (offload round trip) data. Caveats in the data audit (`docs/data_audit.md`) apply: ESP8266 grover
Phase 2 ran under several firmware versions, Phase 3 includes the PC-side Qiskit Aer simulation, one unit per board.

## Step 1: memory wall, n_max = floor(log2(B / 8))

OBSERVED: for the 10 series that stopped at a recorded memory wall (Uno h_all/bell_ghz/qft/grover, ESP8266 and ESP32 h_all/bell_ghz/qft),
B taken from the measurements reproduces the last ok n on **10/10**: Uno B = 2 048 B minus the static data derived from the ok points
(about 1 844 B) gives 7; ESP8266 total free heap read at n=2 plus its state (52 240 B; the firmware does not log the largest block) gives 12; ESP32 largest free
block (110 612 B) gives 13. The fallback B = SRAM / 2 (flowchart wording) gives 7, 12 and **14 for the ESP32 (one qubit too high)**, i.e. 7/10 series.
INTERPRETATION: the formula is exact when B is measured; the SRAM / 2 fallback is only as good as the board's SRAM / largest-block ratio (ESP32: 110 KB of 320 KB).

## Step 2: crossover n*

n* = the n where the offload median round trip per request becomes shorter than the local median time per rep (log-linear interpolation between the two n around
the crossing). OBSERVED:

| circuit | Uno | ESP8266 | ESP32 |
|---|---|---|---|
| h_all | 4.46 | 7.33 | none up to n=13 (offload 1.1x slower at n=13) |
| bell_ghz | 5.96 | 9.94 | 12.63 |
| qft | 3.67 | 7.07 | 12.19 |
| grover | <= 2 (already faster at n=2) | 3.65 | 8.90 |

The offload round trip at n <= 4 is a floor: median 3.4 ms (Uno), 3.3 ms (ESP8266), 6.8 ms (ESP32), set by the serial frame (868 us at 115 200 baud), the PC call
and the firmware's 20 ms-paced loop plus host latency; local time grows about 2x per qubit until it reaches that floor.

Rule of the flowchart: n*_new = n*_ref + log2(clock_new / clock_ref) + A. Seven (circuit, board pair) crossovers have a measured n* on both boards:

| pair | circuit | log2 clock ratio | log2 local speed ratio | A = speed - clock | n* shift measured | error clock only | error with speed ratio |
|---|---|---|---|---|---|---|---|
| Uno -> ESP8266 | h_all | 2.32 | 3.42 | 1.10 | 2.86 | -0.54 | +0.56 |
| Uno -> ESP8266 | bell_ghz | 2.32 | 4.05 | 1.73 | 3.98 | -1.66 | +0.07 |
| Uno -> ESP8266 | qft | 2.32 | 3.13 | 0.80 | 3.40 | -1.08 | -0.28 |
| ESP8266 -> ESP32 | bell_ghz | 1.58 | 2.13 | 0.54 | 2.69 | -1.11 | -0.57 |
| ESP8266 -> ESP32 | qft | 1.58 | 4.75 | 3.17 | 5.12 | -3.54 | -0.37 |
| ESP8266 -> ESP32 | grover | 1.58 | 4.75 | 3.17 | 5.25 | -3.66 | -0.49 |
| Uno -> ESP32 | qft | 3.91 | 8.02 | 4.11 | 8.52 | -4.62 | -0.51 |

(errors in qubits, predicted minus measured). RMS error: clock ratio alone **2.74** qubits; with the measured local speed ratio **0.44** qubits. Architecture adjustment A
(measured): Uno -> ESP8266 +0.80 ... +1.73 (h_all, grover +1.10, +0.87); ESP8266 -> ESP32 +0.54 for bell_ghz (CNOT swaps, no float arithmetic) and +3.17 ... +3.53 for qft, grover, h_all
(Hadamard / controlled-phase arithmetic). Two crossovers are censored and not in the table (ESP32 h_all: none in range; Uno grover: at or below the first n).

INTERPRETATION (not tested): because the offload cost near the crossover is nearly independent of the board, a board that is r times faster locally moves n* by log2(r); the clock ratio
understates r by the architecture effect (word size, floating-point hardware), which is circuit dependent. The speed-ratio form is therefore a restatement of the data, not a first-principles
prediction: for an unseen board r has to come from a measured local run or from per-class constants, and with three boards each class has one member. The offload floor depends on the
serial rate (115 200 only), the PC and its simulator; a faster link or PC lowers it and moves n* down.

## Limitations

One unit per board, single run per point, one PC, one baud rate; Phase 3 grover n >= 11 time-capped (2-42 requests) so the grover crossover rests on n <= 10; ESP32 h_all has no crossover in range, so its
n* is not an estimate; the ESP32's higher floor (6.8 ms) is not explained (UNVERIFIED); constants A come from the same data they are scored on.
