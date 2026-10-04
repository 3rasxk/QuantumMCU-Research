# Experiment plan and memory-wall predictions (restart, 2026-10-03)

Status: **plan only, no hardware touched.** Everything marked **UNVERIFIED** has
not been observed in the restarted dataset; it comes from code reading, the
compile-only build matrix (`docs/preflight_report.md` P2-8) or the retired
dataset (`data/archive/restart_20261003T111500Z/`, read once to freeze numbers).

## 1. Scope

| | |
|---|---|
| Circuits | `h_all`, `bell_ghz`, `qft`, `grover` (qpe, steane_encode removed from the plan; code stays in `firmware/common/circuits.hpp`) |
| Boards | Uno, ESP8266, ESP32 |
| Phases | 2 (on-device) and 3 (offload, same four circuits) |
| Timing reference | second ESP32 pulse counter, see `docs/design/counter_design.md` (collect the restarted dataset only after it works) |
| Machine-readable plan | `pc/shared/experiment_plan.py`; times: `python pc/run.py --plan` |

Plan n range per row = minimum meaningful n (h_all 1, bell_ghz 2, qft 1, grover 2,
`pc/run.py` `MIN_VALID_N`) up to the **predicted wall n**, which is attempted
because the failure is the evidence. Phase 3 uses the same n range (no board
wall, the state lives on the PC), grover capped at n=10 by PC-side Aer cost.

## 2. Memory model, from the code

| Fact | Where | Value |
|---|---|---|
| State element | `firmware/common/qsim.hpp:30-33` | `struct Cplx { float re; float im; }` = **8 B** (float32; no `std::complex`) |
| Index type | `firmware/common/qsim.hpp:28` | `typedef uint32_t qsize_t` |
| State size | all boards | **8 x 2^n bytes** (one buffer, in-place gates) |
| Uno allocation | `firmware/uno/src/main.cpp:25,30` | `static Cplx g_state[STATE_COUNT]`, `STATE_COUNT = 1 << N_QUBITS` (compile-time, `.bss`) |
| ESP8266 allocation | `firmware/esp8266/src/main.cpp:67` | `g_state = (Cplx*)malloc(n_states * sizeof(Cplx))`, NULL checked, `free` at `:108` |
| ESP32 allocation | `firmware/esp32/src/main.cpp:65` | same `malloc`, NULL checked, `free` at `:107`; also logs `esp_get_free_heap_size` (`:79`) and `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` (`:88`) |
| Extra buffer per gate | `firmware/common/qsim.hpp` (`qsim_h`, `qsim_cnot`, `qsim_cphase`) | **none**: gates swap/update in place with a few locals (`Cplx a, b, tmp`) |
| Extra buffer per circuit | `firmware/common/circuits.hpp:108-134,152-` | **none**. Grover's multi-controlled gates recurse (`mc_phase_apply` <-> `mc_x_apply`), depth about 2(n-1) frames: **stack only** |
| WiFi | `firmware/esp8266/src/main.cpp:56-57`, `firmware/esp32/src/main.cpp:56` | forced off so its stack does not take heap |
| Other large RAM users | none in firmware | Serial buffers, Arduino core, SDK, FreeRTOS loop task: part of the static/heap baseline below |

Consequence: **the memory wall depends only on n and board, not on the circuit.**
Stack depth for grover is the one circuit-specific RAM item, and it matters only
on the Uno (below).

### Required bytes per n

| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| state bytes | 16 | 32 | 64 | 128 | 256 | 512 | 1 024 | 2 048 | 4 096 | 8 192 | 16 384 | 32 768 | 65 536 | 131 072 | 262 144 | 524 288 |

## 3. Per-board prediction

All predictions below are derived from the code and arithmetic. The few facts taken from
retired observations are in section 8 ("Prior observations") and are named where used.

**Uno (ATmega328P, 2 048 B SRAM).** The state is a static array of 8 x 2^n bytes
(`firmware/uno/src/main.cpp:30`). n=8 needs 2 048 B, the whole SRAM, before counting the
core's own static data (baseline about 200 B, ESTIMATE, section 8). Linker overflow
(`build_overflow`) at n=8 is therefore certain by arithmetic; n=7 needs 1 024 B + baseline,
about 60 % of SRAM, leaving a stack gap of roughly 800 B (ESTIMATE). Grover's recursion needs
a few hundred bytes of it (frame size UNVERIFIED), so a runtime stack collision at grover
n=7 is a risk to watch, not a prediction.
**Last ok n=7, wall n=8, evidence build_overflow.**

**ESP8266 (81 920 B DRAM).** Static about 29 kB (compile-only build matrix, section 8).
Upper bound for any single allocation: 81 920 - 29 200 = **52 720 B < 65 536 B (n=13)**,
so n=13 cannot succeed whatever the exact heap value. n=12 needs 32 768 B; it fits if usable
heap is at least 32.8 KB (expected about 45-50 KB with WiFi off, **UNVERIFIED**:
`largest_block` is not logged by the ESP8266 firmware).
**Last ok n=12, wall n=13, evidence malloc_failed** (clean OOM, no hang).

**ESP32 (327 680 B DRAM).** Static about 43.4 kB (build matrix). The limit is the largest
single block, not total free heap (`firmware/esp32/src/main.cpp:88` logs it). n=13 needs
65 536 B, n=14 needs 131 072 B. A largest block of about 110 KB, seen once on this board
(section 8, **UNVERIFIED for the new run**), puts the wall between them.
**Last ok n=13, wall n=14, evidence malloc_failed.**

### Prediction table

| Board | Circuit | Last ok n (memory) | Wall n | Evidence expected | Reachable in practice? |
|---|---|---|---|---|---|
| Uno | h_all, bell_ghz, qft | 7 | 8 | build_overflow | yes |
| Uno | grover | 7 | 8 | build_overflow | yes (about 36 min at n=7, ESTIMATE) |
| ESP8266 | h_all, bell_ghz, qft | 12 | 13 | malloc_failed | yes |
| ESP8266 | grover | 12 | 13 | malloc_failed | **no: time-limited from n=9** (section 4) |
| ESP32 | h_all, bell_ghz, qft | 13 | 14 | malloc_failed | yes |
| ESP32 | grover | 13 | 14 | malloc_failed | **no: time-limited from n=10** (section 4) |

Phase 3: no memory wall (the state lives on the PC); the limit there is PC-side simulation
time.

Rule kept from `docs/preflight_report.md` H1: a wall is recorded only with positive
evidence (`build_overflow`, `malloc_failed`); a silent board is not a wall.

## 4. Points limited by run time, not memory

Per-rep time = model `expected_exec_time_us` (`pc/shared/timing_model.py`: gate counts x a
prior-fit per-gate cost, ESTIMATE; extrapolated far beyond any n it was fitted at, so large
n carry a wide error band). Per-point = 100 reps + overhead. Assumptions: single-threaded
state-vector loops, no cache effects, float32 only, fixed per-gate cost per amplitude.

| Board | Circuit | n | Per rep | Per point (device) | Note |
|---|---|---|---|---|---|
| Uno | grover | 7 | 21 s | 36 min | not flagged |
| ESP8266 | grover | 8 | 15.6 s | 26 min | per-rep above the assumed 6 s WDT threshold (UNVERIFIED), `watchdog_suspected` risk |
| ESP8266 | grover | 9 | 131 s | **3.6 h** | time-limited |
| ESP8266 | grover | 10 | 1 144 s | **1.3 days** | time-limited |
| ESP8266 | grover | 11 | 9 586 s | **11 days** | time-limited |
| ESP8266 | grover | 12 | 82 090 s | **95 days** | time-limited |
| ESP32 | grover | 9 | 7.0 s | 12 min | above the assumed 5 s WDT threshold (UNVERIFIED) |
| ESP32 | grover | 10 | 61.7 s | **1.7 h** | time-limited |
| ESP32 | grover | 11 | 517 s | **14 h** | time-limited |
| ESP32 | grover | 12 | 4 433 s | **5.1 days** | time-limited |
| ESP32 | grover | 13 | 37 764 s | **44 days** | time-limited, still below the memory wall |
| Phase 3 any | grover | 10 | 40.5 s per request (PC Aer) | 1.1 h | PC-limited, identical on every board |

`pc/run.py --plan` marks every point above 6 h / 24 h / 72 h and every point whose per-rep
time exceeds the WDT threshold, and flags TIME-LIMITED (above 1 h) as a display threshold
only. Nothing is skipped, nothing is capped. Cumulative-time facts for the ceiling decision
are in `docs/design/ceiling_facts.md`.

### Time ceiling: DECIDED 2026-10-03 — no ceiling, run to the memory wall

Owner answer: "hit memory wall". No per-point ceiling is set; every point up to the predicted wall is attempted (Ctrl+C by the operator remains the only stop). The options below are kept for reference only.

The old 4 h ceiling (`timing_model.CEILING_S`) is no longer enforced for Phase 2
(2026-09-22 decision) and is not changed here. Options for a per-point ceiling:

| Ceiling | Adds to the plan (beyond cheap points) | Excludes | Plan total (all 24 rows, estimate) |
|---|---|---|---|
| 2 h | ESP32 grover n=10 | ESP8266 grover n>=9, ESP32 grover n>=11 | 9.8 h |
| **4 h (proposed)** | ESP32 grover n=10, ESP8266 grover n=9 | ESP8266 grover n>=10, ESP32 grover n>=11 | 13.5 h |
| 24 h | also ESP32 grover n=11 | ESP8266 grover n>=10, ESP32 grover n>=12 | 1.2 days |

Proposal: **4 h**. It keeps one long point per board family, matches the retired
ceiling, and the n=11+ points (14 h to 95 days) are not realistic over USB (the
retired ESP32 n=10 run died at 2.9 h). With a ceiling, grover on ESP8266 and ESP32
ends with `skipped` points, not a memory wall, and the report must say so.
`pc/run.py --plan` shows totals with and without the
flagged points.

## 5. Run-time plan (generated)

Produced by `python pc/run.py --plan --brief` (all ESTIMATE from `timing_model.py`: no measured data exists yet;
rows become MEASURED automatically once the new run has ok points). Re-run it for the current numbers and per-n tables.

```
=== plan summary (every point from the minimum n to the predicted wall) ===
ph board    circuit   pts wall n evidence           total   time-limited excl. limited
 2 uno      h_all       8      8 build_overflow    3.3min              -        3.3min
 2 uno      bell_ghz    7      8 build_overflow    3.1min              -        3.1min
 2 uno      qft         8      8 build_overflow    3.4min              -        3.4min
 2 uno      grover      7      8 build_overflow   44.3min              -       44.3min
 2 esp8266  h_all      13     13 malloc_failed    16.4min              -       16.4min
 2 esp8266  bell_ghz   12     13 malloc_failed    14.9min              -       14.9min
 2 esp8266  qft        13     13 malloc_failed    17.2min              -       17.2min
 2 esp8266  grover     12     13 malloc_failed  107.6days 4 pt / 107.6days       39.9min
 2 esp32    h_all      14     14 malloc_failed    12.7min              -       12.7min
 2 esp32    bell_ghz   13     14 malloc_failed    11.9min              -       11.9min
 2 esp32    qft        14     14 malloc_failed    12.8min              -       12.8min
 2 esp32    grover     13     14 malloc_failed   49.5days 4 pt / 49.5days       21.9min
 3 uno      h_all       8    n/a (offload)         2.2min              -        2.2min
 3 uno      bell_ghz    7    n/a (offload)         1.9min              -        1.9min
 3 uno      qft         8    n/a (offload)         2.2min              -        2.2min
 3 uno      grover      7    n/a (offload)         6.7min              -        6.7min
 3 esp8266  h_all      13    n/a (offload)        15.2min              -       15.2min
 3 esp8266  bell_ghz   12    n/a (offload)        14.0min              -       14.0min
 3 esp8266  qft        13    n/a (offload)        15.2min              -       15.2min
 3 esp8266  grover      9    n/a (offload)           1.6h    1 pt / 1.1h       29.4min
 3 esp32    h_all      14    n/a (offload)        11.9min              -       11.9min
 3 esp32    bell_ghz   13    n/a (offload)        11.1min              -       11.1min
 3 esp32    qft        14    n/a (offload)        11.9min              -       11.9min
 3 esp32    grover      9    n/a (offload)           1.6h    1 pt / 1.1h       26.8min

points above 6 h / 24 h / 72 h device time, and watchdog-risk points (per rep above the board's WDT threshold):
  uno      phase 2: >6h 0, >24h 0, >72h 0, watchdog-risk 0
  uno      phase 3: >6h 0, >24h 0, >72h 0, watchdog-risk 0
  esp8266  phase 2: >6h 3, >24h 3, >72h 2, watchdog-risk 5
  esp8266  phase 3: >6h 0, >24h 0, >72h 0, watchdog-risk 0
  esp32    phase 2: >6h 3, >24h 2, >72h 2, watchdog-risk 5
  esp32    phase 3: >6h 0, >24h 0, >72h 0, watchdog-risk 0

grover, time to complete up to the predicted wall (sum of all its points):
  uno      phase 2: n=2..8: 44.3min
  uno      phase 3: n=2..8: 6.7min
  esp8266  phase 2: n=2..13: 107.6days
  esp8266  phase 3: n=2..10: 1.6h
  esp32    phase 2: n=2..14: 49.5days
  esp32    phase 3: n=2..10: 1.6h

per-board totals (all points | excluding TIME-LIMITED points):
  uno        60 pts        1.1h |       1.1h
  esp8266    97 pts   107.7days |       2.7h
  esp32     104 pts    49.6days |       2.0h
GRAND TOTAL 261 points: 157.4days all | 5.8h excluding 10 TIME-LIMITED point(s) (device > 1.0h, flag only; no ceiling set -- owner decision)
estimates are sequential single-operator wall time; the finish clock of a whole plan = start + total
```

## 6. Phase 1 re-validation (PC only)

`analysis/phase1_compare.py` (C++ simulator vs Qiskit Aer, float32 vs float64), run for
every n the new plan collects on any board/phase (`experiment_plan.phase1_n_values`),
including n=1 for h_all/qft and the odd n never validated before. Results:
`data/raw/phase1/infidelity_tvd.20261003T111917Z.csv` (+ matching `phase1_metadata`);
the original `infidelity_tvd.csv` is untouched. Cell = infidelity / TVD. Threshold 1e-3.

| n | h_all | bell_ghz | qft | grover |
|---|---|---|---|---|
| 1 | 3.45e-08 / 1.72e-08 | n/a | 3.45e-08 / 1.72e-08 | n/a |
| 2 | 1.20e-07 / 6.00e-08 | 3.45e-08 / 1.72e-08 | 1.20e-07 / 6.00e-08 | 2.38e-07 / 1.19e-07 |
| 3 | 2.01e-07 / 1.01e-07 | 3.45e-08 / 1.72e-08 | 2.01e-07 / 1.01e-07 | 4.29e-07 / 2.14e-07 |
| 4 | 2.40e-07 / 1.20e-07 | 3.45e-08 / 1.72e-08 | 2.40e-07 / 1.20e-07 | 1.89e-06 / 9.57e-07 |
| 5 | 2.07e-07 / 1.04e-07 | 3.45e-08 / 1.72e-08 | 2.07e-07 / 1.04e-07 | 6.25e-06 / 3.13e-06 |
| 6 | 2.40e-07 / 1.20e-07 | 3.45e-08 / 1.72e-08 | 2.40e-07 / 1.20e-07 | 2.58e-05 / 1.29e-05 |
| 7 | 2.02e-07 / 1.01e-07 | 3.45e-08 / 1.72e-08 | 2.02e-07 / 1.01e-07 | 8.53e-05 / 4.31e-05 |
| 8 | 2.40e-07 / 1.20e-07 | 3.45e-08 / 1.72e-08 | 2.40e-07 / 1.20e-07 | 3.61e-04 / 1.81e-04 |
| 9 | 2.05e-07 / 1.02e-07 | 3.45e-08 / 1.72e-08 | 2.05e-07 / 1.02e-07 | 1.47e-03 / 7.41e-04 **FLAG** |
| 10 | 2.37e-07 / 1.18e-07 | 3.45e-08 / 1.72e-08 | 2.37e-07 / 1.18e-07 | 6.47e-03 / 3.23e-03 **FLAG** |
| 11 | 2.00e-07 / 1.00e-07 | 3.45e-08 / 1.72e-08 | 2.00e-07 / 1.00e-07 | 2.66e-02 / 1.33e-02 **FLAG** |
| 12 | 2.43e-07 / 1.22e-07 | 3.45e-08 / 1.72e-08 | 2.43e-07 / 1.22e-07 | 1.09e-01 / 5.46e-02 **FLAG** (run 2026-10-04, chunked) |
| 13 | 2.09e-07 / 1.05e-07 | 3.45e-08 / 1.72e-08 | 2.09e-07 / 1.05e-07 | NOT RUN |
| 14 | 2.38e-07 / 1.19e-07 | 3.45e-08 / 1.72e-08 | 2.38e-07 / 1.19e-07 | NOT RUN |

- **h_all, bell_ghz, qft: all n=1..14 pass**, worst infidelity 2.4e-07 (h_all/qft), 3.4e-08 (bell_ghz). The never-validated points (n=1 h_all/qft; odd n 5,7,9,11,13) all pass.
- **grover: n=2..8 pass, n=9, 10, 11 are above 1e-3** (1.47e-3, 6.47e-3, 2.66e-2; P(marked) stays >= 0.973). n=9,10 were already known. The error grows about 4x per n (float32 accumulation over 3^n gates).
- **grover n=12: infidelity 1.09e-1, TVD 5.46e-2, P(marked) 0.891** (`data/raw/phase1/infidelity_tvd.20261004T091042Z.csv`, 818 s). Same growth, about 4x per n.
- **grover n=13, 14: NOT RUN.** n=13 needs roughly 1 h or more and a multi-GB circuit on this 8.6 GB machine (an attempt to build the circuit alone ran over 12 minutes while the machine was swapping and was aborted); n=14 would need about 8.6 GB for the circuit alone. By the 4x trend both would exceed 1e-3 by a wide margin.
- **Why the first run died at n=12:** the one-shot Aer run peaks at 0.26 / 0.61 / 1.66 GB for n=9 / 10 / 11 (x2.7 per n, so about 4.5 GB at n=12) on an 8.6 GB machine that was already swapping; the process vanished twice with no traceback, which is what an OS memory kill looks like (the OS log kept no record, so this is inferred, not proven). `phase1_compare.py --chunk-gates 250000` runs the same circuit through Aer in slices and carries the statevector across; at grover n=9 the result is bit-identical to the one-shot run, and the n=12 run peaked at 0.61 GB.

| grover n | Qiskit instructions | C++ simulator | Qiskit total | peak memory |
|---|---|---|---|---|
| 9 | 199 k | 0.1 s | 11.8 s | 0.26 GB |
| 10 | 877 k | 0.8 s | 38.8 s | 0.61 GB |
| 11 | 3.68 M | 6.9 s | 160 s | 1.66 GB (one-shot) |
| 12 | 15.75 M | 58 s | about 760 s | 0.61 GB (chunked); one-shot about 4.5 GB |
| 13 | about 66 M | about 8 min (extrapolated) | hours | circuit about 2 GB+, not completed |
| 14 | about 280 M | about 70 min (extrapolated) | not feasible here | circuit about 8.6 GB |

- Consequence for the experiment: grover points at n>=9 (all validated n above 8 fail 1e-3) carry a float32 precision caveat on top of the time caveat. Owner decision whether to collect them at all.


## 7. UNVERIFIED list

- ESP8266 usable heap and `largest_block` (assumed about 45-50 KB; the wall n=13 does not depend on it).
- ESP32 largest block of about 110 KB holds in the new run (prior observation, section 8).
- Uno grover stack frame size at n=7.
- WDT thresholds (ESP8266 6 s, ESP32 5 s) in `timing_model.WDT_PER_REP_THRESHOLD_S`: see the Part 4 finding in `docs/design/system_design.md` open decisions.
- Compile/upload/boot per point (all ESTIMATE, bases in `timing_model.py`).
- Grover time model beyond small n (extrapolated).

## 8. Prior observations (retired data, NOT part of the new dataset)

Kept only because the design above rests on them. All come from runs made before the ESP32
timer existed; the results were deleted from the tree on 2026-10-04 (git history, commit
`af40643`). None is a result of the restarted experiment and none is used by `pc/run.py`
(its numbers are ESTIMATE or measured in the new run).

- Compile-only build matrix (`docs/preflight_report.md` P2-8, no board involved): Uno static
  RAM about 200 B baseline, at n=8 above 2 048 B (about 110 % of SRAM); ESP8266 static about
  29 kB; ESP32 static about 43.4 kB.
- Uno: n=8 hit `build_overflow` for h_all, bell_ghz, qft, qpe; n=7 ran. Free stack gap at n=7
  about 800 B.
- ESP32: largest free block 110 580 B, free heap 256 440 B; n=13 ok and n=14 `malloc_failed`
  for h_all, bell_ghz, qft.
- ESP8266 (an even earlier REPS=30 dataset): n=12 ok, n=13 `malloc` NULL.
- Grover on the ESP32: n=8 and n=9 completed with times within about 5 % of the model; an n=10
  attempt lost its USB port after about 2.9 h without finishing. This is the evidence behind the
  caution in "Time ceiling".
