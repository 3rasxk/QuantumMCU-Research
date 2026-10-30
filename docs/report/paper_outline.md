# Paper outline: statevector simulation on microcontrollers (working notes, 2026-10-10)

Source idea: `~/Downloads/paperguide.pdf` (Thai outline, title "Characterizing Statevector Quantum Circuit
Simulation on Microcontrollers: Memory, Time, and Precision Limits"). This file records what the data on disk
supports today. Conference names and dates in that PDF were not checked against the CFPs.

## 1. Time model, fitted per gate type (Phase 2, on-device)

`analysis/phase2_gate_cost_fit.py` -> `data/processed/gate_cost_fit.csv`, `gate_cost_validation.csv`.
NNLS on relative error, trained on h_all, bell_ghz, qft with medians >= 100 us (micros() quantisation);
**grover is not in the fit**, so it is an out-of-sample test. Units: microseconds.

Model B: `t = (n_H k_H + n_CNOT k_CNOT + n_CPHASE k_CPHASE) 2^n + (n_H + n_CNOT + n_CPHASE) a`

| board | k_H | k_CNOT | k_CPHASE | a (per gate call) | train MAPE | grover out-of-sample MAPE (max) |
|---|---|---|---|---|---|---|
| Uno | 31.22 | 4.75 | 16.08 | 7.36 | 8.3 % | 32.5 % (46.7 %) |
| ESP8266 | 2.699 | 0.1068 | 1.281 | 6.95 | 9.9 % | 37.1 % (52.0 %) |
| ESP32 | 0.0775 | 0.0946 | 0.0460 | 1.21 | 3.4 % | 5.4 % (16.8 %) |

- Model A (the form in `timing_model.py`, no per-gate term) is in the CSV too: ESP32 grover out-of-sample
  19.4 % (max 62 %), so the per-gate term matters mostly at small n where grover has hundreds of gates.
- The bootstrap 95 % intervals (500 draws over reps) are extremely narrow: they cover rep-to-rep noise only,
  **not** model error. Quote the MAPE columns, not the intervals, as the uncertainty.
- Uno and ESP8266 under-predict grover at every n (about -18 % at n=7 on Uno, -26 % at n=10 on ESP8266):
  the multi-controlled phase in grover is not exactly an H/CNOT/CPHASE mix on soft-float boards. State this as a
  limitation; do not tune the model on grover.
- H is 6.6x the cost of CNOT on Uno and 25x on ESP8266 (no FPU, soft-float), about 0.8x on ESP32 (hardware
  single-precision FPU). This is the FPU insight; the ESP8266 has no FPU at all, so the outline's note on
  "ESP32 FPU / double emulated" should also say that float is emulated on Uno and ESP8266.
- `BOARD_GATE_COST` in `pc/shared/timing_model.py` still holds the prior (retired-data) estimates; this fit
  was NOT written into it (it drives the ETA/plan code and its tests). Adopting it is the owner's call.

## 2. Memory model (Phase 2)

`analysis/paper_figures.py` -> `data/figures/paper/fig1_memory_wall.*`.
Heap before the state = `free_heap_before + 8 * 2^n`, identical for every n (spread 0 B): 1812 B (Uno),
52240 B (ESP8266), 256328 B (ESP32). State = 8 * 2^n bytes.
- Uno: wall n=8 (2048 B > 1812 B). ESP8266: wall n=13 (65536 B > 52240 B). Both agree with "first n whose state
  exceeds the available heap".
- ESP32: wall n=14 although 131072 B < 256328 B, so the limit is the largest contiguous block, not the free
  total. A largest block of about 110 KB was seen only in a retired run (`docs/design/experiment_plan.md`
  section 8); the new `raw.csv` has no `largest_block` column. Re-measure it before claiming it in the paper.
- The memory formula needs the additive overhead term; `2^n * b` alone predicts n=14 ok on ESP32.

## 3. Time figure

`data/figures/paper/fig2_time_vs_n.*`: measured medians with IQR, model B lines, grover hollow, points with
fewer than 10 reps (2 h cap) ringed in orange, model error % below each board.

## 4. Gaps before writing (unchanged by this work)

1. No on-device result data: `raw.csv` holds timing and heap only, so "precision on the microcontroller" is
   currently a PC statement (Phase 1: float32 C++ vs Qiskit Aer float64). Return one result value or checksum
   from the board for at least one circuit per board.
2. Phase 1 grover: infidelity grows about 4x per n and passes 1e-3 only up to n=8 (n=9: 1.5e-3, n=12: 0.109);
   P(marked) is still 0.89 at n=12, so report infidelity and success probability separately. A float16 /
   fixed-point comparison can be run on the PC; there is no such code yet.
3. Every session ran with a dirty git tree (13 different commits); counter reference unusable at many
   points (Uno, ESP8266 h_all); grover points with 1 to 42 reps.
4. Not done and not recommended for round 1: stabilizer simulation (only h_all and bell_ghz are Clifford),
   INA219 energy (extra hardware, sensor slower than the short circuits).
5. Phase 3 (offload) is not in the outline; the data exist for all boards and circuits.
