# Pre-Hardware Preflight Report

> **PRIOR OBSERVATIONS (retired, pre-timer; not part of the new dataset).** This whole file records the pre-run preflight (compile-only build matrix, tool timings, PC-side checks) over six circuits. It is kept for its method and as the basis of the design predictions in `docs/design/experiment_plan.md`. The experiment now covers `h_all`, `bell_ghz`, `qft`, `grover` only; `qpe`/`steane_encode` rows no longer apply. RAM percentages and wall statements here come from compile outputs and retired runs and are **not results of the new dataset**.

**Date:** 2026-09-20
**Commit:** `08d1a9d` — `git describe --tags` → `pre-run-schema-v1`, working tree clean
**Scope:** full verification of the collection pipeline before the first board is
ever connected. **No hardware was touched**: no serial port opened, no upload run,
no `pio device monitor`. Firmware was compiled only (`pio run`, never `-t upload`).
No firmware was modified. Problems found are reported here, not fixed.

Anything that cannot be established without a board is marked
**UNVERIFIED-needs-hardware** rather than assumed passing. Throwaway scripts used
for the checks live under `/tmp` and are not committed; every command is quoted so
each result can be reproduced.

---

## Verdict

### READY to connect the first board.

Nothing blocks steps (a)-(e) of "First hardware contact" in `run_checklist.md`.
The PC-side pipeline is internally consistent, the schema is frozen and enforced,
resume/failure handling behaves correctly under injected faults, and every
firmware environment compiles for every circuit at both ends of its planned `n`
range.

**Four items must be resolved before the expensive sessions (Session B/C), not
before first contact:**

1. **H1** — the two ESP8266 Grover points (`n=8`, `n=9`) are predicted to trip the
   hardware watchdog and be mis-recorded as a Memory Wall. Verify on hardware with
   single points before committing to the 4.2 h session.
2. **H2** — a slow compile is recorded as `build_or_upload_fail`, which the resume
   logic treats as a permanent wall. Measured ESP8266 compiles reach 85 s against
   a 120 s timeout. Pre-warm environments and/or widen that timeout.
3. **H3** — Grover `n=9`/`n=10` fail the project's own Phase 1 fidelity criterion.
   Decide and document how those two points are reported before collecting them.
4. **H4** — compile time alone consumes 94 % of the entire reflash budget, so the
   13.9 h figure has effectively no allowance for 312 uploads. Measure one real
   build+upload per board and update `REFLASH_COST_S`.

None of the four can corrupt the first pilot point, which is why the verdict is
READY rather than NOT READY.

**Counts:** 17 checks — **12 PASS**, **3 FAIL**, **1 PASS-with-findings**,
**1 UNVERIFIED-needs-hardware**.
Underlying automated assertions: **206 executed, 2 failing** (both are P1-2's
Grover fidelity failures; the 204 others pass). Plus 66 firmware builds, all
succeeding with zero compiler warnings.

---

## Status: hardening applied after this report (tag `pre-run-schema-v2`)

This report is the preflight snapshot at `pre-run-schema-v1` (`00f19b3`). The
following round of PC-side-only hardening acted on it; the findings below are
kept as written, with their current state noted here rather than edited in place.

| Finding | State |
|---|---|
| **H1** watchdog mis-attribution | **Mitigated in analysis, not in firmware.** A per-board estimated-per-rep threshold (`timing_model.WDT_PER_REP_THRESHOLD_S`: ESP8266 6 s, ESP32 5 s, Uno none — still an UNVERIFIED assumption) now records a silent board as `watchdog_suspected` rather than `runtime_hang_or_reset`, and **no** hang of either kind is auto-classified as a wall any more. Firmware untouched; options analysed below. |
| **H2** compile timeout became a wall | **Fixed.** Timeouts are now `build_timeout` (distinct `failure_type` and terminal status), never a wall, retried once under the same ≤ 600 s budget rule, with the subprocess timeout raised to a configurable 300 s (~3.5× the measured 85 s peak). |
| **H3** Grover fidelity | **Report-only, by instruction.** Simulator and the 1e-3 criterion deliberately unchanged; a draft Limitations paragraph and an iteration-count table are below. |
| **H4** reflash budget | **Report-only.** `REFLASH_COST_S` and `timing_model.py` deliberately unedited; sensitivity table below. Still needs one measured build+upload per board. |
| **M4** nothing pinned | **Fixed.** `requirements.txt` added; `platform =` pinned to the installed versions in all three `platformio.ini` (rebuild confirmed byte-identical flash/RAM); environment JSON now records per-board platform/framework/toolchain versions via `pio pkg list -e <env>`. |
| **M5** `phase1_compare.py` overwrote raw data | **Fixed.** It now refuses by default; `--out-dir`, `--timestamped-out` or an explicit `--allow-overwrite` are required. |
| **M1, M2, M3, M6, L1-L6** | Unchanged, report-only. |

### H1 — firmware options, analysis only (nothing implemented)

`firmware/` is byte-identical to `pre-run-schema-v1`; this is the analysis the
task asked for, not a change. Three ways a watchdog reset could be prevented,
and what each would cost the measurement:

1. **Feed the watchdog inside `run_circuit()`** (periodic `ESP.wdtFeed()` /
   `esp_task_wdt_reset()` at gate-loop granularity). Removes the reset entirely
   but puts a call *inside* the timed region: `micros()` would then include the
   feed cost on every iteration, inflating exactly the quantity being published,
   by an amount that scales with gate count — i.e. worst at the high-n Grover
   points this is meant to rescue. It would also change what the LA sees, since
   the pulse brackets the same region. Rejected on measurement grounds.
2. **Split the rep into chunks and feed between chunks** (e.g. run the circuit
   in k segments, feeding the WDT at segment boundaries, still inside one
   GPIO pulse). Keeps per-gate cost clean but adds k−1 feeds inside the pulse
   and inside the `micros()` window; the bias is smaller than option 1 and
   *bounded* (k feeds, not one per gate), but it is still non-zero and it makes
   the timed region structurally different from the low-n points it is compared
   against. The LA window would still bracket only `run_circuit()`, so the
   cross-check stays valid — it would just be checking a slightly different
   thing at high n than at low n.
3. **Disable the hardware watchdog for the timed region** (ESP8266:
   `ESP.wdtDisable()` already stops only the *software* WDT; stopping the
   hardware WDT needs a lower-level call and is not reliably supported from the
   Arduino core. ESP32: the task WDT can be deconfigured per task). Zero effect
   on the timed region and therefore the cleanest option for measurement — but
   it removes the only protection against a genuinely stuck board, turning a
   would-be reset into an indefinite hang that only the PC-side timeout catches.
   Acceptable only because that PC-side hard deadline already exists.

If any of these is ever adopted, it is a firmware change and therefore a new
firmware source hash, a new `SCHEMA_VERSION` conversation, and points collected
before and after must not be pooled. The current position is deliberate: **do
not change the firmware; record the watchdog hypothesis honestly and let the
operator decide per point.**

---

## Check table

| ID | What was checked | Method | Result | Evidence |
|---|---|---|---|---|
| P1-1 | Every existing test suite | `.venv/bin/python pc/shared/telemetry_test.py`; `analysis/la_test.py`; `pc/shared/timing_model.py` self-test | **PASS** | telemetry 46/46, la 58/58, 0 failed, **0 skipped** (no skip mechanism exists in either harness). `timing_model.py`'s `__main__` block prints a budget demonstration, not assertions. |
| P1-2 | C++ simulator vs Qiskit Aer, all 6 circuits, every feasible planned `n` | `/tmp/preflight_sim_check.py` (reuses `analysis/phase1_compare.py`; writes to `/tmp` only) | **FAIL** | 62 (circuit, n) pairs: 59 pass, **2 fail** (grover n=9, n=10), 1 refused by the validator (qpe n=2). Table below. |
| P1-3 | Infidelity, TVD, median/IQR vs hand-computed values incl. edge cases | `/tmp/preflight_metrics_protocol.py` | **PASS** | 20/20 assertions: identical/orthogonal/global-phase, disjoint support, even/odd counts, all-ties, single sample, REPS=100 shape. |
| P1-4 | Protocol field order/width/endianness/CRC8; decoder vs corrupt, truncated, oversized frames | same script; firmware `crc8()` host-compiled unmodified | **PASS** | 27/27. CRC-8/SMBUS catalogue vector `0xF4` matches; firmware `crc8()` == PC `crc8()` over 206 byte strings; all 32 single-bit flips rejected. |
| P1-5 | Timing model totals recomputed from scratch vs `run_checklist.md` | `timing_model.session_total_s()` per session | **PASS** | Every row matches to the printed precision; Phase 2 = 8.1 h, Phase 3 = 5.8 h, **grand total 13.89 h**. No drift. 154 points confirmed (131 cheap + 23 grover). |
| P1-6 | Every literal written into `status` / `failure_type` is a member of the enum | `grep` over all four sweeps + runtime validation in `write_point_row` | **PASS** | All `status` literals ∈ `STATUS_TYPES`; all `failure_type` literals ∈ `FAILURE_TYPES`. `*_memory_wall.csv` statuses all match `resume.WALL_STATUS_PREFIXES` or are deliberately non-wall. Two enum values are never written (findings M2/M3). |
| P1-7 | End-to-end dry runs of all four sweep scripts, mocked hardware | `/tmp/preflight_dryrun.py` + an esp8266 run | **PASS** | 55/55. Covers all four `skipped_*` reasons, retry, build failure, malloc, interruption+resume, and the **real** Phase 3 give-up path. `data/raw/` byte-identical (sha256) before/after. |
| P2-8 | Build every environment × every CIRCUIT_ID × smallest and largest planned `n` | `/tmp/preflight_builds.sh` — `pio run` only | **PASS (with findings)** | 66/66 builds succeeded, 0 compiler warnings. Table below. Uno links at >100% SRAM without erroring (finding L2). |
| P2-9 | platformio.ini environments, board IDs, speeds, F_CPU vs the sweep scripts | read `firmware/*/platformio.ini` + `grep` on sweeps | **PASS** | Every baud is 115200 on both sides. Higher Phase 3 bauds are an untested assumption (L4). |
| P2-10 | Every GPIO used per board vs strapping/reserved pins | read all six firmware files | **PASS** | No conflicts. Pin-classification claims are flagged below as my own knowledge, for datasheet confirmation. |
| P2-11 | Phase 2 timing path: what the GPIO pulse and `micros()` bracket; WDT risk | static review of the three `src/main.cpp` | **UNVERIFIED-needs-hardware** | The `micros()` window contains only `run_circuit()` (PASS). The GPIO pulse is wider than it (L1). ESP8266 watchdog risk (H1) cannot be settled without a board. |
| P2-12 | malloc failure reported over the protocol rather than a silent crash | read firmware + dry-run S8 | **PASS** | ESP8266/ESP32 print `MALLOC_FAILED` → `DONE`; the sweep records `failure_type=malloc` / `malloc_failed` and does not retry. Uno has no malloc by design (static array); its failure mode is link-time or a runtime hang, as documented. |
| P3-13 | Clean tree, on the tag, no untracked files the scripts read | `git status`, `git describe --tags` | **PASS** | Clean; `pre-run-schema-v1`; zero untracked files. Firmware source hashes listed below. |
| P3-14 | Python and PlatformIO versions pinned for reproducibility | `ls`, `pio pkg list --global`, `importlib.metadata` | **FAIL** | No requirements file or lockfile; `platform =` lines unpinned (M4). |
| P3-15 | Disk vs expected volume; sleep-prevention check; iCloud/TCC exposure | `df -h`, `telemetry.check_sleep_prevention()`, `brctl status` | **PASS (with findings)** | 22 GiB free vs ~101 MB worst case. Sleep check works (`checked: True, prevented: True`). iCloud sync of Documents is **off**; TCC exposure is real (M6). |
| P3-16 | `data/raw/` contents and layout; no script overwrites raw files | `find`, `grep` over every `open()` | **FAIL** | Sweeps are strictly append-only, but `analysis/phase1_compare.py` overwrites `data/raw/phase1/*.csv` (M5). |
| P3-17 | Failure injection: 8 fault classes | `/tmp/preflight_dryrun.py` scenarios S3-S11 | **PASS** | Table below. No case loses data; two cases are logged ambiguously (M2, M3). |

---

## P1-2 — Simulator correctness

**Tolerance: infidelity (1−F) ≤ 1e-3.** This is not a number invented for this
report — it is the project's own pre-existing Phase 1 pass criterion
(`analysis/phase1_compare.py:42`, `INFIDELITY_THRESHOLD = 1e-3`), and it is kept
so this check is comparable with the Phase 1 results already in
`data/raw/phase1/infidelity_tvd.csv`. It is the right order of magnitude because
the MCU simulator stores amplitudes as **two float32** (`firmware/common/qsim.hpp:30-32`,
`struct Cplx { float re; float im; }`) while Aer computes in complex128: with
~1e-7 relative error per operation, 1e-3 total allows roughly 10^4 accumulating
operations before the criterion bites, which covers every circuit in the sweep
except deep Grover.

**Inputs are identical on both sides and documented:** the Qiskit circuits are
built gate-by-gate to match `firmware/common/circuits.hpp`, not merely to produce
the same final state (`analysis/phase1_compare.py:102-193`), including the
ancilla-free multi-controlled-Z decomposition. Specifically —
angles: QFT/inverse-QFT use `θ = π/2^(k−j)` on both sides (`circuits.hpp:53-71`
vs `phase1_compare.py:67-73,121-126`);
Grover marked state: `|1…1⟩`, oracle and diffuser built from the same
`mc_phase`/`mc_x` decomposition, iteration count `max(1, int((π/4)·√2ⁿ))`
(`phase1_compare.py:127-148`), verified independently by `P(marked)`;
QPE: `U = P(π/2)` on eigenstate `|1⟩`, so the true phase is exactly `φ = 0.25`
(`phase1_compare.py:43`, `QPE_TRUE_PHI`), and the estimate is read back
bit-reversed because the QFT omits the final SWAPs;
Steane: the fixed 7-qubit encoder, checked additionally against all six
stabilizer generators rather than only against Aer (`phase1_compare.py:228-266`).

| Circuit | n range checked | Max infidelity (1−F) | Max TVD | Verdict |
|---|---|---|---|---|
| h_all | 2-14 | 2.432e-07 (n=12) | 1.216e-07 | PASS |
| bell_ghz | 2-14 | 3.447e-08 (n=2) | 1.723e-08 | PASS |
| qft | 2-14 | 2.432e-07 (n=12) | 1.216e-07 | PASS |
| grover | 2-10 | **6.469e-03 (n=10)** | **3.234e-03** | **FAIL at n=9 and n=10** |
| qpe | 3-14 (n=2 refused) | 2.380e-07 (n=4) | 1.190e-07 | PASS |
| steane_encode | 7 | 2.013e-07 | 1.007e-07 | PASS (all 6 stabilizers +1) |

Grover detail — the deviation is monotone in circuit depth, exactly as float32
accumulation predicts:

| n | depth | infidelity | verdict |
|---|---|---|---|
| 7 | 8 529 | 8.53e-05 | pass |
| 8 | 38 089 | 3.61e-04 | pass |
| 9 | 161 399 | **1.474e-03** | **fail (1.5× over)** |
| 10 | 711 251 | **6.469e-03** | **fail (6.5× over)** |

`P(marked)` stays ≥ 0.993 at every n, so the algorithm is still *working* — this
is amplitude precision drift, not a logic error. Both failing points are in the
planned sweep (ESP8266 grover n=9, ESP32 grover n=10). See finding **H3**.

---

## P2-8 — Firmware build matrix (compile-only)

`pio run` was invoked 66 times — every environment (`uno`, `uno_offload`,
`nodemcuv2`, `nodemcuv2_offload`, `esp32dev`, `esp32dev_offload`) × all six
`CIRCUIT_ID` values × the smallest and largest `n` that board actually plans to
collect for that circuit (`steane_encode` has only n=7). **`-t upload` was never
passed.** All 66 succeeded with **0 compiler warnings**.

**Phase 2 (local) — static RAM and flash at the smallest and largest planned `n`:**

| Board | Circuit | n | Static RAM | Flash |
|---|---|---|---|---|
| Uno | h_all | 2 → 8 | 234 → **2250 / 2048 (109.9 %)** | 3 786 → 3 720 / 32 256 |
| Uno | bell_ghz | 2 → 8 | 238 → **2254 / 2048 (110.1 %)** | 3 826 → 3 846 |
| Uno | qft | 2 → 8 | 232 → **2248 / 2048 (109.8 %)** | 4 136 → 4 788 |
| Uno | qpe | 2 → 8 | 232 → **2248 / 2048 (109.8 %)** | 4 846 → 5 294 |
| Uno | grover | 2 → 7 | 236 → 1 228 / 2048 (60.0 %) | 5 650 → 5 584 |
| Uno | steane_encode | 7 | 1 234 / 2048 (60.3 %) | 4 188 |
| ESP8266 | h_all | 2 → 13 | 28 224 → 28 224 / 81 920 (34.5 %) | 268 387 → 268 403 / 1 044 464 |
| ESP8266 | qft | 2 → 13 | 28 220 → 29 196 (35.6 %) | 268 639 → 273 583 |
| ESP8266 | grover | 2 → 9 | 29 200 → 29 200 (35.6 %) | 273 987 → 274 003 |
| ESP8266 | qpe | 2 → 13 | 29 196 → 29 196 (35.6 %) | 274 007 → 274 135 |
| ESP32 | h_all | 2 → 14 | 43 416 → 43 416 / 327 680 (13.2 %) | 725 253 → 725 269 / 1 310 720 (55.3 %) |
| ESP32 | grover | 2 → 10 | 43 416 → 43 416 (13.2 %) | 730 065 → 730 001 (55.7 %) |
| ESP32 | qpe | 2 → 14 | 43 420 → 43 420 (13.3 %) | 730 161 → 730 265 (55.7 %) |

(`bell_ghz`/`steane_encode` on the ESPs behave identically to `h_all`; full 66-row
data was produced by `/tmp/preflight_builds.sh` → `/tmp/preflight_builds.csv`.)

**Phase 3 (offload)** static RAM is flat in `n` on every board, as expected — the
state vector lives on the PC. Uno: 796-806 / 2048 B (~39 %), flash ~2.6 kB.
ESP8266: ~29 kB. ESP32: ~43 kB.

**Measured compile time (compile only — `-t upload` never run):**

| Board | builds | mean | max | `REFLASH_COST_S` assumption (compile **+** upload) |
|---|---|---|---|---|
| Uno | 22 | 7.3 s | 13 s | 20 s |
| ESP8266 | 22 | 47.3 s | 85 s | 30 s |
| ESP32 | 22 | 17.3 s | 34 s | 30 s |

**Cold or incremental?** Every one of the 66 builds was a **full rebuild**, and
none was incremental. Changing `N_QUBITS` or `CIRCUIT_ID` changes `build_flags`,
which invalidates PlatformIO's whole object cache including the framework — and
the real run changes `N_QUBITS` at every single data point. So these figures are
representative of all 312 planned reflashes, not just of a cold start. (The
PlatformIO *packages* were already installed before the first build, so none of
these timings include a toolchain download; a first-ever run on a fresh machine
would be slower still, and that download happens *inside* the same `pio run` the
timeout applies to.)

| Board | builds | **median** | mean | max | Phase 2 median | Phase 3 median |
|---|---|---|---|---|---|---|
| Uno | 22 | **7.5 s** | 7.3 s | 13 s | 9.0 s | 6.0 s |
| ESP8266 | 22 | **40.0 s** | 47.3 s | 85 s | 40.0 s | 40.0 s |
| ESP32 | 22 | **16.0 s** | 17.3 s | 34 s | 16.0 s | 16.0 s |

(An earlier interim figure of 63.7 s for the ESP8266 was computed from the first
6 builds only, before the matrix finished; the completed set gives 47.3 s mean /
40.0 s median. The mean exceeds the median because of a right tail — the
per-environment first builds — which is also why the max, not the median, is the
number the timeout has to survive.)

**Sensitivity of the run total to these measurements** (compile measured, upload
still unmeasured — nothing here edits `REFLASH_COST_S` or `timing_model.py`):

| | assumed reflash (compile+upload) | measured compile only | unmeasured remainder |
|---|---|---|---|
| Uno (73 reflashes) | 0.41 h | 0.15 h | 0.26 h of slack |
| ESP8266 (115) | 0.96 h | **1.51 h** | already 0.55 h **over** before any upload |
| ESP32 (124) | 1.03 h | 0.59 h | 0.44 h of slack |
| **total (312)** | **2.40 h** | **2.25 h (94 %)** | **~0.15 h left for 312 uploads** |

The 13.9 h headline is therefore optimistic by however long 312 uploads take
minus ~9 minutes. Measuring one real build+upload per board settles it; see finding **H4**.


**Static RAM vs the recorded memory wall.** The Uno figures are the interesting
ones because its state array is static (`firmware/uno/src/main.cpp:31`), so the
linker sees the whole cost: RAM usage doubles per `n`, and at `n=8` it is
**2254 / 2048 bytes = 110 %** — over the physical SRAM, yet `pio run` still exits
0. That is precisely the failure mode the firmware header documents (link
succeeds, `.bss` overlaps the stack, the board hangs at run time) and it agrees
with the retired-run observation that n=7 was the last n that ran: n=8 is the first point that
cannot work. The ESP boards allocate with `malloc()` at run time, so their static
RAM does not move with `n` and the wall is invisible at build time by design — it
is reported over the protocol instead (P2-12).

---

## P3-17 — Failure injection results

All injected with mocks; Phase 2 mocks only `serial.Serial` so the **real**
`read_serial_trials()` runs (including its `signal.alarm` hard deadline), and
Phase 3 mocks only `serial.Serial` so the **real** `run_offload_session()`
give-up path runs.

| Injected fault | Logged `status` | Logged `failure_type` | Terminal record | Pipeline behaviour | Data loss? |
|---|---|---|---|---|---|
| Build failure | `failed` | `build` | `build_or_upload_fail` | stops that circuit (wall), continues others | none |
| Upload failure | `failed` | `build` | `build_or_upload_fail` | same path (upload and compile share the return) | none |
| Serial disconnect mid-point | `retrying` → `failed` | `hang` ⚠ | `runtime_hang_or_reset(...)` | retries once (budget ≤ 600 s), then wall | none |
| No response (hang) | `retrying` → `failed` | `hang` | `runtime_hang_or_reset(reset_count=0)` | retry then wall; **0 raw rows written** | none |
| Garbage bytes | `failed` | `hang` | `runtime_hang_or_reset(...)` | garbage never parsed as trials | none |
| CRC error storm (Phase 3) | `failed` | `serial` ⚠ | `session_incomplete` | `crc_error_count=8` recorded correctly | none |
| malloc failure (ESP) | `failed` | `malloc` | `malloc_failed` | **not** retried (deterministic) | none |
| Host clock jump (backwards) | unaffected | — | — | `time_lost_to_interruption_s` stays ≥ 0; `wall_clock_s` is `perf_counter`-based | none |
| Interruption → orphan raw rows | — | — | — | orphans purged, point redone from scratch, completed points untouched | **none** (by design: partial samples are discarded, never topped up) |

⚠ = logged ambiguously; see findings M2 and M3. No injected case lost data or
wrote a partial sample.

---

## Findings

### HIGH

**H1 — ESP8266 Grover n=8 and n=9 are predicted to trip the hardware watchdog and
be recorded as a Memory Wall.**
`firmware/esp8266/src/main.cpp:84,88` disables the watchdog around the timed
region with `ESP.wdtDisable()` … `ESP.wdtEnable(0)`. *(My own knowledge, please
confirm against the ESP8266 core sources/datasheet:* `ESP.wdtDisable()` stops only
the **software** watchdog; the **hardware** WDT still fires at roughly 8 s and is
not fed by anything inside `run_circuit()`.*)* The planned per-rep durations are
**15.62 s for grover n=8 and 130.50 s for grover n=9**
(`timing_model.expected_exec_time_us`), i.e. ~2× and ~16× that window. If the
reset happens, `read_serial_trials()` sees a repeated CSV header, increments
`reset_count`, clears the rows, and the point eventually ends as
`runtime_hang_or_reset(reset_count=N)` — which `resume.is_wall_status()`
(`pc/shared/resume.py:34,46`) treats as a genuine wall, so every higher `n` for
that circuit is abandoned and stays abandoned across resumes
(`resume.known_wall_n()`). The published conclusion would be "ESP8266 Grover wall
at n=8", when the model says its *memory* wall is n=12 and n≥10 is
compute-infeasible. ESP32 has the same shape at a smaller scale (grover n=9 =
7.02 s/rep, n=10 = 61.69 s/rep, `firmware/esp32/src/main.cpp:77-85` yields only
*between* reps).
**Recommended:** before Session B, run ESP8266 `grover --n-start 8 --n-max 8` as a
single point and read `reset_count` from `uno`-style note in
`esp8266_memory_wall.csv`. If it resets, record it as a watchdog limit — a real
and reportable finding — and do not let it be published as a memory wall. Fixing
it would require a firmware change (feeding the HW WDT inside the timed region),
which is explicitly out of scope and would perturb the measurement.
**UNVERIFIED-needs-hardware.**

**H2 — A slow first compile is permanently recorded as a wall.**
`pc/phase2_sweep/esp8266_sweep.py:119,124` (and `:136`) give `pio run` a 120 s
timeout; `uno_sweep.py:122,146` the same; `esp32_sweep.py:110,127` and
`phase3_offload/sweep.py:139,156` use 150 s. On `subprocess.TimeoutExpired` the
code returns `ok=False`, which becomes `build_or_upload_fail` → a wall status →
the circuit is abandoned and `known_wall_n()` keeps skipping it on every later
resume. Measured here over 22 ESP8266 builds: **mean 47.3 s, max 85 s** against
that 120 s ceiling — and because every data point changes `N_QUBITS` and so
triggers a full rebuild, that margin applies to all 115 ESP8266 reflashes, not
just to a cold start. Any additional load (Spotlight, thermal throttling, a
toolchain download inside the same `pio run`) can push a build over the line, and
the result is indistinguishable in the data from a genuine memory wall.
Uno (max 13 s / 120 s) and ESP32 (max 34 s / 150 s) have comfortable margins.
**Recommended:** raise the ESP8266 timeout, pre-warm every environment once
(`pio run -e <env>` per board) before starting a sweep, and/or distinguish
`c_rc == -1` (timeout) from a real compile error so a timeout is retryable rather
than a wall.

**H4 — The 13.9 h budget is optimistic: compile time alone eats 94 % of the whole
reflash allowance, leaving nothing for uploads.**
`REFLASH_COST_S = {uno: 20, esp8266: 30, esp32: 30}` (`pc/shared/timing_model.py`)
is meant to cover compile **and** upload per data point. Measured here across 66
real builds (compile only, no upload): Uno 7.3 s mean, ESP8266 **47.3 s** mean
(85 s max), ESP32 17.3 s mean. Over the 312 reflashes the run actually performs
(73 Uno + 115 ESP8266 + 124 ESP32, Phase 2 and Phase 3 combined):

| | assumed total reflash | measured **compile only** |
|---|---|---|
| Uno | 0.41 h | 0.15 h |
| ESP8266 | 0.96 h | **1.51 h** |
| ESP32 | 1.03 h | 0.59 h |
| **total** | **2.40 h** | **2.25 h (94 %)** |

So the entire upload half of every reflash — all 312 of them — is budgeted at
about 9 minutes in total. A flash-size ÷ `upload_speed` estimate puts the real
figure far higher, driven by `upload_speed = 115200` on both ESP boards
(`firmware/esp32/platformio.ini:18,29`, `firmware/esp8266/platformio.ini:14,25`):
ESP32 images are ~730 kB, which at 115200 baud is on the order of a minute each
*(estimate only — esptool compresses images before writing, so treat this as an
upper bound; it is exactly what a single measured upload would settle)*.
**Recommended:** measure one real build+upload per board before scheduling
(already called for in `run_checklist.md` § Reflash cost) and update
`REFLASH_COST_S` per board rather than keeping one placeholder each; and consider
raising `upload_speed` for the two ESP environments, which is a `platformio.ini`
change with no effect on what is being measured (upload happens outside every
timed region). **Partly UNVERIFIED-needs-hardware** — the compile half is
measured, the upload half is not.

**H3 — Grover n=9 and n=10 exceed the project's own fidelity criterion.**
Measured 1.474e-03 and 6.469e-03 against `INFIDELITY_THRESHOLD = 1e-3`
(`analysis/phase1_compare.py:42`); root cause is float32 amplitudes
(`firmware/common/qsim.hpp:30-32`) accumulating over depths of 161 k and 711 k
gates. Both are planned collection points. The benchmark measures *time*, not
fidelity, so the data is still usable — but the Phase 1 claim "infidelity ≤ 1e-3
for every circuit and n" is not true for the sweep's full `n` range and must not
be restated as-is.
**Recommended:** either report those two points as timing-only with the measured
infidelity quoted, or state a depth-dependent criterion with this float32
justification. Do not silently widen the threshold.

**Numeric types, for the record:** the MCU firmware and the PC validation binary
run the *same* source (`firmware/common/qsim.hpp`, `circuits.hpp`) and therefore
the same precision — `struct Cplx { float re; float im; }`, i.e. IEEE-754
**binary32**, on Uno, ESP8266, ESP32 and in `pc/phase1_validate` alike. Qiskit
Aer computes in **complex128** (binary64). The 1e-3 pass criterion is defined in
exactly one place, `analysis/phase1_compare.py:43`
(`INFIDELITY_THRESHOLD = 1e-3`), and is applied per `(circuit, n)` row of
`data/raw/phase1/infidelity_tvd.csv`.

**Infidelity vs Grover iteration count** — the deviation tracks iteration count
(hence gate depth) monotonically, which is the signature of accumulating
rounding rather than a logic error:

| n | Grover iterations | circuit depth | infidelity (1−F) | TVD | P(marked) | vs 1e-3 |
|---|---|---|---|---|---|---|
| 6 | 6 | 2 173 | 2.579e-05 | 1.290e-05 | 0.9966 | pass |
| 7 | 8 | 8 529 | 8.528e-05 | 4.306e-05 | 0.9955 | pass |
| 8 | 12 | 38 089 | 3.612e-04 | 1.810e-04 | 0.9996 | pass (within 3×) |
| 9 | 17 | 161 399 | **1.474e-03** | 7.414e-04 | 0.9980 | **fail (1.5×)** |
| 10 | 25 | 711 251 | **6.469e-03** | 3.234e-03 | 0.9930 | **fail (6.5×)** |

Iteration count is `max(1, ⌊(π/4)·√(2ⁿ)⌋)`, matched gate-for-gate on both sides.

**Draft "Limitations" paragraph** (for the report; wording ready to lift):

> The on-device simulator represents each amplitude as a pair of IEEE-754
> binary32 floats, a deliberate constraint of the 8-bit target: the Arduino Uno
> has 2 kB of SRAM, and binary64 amplitudes would halve the reachable qubit
> count on every board while requiring software floating-point emulation on two
> of the three. Validation against Qiskit Aer (binary64) therefore measures the
> accumulated effect of this choice as well as the correctness of the gate
> sequence. Across the five shallow circuits the agreement is at the 1e-7 level
> for every qubit count tested. For Grover, whose ancilla-free multi-controlled-Z
> decomposition makes circuit depth grow as O(3ⁿ), the infidelity grows
> monotonically with iteration count and crosses the project's 1e-3 acceptance
> threshold between n=8 (3.6e-4) and n=9 (1.5e-3), reaching 6.5e-3 at n=10. The
> algorithm still succeeds at every tested n — the probability of the marked
> state stays above 0.993 throughout — so the discrepancy is amplitude-level
> precision loss, not a structural error. We therefore report execution-time
> results for Grover at n=9 and n=10, which are unaffected by amplitude
> precision, while noting that their state-vector fidelity is outside the
> validation threshold used for the remaining points. No change was made to the
> simulator or to the threshold in response to this finding; both are recorded
> as stated limitations of the measurement.

### MEDIUM

**M4 — Nothing is pinned.** No `requirements.txt`, lockfile, or `pyproject.toml`
exists anywhere in the repo; `firmware/*/platformio.ini:6-10` declare
`platform = espressif32` / `espressif8266` / `atmelavr` with no `@version`. A
`pio pkg update` mid-run silently changes the compiler that produces the firmware
whose execution time is the experiment's dependent variable. Worse, the
environment JSON records only the PlatformIO **Core** version
(`pc/shared/telemetry.py:_pio_version` runs `pio --version`), not the platform or
framework versions, so the change would not even be visible afterwards.
**Current versions, for the record:** atmelavr 5.3.0, espressif32 7.0.1,
espressif8266 4.2.1, framework-arduino-avr 5.4.0,
framework-arduinoespressif32 3.20017.241212, framework-arduinoespressif8266
3.30102.0, PlatformIO Core 6.1.19; Python 3.11.7, qiskit 2.5.1, qiskit-aer 0.17.2,
numpy 2.4.6, pyserial 3.5, scipy 1.17.1, pandas 3.0.5, matplotlib 3.11.1.
**Recommended:** pin the three `platform =` lines to the versions above and freeze
the Python environment (`pip freeze > requirements.txt`) before the first session.

**M5 — `analysis/phase1_compare.py` overwrites raw data.** Lines 292 and 317 open
`data/raw/phase1/phase1_metadata.csv` and `infidelity_tvd.csv` with mode `"w"`.
Every other `data/raw/` writer is append-only, and the sweeps' `--fresh` archives
rather than deletes (`pc/shared/resume.archive_existing`). Re-running Phase 1
validation destroys the previous Phase 1 dataset with no recovery path. (This is
why this preflight ran its own comparison out of `/tmp` instead.)
`analysis/la_capture_plan.py:202` also writes under `data/raw/` with `"w"`, but
that file is a regenerable plan, not measurement data.

**M6 — RESOLVED (2026-09-22): the repo lives outside `~/Documents` now.**
This finding originally reported the repo path under `~/Documents`
(`~/Documents/QuantumMCU Research/quantum-lab`), which macOS gates behind
Privacy & Security → Files and Folders — not hypothetical, access to the
whole repository was lost twice while building this tooling, mid-task, with
`Operation not permitted` on every read. The working copy has since moved to
`~/Developer/quantum-lab`, which is not under any TCC-gated folder category
(Documents/Desktop/Downloads), so this risk no longer applies to collection
runs from that path. Kept here for the historical record — if the repo is
ever relocated back under `~/Documents`, `~/Desktop`, or `~/Downloads`, this
risk returns and the original recommendation applies again: confirm the
Files and Folders grant for the terminal/host app before starting a
multi-hour session, or accept that resume exists exactly for this.

**M2 — A cable/port disconnect is tagged `failure_type=hang`.**
`pc/phase2_sweep/uno_sweep.py:464` (and `esp32_sweep.py:460`,
`esp8266_sweep.py:469`) set `failure_type="hang"` for every non-`done` outcome.
Verified by injection: a `serial.SerialException` mid-point produces
`status=failed, failure_type=hang`, with the real cause visible only as text
inside `failure_message` (`serial_error=…`). `FAILURE_TYPES` contains `"serial"`,
which no Phase 2 path ever writes. Post-hoc, "the cable fell out" and "the board
stopped answering" are indistinguishable without string-matching a free-text
field — and they have opposite implications for whether a wall is real.

**M3 — A PC-side Aer failure is tagged `failure_type=serial`.**
`pc/phase3_offload/sweep.py:517` sets `"none" if status == "ok" else "serial"`.
When `simulate_and_sample()` raises (e.g. `MemoryError` at high n), the exception
is captured into `last_sim_error` (`sweep.py:234-238`) and the session ends
`session_incomplete` → `failure_type="serial"`, even though nothing went wrong on
the wire. `FAILURE_TYPES` contains `"sim"`, which no path ever writes, and unlike
the CRC case (which genuinely cannot be separated — see `telemetry.py`'s comment
block and the accepted decision) **this one is separable**: `last_sim_error` is
non-empty exactly when the cause was PC-side simulation.

**M1 — `qpe n=2` is collected but never validated.**
`n_values_for_sweep` (`pc/shared/circuit_ids.py:27`) returns `range(2, n_max+1)`
for `qpe`, so `qpe n=2` is one of the 154 planned points on all three boards. The
Phase 1 validator refuses it: `pc/phase1_validate/main.cpp:34` rejects `n < 3` and
`analysis/phase1_compare.py:39` restricts `qpe` to `n ≥ 3`. The firmware itself
has no such guard, so the point will build, run and produce timings — with a
1-qubit counting register, which cannot represent `φ = 0.25` at all. The timing is
meaningful; the circuit's *output* is not, and nothing in the pipeline says so.

### LOW

**L1 — The LA pulse is wider than the `micros()` window.** In all three Phase 2
firmwares the order is `digitalWrite(HIGH)` → `t0 = micros()` → `run_circuit()` →
`t1 = micros()` → `digitalWrite(LOW)` (`firmware/uno/src/main.cpp:86-90`,
`esp8266/src/main.cpp:83-89`, `esp32/src/main.cpp:81-85`). The pulse therefore
includes one `digitalWrite` at each end — and on the ESP8266 also
`ESP.wdtDisable()` and `ESP.wdtEnable(0)` — which the `micros()` interval excludes.
The LA will read systematically *longer* than `micros()`, by a fixed offset
(*my own knowledge: `digitalWrite` costs roughly 3-5 µs on AVR, well under 1 µs on
the ESPs*). At the shortest Uno point (~284 µs) that is a ~1-3 % bias, inside the
5 % relative threshold, and the per-board absolute floor added in `la_crosscheck.py`
absorbs the rest. Worth stating in the write-up rather than discovering during
analysis. **UNVERIFIED-needs-hardware** (the magnitude, not the direction).

**L2 — Uno links over 100 % SRAM without failing.** `bell_ghz n=8` reports
`RAM: 2254 bytes from 2048` and `pio run` exits 0. The sweep therefore uploads and
waits out a full timeout budget to discover at run time what the linker already
knew. Not a correctness bug (this *is* the documented Uno failure mode), but
`build_and_upload` already parses `ram_pct` and could short-circuit.

**L3 — Disk is at 89 % capacity.** 22 GiB free against a worst-case data volume of
~101 MB (0.69 MB Phase 2 raw + 0.79 MB Phase 3 raw + ~62 KB telemetry + ~0.10 GB
if every LA capture is taken in FORMAT A). Ample for the data; thin for macOS
generally, and `.pio` build directories grow.

**L4 — Phase 3 bauds above 115200 are untested.** The default is `[115200]`
(`pc/phase3_offload/sweep.py:279`) and everything agrees at that rate. The module
header suggests `--bauds 115200 250000`. Whether the CH340/CP2102/native-USB chip
on each specific board sustains 250000 is an assumption; no board has been
connected. **UNVERIFIED-needs-hardware.**

**L6 — Phase 3 records no `f_cpu` in its environment metadata.**
`pc/phase3_offload/sweep.py:362-363` passes `None` for the `f_cpu` argument of
`write_environment_metadata`, so Phase 3 session JSONs carry `"f_cpu": null`
while Phase 2's carry the real value (Uno 16 MHz, ESP8266 80 MHz, ESP32 240 MHz —
`uno_sweep.py:86`, `esp8266_sweep.py:89`, `esp32_sweep.py:80`). Those constants
are also hardcoded PC-side and never cross-checked against the firmware build;
they happen to match because no `platformio.ini` overrides `board_build.f_cpu`.

**L5 — Offload array types differ across boards.**
`firmware/uno/src_offload/main_offload.cpp:29` uses `uint8_t g_timed_out[REPS]`
while `firmware/esp8266/src_offload/main_offload.cpp:25` uses `long g_timed_out[REPS]`
(300 bytes extra static RAM, harmless on an ESP). Cosmetic inconsistency only.

---

## Claims that come from my own knowledge, not from this repo

Flagged for datasheet confirmation, as requested:

1. **ESP8266:** `ESP.wdtDisable()` disables only the software watchdog; the
   hardware WDT still resets the chip at roughly 8 s. (Basis for H1.)
2. **ESP8266 strapping/reserved pins:** GPIO0, GPIO2, GPIO15 are boot-mode
   strapping pins; GPIO1/GPIO3 are UART0 TX/RX; GPIO6-GPIO11 are wired to the
   SPI flash. The firmware uses **GPIO5 (= D1 on the NodeMCU silkscreen)**, which
   is none of these → no conflict.
3. **ESP32 strapping/reserved pins:** GPIO0, GPIO2, GPIO5, GPIO12, GPIO15 are
   strapping pins; GPIO6-GPIO11 are flash; GPIO34-GPIO39 are input-only. The
   firmware uses **GPIO4** → no conflict. *(Note GPIO5 is a strapping pin on
   ESP32 but an ordinary pin on ESP8266; the two boards' timing pins are
   deliberately different numbers.)*
4. **ESP32 Arduino core:** the task watchdog is typically not enabled for the
   Arduino `loopTask` by default, which is why a 61 s blocking `run_circuit()` may
   survive; IDLE-task starvation behaviour depends on the sdkconfig shipped with
   the installed core version.
5. **Uno/AVR:** no watchdog is enabled by the Arduino core by default, so the
   21 s/rep Grover n=7 point should not reset; pins 0/1 are UART0 and are not used
   by the firmware (it uses D7).
6. **`digitalWrite` cost:** ~3-5 µs on a 16 MHz AVR, sub-µs on the ESPs.
   (Basis for L1's magnitude.)
7. **CRC-8/SMBUS:** the catalogue check value for the ASCII string `123456789`
   is `0xF4` — this one is not merely knowledge, it was verified against both
   implementations in P1-4.

---

## What can only be verified once hardware is connected

1. **The real reflash cost.** `REFLASH_COST_S = {uno: 20, esp8266: 30, esp32: 30}`
   (`pc/shared/timing_model.py`) has never been measured, and it is ~90 % of every
   cheap-circuit session. The whole 13.9 h estimate rests on it.
2. **H1, the ESP8266 watchdog behaviour** on Grover n=8/n=9 — and hence whether
   the ESP8266 "wall" is a memory wall or a watchdog limit.
3. **Whether Uno n=8 really hangs** as the 110 % static RAM figure predicts.
4. **`pio run -t upload`** — the upload half of `build_and_upload` has never been
   executed in any form, on any board.
5. **Port enumeration and re-enumeration**, including the USB-CDC path change
   `find_uno_port()` exists to absorb.
6. **Serial reliability at 115200** over 100-rep bursts, and anything above that
   rate for Phase 3 (L4).
7. **Measured vs modelled per-rep execution time** — the model was fitted on the
   n=30 dataset and has not been checked against the current firmware.
8. **The LA end-to-end**: whether a real export matches FORMAT A/B, the loaned
   unit's actual supported sample rates, and the L1 pulse-width offset.
9. **Boot behaviour**: `while (!Serial)` on the Uno, ESP boot-ROM chatter on the
   wire, and whether `BOOT_WAIT_S` (1.0 s Uno / 1.5 s Phase 3) is enough.
