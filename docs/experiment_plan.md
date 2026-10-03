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
| Timing reference | second ESP32 pulse counter, see `docs/counter_design.md` (collect the restarted dataset only after it works) |
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

**Uno (ATmega328P, 2 048 B SRAM).** Static baseline about 200 B (n=2 compiles to
232-238 B including a 32 B state). Compile RAM = baseline + 8 x 2^n:
n=7 -> 1 226-1 228 B (60 %), n=8 -> 2 248-2 254 B (109.8-110.1 %, build matrix
P2-8). The linker overflows at n=8: **build_overflow**, no run needed.
Free stack gap measured at n=7: 788-804 B (`free_heap_before` column of the retired
raw data); grover recursion needs a few hundred bytes of it (UNVERIFIED frame size),
and grover n=7 completed 100 reps in the retired data, so the stack is not the wall.
**Last ok n=7, wall n=8, evidence build_overflow.** Measured in the retired dataset
for h_all, bell_ghz, qft, grover (and qpe).

**ESP8266 (81 920 B DRAM).** Static 28 224-29 200 B (build matrix, 34.5-35.6 %).
Upper bound for any single allocation: 81 920 - 29 200 = **52 720 B < 65 536 B (n=13)**,
so n=13 cannot succeed whatever the exact heap value. n=12 needs 32 768 B; it fits
if usable heap >= 32.8 KB (expected about 45-50 KB with WiFi off, **UNVERIFIED**:
`largest_block` was never logged on the ESP8266). The superseded REPS=30 run saw
n=12 ok, n=13 `malloc` NULL for h_all, bell_ghz, qft.
**Last ok n=12, wall n=13, evidence malloc_failed** (clean OOM, no hang).

**ESP32 (327 680 B DRAM).** Static 43 416 B (13.2 %). Largest single block is the
limit, not total free heap: the retired telemetry shows `free_heap_before` 256 440 B
but `largest_block` **110 580 B** constant for every n and circuit
(**UNVERIFIED for the restart** until re-observed; core/toolchain versions are pinned
in `firmware/esp32/platformio.ini`, but nothing here proves the same block size).
n=13 needs 65 536 B (fits); n=14 needs 131 072 B (> 110 580).
Retired data: h_all, bell_ghz, qft n=13 ok, n=14 `malloc_failed`.
**Last ok n=13, wall n=14, evidence malloc_failed.**

### Prediction table

| Board | Circuit | Last ok n (memory) | Wall n | Evidence expected | Reachable in practice? |
|---|---|---|---|---|---|
| Uno | h_all | 7 | 8 | build_overflow | yes (measured earlier) |
| Uno | bell_ghz | 7 | 8 | build_overflow | yes (measured earlier) |
| Uno | qft | 7 | 8 | build_overflow | yes (measured earlier) |
| Uno | grover | 7 | 8 | build_overflow | yes; n=7 took 2 999 s (30 s/rep) in the retired data |
| ESP8266 | h_all | 12 | 13 | malloc_failed | yes |
| ESP8266 | bell_ghz | 12 | 13 | malloc_failed | yes |
| ESP8266 | qft | 12 | 13 | malloc_failed | yes |
| ESP8266 | grover | 12 | 13 | malloc_failed | **no: time-limited from n=9** (section 4) |
| ESP32 | h_all | 13 | 14 | malloc_failed | yes |
| ESP32 | bell_ghz | 13 | 14 | malloc_failed | yes |
| ESP32 | qft | 13 | 14 | malloc_failed | yes |
| ESP32 | grover | 13 | 14 | malloc_failed | **no: time-limited from n=10** (section 4) |

Phase 3: no memory wall (static RAM flat in n: Uno 796-806 B, ESP8266 about 29 kB,
ESP32 about 43 kB, build matrix P2-8); limits there are PC-side simulation time.

Rule kept from `docs/preflight_report.md` H1: a wall is recorded only with positive
evidence (`build_overflow`, `malloc_failed`); a silent board is not a wall.

## 4. Points limited by run time, not memory

Per-rep time = model `expected_exec_time_us` (`pc/shared/timing_model.py`, grover
fitted from gate counts; model vs retired ESP32 measurement: n=8 85 s vs 90.7 s,
n=9 702 s vs 735 s, i.e. within about 5 %). Per-point = 100 reps + overhead.

| Board | Circuit | n | Per rep | Per point (device) | Note |
|---|---|---|---|---|---|
| Uno | grover | 7 | 30 s (measured) | 50 min (measured) | not flagged |
| ESP8266 | grover | 8 | 15.6 s | 26 min | per-rep above the assumed 6 s WDT threshold (UNVERIFIED), `watchdog_suspected` risk |
| ESP8266 | grover | 9 | 131 s | **3.6 h** | time-limited |
| ESP8266 | grover | 10 | 1 144 s | **1.3 days** | time-limited |
| ESP8266 | grover | 11 | 9 586 s | **11 days** | time-limited |
| ESP8266 | grover | 12 | 82 090 s | **95 days** | time-limited |
| ESP32 | grover | 9 | 7.0 s | 12 min (735 s measured) | not flagged |
| ESP32 | grover | 10 | 61.7 s | **1.7 h** | in the retired run this point lost the USB port at 10 252 s without finishing (`Errno 6`) |
| ESP32 | grover | 11 | 517 s | **14 h** | time-limited |
| ESP32 | grover | 12 | 4 433 s | **5.1 days** | time-limited |
| ESP32 | grover | 13 | 37 764 s | **44 days** | time-limited, still below the memory wall |
| Phase 3 any | grover | 10 | 40.5 s per request (PC Aer) | 1.1 h | PC-limited, identical on every board |

`pc/run.py` flags a point **TIME-LIMITED** when its device time exceeds 1 h. That is a
display threshold only. Nothing is skipped, nothing is capped.

### Time ceiling: OWNER DECISION (not set)

The old 4 h ceiling (`timing_model.CEILING_S`) is no longer enforced for Phase 2
(2026-09-22 decision) and is not changed here. Options for a per-point ceiling:

| Ceiling | Adds to the plan (beyond cheap points) | Excludes | Plan total (all 24 rows, estimate) |
|---|---|---|---|
| 2 h | ESP32 grover n=10 | ESP8266 grover n>=9, ESP32 grover n>=11 | 10.5 h |
| **4 h (proposed)** | ESP32 grover n=10, ESP8266 grover n=9 | ESP8266 grover n>=10, ESP32 grover n>=11 | 14.1 h |
| 24 h | also ESP32 grover n=11 | ESP8266 grover n>=10, ESP32 grover n>=12 | 1.2 days |

Proposal: **4 h**. It keeps one long point per board family, matches the retired
ceiling, and the n=11+ points (14 h to 95 days) are not realistic over USB (the
retired ESP32 n=10 run died at 2.9 h). With a ceiling, grover on ESP8266 and ESP32
ends with `skipped` points, not a memory wall, and the report must say so.
Decide before collection; `pc/run.py --plan` shows totals with and without the
flagged points.

## 5. Run-time plan (generated)

Produced by `python pc/run.py --plan --brief` at plan time (estimates; Uno phase 2
rows use medians measured in the retired dataset, everything else
`timing_model.py`). Re-run it for the current numbers and per-n tables.

```
=== plan summary (every point from the minimum n to the predicted wall) ===
ph board    circuit   pts wall n evidence           total   time-limited excl. limited
 2 uno      h_all       8      8 build_overflow    2.7min              -        2.7min
 2 uno      bell_ghz    7      8 build_overflow    2.5min              -        2.5min
 2 uno      qft         8      8 build_overflow    2.8min              -        2.8min
 2 uno      grover      7      8 build_overflow      1.0h              -          1.0h
 2 esp8266  h_all      13     13 malloc_failed    14.2min              -       14.2min
 2 esp8266  bell_ghz   12     13 malloc_failed    12.9min              -       12.9min
 2 esp8266  qft        13     13 malloc_failed    15.1min              -       15.1min
 2 esp8266  grover     12     13 malloc_failed  107.6days 4 pt / 107.6days       38.6min
 2 esp32    h_all      14     14 malloc_failed    18.0min              -       18.0min
 2 esp32    bell_ghz   13     14 malloc_failed    16.9min              -       16.9min
 2 esp32    qft        14     14 malloc_failed    18.1min              -       18.1min
 2 esp32    grover     13     14 malloc_failed   49.5days 4 pt / 49.5days       25.4min
 3 uno      h_all       8    n/a (offload)         2.2min              -        2.2min
 3 uno      bell_ghz    7    n/a (offload)         1.9min              -        1.9min
 3 uno      qft         8    n/a (offload)         2.2min              -        2.2min
 3 uno      grover      7    n/a (offload)         6.6min              -        6.6min
 3 esp8266  h_all      13    n/a (offload)        13.0min              -       13.0min
 3 esp8266  bell_ghz   12    n/a (offload)        12.0min              -       12.0min
 3 esp8266  qft        13    n/a (offload)        13.0min              -       13.0min
 3 esp8266  grover      9    n/a (offload)           1.6h    1 pt / 1.1h       28.0min
 3 esp32    h_all      14    n/a (offload)        17.4min              -       17.4min
 3 esp32    bell_ghz   13    n/a (offload)        16.1min              -       16.1min
 3 esp32    qft        14    n/a (offload)        17.4min              -       17.4min
 3 esp32    grover      9    n/a (offload)           1.6h    1 pt / 1.1h       30.0min

per-board totals (all points | excluding TIME-LIMITED points):
  uno        60 pts        1.4h |       1.4h
  esp8266    97 pts   107.7days |       2.4h
  esp32     104 pts    49.7days |       2.7h
GRAND TOTAL 261 points: 157.5days all | 6.5h excluding 10 TIME-LIMITED point(s) (device > 1.0h, flag only; no ceiling set -- owner decision)
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
| 12 | 2.43e-07 / 1.22e-07 | 3.45e-08 / 1.72e-08 | 2.43e-07 / 1.22e-07 | NOT RUN |
| 13 | 2.09e-07 / 1.05e-07 | 3.45e-08 / 1.72e-08 | 2.09e-07 / 1.05e-07 | NOT RUN |
| 14 | 2.38e-07 / 1.19e-07 | 3.45e-08 / 1.72e-08 | 2.38e-07 / 1.19e-07 | NOT RUN |

- **h_all, bell_ghz, qft: all n=1..14 pass**, worst infidelity 2.4e-07 (h_all/qft), 3.4e-08 (bell_ghz). The never-validated points (n=1 h_all/qft; odd n 5,7,9,11,13) all pass.
- **grover: n=2..8 pass, n=9, 10, 11 are above 1e-3** (1.47e-3, 6.47e-3, 2.66e-2; P(marked) stays >= 0.973). n=9,10 were already known. The error grows about 4x per n (float32 accumulation over 3^n gates).
- **grover n=12, 13, 14: NOT RUN.** The run was killed silently at n=12 on an 8.6 GB machine (cause UNVERIFIED, memory is the likely one: n=11 has 3.0 M gates, n=12 about 13 M Qiskit instructions); a retry died the same way. n=13/14 are out of reach on this machine. These n are on the plan only for ESP8266 (n=12, 13 wall) and ESP32 (n=11..13), all TIME-LIMITED points (section 4); by the 4x trend they would also exceed 1e-3.
- Consequence for the experiment: grover points at n>=9 carry a float32 precision caveat on top of the time caveat. Owner decision whether to collect them at all.


## 7. UNVERIFIED list

- ESP8266 usable heap and `largest_block` (assumed about 45-50 KB; the wall n=13 does not depend on it).
- ESP32 `largest_block` = 110 580 B holds for the restart.
- Uno grover stack frame size at n=7 (measured outcome only).
- WDT thresholds (ESP8266 6 s, ESP32 5 s) in `timing_model.WDT_PER_REP_THRESHOLD_S`.
- ESP8266 compile/upload per point (compile = preflight median, upload guessed 15 s) and ESP32 upload 53.4 s (retired telemetry): estimates, not this dataset.
- Grover time model beyond n=9 (extrapolated; ESP32 n=10 never completed).
