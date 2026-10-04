# System design: runner, target board, ESP32 counter, files (2026-10-04)

Status: **design only. No code for the reference path exists yet except the hardware-free pieces
`pc/shared/counter_proto.py`, `counter_sim.py`, `counter_selftest.py` and the UNFLASHED DRAFT
`firmware/counter_esp32/`.** Statements about hardware that come from general knowledge, not from
this repo, are marked **UNVERIFIED**. Repo facts carry `file:line`.

## 0. What stays and what is new

- **Method kept:** every target firmware still times each rep with `micros()` around `run_circuit()`
  and prints it as column `exec_time_us` (`firmware/uno/src/main.cpp:84-100`,
  `firmware/esp8266/src/main.cpp:79-90`, `firmware/esp32/src/main.cpp:77-90`). Unchanged, byte for byte.
- **New:** an ESP32 counter measures the same pulse (the target raises `GPIO_TIMING_PIN` around the
  same call: Uno 7, ESP8266 GPIO5, ESP32 GPIO4). The new dataset records both for every point.
- **Central analysis:** `micros()` minus counter width, per rep, per point, per n, per board.
- All results measured before the counter existed were deleted (git history `af40643`).

## a. Architecture and data flow

```
 pc/run.py (runner, validates + prints plan/ETA)
   |  subprocess (existing, pc/run.py:789)
   v
 sweep script  (pc/phase2_sweep/<board>_sweep.py, owns BOTH serial ports)
   |-- counter port  <---->  counter ESP32 (firmware/counter_esp32, GPIO34 input)
   |-- target port   <---->  target board (pio build/upload, then rows over serial)
   |
   per point (circuit, n):
     1 counter ARM(session, board, circuit, n, reps, min_width, max_width)  -> ARM_ACK
     2 build + upload target (existing build_and_upload)
     3 target runs REPS reps: each rep pulses the pin, prints exec_time_us (micros())
     4 counter streams PULSE frames (seq, rise_us, width_ns, flags) as they happen
     5 sweep reads the target rows (existing read_serial_trials) -> raw.csv, memory_wall.csv, points.csv (unchanged)
     6 counter END -> REPORT (counts, anomaly mask, pcnt count) ; pulses -> ref_pulses.csv, ref_points.csv
     7 post-step: join pulse i with raw.csv rep i (sequence join) -> ref_compare*.csv
```

- **Who owns which port:** the sweep subprocess opens the target port and the counter port, as
  `uno_sweep.py` today owns the target port and calls `la_capture` (`pc/phase2_sweep/uno_sweep.py:733-905`).
  `pc/run.py` never opens a serial port (`pc/run.py` header); it only checks both device files exist and are
  not held (`port_holder_pids`, `pc/run.py:~470`) and passes `--counter-port` through.
- **Startup order:** (1) runner preflight: git state, sleep prevention, both ports free, resume state; (2) sweep
  opens counter, reads a heartbeat, checks counter firmware hash + stored calibration age, (3) optional
  loopback self-test at session start; (4) per-point loop above; (5) at exit END/disarm the counter.
- **Shutdown order:** target first (sweep ends), then counter disarm in a `finally`, then close ports.
- **Ctrl+C:** `KeyboardInterrupt` is already handled inside the sweep (`uno_sweep.py:335`); the point in flight
  keeps its existing semantics (no terminal row, re-run on resume). New rule: the `finally` sends END to the
  counter and writes whatever pulses arrived to `ref_pulses.csv` with `ref_status = aborted`; nothing is joined for an
  unfinished point. `pc/run.py` finishes as today (ledger `interrupted`, `pc/run.py:~795`).
- **Never touched by the counter path:** the target's `micros()` data, status strings, resume logic.

## b. Run orchestration and owner policy

Proposed flags (runner and sweeps): `--ref counter` (default for official runs) and `--counter-port PORT`
(never auto-guessed, like `--port`). `--ref none` selects the counter-less bucket.

**Policy question for the owner (open decision 1).** Recommendation: **official runs REQUIRE the counter**
(`--ref counter`), because the micros()-vs-counter comparison is the central analysis and a point without it
cannot be repaired later. Counter-less runs, if allowed at all, go to the separate `no_ref/` bucket and are
excluded from the central analysis (debugging only).

Behaviour when the reference misbehaves (the target measurement always stays valid):

| Situation | Target data (raw/points/memory_wall) | Reference record | Run continues? |
|---|---|---|---|
| counter missing at start | n/a | refuse to start (required mode) / start in `no_ref` (optional mode) | no / yes |
| counter heartbeat lost mid-point | unchanged, point status as usual | `ref_status = counter_lost`, pulses so far kept | yes, point flagged; operator told |
| counter disconnects (serial error) | unchanged | same, plus issue log line | yes; next point re-checks, stops after 2 consecutive points without counter |
| pulse count != reps | unchanged | `ref_status = count_mismatch`, no join | yes |
| anomaly code 1-9 raised | unchanged | codes stored in `ref_points.csv`, glitch pulses kept with flag | yes |
| target build/upload fails or runtime hang | status as today | `ref_status = no_target_run`; counter disarmed | as today |

The reference problem is logged in the reference files and in `ref_issues.log`; it never rewrites a target
status and is never counted as a Memory Wall (rule from `docs/preflight_report.md` H1 is untouched).

## c. Folder layout and schemas

**Buckets.** `with_la/`, `no_la/` become `with_ref/`, `no_ref/` in `pc/shared/paths.py` (`_la_bucket`, `:46`;
`raw_dir` `:50`; `figures_dir`; `la_dir` becomes `ref_dir`). No data exists in any bucket (verified: no `with_la`
or `no_la` folder under `data/`), so the rename is path-only. Resume never crosses buckets (kept: it is
bucket-local because every path is bucket-local).

```
data/raw/phase2/<board>/<circuit>/with_ref/
    raw.csv  memory_wall.csv  points.csv  sessions.csv  env/<session>.json      (existing, UNCHANGED schemas)
    ref/ref_pulses.csv  ref_points.csv  ref_compare.csv  ref_compare_points.csv  ref_issues.log
    env/<session>.ref.json                                                       (new sidecar)
```

`raw.csv`, `points.csv`, `sessions.csv` keep their columns and `SCHEMA_VERSION = 2`
(`pc/shared/telemetry.py:62`). New file types get their own constants in a new `pc/shared/ref_schema.py`:

| File | Constant | One row per | Columns |
|---|---|---|---|
| `ref_pulses.csv` | `REF_PULSES_SCHEMA_VERSION = 1` | pulse | schema_version, session_id, counter_session, board, circuit, n, seq, rise_us, width_ns, flags |
| `ref_points.csv` | `REF_POINTS_SCHEMA_VERSION = 1` | point | schema_version, session_id, board, circuit, n, reps_expected, pulses_received, pulses_used, ref_status, anomaly_mask, anomaly_codes, min_ns, median_ns, max_ns, report_pulses, pcnt_count, overruns, counter_fw_hash, timestamp_utc |
| `ref_compare.csv` | `REF_COMPARE_SCHEMA_VERSION = 1` | rep | schema_version, session_id, board, circuit, n, rep, micros_us, counter_us, diff_us, diff_pct |
| `ref_compare_points.csv` | same constant | point | schema_version, session_id, board, circuit, n, n_pairs, median_diff_us, mean_diff_us, std_diff_us, iqr_diff_us, max_abs_diff_us, median_diff_pct, ref_status, micros_quantization_us |

`diff_us = micros_us - counter_us` (positive: the board's own timer reads longer). `micros_quantization_us`
records the board's `micros()` tick (4 us on the Uno, 1 us on ESP: README Limitations), so a diff of one tick is
not misread as error. Each writer refuses to append to a file whose `schema_version` differs (same guard as
`pc/shared/telemetry.py:160-175`).

**Join key.** `(session_id, board, circuit, n)` identifies the point; within it, **pulse order = rep order**
(`pulse seq i` pairs with `raw.csv` rep `i`). Rule: pulses flagged glitch are dropped from the pairing; the
remaining count must equal `REPS` (100) or the point is `count_mismatch` and nothing is joined (carried over
from `analysis/la_crosscheck.py` header: refuse rather than guess an offset).

**Environment sidecar** `env/<session>.ref.json` (`REF_ENV_SCHEMA_VERSION = 1`): counter firmware git hash and
`firmware/counter_esp32/src/main.cpp` sha256, counter port, counter heartbeat `free_heap`, pin map
(`IN_DUT`, `GND`), divider values and measured Vout, series/pull-down resistors, calibration result
(ppm, method, date, duration), self-test result and its caveat ("self-loopback only"), WiFi state of the counter.
A sidecar keeps `env/<session>.json` and its schema untouched.

## d. Removed, replaced, kept

| Item | Fate |
|---|---|
| sigrok-cli path `pc/shared/la_capture.py` | replaced by `pc/shared/counter_client.py` |
| `capture_plan.csv`, `analysis/la_capture_plan.py` (sample-rate plan) | removed: the counter has a fixed resolution; only `REPS` is needed |
| `analysis/la_pulses.py` (parses capture files) | removed: pulses arrive as frames; anomaly rules live in the counter and in `counter_sim.py` |
| `analysis/la_crosscheck.py` | **kept in substance** (sequence join, micros comparison, refuse-if-unclean); renamed `ref_crosscheck.py`, reads `ref_pulses.csv` |
| LA docs (`run_checklist.md` LA section, `docs/manual_run_guide.md` LA section) | rewritten for the counter |
| `analysis/la_test.py` | see the Part 4 finding in section h |

**Files that change, in dependency order** (nothing under `firmware/uno|esp8266|esp32|common` changes):

1. `pc/shared/ref_schema.py` (new: constants, column lists, writers/guards)
2. `pc/shared/counter_client.py` (new: serial client over `counter_proto.py`; `counter_sim.py` as test double)
3. `pc/shared/paths.py` (buckets `with_ref`/`no_ref`, `ref_dir`, kwarg `la` -> `ref`) and `paths_test.py`
4. `pc/shared/telemetry.py` (kwarg only; sidecar writer; **no column or SCHEMA_VERSION change**), `telemetry_test.py`
5. `pc/shared/run_history.py`, `pc/run_history.py`, `pc/backfill_run_history.py` (+ tests): `la` -> `ref` in new lines; old ledger lines keep `la`
6. `pc/phase2_sweep/uno_sweep.py`, `esp32_sweep.py`, `esp8266_sweep.py` (`--ref`, `--counter-port`; arm/stop/join hooks replacing `lac.*`; the ESP sweeps gain it) and their `*_test.py`
7. `analysis/ref_crosscheck.py` (renamed `la_crosscheck.py`), `analysis/phase2_uno_run_plots.py`, `analysis/phase2_exec_time_pub.py` (bucket names, comparison plots)
8. `pc/run.py` (`LA_SUPPORTED` -> counter support, `--ref`, `--counter-port`, preflight counter check, ETA adds counter arm cost) and `run_test.py`
9. Docs: `README.md`, `README.th.md`, `run_checklist.md`, `docs/manual_run_guide.md`, `docs/run/*.md`
10. Delete: `pc/shared/la_capture.py`, `la_capture_test.py`, `analysis/la_pulses.py`, `la_capture_plan.py`, `la_test.py`

## e. Wiring (per target board)

Counter pins (draft firmware, **ESP32 DevKit**): capture input `IN_DUT = GPIO34`, self-test pair
`GEN_OUT = GPIO25` -> `IN_SELF = GPIO35` (permanent jumper), LED GPIO2.

| Target | Signal / target pin | Level | Counter pin | Network between | Notes |
|---|---|---|---|---|---|
| Uno | D7 (`uno/src/main.cpp:27`) | **5 V** | GPIO34 | divider R1 2.2 kohm (D7 to node), R2 3.9 kohm (node to GND), node -> 330 ohm -> GPIO34 | Vout 3.2 V (3.0 V at 4.7 V supply); R2 doubles as pull-down. Thevenin 1.41 kohm + 330 ohm, C 20 pF (UNVERIFIED) -> tau 35 ns; rising/falling 50 % crossing 25/23 ns, width error about 2-4 ns |
| ESP8266 | GPIO5 = D1 (`esp8266/src/main.cpp:27`) | 3.3 V | GPIO34 | direct via 330 ohm, plus 10 kohm pull-down at the counter side | do not use GPIO1/3 (UART0) |
| ESP32 | GPIO4 (`esp32/src/main.cpp:28`) | 3.3 V | GPIO34 | direct via 330 ohm, plus 10 kohm pull-down | second ESP32 needed as the counter |

- **Common GND** between target and counter: mandatory; signal only otherwise. **Power:** each board from its own
  USB port; the counter's 3V3 is never connected to the target.
- **Pull-down:** the input-only pads GPIO34-39 have no internal pull resistors (UNVERIFIED), and a 3.3 V target's pin
  floats during reset/upload, so a 10 kohm pull-down at the counter keeps the line low and avoids phantom pulses
  (the 3.9 kohm divider resistor does this on the Uno).
- **Pin restrictions checked (general ESP32 knowledge, UNVERIFIED):** GPIO34/35 are input-only (right for a capture
  input that must never drive the line); GPIO6-11 are the flash bus (unused); strapping pins 0, 2, 5, 12, 15 are
  avoided for signals (GPIO2 only drives the LED after boot); GPIO25 is an ordinary output (also DAC1, unused).
  The self-test pair uses GPIO35, **not** the DUT input pin GPIO34, so the self-test never exercises the exact pad the
  DUT is wired to (limitation, section f gate G4 covers it with a dummy-pulse step).
- **Level shifter alternative:** a BSS138 module works but is not needed.

## f. Readiness gates and bring-up

**Go / no-go before the first official point** (all must pass; record the result in `run_log.md`):

| Gate | Check |
|---|---|
| G1 data state | `data/raw/phase{2,3}` empty or only the new dataset; `run_history.jsonl` has `restart` and `purge` events |
| G2 git | clean tree, tag recorded, `pc/run.py --dry-run` clean for every board x circuit |
| G3 tests | all suites pass (pre-existing failures listed separately) |
| G4 counter standalone | firmware flashed from a clean build, heartbeat OK, loopback self-test passes at all widths (S1 result) |
| G5 counter + dummy pulses | a second MCU/generator drives the real input pad GPIO34 through the real wiring, known widths measured |
| G6 calibration | clock calibration done and stored (`docs/counter_design.md` section 15); result and ppm in the sidecar |
| G7 wiring | wiring table checked with a multimeter: divider Vout, GND continuity, pull-down, no connection to 3V3 |
| G8 ports | target and counter device files confirmed with the owner, not auto-guessed; neither held (lsof) |
| G9 environment | sleep prevention on (`pmset`), USB hub powered, ESP32 counter WiFi off or dashboard-only per policy |
| G10 ETA | `python pc/run.py --plan` shown and accepted; no ceiling decision pending |

**Bring-up order:** (1) counter standalone (S1: self-loopback); (2) counter + dummy pulses on GPIO34;
(3) counter + **Uno pilot** (cheapest, slowest-changing, 5 V path): h_all n=2..4 only, compare micros() vs counter,
inspect a few reps by hand; (4) full Uno; (5) ESP8266; (6) ESP32 (second ESP32 as counter); (7) Phase 3 only
if the owner decides it needs the counter (section g).

## g. Open decisions for the owner

1. **Counter required or optional** for official runs (recommended: required; counter-less points in `no_ref/`, excluded from the central analysis).
2. **Per-point time ceiling.** Current recorded decision: none, run to the memory wall. Facts in `docs/ceiling_facts.md` (no value is proposed here beyond the earlier note).
3. **ESP32 watchdog threshold** (`timing_model.WDT_PER_REP_THRESHOLD_S`, 5.0 s). Finding (section h): the installed Arduino-ESP32 core's own `sdkconfig` has the task watchdog at 5 s but checks only the CPU0 idle task, while the sketch's loop task runs on CPU1; the 5.0 s per-rep rule has no basis there. Recommendation: set the ESP32 threshold to `None` and classify `watchdog_suspected` from a reset signature instead (below).
4. **Does Phase 3 use the counter?** Phase 3 times a serial round trip with `micros()` on the board
   (`firmware/*/src_offload/main_offload.cpp`), and the offload firmware does not toggle `GPIO_TIMING_PIN`
   (`GPIO_TIMING_PIN` appears only in the Phase 2 `main.cpp` files). The counter would therefore see nothing in
   Phase 3, and giving it something to see needs a firmware change (pulse at request send / response receive),
   which is out of scope here. Even then it would measure only the board-side interval, not the PC simulation.
   **Recommendation: no counter in Phase 3**; keep `micros()` round-trip timing and report it as such.
5. Counter protocol items found in the draft review (`docs/counter_design.md` section 13): `max_width_s` is u16
   (18 h limit, plan has 22.8 h reps), heartbeat time is whole seconds (too coarse for calibration), no ARM start timeout.
   They need a protocol decision before S2: widen `max_width_s` to u32 and add a 64-bit microsecond field.

## h. Housekeeping findings (PC only, read-only)

- **`analysis/la_test.py` failure** (`crosscheck: clean point not flagged`, fails at the pre-restart commit `8fa119f`
  too): the test writes the MCU rows with `_write_raw_rows(...)` into `sp.raw_csv_path(board, circuit, phase)` whose
  default bucket is `no_la/` (`analysis/la_test.py:35`), but `analysis/la_crosscheck.py` reads `la=True`, i.e. `with_la/`,
  since the 2026-09-22 bucket split (`load_mcu_exec_times`, `la_crosscheck.py:145-157`). The row for `h_all` n=2 finds no MCU
  data, is refused, and `median_relative_diff` is empty, so the next line's `float('')` raises. It is a stale test of the LA path,
  which this design removes. Recommendation: **delete with the LA path** (`la_test.py` is replaced by `ref_crosscheck_test.py`);
  a one-line fix (`la=True` in the helper) would only prolong code that is going away.
- **ESP32 5.0 s watchdog threshold.** Basis in the repo: the comment at `pc/shared/timing_model.py` (`WDT_PER_REP_THRESHOLD_S`)
  says "ESP-IDF default Task WDT is 5 s" and marks it UNVERIFIED. Checked read-only against the installed core
  (`framework-arduinoespressif32/tools/sdk/esp32/sdkconfig`): `CONFIG_ESP_TASK_WDT_TIMEOUT_S=5`,
  `CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0=y`, `CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU1` not set, interrupt WDT 300 ms
  (only trips if interrupts stay disabled). The Arduino loop task normally runs on CPU1 (UNVERIFIED), so a compute-bound rep does
  not starve the watched idle task. The firmware calls `yield()` only between reps (`esp32/src/main.cpp:77`). A retired run that
  completed a 7 s/rep point without reset also contradicts the threshold. **Proposed rule (not applied):** ESP32 threshold `None`;
  classify `watchdog_suspected` when the serial stream shows a reset signature (boot banner `rst:` / the CSV header line
  reappearing mid-point) instead of from a predicted per-rep time; ESP8266 keeps 6 s until evidence (its firmware disables only the
  software WDT around a rep, `esp8266/src/main.cpp:84-88`, the hardware WDT stays, about 8 s UNVERIFIED).
