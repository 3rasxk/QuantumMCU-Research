# Audit: Phase 2 and Phase 3 coverage and consistency

Scope: boards Uno, ESP8266, ESP32; circuits h_all, bell_ghz, qft, grover; the `with_ref` bucket of `data/raw/phase2` and `data/raw/phase3`
(the only bucket that exists). Nothing under `data/archive/` and no pre-restart data. Read-only: nothing in `data/raw/` was touched and no
board was run. Line numbers are at commit `0d94d2e` (the base of branch `audit-phase2-phase3`) unless stated.
Tags: **OBSERVED** = computed from files in the repo; **INTERPRETATION** = my reading, not tested; **UNVERIFIED** = not backed by data on disk.
Scripts: `analysis/audit_coverage.py` (table), `analysis/audit_consistency.py` (per-point statistics), `analysis/audit_circuit_equivalence.py`
(circuit equality); outputs `data/derived/phase2_phase3_coverage.csv`, `phase2_phase3_point_stats.csv`, `circuit_equivalence.csv`,
`grover_iterations_equivalence.csv`.

## 0. Headline

1. **The premise "Phase 2 reaches n=7 but Phase 3 only n=3" is not what the data on disk show.** For all 12 board x circuit rows, Phase 3
   has ok data at **every n where Phase 2 has ok data** (column "P2 ok missing in P3" is empty in every row), and goes beyond it. I could not
   find where an "n=3" Phase 3 range comes from (UNVERIFIED; possibly older retired data or an in-progress session).
2. **The real gaps are different:** (i) n=1 of h_all and qft was never collected in either phase (12 points); (ii) Phase 3 stops short of
   "Phase 2 wall + 3" for 7 of 12 rows (25 missing points in total, of which 13 are beyond-wall points that exist only because the
   range was chosen ad hoc per invocation); (iii) a few rows hit real limits (grover time on the ESP boards).
3. **Other things that matter more for a crossover than coverage** (section 3): Phase 3 round-trip latency is noisy (IQR/median > 20 % in 97
   of 177 points; Phase 2 only 3 of 113), the Phase 3 floor of 3.3-6.8 ms at small n is set by the PC and the link, 125 of 173 Phase 3
   points have a cold first request (more than 2x the median), several series mix firmware versions, and the offload timing is baud-specific
   (only 115 200 was run).
4. Corrections to the task text: the per-point ceiling in code is **2 h** (`POINT_TIME_CAP_S`, `pc/shared/timing_model.py:404`), not 24 h
   (`CEILING_S = 14400` at `:67` is documented as unused for Phase 2; 24 h appears only as a display tier in `pc/shared/eta.py`); the offload
   protocol limit is n <= 32 because the sampled outcome is a uint32 (`firmware/common/protocol.hpp:8`), tighter in practice by the PC safety cap n <= 22
   (`pc/phase3_offload/sweep.py:106`).

## 1. Coverage table (Step 1)

Row = board x circuit. "ok n" = points whose terminal record (`memory_wall.csv` Phase 2, `session_log.csv` Phase 3) is `ok`. Walls count only with positive evidence
(`build_overflow`, `malloc_failed`); hangs, resets and timeouts are never walls. "cap" = ok points that stopped at the 2 h per-point cap with fewer than 100 reps
(`time_capped reps=k/100` in `points.csv`); "skip" = points not run because one rep or request alone would exceed the cap or the PC memory (`skipped_*`).
Firmware hash = `firmware_source_hash` of the session env JSON (first 6 hex digits; hash of `firmware/common` + the board's `src` or `src_offload`).
Schema version is 2 in every file of both phases (column in the CSV). Baud: 115 200 only. crc_error and timed_out are counted over all rows of `raw.csv`.

<!-- COVERAGE-TABLE:BEGIN -->
| board | circuit | P2 ok n | P2 wall (evidence) | P2 time-capped / skipped n | P2 reps | P2 fw hashes | P3 ok n | P3 baud | P3 reps | P3 crc / timed out | P3 fw hashes | overlap n | P2 ok missing in P3 | P3 beyond P2 wall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uno | h_all | 2-7 | 8 (build_overflow) | - | 100 | 7feb4a | 2-22 | 115200 | 100 | 0 / 0 | 8ce753 | 2-7 | - | 8-22 |
| uno | bell_ghz | 2-7 | 8 (build_overflow) | - | 100 | 7feb4a | 2-22 | 115200 | 100 | 0 / 0 | 8ce753 | 2-7 | - | 8-22 |
| uno | qft | 2-7 | 8 (build_overflow) | - | 100 | 7feb4a | 2-22 | 115200 | 100 | 0 / 0 | 8ce753 | 2-7 | - | 8-22 |
| uno | grover | 2-7 | 8 (build_overflow) | - | 100 | 7feb4a | 2-10 | 115200 | 100 | 0 / 0 | 8ce753 | 2-7 | - | 8-10 |
| esp8266 | h_all | 2-12 | 13 (malloc_failed) | - | 100 | 6a19c5 | 2-15 | 115200 | 100 | 0 / 0 | 54bef9 | 2-12 | - | 13-15 |
| esp8266 | bell_ghz | 2-12 | 13 (malloc_failed) | - | 100 | 6a19c5 | 2-15 | 115200 | 100 | 0 / 0 | 54bef9 | 2-12 | - | 13-15 |
| esp8266 | qft | 2-12 | 13 (malloc_failed) | - | 100 | 6a19c5 | 2-15 | 115200 | 100 | 0 / 0 | 54bef9 | 2-12 | - | 13-15 |
| esp8266 | grover | 2-10 | none observed | cap 9-10; skip 11-16 | 4-100 | 5413c4 6a19c5 6cb0e9 | 2-13 (cap 11-13; skip 14-15) | 115200 | 2-100 | 0 / 0 | 1b7b5c e33508 | 2-10 | - | - |
| esp32 | h_all | 2-13 | 14 (malloc_failed) | - | 100 | 5f10cc | 2-14 | 115200 | 100 | 0 / 0 | 1e404b | 2-13 | - | 14 |
| esp32 | bell_ghz | 2-13 | 14 (malloc_failed) | - | 100 | 5f10cc | 2-14 | 115200 | 100 | 0 / 0 | 1e404b | 2-13 | - | 14 |
| esp32 | qft | 2-13 | 14 (malloc_failed) | - | 100 | 5f10cc | 2-14 | 115200 | 100 | 0 / 0 | 1e404b | 2-13 | - | 14 |
| esp32 | grover | 2-12 | none observed | cap 11-12; skip 13-18 | 1-100 | 447814 5f10cc | 2-13 (cap 11-13; skip 14-18) | 115200 | 2-100 | 0 / 0 | 1e404b | 2-12 | - | - |
<!-- COVERAGE-TABLE:END -->

Reading it (OBSERVED):
- **Overlap** is the full Phase 2 ok range in every row; **no Phase 2 ok n is missing in Phase 3**.
- Walls: Uno n=8 (`build_overflow`, all four circuits), ESP8266 n=13 and ESP32 n=14 (`malloc_failed`, h_all, bell_ghz, qft). **grover on the ESP boards has no wall** (it never got that far).
- Phase 3 goes beyond the Phase 2 wall as far as n=22 on the Uno, n=15 on the ESP8266, n=14 on the ESP32 for h_all/bell_ghz/qft.
- Reps are 100 everywhere except the grover points marked "cap" (Phase 2 ESP8266 n=9, 10: 37 and 4 reps; ESP32 n=11, 12: 13 and 1; Phase 3 n=11, 12, 13 on both ESP boards: 42, 9, 2).
- Phase 3: 0 CRC errors and 0 timeouts in every row.
- Firmware hashes: Phase 2 grover has 2-3 hashes on the ESP boards; Phase 3 ESP8266 has 3 (section 3.7). **No point has more than one hash or schema.**

## 2. Root cause of every gap (Step 2)

Classes: (a) config / range mismatch, (b) real limit with evidence, (c) run failure, (d) unknown.
"Required" = the rule requested in the task: Phase 2 from the minimum n to the wall; Phase 3 every Phase 2 ok n plus wall+1..wall+3.

| # | gap | cause and evidence | class |
|---|---|---|---|
| G1 | n=1 of **h_all and qft** missing in **both** phases, all boards (12 points) | The sweeps default `--n-start` to 2 (`pc/phase2_sweep/uno_sweep.py:382`, `esp8266_sweep.py`, `esp32_sweep.py`, `pc/phase3_offload/sweep.py:294`, all `default=2`) while the plan's minimum for h_all/qft is 1 (`pc/run.py:107-112` `MIN_VALID_N`; `pc/shared/experiment_plan.py:19`). `pc/run.py` applies `MIN_VALID_N` only for `--fresh` runs (`effective_n_start_for_fresh`, `pc/run.py:222`, used under `if args.fresh` at `:784`). Of the 93 live invocations in `data/run_history.jsonl` since 2026-10-04 only 3 used `--fresh` (two Uno h_all Phase 2 test runs at 16:47 and 16:51 UTC, ledger `ok: 7` = n=1..7, whose data are not in `data/raw`, fate UNVERIFIED; and an ESP8266 grover Phase 3 run, minimum n 2 anyway); 69 of 93 had no `--n-start`, so the official sessions (from 19:17 UTC) started at the script default 2. No n=1 row exists in any `memory_wall.csv`/`session_log.csv`. | (a) |
| G2 | Phase 3 **ends before Phase 2 wall + 3** on 7 rows: Uno grover (ok 2-10, required to 11), ESP8266 h_all/bell_ghz/qft (ok 2-15, required to 16), ESP32 h_all/bell_ghz/qft (ok 2-14, required to 17) | There was no rule for the Phase 3 range. `docs/design/experiment_plan.md:18-21` says Phase 3 uses the same n range as Phase 2 (no wall), `pc/shared/experiment_plan.py:57-64` (`plan_n_values`) returns the Phase 2 range for Phase 3, and `PHASE3_GROVER_N_MAX = 10` (`:41`) caps grover. In practice the range was chosen per invocation: `docs/run/phase3.md:47-50` recommends `--n-max 8` (Uno), `13` (ESP8266), `14` (ESP32), `10` (grover); the ledger (`data/run_history.jsonl`) shows ESP8266 Phase 3 run with `--n-max 15`, ESP32 with `--n-max 14`, Uno grover with `--n-max 10`, Uno h_all/bell_ghz/qft with no `--n-max` (script default `N_SAFETY_CAP = 22`, `pc/phase3_offload/sweep.py:106,314`). So Uno reaches 22 by accident of the default and the ESP boards stop at wall+2 and wall+0. | (a) |
| G3 | **Uno grover Phase 3 n=11** (part of G2) | Capped by `--n-max 10` (above). Feasible: ESP boards ran n=11 with 42 reps under the 2 h cap (`session_log.csv`: `frames_served` 42); the cost is PC-side, identical for every board. Needs 42, not 100, reps (2 h cap) | (a) range; reps limit is (b) |
| G4 | Phase 3 grover on ESP8266 and ESP32 **n >= 14** (not run; 5 `skipped_sim_cost_infeasible` rows on the ESP32, 2 on the ESP8266) | `data/raw/phase3/esp32/grover/with_ref/predicted.csv`: model time per request 13 038 s at n=14 (calibrated 7 709 s; > 2 h cap, `timing_model.py:404`), 55 543 s at n=15, PC memory for n >= 17 (10.3 GB circuit for 8.6 GB RAM). Measured: n=13 ran 2 requests in 2 h (`points.csv`: `time_capped reps=2/100`), 1 836.7 s and 3 216.4 s per request in two sessions. The ESP8266 n=14, 15 rows carry the older reason "PC memory about 182.5 GB" (written before grover n >= 12 was simulated in slices, commits `d94c9b9` then `db27e2e`); with the current model the reason would be the time cap. **The n >= 14 limit is a model estimate (`ESTIMATE_not_measured`), not a measurement.** `--force-infeasible` (1 request, 3-4 h at n=14) could measure it; not planned | (b) |
| G5 | Phase 2 grover on **ESP8266 n >= 11 and ESP32 n >= 13** (12 `skipped_compute_infeasible` rows) | One rep exceeds the 2 h per-point cap: `predicted.csv` (e.g. ESP32 n=13: 10 h 43 min per rep). Points just below the cap have few reps (ESP8266 n=9: 37, n=10: 4; ESP32 n=11: 13, n=12: 1). No memory wall was reached, so grover has **no Phase 2 wall** on the ESP boards | (b) |
| G6 | Phase 2 grover ESP8266 n=8, 9 first attempts failed, ESP32 n=12 failed once | `points.csv` `failure_type=watchdog_suspected` (`watchdog_reset_loop=true,reset_count=4`) for ESP8266 n=8 (session 20261005T160709) and n=9 (20261006T084326): the hardware watchdog (about 8.4 s) reset the board; the points were re-run after the firmware feed in `firmware/esp8266/src/main.cpp` (uncommitted at run time). ESP32 n=12: `serial_error ... [Errno 6] Device not configured` (session 20261008T221112), re-run in 20261009T072959. Both end with ok data | (c), resolved |
| G7 | Phase 3 ESP8266 grover n=12, 13 needed many attempts | Ledger: 9 invocations killed (`returncode=-9`, SIGKILL, PC out of memory building the whole gate list; `pc/shared/timing_model.py:486-490`), port-not-found, then success with the sliced simulation (`chunked_sim.py`). Both points exist now (9 and 2 requests) | (c), resolved |
| G8 | ESP32 and ESP8266 Phase 2 **idle runs / early stops** (e.g. ESP32 `20:37` and `esp8266 12:20, 14:33` without end event) | Ledger entries with no end event (operator interruption); no point lost, resume skipped completed points | (c), harmless |

No gap is category (d) except the origin of the "n=3" premise (section 0, UNVERIFIED).
Protocol and firmware limits checked and **not** the cause of any gap: n field is one byte (`protocol.hpp:6`, `req[1] = (uint8_t)N_QUBITS`); outcome is u32 so n <= 32; PC safety cap n <= 22; firmware keeps `g_latency_us[REPS]` (800 B at 100 reps) so no buffer depends on n; response timeout is `max(5 s, 3 x model request time)` (`timing_model.py` `phase3_response_timeout_ms`), after commit `5076c76` fixed a 5 s timeout that timed out half of grover n=9 requests - **all data on disk have 0 timeouts**, so older firmware's 5 s timeout did not cost points in the final data.
PC-side simulation time (`simulate_and_sample`, `pc/phase3_offload/sweep.py:196`) is the only thing that limits grover in Phase 3 (G4) and it did cause SIGKILLs, not timeouts (G7).

### Was Phase 3 collected with the current firmware and protocol?

Protocol: unchanged since `7a22d20` (2026-09-13), `git log -- firmware/common/protocol.hpp pc/phase3_offload/protocol.py`. Offload firmware: changed three times during the Phase 3 window (`27b6094` counter pin 2026-10-07 16:28; `5076c76` per-point reps and response timeout 18:34; `579fe78` 64-bit latency 2026-10-08 05:13).
I hashed the current offload sources the way `pc/shared/telemetry.py:_firmware_build_hash` does and compared with the session hashes (OBSERVED):

| board | hash of HEAD `src_offload` + common | Phase 3 series hashes | verdict |
|---|---|---|---|
| Uno | 8ce753... | 8ce753... (all circuits) | current |
| ESP32 | 1e404b... | 1e404b... (all circuits) | current |
| ESP8266 | e33508... | h_all/bell_ghz/qft: **54bef9...**; grover n=2-11: **1b7b5c...**; grover n=12, 13: e33508... | **older firmware** for 3 of 4 series |

Phase 2 against the current tree: Uno `7feb4a...` current; ESP8266 HEAD `6a19c5...` equals h_all/bell_ghz/qft and grover n=2-7, while grover n=8 (`6cb0e9...`) and n=9, 10 (`5413c4...`) ran with **uncommitted** watchdog code that exists only in the working tree (`5413c4...` is the hash of today's dirty tree); ESP32 HEAD `5f10cc...` equals n <= 11, grover n=12 (`447814...`) ran with the **uncommitted** 64-bit timer (`firmware/esp32/src/main.cpp` `esp_timer_get_time`).
INTERPRETATION: none of these edits changes what is between `t0` and `t1` except adding a timer interrupt (about microseconds per second) on the ESP8266 grover n >= 8 points, so the effect on timing is probably small; **UNVERIFIED**, it was not measured. Whatever is collected next should come from committed firmware (section 5).

## 3. Consistency audit beyond coverage (Step 3)

### 3.1 What is timed

- **Phase 2** (`firmware/*/src/main.cpp` at HEAD: Uno `:87-89`, ESP32 `:82-84`, ESP8266 `:85-87`): `t0 = micros()` immediately before `run_circuit()`, `t1` immediately after (the uncommitted ESP32 edit uses the 64-bit `esp_timer_get_time()` instead). `run_circuit()` = `qsim_init0` + the circuit's gate loops on the board (`firmware/common/circuits.hpp`). Excluded: state allocation (before the loop), serial printing, heap reads (the heap read is before the pin goes high), build/upload/boot. The same interval is high on `GPIO_TIMING_PIN` for the counter. Unit: us per rep, one value per rep, 100 reps. Output of the circuit is **not** read, sampled or sent.
- **Phase 3** (`firmware/*/src_offload/main_offload.cpp`, ESP32 `:73-104`): the board sends a 4-byte request `[0xAA][n][circuit][crc]`, `t0 = micros()` is taken **just before** `Serial.write`, `t1` when the 6-byte response has been received (or the timeout), so the timed interval = request frame on the wire (868 us at 115 200 baud for 10 bytes) + PC wake-up and read + **`simulate_and_sample`: a Qiskit circuit is rebuilt, run with Aer statevector, one outcome sampled with `np.random.choice`** (`pc/phase3_offload/sweep.py:196-210`; uncached by design) + response frame. The board does **no** circuit work. Excluded: `delay(20)` between reps (`:104`), build/upload/boot. 64-bit counter handles `micros()` wrap (`579fe78`). Unit: us per request; `avg_round_trip_latency_s` in `points.csv` is a per-request mean (audit check B2d).

Comparable for a crossover? Yes, for the question "how long until I have the result of this circuit at n: on the board, or by asking the PC over a serial link", under these conditions (INTERPRETATION):
- Phase 2 ends with the full statevector in board RAM; Phase 3 ends with **one sampled basis state** returned. They deliver different things. Phase 2 has no sampling cost and Phase 3 has no cost for sending the state back; sampling 2^n probabilities is one more sweep and is small next to the gate loops (not measured).
- Phase 3 contains no on-board work at all (the board is a client), so "offload latency" is link + PC time. A real offload design would also need the PC to be available; the PC here is a laptop (8.6 GB RAM) running Aer, so the crossover is specific to this PC and to Aer, not a property of the board alone.
- Phase 3 is measured at **one baud rate** (3.5).
- Both are "wall time for one run", median of 100 reps, same unit (us); for grover at n >= 11 the number of reps drops (cap) in both phases.

### 3.2 Reps, warm-up, statistic, units

| item | Phase 2 | Phase 3 | evidence |
|---|---|---|---|
| reps per point | 100 (`REPS`, `timing_model.py:30`, firmware `#define REPS`); fewer only for time-capped grover | 100 requests; fewer under the 2 h cap (`phase3_point_reps`) | coverage table |
| warm-up reps excluded | none (`WARMUP_REPS = 0`, `pc/shared/telemetry.py:514`) | none | rep 0 is in `raw.csv` |
| cold first rep | rep 0 > 2x median in 20 of 111 points (mostly ESP32 at tiny n) | rep 0 > 2x median in **125 of 173** points (first request pays Aer initialisation, INTERPRETATION) | `analysis/audit_consistency.py` (computed ad hoc) |
| statistic used by the analysis | median, IQR | median, IQR | `analysis/` (Phase 4 report) |
| unit | us | us | |
| per-rep jitter | IQR/median small (3 points above 20 %, all ESP32 at medians <= 3 us) | **97 of 177 points above 20 %** (Uno 46 of 72, ESP8266 39 of 54, ESP32 12 of 51); 90 of those 97 have median < 20 ms, i.e. in the flat floor | `phase2_phase3_point_stats.csv` |

The median hides the cold first request, but a **mean** would not; use the median for both phases (as the analysis does) and say so.
Outliers (OBSERVED): crc_error and timed_out are 0 for every Phase 3 point and every Phase 2 point is a "ok" point; the Phase 3 noise is **host jitter** around a floor of about 3.4 ms (Uno), 3.3 ms (ESP8266), 6.8 ms (ESP32) at n <= 4 (median of the 12 per-point medians), which is also where all crossovers with the Uno and ESP8266 lie. INTERPRETATION: for crossovers inside that band, n* is only meaningful to about +-1 n; a repeat of those Phase 3 points would quantify it (not done).

### 3.3 Circuit definitions

Phase 2 builds the circuit in `firmware/common/circuits.hpp`; Phase 3 builds it with `build_qiskit_circuit` in `analysis/phase1_compare.py:102-148` (imported at `pc/phase3_offload/sweep.py:71`). **Same circuit, same meaning of n** (OBSERVED, `analysis/audit_circuit_equivalence.py`): the number of H, CNOT and (controlled) phase gates is identical for h_all, bell_ghz, qft at n = 2..14 and for grover at n = 2..10 (48 of 48 points; the Qiskit grover build above n = 10 is memory heavy, so n >= 11 is covered by the closed-form check below), and the Grover iteration count `floor(pi/4 sqrt(2^n))`, computed in float32 in C++ (`circuits.hpp:158-160`) and float64 in Python (`phase1_compare.py:129`), is **equal for every n = 2..22**. n always means the number of qubits (state size 2^n). The qft has no final swaps in both (`do_swaps=False`). Phase 1 had measured the same equivalence numerically (infidelity <= 1e-3 except grover n >= 9, which fails on the PC build, a property of float32 accumulation, not of a different circuit).

### 3.4 Differences inside a phase

- Phase 2 / 3 series spanning more than one firmware hash: Phase 2 ESP32 grover (2), ESP8266 grover (3); Phase 3 ESP8266 (3 series, 3 hashes, see section 2). 8 points were collected twice (`points.csv` keeps both ok rows, `raw.csv` only the last), and Phase 3 ESP32 grover n=13 has two runs that differ by 1.75x (1 836.7 s vs 3 216.4 s per request, 2 requests each): a time-capped point with 2 requests is not repeatable to better than that.
- Phase 3 grover for n >= 12 is simulated in slices (`chunked_sim.py`), n <= 11 in one piece; the code states the results are identical bit for bit at n=9 (docstring in `analysis/phase1_compare.py:154-156`); the timings of the two regimes are only comparable if the slicing overhead is small (UNVERIFIED).

### 3.5 Baud rate

Only 115 200 baud was run in Phase 3 for every board and circuit (`session_log.csv`, `raw.csv` `baud_rate`); `--bauds` defaults to `[115200]` and other rates were never run. The frame is 10 bytes, 868 us at 115 200 baud; at higher rates that term becomes about 87 us at 1 Mbaud, but the floor is 3.3-6.8 ms, so **most of the floor is not the wire** (INTERPRETATION from the numbers; UNVERIFIED which part is PC wake-up, Aer start-up or the 20 ms-paced firmware loop). Report the crossover **at 115 200 baud** and state that it was not tested at other baud rates. A second baud rate would need new Phase 3 points for every row (not planned; cost in section 5).

### 3.6 Known data validity issues (confirmed or corrected)

- **Counter**: confirmed uncalibrated. All 60 session sidecars (`env/*.ref.json`) have `"calibration": {}` and `"selftest": "self-loopback only"`. A PC-clock comparison exists (`data/calibration/counter_20261004.json`, +17.5 +- 1.9 ppm, 2026-10-04) but is not linked to any session and "says nothing about the target board's own clock".
- **Phase 3 samples one shot** on the PC (`np.random.choice`, `sweep.py:208`) and **never checks it** against a reference: confirmed. The Phase 3 number is a latency, not a correctness result.
- **"Phase 3 reference data may be invalid": corrected.** They are not invalid and not simulated: every Phase 3 session was run with `--ref counter` (the counter is a physical ESP32 on the timing pin; the offload firmware raises `GPIO_TIMING_PIN` for one round trip, `docs/design/system_design.md:192`), and `ref_points.csv` records 110 points `ok`, 60 `count_mismatch`, 5 `anomaly`, 2 `counter_lost`, 2 `arm_failed` (OBSERVED, sum over the 12 series). What is inconsistent is the **documentation**: `docs/data_audit.md` (check E3) and `docs/analysis/paper_plan.md:132` state a policy that Phase 3 runs without the counter and treat the Phase 3 counter data as excluded, while `docs/design/system_design.md:192` records the opposite decision (2026-10-07, "yes, optionally"). The owner needs to pick one; I did not use Phase 3 counter data. INTERPRETATION: running `--ref counter` adds host-side work during Phase 3 that could add to the host jitter in 3.2; not measured.
- Phase 2 `micros()` vs counter is also only between two uncalibrated clocks (Phase 4 report, section 6).

### 3.7 What the crossover can and cannot show (INTERPRETATION)

- Rows with a crossover at n <= wall (Phase 4 report): Uno 3.7-6.0, ESP8266 7.1-9.9, ESP32 12.2-12.6 (qft/bell_ghz), grover ESP8266 3.7 and ESP32 8.9 (Uno: already faster offloaded at n=2); **ESP32 h_all has none up to n=13** (offload 1.11x slower at n=13). The local measurement stops at the wall (n=13 on the ESP32), so for ESP32 h_all the crossover, if any, lies at or beyond the wall and **cannot be measured locally**: beyond the wall the choice is not offload-or-local, it is offload-or-nothing. More Phase 3 points beyond the wall (requested rule) document how offload latency grows there; they do not add a local point.
- Phase 3 floors on the Uno/ESP8266 are about 3.3 ms and Phase 2 of those boards reaches that range at n=4-7, so those crossovers sit where Phase 3 is noisiest (3.2).

## 4. What I changed (Step 4, code and config only)

| file | change |
|---|---|
| `config/sweep_ranges.toml` (new) | the single source of truth: per-circuit minimum n, per-board wall n with its evidence, `offload_beyond_wall = 3`, reps 100, statistic, baud, protocol/PC/time caps, and the Phase 3 circuit limit (grover n <= 13) with its evidence. Phase 2 range = min n .. wall n; Phase 3 = min n .. min(wall + 3, circuit limit, caps) |
| `pc/shared/sweep_ranges.py` (new) | loader (`tomllib`, no new dependency; PyYAML is not installed), `n_range`, `planned_n`, `n_values`, `phase3_gaps`, `validate` |
| `pc/phase2_sweep/{uno,esp8266,esp32}_sweep.py`, `pc/phase3_offload/sweep.py` | `--n-start` / `--n-max` default to `None` = the config range of that (board, circuit); explicit flags still override. Phase 3 `--bauds` default from the config; `--n-max` above 32 is refused |
| `pc/run.py` | `MIN_VALID_N` and the preflight default n-max come from the config (no behaviour change except that the displayed defaults now match the sweeps) |
| `pc/shared/experiment_plan.py`, `pc/shared/eta_test.py` | plan ranges / ETA come from the config; `phase1_n_values` uses the Phase 2 ranges only (Phase 3 uses the Qiskit side only, so Phase 1 need not validate n beyond the walls); two test expectations updated (Phase 3 grover on the ESP32 is 2..13, h_all 1..17) |
| `pc/shared/sweep_ranges_test.py` (new, 59 checks) | fails if Phase 3 planned n do not cover every Phase 2 ok n for any board x circuit (reads `data/raw`), if the config rules are violated, if the sweeps stop reading the config, and has a negative control; I confirmed by mutation (grover limit set to 9) that it fails |
| `pc/plan_collection.py` (new) | read-only dry run: planned list vs `data/raw`, missing points, per-board time estimate, the exact commands |

Not changed (real limits, category b): grover n >= 14 in Phase 3 and n >= 11 / 13 in Phase 2 on the ESP boards. Not changed: anything under `data/raw/`, `firmware/`.
Not done (needs your decision): the stale text in `docs/design/experiment_plan.md:18-21` and `docs/run/phase3.md:47-50` (both have uncommitted edits in your working tree, so I did not edit them); they describe the old "same range" rule.

## 5. Planned re-collection (additive only, nothing is run until you confirm)

Missing = planned by the config minus points that already have a terminal record. Output of `pc/plan_collection.py`: **25 points**.

| board | Phase 2 | Phase 3 |
|---|---|---|
| Uno | h_all n=1, qft n=1 | h_all n=1, qft n=1, grover n=11 (42 reps under the 2 h cap) |
| ESP8266 | h_all n=1, qft n=1 | h_all n=1, qft n=1, h_all / bell_ghz / qft n=16 |
| ESP32 | h_all n=1, qft n=1 | h_all n=1, qft n=1, h_all / bell_ghz / qft n=15, 16, 17 |

Estimated time (`pc/shared/eta.py`, sequential, ESTIMATE): Uno 1 h 59 min (all of it the grover n=11 point), ESP8266 8 min, ESP32 15 min; **total about 2 h 21 min**. The estimate uses the measured compile/upload medians of the existing points.
Commands are in the final reply and printed by `.venv/bin/python pc/plan_collection.py`. They keep the `--ref counter --counter-port tcp:5055` flags so the new points land in the same `with_ref` bucket (resume never crosses buckets); they resume, skip done points and append.

Before running, decide (I did not touch any of this):
1. **Commit the firmware first.** The working tree has uncommitted firmware edits (`firmware/esp8266/src/main.cpp` watchdog feed, `firmware/esp32/src/main.cpp` 64-bit timer) that are already part of some existing points; collecting new points from a dirty tree adds yet another hash to each series.
2. Phase 3 ESP8266 h_all/bell_ghz/qft were collected with older offload firmware; the new n=16 points will not match their hash (INTERPRETATION: no effect on t0..t1, UNVERIFIED).
3. Optional, not in the list: repeat the Phase 3 points near each crossover (host jitter, section 3.2), a second baud rate (3.5), `--force-infeasible` grover n=14 (measures the limit instead of estimating it), re-collection of the grover series under one committed firmware.

## 6. UNVERIFIED

- Where the "Phase 3 only to n=3" figure comes from.
- Effect of the uncommitted watchdog interrupt (ESP8266 grover n >= 8) and of the 64-bit timer (ESP32 grover n=12) on timing.
- Whether the Phase 3 floor (3.3-6.8 ms) is PC wake-up, Aer start-up or firmware pacing; whether `--ref counter` adds host jitter.
- The Phase 3 grover limit at n >= 14 is a model estimate; n=14 was never attempted.
- Timing of sliced (n >= 12) versus one-piece (n <= 11) Aer runs.
- Behaviour at any baud rate other than 115 200.
