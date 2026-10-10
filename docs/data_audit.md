# Data audit: Phase 1-3, all boards, all circuits

Audit date 2026-10-10, repository state `pre-run-uno-v8-45-g965c43c-dirty` (HEAD `965c43c`, 62 changed or untracked paths in the
working tree, none of them under `data/raw/`). Read-only: nothing under `data/raw/`, `data/archive/` or `firmware/` was touched, no
hardware was accessed. Everything the files do not show is marked UNVERIFIED. Numbers are produced by `analysis/audit_data.py`
(tests: `analysis/audit_data_test.py`) into `data/processed/audit/*.csv`; this report quotes those tables.

Reading guide: OBSERVED = a number computed from the CSVs; INTERPRETATION = a reading the numbers do not contradict and that was
not tested here. Severity: Critical (a result cannot be used), High (changes what a claim may say), Medium (a gap to close or
state), Low (hygiene).

## 1. Gating and inventory

**Provenance task: complete.** It was done earlier in this working session, read-only, and its results are re-checked here
by the automated checks S1, S3, E2, E3.

| question | result | evidence |
|---|---|---|
| What is on `counter_port: tcp:5055`? | The counter's own WiFi link: the ESP32 counter firmware is a TCP *client* that connects to the PC; the PC runs a TCP *listener*. It is not the simulator and not a serial-to-TCP bridge. | `firmware/counter_esp32/src/main.cpp:60-68` (`WiFiClient net`), `:429-445` (`net.connect(PC_HOST, PC_PORT)`); `pc/counter/client.py:37-60` (`TcpServerTransport`), `:147-151` (`make_transport`); the only live path is `pc/counter/hooks.py:132`; `SimTransport` (`client.py:154`) is used only by tests |
| Could any session's reference come from the simulator? | No. 0 sessions are REFERENCE-INVALID (check E2). 25 Phase 2 sessions are REFERENCE-PHYSICAL; 35 Phase 3 sessions are REFERENCE-EXCLUDED by policy (below). | `sessions.csv`, column `reference_state` |
| Counter firmware hashes | 4 values, all protocol version 2. `53b557a22c92` = commit `2cfc36a` (4 Uno Phase 2 sessions, 2026-10-04); `2609e5d04463` = a version of `firmware/counter_esp32/src/main.cpp` between `2cfc36a` and `3dd3a9e` that was never committed (13 Phase 2 + 6 Phase 3 sessions: Uno and ESP8266); `de8c90c716db` = `3dd3a9e` (3 Phase 3 ESP8266 sessions); `bdd71b1e7af9` = `579fe78` = working tree (8 Phase 2 ESP32 + 26 Phase 3 sessions). The hash is of the counter *source file* at run time (`pc/counter/hooks.py:196`), not of the flashed binary. | `sessions.csv` columns `counter_fw_sha`, `counter_proto` |
| Snapshot commit and manifest | `2981e39` (post-purge data, 257 files + ledger) and `c074d48` (`docs/data_snapshot_manifest.txt`, 344 sha256 lines) | `git log` |

**Sessions.** 60 sessions: 25 Phase 2, 35 Phase 3, 2026-10-04 19:17 UTC to 2026-10-09 23:35 UTC, all on one host OS.

| phase | board | sessions | first_utc | last_utc | commits | fw_hashes | dirty | ledger_matched |
|---|---|---|---|---|---|---|---|---|
| 2 | esp32 | 8 | 2026-10-08T21:01 | 2026-10-09T07:30 | 7fae083 | 2 | 8 | 8 |
| 2 | esp8266 | 9 | 2026-10-05T10:44 | 2026-10-06T10:28 | d4e26f2 | 3 | 9 | 9 |
| 2 | uno | 8 | 2026-10-04T19:17 | 2026-10-05T02:52 | d4e26f2 | 1 | 8 | 8 |
| 3 | esp32 | 8 | 2026-10-09T04:56 | 2026-10-09T23:35 | 7fae083 | 1 | 8 | 8 |
| 3 | esp8266 | 23 | 2026-10-07T09:37 | 2026-10-08T04:30 | 5d08452, 5076c76, 8e3c678, 012c934, 3dd3a9e, 579fe78, d94c9b9, d71a602, db27e2e, 27b6094 | 3 | 23 | 23 |
| 3 | uno | 4 | 2026-10-08T12:19 | 2026-10-08T13:09 | 7fae083 | 1 | 4 | 4 |

- **UNMATCHED sessions: 0.** Every session matches a live, non-dry-run `started` entry of `data/run_history.jsonl` within 30 s
  (check S1). Ledger end events of those invocations: completed 37, failed 12, interrupted 2, no end event 9. A failed or interrupted
  invocation can still have produced points; the points themselves are what the completeness matrix classifies.
- **REFERENCE-INVALID sessions: 0.** Phase 3 reference data exist and are excluded by policy (below), not because they are simulated.
- **Tracked in git:** 60 of 60 (since commit `2981e39`; before it all of `data/raw/phase2` and most of `data/raw/phase3` were untracked).
- **`git_dirty`:** true for 60 of 60. `git_dirty` is computed from `git status --porcelain`, which also lists untracked files
  (`pc/shared/telemetry.py:369-372`), so it cannot show on its own whether tracked code was modified.
- **Firmware source hash vs the run commit's tree:** differs for 3 sessions (ESP32 Phase 2 grover n=12, ESP8266 Phase 2 grover n=8 and
  n=9..10). Hash recipe: `pc/shared/telemetry.py:416-430`. 36 sessions equal the hash of the current working tree.
- **Sleep prevention** (`pmset` check recorded in the env JSON): true for 60 of 60. No other host-load indicator is recorded
  (UNVERIFIED whether the PC was otherwise idle during Phase 3).

**Phase 3 reference data.** They exist for all 12 Phase 3 point sets: 35 sessions, 179 compared points, 19 033 counter pulses
for 17 308 requests; per-point `ref_status`: ok 110, count_mismatch 60, anomaly 5, counter_lost 2, arm_failed 2; 352 lines of
`ref_issues.log`. Two corrections to the premise: (1) the offload firmware **does** toggle the timing pin, high for one round trip, on
all three boards (`firmware/uno/src_offload/main_offload.cpp:72,91`, `firmware/esp32/src_offload/main_offload.cpp:72,92`,
`firmware/esp8266/src_offload/main_offload.cpp:74,94`); (2) every Phase 3 session was started with `--ref counter` (check E3), and
`docs/design/system_design.md:192` records the opposite of the current policy ("DECIDED 2026-10-07: yes, optionally"). By the policy
that Phase 3 runs without the counter, all Phase 3 reference data are excluded from every counter statistic below.

## 2. Completeness matrix

Plan: `pc/shared/experiment_plan.py:19` (minimum n per circuit), `:32` (predicted walls), `:41` (Phase 3 grover cap), `:57`
(`plan_n_values`). Phase 3 baud planned: `[115200]` only (`docs/run/phase3.md:174`, `docs/manual_run_guide.md:114`: other rates are
UNVERIFIED and were never run); collected: 115200 only. Long table for heat maps: `data/processed/audit/completeness.csv`
(columns phase, board, circuit, n, baud, planned, category, terminal_status, reps, reps_flag, attempts, failed_attempt_types,
superseded_rows, dup_rep_rows, session_id, firmware_hash).

| phase | board | planned | planned_missing | ok | ok_100_reps | ok_capped | wall | time_limited | sim_cost_skipped | extra_unplanned | failed_attempts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | esp32 | 54 | 2 | 47 | 45 | 2 | 3 | 6 | 0 | 4 | 3 |
| 2 | esp8266 | 50 | 2 | 42 | 40 | 2 | 3 | 6 | 0 | 3 | 5 |
| 2 | uno | 30 | 2 | 24 | 24 | 0 | 4 | 0 | 0 | 0 | 4 |
| 3 | esp32 | 50 | 2 | 51 | 48 | 3 | 0 | 0 | 5 | 8 | 0 |
| 3 | esp8266 | 47 | 2 | 54 | 51 | 3 | 0 | 0 | 2 | 11 | 0 |
| 3 | uno | 30 | 2 | 72 | 72 | 0 | 0 | 0 | 0 | 44 | 0 |

- **Planned but neither collected nor classified: 12 points**, all `n=1` of `h_all` and `qft` on every board in both phases
  (`MIN_N` is 1 for these circuits, the sweeps started at n=2). Check B1c.
- **Not in the plan but collected:** Phase 2: time-limited entries beyond the predicted wall (ESP32 grover n=15..18, ESP8266 grover
  n=14..16). Phase 3: Uno h_all/bell_ghz/qft up to n=22 (plan: n<=8), ESP8266 h_all/bell_ghz/qft n=14..15, grover beyond n=10 on
  ESP8266 and ESP32 (`--force-infeasible`, `docs/run/phase3.md`).
- **Reps:** every ok point has exactly 100 reps except 10 that carry a recorded `time_capped reps=k/100 cap_s=7200` note: Phase 2
  ESP8266 grover n=9 (37 reps) and n=10 (4), ESP32 grover n=11 (13) and n=12 (1); Phase 3 ESP8266 and ESP32 grover n=11 (42),
  n=12 (9), n=13 (2). Check B1a. The per-point cap is 7 200 s (`pc/shared/timing_model.py:404`), not 24 h (see finding M4).
- **Duplicates and superseded rows:** 0 duplicated `(n, rep)` rows; 0 points with several terminal rows. But `points.csv` keeps
  superseded `ok` rows: 8 points were collected twice (table in section 3, check F1).
- **Interrupted points leave no partial raw rows** (check B1b): no raw rows exist for any point whose terminal status is not ok.

## 3. Correctness checks

Result counts: FAIL 6, INFO 2, PASS 19. PASS means the property holds on all data; FAIL is a finding (section 4); INFO is a fact to know;
UNVERIFIED is listed in section 7.

| id | result | check | evidence |
|---|---|---|---|
| A1 | PASS | telemetry files carry SCHEMA_VERSION=2, one version per file | 24 point sets |
| A2a | PASS | points.csv status / failure_type are members of telemetry.STATUS_TYPES / FAILURE_TYPES |  |
| A2b | PASS | terminal-record statuses (memory_wall.csv / session_log.csv) match the known status vocabulary |  |
| A3 | PASS | no_ref and with_ref never mixed (one bucket present; env bucket == directory; flag consistent) | buckets present: ['with_ref']; inconsistent sessions: [] |
| A4a | PASS | no duplicated (n, [baud], rep) rows in any raw.csv (resumed runs only appended) |  |
| A4b | PASS | points.csv start_utc non-decreasing (append order = time order) |  |
| B1a | PASS | every ok point has exactly 100 reps, or a recorded time_capped note | 290 ok points; 10 capped with a recorded note; mismatches:  |
| B1b | PASS | no raw rows for a point whose terminal status is not ok (interrupted points leave no partial rows) |  |
| B1c | FAIL | every planned point is collected or explicitly classified | p2 esp32/h_all n=1; p2 esp32/qft n=1; p2 esp8266/h_all n=1; p2 esp8266/qft n=1; p2 uno/h_all n=1; p2 uno/qft n=1; p3 esp32/h_all n=1; p3 esp32/qft n=1; p3 esp8266/h_all n=1; p3 esp8266/qft n=1; p3 uno/h_all n=1; p3 uno/qft n=1 |
| B1d | PASS | no point has several terminal rows (superseded) | 0 points |
| D1 | PASS | every wall row has positive evidence (build_overflow with compile_ram_pct > 100, or a malloc failure attempt) |  |
| D2 | PASS | no watchdog / hang / time-limited point is classified as a wall | 0 offending rows |
| D3 | INFO | failed attempts of type watchdog_suspected / serial / hang are recorded as failures (not walls) | 2 attempts: esp8266/grover p2 n=8 watchdog_suspected: watchdog_reset_loop=true,reset_count=4 / esp8266/grover p2 n=9 watchdog_suspected: watchdog_reset_loop=true,reset_count=4 |
| E1 | PASS | counter-ok points: pulses used equals the reps present in raw.csv (capped points have fewer than 100) | 45 points;  |
| E2 | PASS | no session with a simulated / unknown / missing counter reference | 0 sessions:  |
| E3 | FAIL | Phase 3 sessions recorded without a counter reference (policy: Phase 3 runs without the counter) | 35 of 35 Phase 3 sessions used --ref counter |
| S1 | PASS | every session matches a live, non-dry-run 'started' entry of data/run_history.jsonl | 0 unmatched:  |
| S2 | PASS | session env files are tracked in git | 0 untracked |
| S3 | FAIL | firmware source hash of every session equals the hash of the run commit's firmware tree | 3 sessions differ (uncommitted firmware at run time): esp32:4478147465f99625, esp8266:5413c474786bad15, esp8266:6cb0e9ea301922b4 |
| S4 | FAIL | git_dirty false (clean working tree at collection) | 60 of 60 sessions dirty (git status --porcelain counts untracked data files, pc/shared/telemetry.py:369-372, so this flag cannot show code changes alone) |
| S5 | FAIL | one firmware source hash per (board, phase, circuit) series | ('esp32', 2, 'grover'): 2 hashes; ('esp8266', 2, 'grover'): 3 hashes; ('esp8266', 3, 'grover'): 2 hashes |
| S6 | FAIL | failed points counted in sessions.csv equal the failed rows in points.csv (every failure has a row) | p2 esp32/grover: sessions.csv n_points_failed=1, points.csv failed rows=0 |
| F1 | INFO | repeat data: points collected more than once (points.csv ok rows); agreement of the totals | 8 repeated points; max device_exec_s ratio 1.75; raw.csv keeps only the last run's reps, so per-rep repeatability cannot be assessed |
| B2a | PASS | ref_compare_points.csv medians/IQR equal a recomputation from ref_compare.csv rows | 376 values compared; 28 IQR values equal the 'exclusive' quantile convention (pc/counter/crosscheck.py:42-45 statistics.quantiles) instead of numpy linear used by the charts; true mismatches:  |
| B2d | PASS | units: device_exec_s is a total over the point's reps (>= sum of the board-timed reps); Phase 3 avg_round_trip_latency_s equals the per-request mean of e2e_latency_us (pc/phase3_offload/sweep.py:547,598) | 290 points;  |
| B2b | PASS | Uno compile_ram_pct equals compile_ram_used_bytes / 2048 (rounded to 0.1) |  |
| B2c | PASS | medians quoted in docs/analysis/**/*.md equal a recomputation from raw.csv | 24 values;  |

Notes on individual items (the checks above carry the numbers):

- **(a) schema.** All telemetry files carry `SCHEMA_VERSION=2`; no file mixes versions; only the `with_ref` bucket exists, so no_ref and
  with_ref data cannot be mixed; resumed runs only appended.
- **(b) recompute.** `points.csv`/`sessions.csv` store no medians. The medians quoted in `docs/analysis/**` (24 values) equal a
  recomputation from `raw.csv` (check B2c). `README.md` and `run_log.md` quote no number from the new dataset (finding M2, M3). Counter
  comparison medians match (376 values compared, check B2a), except that 28 IQR values were stored with the *exclusive* quantile
  convention (`pc/counter/crosscheck.py:42-45`) while the charts use numpy's linear convention; the differences are at most 0.006 us.
  **Units (check B2d, 290 points):** in `points.csv` `device_exec_s` is the **wall time of the whole request/rep loop of the point**
  (a total, `pc/phase3_offload/sweep.py:547`), `pc_sim_s_total` is the **sum** of the PC's simulation times over the requests
  (`:595`), `serial_transfer_s_total` is `max(device_exec_s - pc_sim_s_total, 0)` (`:597`), i.e. a remainder that includes the
  firmware's `delay(20)` between requests (`firmware/*/src_offload/main_offload.cpp:103-106`), not a measured transfer, and
  `avg_round_trip_latency_s` is **per request** (equals the mean of `e2e_latency_us` / 1e6).
- **(c) physical sanity.** Median time per rep never decreases with n (0 non-monotonic points of 113). Doubling per qubit: see
  section 5. Point-level quality (all 100 reps are used, WARMUP_REPS=0; rules fixed in `analysis/audit_data.py`):

| flag | points | of |
|---|---|---|
| non_monotonic (median below previous n) | 0 | 113 |
| Tukey outlier-heavy (> 5 % of reps) | 57 | 113 |
| dev_frac > 5 % (reps off the median by > max(1 %, 2 resolutions)) | 15 | 113 |
| drift (last 20 vs first 20 reps > 10 %) | 1 | 113 |
| bimodal heuristic | 0 | 113 |
| warm-up flag (rep 0 > 2 x median) | 20 | 113 |
| median below 20 x micros() resolution | 11 | 113 |

  Boards of the flagged points: warm-up flag {'esp32': 16, 'esp8266': 4}; dev_frac flag {'esp32': 12, 'uno': 3}; median below 20 x resolution {'esp32': 10, 'esp8266': 1}. The Tukey rule
  flags 57 points mainly because the IQR is 0 for most points (reps are identical or differ by one tick), so any deviating rep counts as
  an outlier; the secondary measure `dev_frac` is more informative. IQR / median has a median of 5e-4 (ESP32 up to 0.5 at 3 us), so IQR bars
  on log charts are mostly invisible. No bimodal point. One drift flag (ESP32 qft n=2, 3 us). `micros()` resolution: **Uno 4 us**
  (`~/.platformio/packages/framework-arduino-avr/cores/arduino/wiring.c:100-102`, prescaler 64 at `:255-266`, VERIFIED in the core source);
  ESP32 `micros()` returns `esp_timer_get_time()` (`framework-arduinoespressif32/cores/esp32/esp32-hal-misc.c:166-169`) and ESP8266
  `system_get_time()` (`framework-arduinoespressif8266/cores/esp8266/core_esp8266_wiring.cpp:180-182`), both in microseconds;
  the underlying timer resolution of those two is UNVERIFIED. No point has a median below its resolution.
- **(d) walls.** All 10 Phase 2 wall rows have positive evidence: Uno `build_overflow` with `compile_ram_pct` 109.8-110.1 for all four
  circuits at n=8; ESP8266 `malloc_failed` at n=13 (h_all, bell_ghz, qft); ESP32 `malloc_failed` at n=14 (h_all, bell_ghz, qft); each has a
  `failure_type=malloc|build` attempt in `points.csv` (check D1). No watchdog, hang or time-limited point is a wall (D2). **ESP8266
  `watchdog_reset_loop`**: grover n=8 (session `20261005T160709`, 54 s wall, `reset_count=4`) and n=9 (session `20261006T084326`, 258 s):
  recorded as `failed` attempts with `failure_type=watchdog_suspected` in `points.csv`, counted in `sessions.csv`, and listed in the ledger
  as `watchdog_suspected(watchdog_reset_loop=true,reset_count=4)`; they have **no `memory_wall.csv` terminal row and no raw rows**; the
  points were later re-run to completion (n=8 with 100 reps, n=9 stopped by the cap at 37 reps) after a firmware change (hardware watchdog feed,
  `firmware/esp8266/src/main.cpp:31-42`, `:79-83`, uncommitted). **ESP32 `serial_error ... [Errno 6] Device not configured`**: grover n=12 in
  session `20261008T221112`; recorded in `sessions.csv` (`n_points_failed=1`) and in the ledger point counts only: **no `points.csv` row,
  no `memory_wall.csv` row, no raw rows** (check S6); n=12 was re-run in a later session (1 rep, time-capped). Neither is a wall.
  **Time-limited:** 12 Phase 2 points (ESP32 grover n=13..18, ESP8266 grover n=11..16) are `skipped_compute_infeasible` (not run); the
  ceiling in force is **2 h per point** (`pc/shared/timing_model.py:404`); `CEILING_S = 14400` (`:67`) is documented as no longer used by
  Phase 2. A 24 h ceiling does not exist in the code (24 h appears only as a display tier in `pc/shared/eta.py:229`).
- **(e) reference counter, valid Phase 2 sessions (25 sessions, 125 point entries).** Counter statuses of the 93 joined points with at
  least 10 pairs: ESP32 45 ok (one further ESP32 point, grover n=12, has a single pair and is excluded); **ESP8266 26 anomaly, Uno 21 anomaly + 1 count_mismatch** (the counter flagged an anomaly, mostly
  extra pulses; the pairing by pulse width still matched 100 pairs). Pulse counts equal reps for all 45 counter-ok points (E1).
  Counter firmware heterogeneity: ESP32 sessions all ran `bdd71b1e7af9`; Uno and ESP8266 ran the older `53b557a22c92`/`2609e5d04463`:
  the counter software differs between boards. Calibration is **empty in every sidecar**, the self-test is "self-loopback only"; a
  +17.5 +/- 1.9 ppm calibration against the PC clock exists in `data/calibration/counter_20261004.json` but is not recorded in the
  sessions. Differences are relative to this counter. Table:

| board | points | counter_ok | median_diff_us_min | median_diff_us_max | pct_min | pct_max | within_micros_resolution |
|---|---|---|---|---|---|---|---|
| esp32 | 45 | 45 | -1.3 | 1.064e+04 | -37.5 | 0.002 | 32 |
| esp8266 | 26 | 0 | -8.144 | -6.925 | -36.24 | -0.055 | 0 |
| uno | 22 | 0 | -1.463e+05 | -6.738 | -9.825 | -0.488 | 0 |

- **(f) repeatability.** 8 points were collected twice (`points.csv` keeps both `ok` rows; `raw.csv` keeps only the last run's reps, so no
  per-rep repeatability exists). Totals: Uno Phase 2 7 points, `device_exec_s` of the two runs agree within 3.5 %; **Phase 3 ESP32
  grover n=13: 1 836.7 s vs 3 216.4 s per request (x1.75), both runs 2 requests**.

| phase | board | circuit | n | runs | sessions | device_exec_s | device_exec_max_over_min | avg_round_trip_s | avg_rt_max_over_min |
|---|---|---|---|---|---|---|---|---|---|
| 2 | uno | bell_ghz | 6 | 2 | 20261004T192129;20261005T023225 | 2.215;2.292 | 1.035 |  |  |
| 2 | uno | bell_ghz | 7 | 2 | 20261004T192129;20261005T023225 | 2.607;2.605 | 1.001 |  |  |
| 2 | uno | h_all | 2 | 2 | 20261004T191738;20261005T015412 | 2.02;2.017 | 1.001 |  |  |
| 2 | uno | h_all | 4 | 2 | 20261004T191738;20261005T015412 | 2.064;2.061 | 1.001 |  |  |
| 2 | uno | h_all | 5 | 2 | 20261004T191738;20261005T015412 | 2.347;2.346 | 1 |  |  |
| 2 | uno | h_all | 6 | 2 | 20261004T191738;20261005T015412 | 3.01;3.01 | 1 |  |  |
| 2 | uno | qft | 6 | 2 | 20261004T193028;20261005T015512 | 4.469;4.461 | 1.002 |  |  |
| 3 | esp32 | grover | 13 | 2 | 20261009T120915;20261009T233506 | 3674.259;6433.783 | 1.751 | 1836.6802;3216.4449 | 1.751 |

- **(g) Phase 3 consistency.** 17 206 requests, 0 CRC errors, 0 timeouts, no failed or retried point. Frame time at 115 200 baud:
  (4 + 6 bytes) x 10 bits / 115 200 = 868 us per request (`sweep.py:245,262`); the minimum observed round trip is 1 324 us (Uno), 1 752 us
  (ESP8266), 4 206 us (ESP32). At n <= 4 the median round trip is 3.3-6.8 ms of which the PC simulation is 2.7-2.9 ms; the remainder beyond
  frame time and PC simulation is about 0 for Uno and ESP8266 and 3.1 ms for ESP32. The PC simulation share of the round trip at n >= 8
  is 0.89 (Uno), 0.79 (ESP8266), 0.64 (ESP32) (medians). Time **outside** the timed round trip has a median of 31.8 ms (ESP8266), 34.2 ms (ESP32) and 40.8 ms (Uno) per request (`delay(20)` plus host-side latency); in 6 points the PC's simulation total exceeds the board's own round-trip sum by up to
  0.5 % (clock difference; on the Uno consistent with its `micros()` running slow, see section 5).

| board | points | requests | crc | timeouts | min_rt_us | frame_us | outside_median_us | rt_us | pc_sim_us | beyond_frame_and_sim_us | pc_sim_share_of_round_trip_median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| esp32 | 51 | 4853 | 0 | 0 | 4206 | 868.1 | 3.418e+04 | 6755 | 2910 | 3078 | 0.6 |
| esp8266 | 54 | 5153 | 0 | 0 | 1752 | 868.1 | 3.177e+04 | 3252 | 2785 | -20.3 | 0.8 |
| uno | 72 | 7200 | 0 | 0 | 1324 | 868.1 | 4.08e+04 | 3415 | 2735 | -283.1 | 0.9 |

- **(h) Phase 1.** `data/raw/phase1/infidelity_tvd.20261003T111917Z.csv` (51 rows, h_all n=1..14, bell_ghz n=2..14, qft n=1..14, grover
  n=2..11) is the validation for the current plan; `infidelity_tvd.20261004T091042Z.csv` adds grover n=12. The un-timestamped
  `infidelity_tvd.csv` is an older file (September) that still contains the retired circuits qpe and steane_encode and fewer n; it is
  not the current validation. Pass criterion `infidelity <= 1e-3` (`analysis/phase1_compare.py:43`). h_all, bell_ghz, qft: all pass,
  max infidelity 2.4e-7. **Grover fails for n >= 9**: n=9 1.47e-3, n=10 6.47e-3, n=11 2.66e-2, n=12 0.109 (depth 161 399 / 711 251 /
  2 985 991 / 12 795 101). Infidelity / depth is about 9e-9 per gate at n=8..11 (OBSERVED), consistent with float32 rounding accumulating over
  depth (INTERPRETATION). The boards ran grover up to n=12 (Phase 2 ESP32) and n=13 (Phase 3), so the largest board runs have no Phase 1 row
  at n=13. These tables validate the **PC build** of the simulator against Qiskit; **no board-level correctness data exist**: Phase 2 `raw.csv`
  holds timings and heap, never a state or outcome; in Phase 3 the board times the round trip and checks frame CRC only.
- **(i) stale statements in the docs.** See findings M2-M5, L5, L6.

## 4. Findings, ranked

**Critical: none.** All 290 ok points (113 Phase 2, 177 Phase 3) trace to a live ledger entry, a tracked session and a 100-rep (or
recorded time-capped) raw block with no duplicates.

**High**

- **H1. The firmware changed inside data series.** ESP8266 Phase 2 grover: n=2..7 under firmware hash `6a19c55beaadc693` (committed state),
  n=8 under `6cb0e9ea301922b4` (matches neither any commit nor the current working tree: **code state of that session cannot be
  reconstructed**), n=9..10 under `5413c474786bad15` (equals the current uncommitted working tree). The changes add a 1 s timer1 interrupt that feeds
  both watchdogs and remove the `ESP.wdtDisable()` window around the circuit (`firmware/esp8266/src/main.cpp:31-42,79-83,99-106`, uncommitted);
  its timing cost is stated as "a few microseconds per second" in a comment and is UNVERIFIED. ESP32 Phase 2 grover n=12 ran under
  `4478147465f99625` which times with the 64-bit `esp_timer_get_time()` (`firmware/esp32/src/main.cpp:83-92`, uncommitted) while n<=11 used 32-bit
  `micros()`; the stated reason is that a rep above 71.6 min would wrap (the n=12 median, 4.52e9 us, is above 2^32 us). The ESP8266 Phase 3 grover series also has two firmware
  hashes (n=2..11 vs n=12..13). Checks S3, S5. A paper must state the firmware per point or re-collect under one committed state.
- **H2. Phase 3 reference data conflict with the stated policy** (check E3; section 1). 179 points with counter data exist; they are
  excluded here. Documentation (`docs/design/system_design.md:192`) says the opposite and the offload firmware does toggle the pin.
- **H3. The counter reference is clean only for the ESP32.** Every compared Uno and ESP8266 Phase 2 point is flagged by the counter
  (48 of 48: 26 anomaly on the ESP8266, 21 anomaly and 1 count_mismatch on the Uno), and the counter firmware differs across boards (section 3e), so a cross-board counter comparison is confounded by the counter
  software and the counter is not calibrated. See section 5 for what the differences look like.

**Medium**

- **M1.** 12 planned points are missing: n=1 of h_all and qft, all boards and phases (check B1c).
- **M2.** `README.md:50-56` states "No hardware data exists in the restarted dataset yet ... Phase 3 (offload) has not been run on any
  board": contradicted by 60 sessions.
- **M3.** `run_log.md` has no entry after 2026-10-04 (last rows `:273-274`); none of the 60 sessions (2026-10-04 19:17Z to 2026-10-09) is
  recorded there.
- **M4.** Ceiling documentation: `docs/design/ceiling_facts.md:9-10` says no ceiling, "run to the memory wall"; the code enforces a 2 h
  per-point cap (`pc/shared/timing_model.py:404`) and 12 Phase 2 points were skipped under it. The cap is not 24 h.
- **M5.** The ESP32 grover serial-error attempt (n=12) has no `points.csv` row (check S6; section 3d).
- **M6.** Repeat data: the only per-point repeat with a Phase 3 comparison disagrees by x1.75 (ESP32 grover n=13); `raw.csv` keeps only the
  last run, so no per-rep repeatability exists; `points.csv` keeps superseded `ok` rows (8 points).
- **M7.** Wall evidence exists for 3 of 4 circuits on the ESP boards: ESP8266 and ESP32 grover reach the 2 h cap before the memory limit
  (limits table below), so their wall is untested.
- **M8.** Phase 1: grover infidelity exceeds the 1e-3 criterion for n >= 9 (section 3h); the un-timestamped Phase 1 file is stale.
- **M9.** Small-n timing quality on the ESP32 (section 3c): 10 points with a median below 20 x resolution, 20 points with a rep 0 above
  2 x the median (mostly ESP32).
- **M10.** Anonymity: 24 files under `data/raw/` contain an absolute path with a user name (`sessions.csv`: `env_json_path`) and 60 contain
  serial device names; raw data cannot be released for double-blind review without scrubbing.

**Low**

- **L1.** `git_dirty` carries no information (true for 60 of 60; counts untracked files).
- **L2.** Counter IQR convention differs from the charts' (28 of 376 stored values; <= 0.006 us).
- **L3.** The timing model's constants come from retired data (`pc/shared/timing_model.py:179-186`); measured / estimate has a median of 1.05-1.11
  per board and a maximum of 4.7 (ESP32 small n); it is an ESTIMATE, never a result.
- **L4.** Tukey outlier counting is degenerate for IQR=0 data (reported with `dev_frac`).
- **L5.** `README.md:44-48` hardware table (FPU column, 80 KB SRAM for the ESP8266, 320 KB for the ESP32) quotes no source; clock rates are
  recorded in the env JSON (`f_cpu` 16 / 80 / 240 MHz, VERIFIED as build settings, not measured); the FPU row is UNVERIFIED in this repository.
  `docs/report/paper_outline.md:28` quotes H/CNOT cost ratios (6.6x Uno, 25x ESP8266, 0.8x ESP32) taken from the retired-data fit.
- **L6.** The pre-run wall predictions (`pc/shared/experiment_plan.py:32`, commit `80aef1a`, 2026-10-03 18:26 +07:00) were written before any data
  of the new set (first session 2026-10-04 19:17 UTC) but are **not independent of retired observations**: `MEASURED_WALL_N = {uno: 7, esp8266: 12,
  esp32: 13}` existed since `30b9718` (2026-09-19) and the predicted walls are exactly those values + 1; the ESP32 prediction rests on a
  110 KB largest block seen in retired data (`docs/design/experiment_plan.md:69-72`).

## 5. Analysis

### 5.1 Time vs n (OBSERVED)

Slope = fitted slope of log2(median) vs n over the last five 100-rep points of each series (reference: 1 doubling per qubit = cost proportional to
the 2^n amplitudes at a fixed gate count). `ratio_*` = median(n) / median(n-1).

| board | circuit | n_first | n_last | fit_range | slope_doublings_per_qubit | ratio_min | ratio_median | ratio_max | ratio_last |
|---|---|---|---|---|---|---|---|---|---|
| uno | h_all | 2 | 7 | 3..7 | 1.249 | 2.294 | 2.352 | 2.859 | 2.294 |
| uno | bell_ghz | 2 | 7 | 3..7 | 1.108 | 2.087 | 2.207 | 2.351 | 2.125 |
| uno | qft | 2 | 7 | 3..7 | 1.245 | 2.345 | 2.37 | 6.616 | 2.37 |
| uno | grover | 2 | 7 | 3..7 | 2.588 | 5.198 | 5.365 | 6.9 | 6.9 |
| esp8266 | h_all | 2 | 12 | 8..12 | 1.142 | 2.173 | 2.288 | 3 | 2.173 |
| esp8266 | bell_ghz | 2 | 12 | 8..12 | 1.074 | 1.962 | 2.069 | 2.141 | 2.074 |
| esp8266 | qft | 2 | 12 | 8..12 | 1.225 | 2.183 | 2.32 | 8.857 | 2.309 |
| esp8266 | grover | 2 | 8 | 4..8 | 2.692 | 4.489 | 5.625 | 8.268 | 8.268 |
| esp32 | h_all | 2 | 13 | 9..13 | 1.13 | 1.75 | 2.177 | 2.296 | 2.163 |
| esp32 | bell_ghz | 2 | 13 | 9..13 | 1.182 | 1.5 | 2.267 | 2.451 | 2.169 |
| esp32 | qft | 2 | 13 | 9..13 | 1.217 | 2.087 | 2.274 | 3.667 | 2.435 |
| esp32 | grover | 2 | 10 | 6..10 | 3.004 | 4.115 | 6.752 | 8.667 | 8.667 |

- h_all, bell_ghz, qft: slopes 1.07-1.25; grover: 2.59 (Uno), 2.69 (ESP8266), 3.00 (ESP32). Time per rep never decreases with n.
- INTERPRETATION: slopes above 1 for h_all (n gates) and qft (n + n(n-1)/2 gates) are in the direction a growing gate count gives;
  grover's slope reflects its gate count growing about 2^(n/2) iterations x a multi-controlled-phase gate list that itself grows with n
  (`pc/shared/timing_model.py:114-176`). Not separated from fixed per-call overhead or memory effects.
- **Model estimate vs measured** (`tm.expected_exec_time_us`, an ESTIMATE from retired data): measured / estimate per series:

| board | circuit | points | median | min | max |
|---|---|---|---|---|---|
| esp32 | bell_ghz | 12 | 0.976 | 0.861 | 2.745 |
| esp32 | grover | 11 | 1.136 | 1.019 | 4.713 |
| esp32 | h_all | 12 | 1.01 | 1 | 3.179 |
| esp32 | qft | 12 | 1.119 | 0.952 | 3.683 |
| esp8266 | bell_ghz | 11 | 0.973 | 0.945 | 1.127 |
| esp8266 | grover | 9 | 1.722 | 1.471 | 3.729 |
| esp8266 | h_all | 11 | 1.019 | 1 | 1.099 |
| esp8266 | qft | 11 | 1.076 | 1 | 2.696 |
| uno | bell_ghz | 6 | 1.081 | 1.001 | 1.109 |
| uno | grover | 6 | 1.685 | 1.395 | 2.188 |
| uno | h_all | 6 | 1.078 | 1 | 1.209 |
| uno | qft | 6 | 1.164 | 1 | 1.897 |

### 5.2 Limits (OBSERVED) and the pre-run prediction

| board | circuit | last_ok_n | limit_n | limit_kind | evidence | predicted_wall_n | matches_prediction | watchdog_attempts |
|---|---|---|---|---|---|---|---|---|
| uno | h_all | 7 | 8 | memory | build_overflow, compile_ram_pct=109.9 | 8 | True | 0 |
| uno | bell_ghz | 7 | 8 | memory | build_overflow, compile_ram_pct=110.1 | 8 | True | 0 |
| uno | qft | 7 | 8 | memory | build_overflow, compile_ram_pct=109.8 | 8 | True | 0 |
| uno | grover | 7 | 8 | memory | build_overflow, compile_ram_pct=110.0 | 8 | True | 0 |
| esp8266 | h_all | 12 | 13 | memory | malloc_failed | 13 | True | 0 |
| esp8266 | bell_ghz | 12 | 13 | memory | malloc_failed | 13 | True | 0 |
| esp8266 | qft | 12 | 13 | memory | malloc_failed | 13 | True | 0 |
| esp8266 | grover | 10 | 11 | time ceiling | skipped_compute_infeasible from n=11 (1 rep > 7200 s) | 13 |  | 2 |
| esp32 | h_all | 13 | 14 | memory | malloc_failed | 14 | True | 0 |
| esp32 | bell_ghz | 13 | 14 | memory | malloc_failed | 14 | True | 0 |
| esp32 | qft | 13 | 14 | memory | malloc_failed | 14 | True | 0 |
| esp32 | grover | 12 | 13 | time ceiling | skipped_compute_infeasible from n=13 (1 rep > 7200 s) | 14 |  | 0 |

Memory model (`bytes(n) = 8 * 2^n`, state of `Cplx` = 2 floats, `firmware/common/qsim.hpp:30-33`; Uno available = 2 048 B minus the static data derived from the
ok points; ESP boards available = free heap or largest free block read at the smallest ok n, plus the state it already holds):

| board | circuit | model_basis | predicted_wall_n | observed_wall_n | agree |
|---|---|---|---|---|---|
| uno | h_all | static 202 B (compile RAM used - state), RAM 2048 B | 8 | 8 | True |
| uno | bell_ghz | static 206 B (compile RAM used - state), RAM 2048 B | 8 | 8 | True |
| uno | qft | static 200 B (compile RAM used - state), RAM 2048 B | 8 | 8 | True |
| uno | grover | static 204 B (compile RAM used - state), RAM 2048 B | 8 | 8 | True |
| esp8266 | h_all | free_heap_before at n=2 + its state = 52240 B | 13 | 13 | True |
| esp8266 | bell_ghz | free_heap_before at n=2 + its state = 52240 B | 13 | 13 | True |
| esp8266 | qft | free_heap_before at n=2 + its state = 52240 B | 13 | 13 | True |
| esp8266 | grover | free_heap_before at n=2 + its state = 51264 B | 13 | none reached |  |
| esp32 | h_all | largest_block at n=2 + its state = 110612 B | 14 | 14 | True |
| esp32 | bell_ghz | largest_block at n=2 + its state = 110612 B | 14 | 14 | True |
| esp32 | qft | largest_block at n=2 + its state = 110612 B | 14 | 14 | True |
| esp32 | grover | largest_block at n=2 + its state = 110612 B | 14 | none reached |  |

The model reproduces the observed wall n for all 10 walls (Uno 8; ESP8266 13; ESP32 14); grover on ESP8266 and ESP32 did not reach it. The
ESP32 wall is set by the largest contiguous block (110 580 B at every ok n; state 65 536 B at n=13 fits, 131 072 B at n=14 does not), not by total free heap
(about 256 KB). The ESP8266 wall: 52 240 B available at n=2 including the state vs 65 536 B at n=13; `largest_block` is not logged by the ESP8266 firmware
(UNVERIFIED whether the block, not total heap, is the limit there). Limiting factor per limit (INTERPRETATION from the evidence column): Uno memory
(static RAM overflow at link time); ESP8266 and ESP32 h_all/bell_ghz/qft memory (allocation failure); ESP8266 and ESP32 grover time ceiling (2 h cap), with the
ESP8266 additionally showing watchdog resets at n=8..9 that a firmware change removed.

### 5.3 Cross-board (OBSERVED; no single cause attributed)

Ratio of median time per rep at equal (circuit, n):

| circuit | pair | n_points | min | median | max |
|---|---|---|---|---|---|
| h_all | Uno / ESP8266 | 6 | 10.55 | 10.96 | 11.83 |
| h_all | Uno / ESP32 | 6 | 142 | 312.9 | 370.5 |
| h_all | ESP8266 / ESP32 | 11 | 12 | 34.55 | 35.13 |
| bell_ghz | Uno / ESP8266 | 6 | 11.38 | 15.76 | 17.02 |
| bell_ghz | Uno / ESP32 | 6 | 74 | 107.4 | 116 |
| bell_ghz | ESP8266 / ESP32 | 11 | 3.62 | 5.69 | 8.67 |
| qft | Uno / ESP8266 | 6 | 7.79 | 9.02 | 10.43 |
| qft | Uno / ESP32 | 6 | 97.33 | 216.8 | 267.1 |
| qft | ESP8266 / ESP32 | 11 | 9.33 | 26.5 | 27.77 |
| grover | Uno / ESP8266 | 6 | 6.4 | 9.12 | 10.37 |
| grover | Uno / ESP32 | 6 | 164.8 | 257.6 | 276.8 |
| grover | ESP8266 / ESP32 | 9 | 25.73 | 26.7 | 28.49 |

Clock, floating-point hardware, RAM, compiler and the timer API all differ between the boards; these runs cannot separate them. The Uno / ESP8266
ratio is 6.4-17 and varies little with n; the ESP8266 / ESP32 ratio spans 3.6-35 and depends on the circuit (h_all 12-35, bell_ghz 3.6-8.7).

### 5.4 micros() vs counter (valid Phase 2 sessions only; relative to an uncalibrated counter)

| board | points | counter_ok | median_diff_us_min | median_diff_us_max | pct_min | pct_max | within_micros_resolution |
|---|---|---|---|---|---|---|---|
| esp32 | 45 | 45 | -1.3 | 1.064e+04 | -37.5 | 0.002 | 32 |
| esp8266 | 26 | 0 | -8.144 | -6.925 | -36.24 | -0.055 | 0 |
| uno | 22 | 0 | -1.463e+05 | -6.738 | -9.825 | -0.488 | 0 |

OBSERVED: `micros()` minus counter is negative at every point except ESP32 grover n=7, 8, 9, 11 (+1.45 us ... +10.6 ms, +0.001 to +0.002 %) and ESP32 qft n=13 (+0.06 us). ESP8266: a near-constant -7.5 us
(-8.1 ... -6.9) at every n, so the relative difference shrinks from -36 % to -0.06 %. Uno: -6.7 ... -146 314 us; relative -0.49 to -0.53 % at n=6,7 (the
Uno `micros()` reads about 0.5 % short; commit `21390e3` states "Uno micros() clock about 0.49 % slow" from the calibration run). ESP32: -0.4 ... -1.2 us for n <= 5, within the 1 us
resolution for 32 of 45 points, -0.006 % at n=13; the small positive differences at large grover n (+0.002 %, about 20 ppm) are the size of the
+17.5 +/- 1.9 ppm counter-vs-PC-clock calibration, which would be the reading if the target ESP32's clock agrees with the PC's (UNVERIFIED: the two ESP32 crystals can differ independently). INTERPRETATION: a constant offset is what the code between the pin toggle and the timer reads
would produce (the pin is set before `t0` and cleared after `t1`); this was not isolated. The Uno's proportional part would be a clock-frequency
difference between the Uno and the counter; which clock is off is UNVERIFIED (no external reference).

### 5.5 Phase 3 offload crossover (OBSERVED)

First n at which the offload median round trip is below the local Phase 2 median per rep (same board, circuit, n; each curve measures something different:
local = the board runs the circuit; offload = serial request + PC simulation of the circuit with Qiskit Aer + reply):

| board | circuit | common_n | crossover_n | offload_over_local_at_first | offload_over_local_at_last |
|---|---|---|---|---|---|
| uno | h_all | 2..7 | 5 | 11.39 | 0.127 |
| uno | bell_ghz | 2..7 | 6 | 22.27 | 0.362 |
| uno | qft | 2..7 | 4 | 10.16 | 0.09 |
| uno | grover | 2..7 | 2 | 0.999 | 0.007 |
| esp8266 | h_all | 2..12 | 8 | 134.6 | 0.031 |
| esp8266 | bell_ghz | 2..12 | 10 | 238.3 | 0.214 |
| esp8266 | qft | 2..12 | 8 | 130.8 | 0.02 |
| esp8266 | grover | 2..10 | 4 | 5.982 | 0.019 |
| esp32 | h_all | 2..13 | none in range | 3239 | 1.106 |
| esp32 | bell_ghz | 2..13 | 13 | 3248 | 0.776 |
| esp32 | qft | 2..13 | 13 | 2283 | 0.47 |
| esp32 | grover | 2..12 | 9 | 282.6 | 0.081 |

"none in range": ESP32 h_all, where offload / local stays at or above 1.1 up to n=13. The offload round trip is nearly constant at small n (3-7 ms, set by the
serial frame, the PC call and `delay(20)`), local time doubles per qubit, so a crossover exists wherever local time reaches that floor.
Phase 3 grover at n >= 11 is time-capped (2-42 requests).

## 6. Prediction accuracy

**Rules, fixed before the results were computed** (they are also the header of `analysis/audit_data.py`): model M1: `t = c_board * G(circuit, n) * 2^n`, G = total
gate count (`pc/shared/timing_model.py:144-176`), because every gate loops over all 2^n indices (`firmware/common/qsim.hpp:65,86,107`); M1c adds a
non-negative constant per point. Fit on the smaller half (floor(k/2) points by n) of the ok points of one (board, circuit) by least squares on the relative error;
evaluate on every ok point (in-sample / extrapolation labelled). Leave-one-circuit-out (LOCO): one c per board from the other three circuits, predicting the
fourth. Success is reported as measured / predicted with its median, min, max and the share within +/-25 % and within a factor 2. **Added after M1's LOCO result, labelled
post-hoc:** M2 (touched amplitudes: H 2^n, CNOT 2^(n-1), CPHASE 2^(n-2), qsim.hpp loops) and M3 (three per-gate-type costs fitted by non-negative least squares,
LOCO only). Every point is in the tables; none is dropped.

Within-series extrapolation (fit on the smaller half, evaluated on the larger half; 59 extrapolated points, 54 in-sample points):

| variant | declared | set | points | median_ratio | min_ratio | max_ratio | within_25pct | within_2x |
|---|---|---|---|---|---|---|---|---|
| M1 | pre | extrapolation | 59 | 0.638 | 0.487 | 0.999 | 0.39 | 0.966 |
| M1 | pre | fit (smaller half) | 54 | 1.021 | 0.71 | 2.807 | 0.63 | 0.87 |
| M1c | pre | extrapolation | 59 | 0.721 | 0.519 | 1.19 | 0.458 | 1 |
| M1c | pre | fit (smaller half) | 54 | 1.002 | 0.794 | 1.982 | 0.87 | 1 |
| M2 | post-hoc | extrapolation | 59 | 0.802 | 0.557 | 1.109 | 0.559 | 1 |
| M2 | post-hoc | fit (smaller half) | 54 | 1.022 | 0.702 | 2.538 | 0.685 | 0.963 |
| M2c | post-hoc | extrapolation | 59 | 0.838 | 0.655 | 1.293 | 0.831 | 1 |
| M2c | post-hoc | fit (smaller half) | 54 | 1.004 | 0.702 | 1.865 | 0.87 | 1 |

By board (extrapolation points):

| variant | declared | board | points | median_ratio | min_ratio | max_ratio | within_25pct | within_2x |
|---|---|---|---|---|---|---|---|---|
| M1 | pre | esp32 | 24 | 0.737 | 0.54 | 0.999 | 0.5 | 1 |
| M1 | pre | esp8266 | 23 | 0.582 | 0.487 | 0.955 | 0.261 | 0.913 |
| M1 | pre | uno | 12 | 0.683 | 0.549 | 0.905 | 0.417 | 1 |
| M1c | pre | esp32 | 24 | 0.854 | 0.61 | 1.19 | 0.5 | 1 |
| M1c | pre | esp8266 | 23 | 0.673 | 0.519 | 0.97 | 0.348 | 1 |
| M1c | pre | uno | 12 | 0.794 | 0.594 | 0.941 | 0.583 | 1 |
| M2 | post-hoc | esp32 | 24 | 0.768 | 0.678 | 1.109 | 0.5 | 1 |
| M2 | post-hoc | esp8266 | 23 | 0.827 | 0.557 | 0.955 | 0.522 | 1 |
| M2 | post-hoc | uno | 12 | 0.846 | 0.687 | 1.087 | 0.75 | 1 |
| M2c | post-hoc | esp32 | 24 | 0.888 | 0.751 | 1.293 | 0.875 | 1 |
| M2c | post-hoc | esp8266 | 23 | 0.833 | 0.655 | 0.97 | 0.696 | 1 |
| M2c | post-hoc | uno | 12 | 0.911 | 0.777 | 1.087 | 1 | 1 |

By circuit (extrapolation points, with-constant variants):

| variant | declared | circuit | points | median_ratio | min_ratio | max_ratio | within_25pct |
|---|---|---|---|---|---|---|---|
| M1c | pre | bell_ghz | 15 | 0.828 | 0.624 | 1.19 | 0.667 |
| M1c | pre | grover | 14 | 0.677 | 0.557 | 0.792 | 0.071 |
| M1c | pre | h_all | 15 | 0.959 | 0.904 | 0.97 | 1 |
| M1c | pre | qft | 15 | 0.636 | 0.519 | 0.795 | 0.067 |
| M2c | post-hoc | bell_ghz | 15 | 0.854 | 0.678 | 1.293 | 0.6 |
| M2c | post-hoc | grover | 14 | 0.763 | 0.655 | 0.895 | 0.714 |
| M2c | post-hoc | h_all | 15 | 0.959 | 0.904 | 0.97 | 1 |
| M2c | post-hoc | qft | 15 | 0.833 | 0.759 | 1.087 | 1 |

Leave-one-circuit-out, all 113 ok points:

| variant | declared | points | median_ratio | min_ratio | max_ratio | within_25pct | within_2x |
|---|---|---|---|---|---|---|---|
| M1 | pre | 113 | 1.501 | 0.176 | 13.32 | 0.212 | 0.46 |
| M2 | post-hoc | 113 | 1.54 | 0.199 | 9.351 | 0.097 | 0.442 |
| M3 | post-hoc | 113 | 0.773 | 0.122 | 4.132 | 0.31 | 0.681 |

| variant | declared | board | points | median_ratio | min_ratio | max_ratio | within_25pct | within_2x |
|---|---|---|---|---|---|---|---|---|
| M1 | pre | esp32 | 47 | 1.14 | 0.555 | 4.278 | 0.468 | 0.851 |
| M1 | pre | esp8266 | 42 | 3.38 | 0.176 | 13.32 | 0.024 | 0.048 |
| M1 | pre | uno | 24 | 1.772 | 0.323 | 3.676 | 0.042 | 0.417 |
| M2 | post-hoc | esp32 | 47 | 1.34 | 0.484 | 3.682 | 0.191 | 0.723 |
| M2 | post-hoc | esp8266 | 42 | 2.749 | 0.199 | 9.351 | 0 | 0.024 |
| M2 | post-hoc | uno | 24 | 1.423 | 0.385 | 2.908 | 0.083 | 0.625 |
| M3 | post-hoc | esp32 | 47 | 0.891 | 0.281 | 4.132 | 0.511 | 0.681 |
| M3 | post-hoc | esp8266 | 42 | 0.719 | 0.122 | 3.461 | 0.119 | 0.619 |
| M3 | post-hoc | uno | 24 | 0.735 | 0.254 | 1.954 | 0.25 | 0.792 |

OBSERVED: with the declared model M1, extrapolation to larger n under-estimates the cost per update at small n and so **over-predicts** large n (median measured / predicted
0.64; 39 % within +/-25 %; 97 % within a factor 2). Adding a constant (M1c) moves the median to 0.72 and every point within a factor 2; the post-hoc touched-amplitude
variant with a constant (M2c) has a median of 0.84 with 83 % within +/-25 %. Predicting a circuit from the other three on the same board is far worse: M1 median 1.50, only 46 % of
points within a factor 2 (ESP32 85 %, Uno 42 %, ESP8266 5 %); the per-gate-type fit M3 reaches 68 %. INTERPRETATION: a single per-board cost per gate-amplitude does not transfer between
circuits because the gate types differ in cost on the boards without a floating-point unit (the H gate does float arithmetic, CNOT swaps structs); the ESP32 is the board where one
cost is a reasonable approximation. These models were designed and evaluated on the same 113 points (no held-out board, no pre-registered extrapolation to unseen n beyond the within-series split): the accuracy
numbers describe the fit procedure on this dataset, not a validated predictor.

## 7. Limitations and UNVERIFIED

- One unit per board, single runs, no run-to-run or unit-to-unit spread (8 repeated points only, totals only).
- `micros()` window contents: the timed window is `run_circuit(n_states)` between `t0` and `t1` (e.g. `firmware/esp32/src/main.cpp:82-88`); the pin toggle and
  the reading of the timer are inside/outside it as the code shows; the offset in section 5.4 was not isolated.
- The counter was only self-loopback tested, is not externally calibrated, and its firmware differs across boards.
- Phase 3 contains a PC-side Qiskit Aer simulation (`pc/phase3_offload/sweep.py:316-317`) whose time dominates at larger n; host load is not recorded beyond the sleep-prevention flag.
- No board-level correctness data exist (section 3h); Grover reference caveat: C++ vs Qiskit infidelity exceeds 1e-3 from n=9.
- UNVERIFIED in this repository: the ESP8266 has no FPU (README table, no source); ESP8266/ESP32 `micros()` timer resolution beyond the API return units; `largest_block` on the
  ESP8266; the cost of the ESP8266 watchdog-feed interrupt; whether the Uno or the counter clock causes the -0.5 % Uno difference; the nominal SRAM sizes (README) beyond the
  measured free heap; host load during Phase 3; higher baud rates than 115 200.

## 8. Reproduce

`.venv/bin/python analysis/audit_data.py` (writes `data/processed/audit/*.csv`, refuses an output under `data/raw/`);
`.venv/bin/python analysis/audit_data_test.py` (59 checks on synthetic data).
