# Paper figure and table plan (4-6 page double-column IEEE, double-blind)

Planning only: no figure is built here. A later task builds them with `analysis/paper_figures_ieee.py`. Evidence base:
`docs/data_audit.md` and `data/processed/audit/*.csv` (finding ids H*, M*, L* and check ids refer to that report). Status of the data
that matters for every item: 60 sessions, all `with_ref` bucket; Phase 2 and Phase 3 complete for 3 boards x 4 circuits within the
limits listed in the audit; ESTIMATE = derived from the measured wall times of the earlier runs, not a measurement.

## 1. Two framings, one data set

| framing | claim the data can carry | what stays out of reach |
|---|---|---|
| A. "How many qubits can each board run" | last ok n per board and circuit (Uno 7; ESP8266 12 for h_all/bell_ghz/qft, 10 for grover; ESP32 13, grover 12), the limit that stopped it (memory wall with recorded evidence, or the 2 h per-point cap), and time per rep vs n | grover's memory wall on ESP8266/ESP32 (never reached, M7) |
| B. "What limits simulation on microcontrollers and how well can the limits be predicted" | memory limit predicted exactly for all 10 recorded walls (state bytes vs RAM / largest free block) and time limit extrapolated within a factor 2 for 97-100 % of larger-n points of a series; offload moves the limit to the PC | a predictor that transfers between circuits (leave-one-circuit-out within a factor 2: 46 %); predictions were not independent of retired observations (L6); the models were fitted and scored on the same 113 points |

Both framings share the same three core items (time vs n, limits table, offload comparison); framing B adds the prediction figure
and promotes the limits table.

## 2. Candidate items, ranked by value

Value = how much of the paper's claim it carries. "Support" is the audit's verdict on whether the current data fully support it.

| # | item | supports | support | what is missing or wrong |
|---|---|---|---|---|
| 1 | Fig. A: per-rep time vs n, 3 boards x 4 circuits | A and B (core result) | **YES** with stated caveats | per-point firmware must be stated (H1: ESP8266 grover n=8..10 and ESP32 grover n=12 ran under different uncommitted firmware); 10 time-capped points drawn open; n=1 of h_all/qft absent (M1) |
| 2 | Table: limits per board and circuit (predicted vs observed wall n, evidence, limiting factor) | A and B | **YES** for 10 of 12 rows, **PARTIAL** for ESP8266/ESP32 grover | grover wall not reached (time ceiling first); predictions informed by retired data (L6) must be disclosed |
| 3 | Fig. C: offload (Phase 3) vs local (Phase 2) at equal n, crossover n | A and B | **YES** | one repeat disagrees x1.75 (ESP32 grover n=13, M6); no host-load record; Phase 3 grover n>=11 time-capped (2-42 requests); say what each curve measures |
| 4 | Fig. D: prediction accuracy, measured / predicted vs n, in-sample vs extrapolation | B | **PARTIAL** | rules were fixed for M1/M1c before scoring; M2/M2c/M3 are post-hoc; no held-out board or pre-registered prediction; cross-circuit transfer fails (ESP8266 5 % within 2x) |
| 5 | Table: boards and setup (clock, RAM, FPU, word size, allocation, toolchain, timer) | A and B | **PARTIAL** | clock (`f_cpu`) and toolchain versions are recorded in the env JSON; RAM and FPU need a cited source (README quotes none; ESP8266 "no FPU" UNVERIFIED); timer resolution only VERIFIED for the Uno (4 us) |
| 6 | Fig. 0: system / measurement diagram (boards, counter, PC, Phase 2 vs Phase 3 data paths) | both | **YES** (redraw) | existing wiring drawings are in `docs/design/`; redraw without any identifying text, ports or names |
| 7 | Fig. E: micros() minus counter, per point | method validity | **PARTIAL** | clean for the ESP32 only (45 of 46 points ok); Uno and ESP8266 48 of 48 flagged and under older counter firmware (H3); counter uncalibrated; constant offsets unexplained |
| 8 | Table: numerical accuracy (infidelity, TVD) from Phase 1 | validity of the simulator build | **YES** | validates the PC build only, not board output; grover infidelity > 1e-3 for n >= 9 (M8) |

## 3. Item specifications

Common rules: data from the `with_ref` bucket (the only one that exists); no `no_ref` data; ok points only unless a marker says
otherwise; all 100 reps of a point used (WARMUP_REPS=0); uncertainty = median and IQR (25th-75th percentile, numpy linear
interpolation) over the reps of the point; faint dots = individual reps; a point with one value gets no bar. Every figure: 3.5 in
(single column) or 7.16 in (double column), serif 7-9 pt, fonts embedded (`pdf.fonttype` 42), line style and marker differ per circuit
and per board (grayscale-safe), no colour-only encoding, PDF vector + PNG 600 dpi, metadata stripped, no SVG.

### Fig. A (item 1), double column 7.16 in, three panels
- **Purpose:** show how time per rep scales with n for every board and circuit and where each series stops.
- **Source:** `data/raw/phase2/<board>/<circuit>/with_ref/raw.csv` (`board, circuit, n, rep, exec_time_us`) and `memory_wall.csv` (`n, status`).
- **Filter:** n with terminal status `ok`; time-capped ok points drawn with open markers; `build_overflow`/`malloc_failed` rows as a wall marker on a top strip;
  `skipped_compute_infeasible` as "time-limited, not run". Already implemented as fig1 of `analysis/paper_figures_ieee.py`.
- **Axes:** x number of qubits n (integer ticks); y time per rep in microseconds, log. One panel per board (Uno, ESP8266, ESP32), one line per circuit.
- **Statistics shown:** n of reps in the caption (100 per point, 10 exceptions listed), no p-values.
- **Caption draft:** "Execution time per repetition versus number of qubits for four circuits on three microcontroller boards (log scale). Lines join the median over 100
  repetitions; bars are the interquartile range; faint dots are single repetitions. Open markers: points stopped by a 2 h per-point cap before 100 repetitions
  (fewer repetitions). Crosses: memory wall with recorded evidence (Uno link-time RAM overflow, ESP8266/ESP32 allocation failure). Stars: points not run because one
  repetition was predicted to exceed the cap."
- **Needs before use:** a per-point firmware statement (H1) in the text or a footnote; decide whether ESP8266 grover n=8..10 and ESP32 grover n=12 are drawn
  as is (they are real measurements under a changed firmware) or re-collected.

### Table: limits (item 2), single column
- **Source:** `data/processed/audit/limits.csv` and `memory_model.csv` (derived from `memory_wall.csv`, `points.csv`, `raw.csv` columns `free_heap_before, largest_block`).
- **Columns:** board, circuit, predicted wall n (pre-run, `pc/shared/experiment_plan.py:32`), last ok n, limit n, evidence (`build_overflow` with `compile_ram_pct`, `malloc_failed`), limiting factor
  (memory / 2 h cap), memory-model prediction (from measured free heap / largest block).
- **Current content:** Uno wall n=8 for all four circuits (110 % compile RAM); ESP8266 wall n=13 (h_all, bell_ghz, qft); ESP32 wall n=14 (h_all, bell_ghz, qft); ESP8266 grover
  stopped by the cap at n=10 (time limited from n=11), ESP32 grover at n=12 (from n=13). All 10 observed walls equal the prediction and the memory model.
- **Disclosure required:** predictions were committed before the data but are numerically the retired observations + 1 (L6); the ESP32 one used a retired 110 KB block value.
- **Support:** YES / PARTIAL as in the ranking.

### Fig. C (item 3), single or double column, one panel per board or one panel with three boards
- **Purpose:** show where offloading beats local execution and what the offload cost consists of.
- **Source:** Phase 2 `raw.csv` (`exec_time_us`) and Phase 3 `raw.csv` (`n, baud_rate, rep, e2e_latency_us`), `points.csv` (`pc_sim_s_total, device_exec_s`) for the optional breakdown.
  No counter data (Phase 3 is without the counter; all Phase 3 reference files are excluded, H2).
- **Chart:** per board, per circuit: median and IQR of local time per rep and of offload round trip per request vs n (log y); mark the first n where offload is below local, or "none in range"
  (ESP32 h_all). Optional inset or second figure: share of PC simulation in the round trip (median 0.89 / 0.79 / 0.64 for Uno / ESP8266 / ESP32 at n >= 8).
- **Statistics shown:** crossover n per board and circuit (Uno 5, 6, 4, 2; ESP8266 8, 10, 8, 4; ESP32 none, 13, 13, 9 for h_all, bell_ghz, qft, grover), requests per point (100; grover n>=11 fewer).
- **Caption draft:** "Local execution time per repetition (Phase 2) and offload round-trip latency per request (Phase 3) versus n. In the offload case the PC simulates the circuit
  with a state-vector simulator and the board times only the serial round trip and checks frame integrity; the two curves therefore measure different quantities. Bars: interquartile range."
- **Needs:** a statement of the serial rate (115 200 baud only; other rates untested) and that all requests are one board, one host.

### Fig. D (item 4), single column
- **Purpose (framing B):** how well the time of larger n can be predicted from smaller n.
- **Source:** `data/processed/audit/prediction.csv` and `loco.csv` (from `raw.csv` medians and `pc/shared/timing_model.gate_counts`).
- **Chart:** measured / predicted (log y, reference line at 1 and at 0.5 / 2) vs n, in-sample points filled and extrapolation points open, board by marker, circuit by line style.
  State the model and the split rule in the caption (declared rules: M1/M1c; post-hoc: M2/M2c/M3).
- **Statistics shown:** median ratio, min, max, share within +/-25 % and a factor 2 (M1 extrapolation: 0.64, 39 %, 97 %; M1c: 0.72, 46 %, 100 %; M2c: 0.84, 83 %, 100 %); LOCO within a factor 2: 46 % (M1).
- **Needs:** be explicit that models were scored on the data they were designed on; either keep as "fit procedure" evidence or hold out a board or n.

### Table: boards and setup (item 5), single column
- **Source:** `env/*.json` (`f_cpu`, `pio_packages`, `platformio_version`, `python_version`), firmware source (`firmware/common/qsim.hpp:30-33` state = 8 B per amplitude, allocation policy in
  `firmware/*/src/main.cpp`), measured free heap and largest block from `raw.csv`.
- **Rows:** board, word size, clock (16 / 80 / 240 MHz, recorded build setting), state allocation (static / malloc), usable heap measured (Uno: compile RAM 2 048 B total; ESP8266 free heap ~52 KB at n=2;
  ESP32 free heap ~256 KB, largest block 110 580 B), timer API and resolution (Uno 4 us verified; ESP: 1 us returned, resolution UNVERIFIED), toolchain versions.
- **Needs:** cited sources for RAM size and FPU status (README table has none) or leave those cells out.

### Fig. 0 (item 6), single column
System diagram: target board, GPIO timing pin to the counter board, counter WiFi link to the PC (TCP), Phase 2 data path (board prints timings over USB), Phase 3 data path (board sends 4-byte requests, PC simulates, 6-byte replies).
Redraw from scratch for the paper; the existing wiring drawings in `docs/design/` were not inspected for author text (UNVERIFIED).

### Fig. E (item 7), single column or appendix
`micros()` minus counter per point (median, IQR; us and %), ESP32 only if the claim must rest on a clean reference: `data/raw/phase2/esp32/*/with_ref/ref/ref_compare.csv` (`n, rep, micros_us, counter_us, diff_us, diff_pct`) and
`ref_compare_points.csv` (`n, n_pairs, ref_status`). Caption must state: the counter was only self-loopback tested, is not externally calibrated, and differences are relative to this counter.
Uno (-6.7 ... -146 314 us, -0.49 to -0.53 % at n=6,7) and ESP8266 (-7.5 us constant) points are all counter-flagged and under older counter firmware; show them only as open markers or leave them to the text.

### Table: numerical accuracy (item 8), single column or text
Source: `data/raw/phase1/infidelity_tvd.20261003T111917Z.csv` and `infidelity_tvd.20261004T091042Z.csv` (not the un-timestamped file). Rows: circuit, n range, max infidelity, max TVD, pass criterion 1e-3. h_all, bell_ghz, qft pass up to n=14
(max 2.4e-7); grover passes to n=8 and fails from n=9 (1.47e-3, 6.47e-3, 2.66e-2, 0.109 at n=12). State that it validates the PC build of the simulator against Qiskit and that no board-level correctness data exist.

## 4. Page and column budget (4-6 pages)

| item | size | est. share of a page | place |
|---|---|---|---|
| Fig. 0 system diagram | 1 col | 0.20 | main text |
| Table boards and setup | 1 col | 0.20 | main text |
| Fig. A time vs n | 2 col | 0.35 | main text |
| Table limits | 1 col | 0.25 | main text |
| Fig. C offload vs local | 2 col or 1 col x 3 panels | 0.30 | main text |
| Fig. D prediction accuracy | 1 col | 0.25 | main text if framing B, else appendix |
| Table numerical accuracy | 1 col | 0.15 | main text (4 rows) or one sentence |
| Fig. E micros() vs counter | 1 col | 0.25 | appendix / text; one sentence if pages are short |

About 1.95 pages for figures and tables, leaving room for method, results and limitations in 4-6 pages. Items 7 and 8 are the first to move to text.

## 5. Minimal credible set (if some data are not usable)

Fig. A + limits table + Fig. C + boards table (4 items, about 1.1 pages). Claims it supports: where each board stops and why (with evidence), how time scales, and where offloading pays.
Claims it must not make: a validated predictor, absolute timing accuracy (counter), correctness of board output, anything about grover's memory wall on the ESP boards.

## 6. Additional runs or analyses needed (times are ESTIMATE from the measured wall times of the earlier runs in `points.csv`)

| need | closes | ESTIMATE |
|---|---|---|
| Re-collect ESP8266 Phase 2 grover (n=2..10) under one committed firmware | H1 for the ESP8266 series | 4.7 h |
| Re-collect ESP32 Phase 2 grover under one committed firmware with the 64-bit timer | H1 for the ESP32 series | 5.4 h |
| Collect n=1 for h_all and qft, all boards, both phases (12 points) | M1 | 0.2 h |
| Re-collect Uno and ESP8266 Phase 2 under the counter firmware used for the ESP32, then compare counter statuses | H3 | 6.3 h for both boards in full; 1.5 h without ESP8266 grover |
| Repeat the 105 Phase 2 points that take under 10 min, twice more | M6 (per-rep repeatability; `raw.csv` must keep every run) | 3.5 h |
| Re-run Phase 3 without the counter (policy): all circuits / without grover | H2 | 14.2 h / 1.9 h (grover 12.2 h, mostly the PC simulation) |
| External frequency reference for the counter | counter calibration | unknown (needs hardware not in this repository) |
| Explain the constant `micros()` - counter offsets (Uno -16 us, ESP8266 -7.5 us) | Fig. E | analysis only (code path between pin toggle and timer reads) |
| Scrub paths, ports and host names from any data shipped with the paper | M10 | analysis only |
| Update README, run_log, ceiling doc, system_design to match the data | M2-M4 | docs only |

## 7. Double-blind check list

Figure content and metadata: no author, school, repository URL, serial port, user name, host name or absolute path in a figure, its caption, its PDF/PNG metadata
(`analysis/paper_figures_ieee.py` strips metadata and a test checks the generated PDFs). Data and docs that do identify: `data/raw/**/sessions.csv` (absolute path with a user name, 24 files),
env JSON files (60 files with serial device names and host OS), `data/run_history.jsonl` (host name), the git remote URL and tag names (`pre-run-uno-v*`), commit messages. Do not
quote commit hashes or tags in the submitted text; `paper/figures/CAPTIONS.md` has an author-only line that must be removed.
