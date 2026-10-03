# QuantumMCU Research — Quantum Lab

> **RESTART 2026-10-03 — scope cut and full re-collection.** The experiment now
> covers four circuits only (`h_all`, `bell_ghz`, `qft`, `grover`); `qpe` and
> `steane_encode` were removed from the plan (their code stays in
> `firmware/common/circuits.hpp`; `pc/run.py` refuses them). All hardware data
> collected so far is retired to `data/archive/restart_20261003T111500Z/`
> (MANIFEST.json, sha256-verified) and will be re-collected from scratch.
> The Logic Analyzer timing reference is being replaced by a second ESP32
> pulse counter (`docs/counter_design.md`). Numbers below that cite measured
> data refer to the retired dataset. Plan and predictions:
> `docs/experiment_plan.md`; `python pc/run.py --plan` prints the time table.

Comparative performance benchmarking of quantum micro-simulators across
diverse microcontroller architectures for edge computing.

**Research question:** for a given circuit and qubit count, should a
microcontroller simulate the quantum circuit *locally*, or *offload* it to a
PC running Qiskit Aer?

## What is measured, and what is not

- **Measured (Phase 2, on-device):** wall-clock execution time per circuit
  repetition, via `micros()` bracketing the simulation loop on the MCU
  itself, for `n = 2` upward until the board fails. Compile-time RAM usage
  (`avr-size` / equivalent) is recorded for every point, not just failures.
  A Logic Analyzer cross-check of the `micros()` timing exists in code
  (`--la`, Uno only) but has **never been run against real hardware or even
  a `sigrok-cli` demo driver** — see Limitations.
- **Measured (Phase 3, offload):** round-trip latency and frame integrity
  (CRC-8) of a fixed 4-byte request / 6-byte response protocol between MCU
  and PC. The PC re-simulates with Qiskit Aer from scratch on every request
  (no caching), so the measured cost reflects genuine offload overhead.
- **NOT measured, anywhere in this project:** simulation *correctness* on
  the board itself. Phase 1 validates the hand-written C++ simulator against
  Qiskit Aer once, on the PC, before any board is trusted — the boards never
  report a fidelity number back. Phase 3's "board" doesn't compute at all;
  it only relays a request and receives a numeric outcome. If a board's
  arithmetic were subtly wrong, this project's current instrumentation would
  not detect it independently of Phase 1's PC-side check.

## Hardware

| Board | Word size | FPU | Clock | SRAM | Allocation |
|---|---|---|---|---|---|
| Arduino Uno R3 (ATmega328P) | 8-bit | no | 16 MHz | 2 KB | static array only |
| NodeMCU ESP8266 (ESP-12E) | 32-bit | no | 80 MHz | 80 KB | dynamic (`malloc`) |
| ESP32 DevKit V1 | 32-bit | **yes** | 240 MHz | 320 KB | dynamic (`malloc`) |

**Only the Uno has ever been run against real hardware in this repository.**
ESP8266 and ESP32 are fully implemented (firmware, sweep scripts, timing
model) but every number for them anywhere in this repo — timing estimates,
expected walls — is a **prediction from `pc/shared/timing_model.py` and a
compile-only build matrix**, not a measurement. Phase 3 (offload) has not
been run on any board. Treat every ESP8266/ESP32/Phase-3 claim as
UNVERIFIED until real data exists under `data/raw/phase{2,3}/{esp8266,esp32}/`.

Four test circuits, built from three gates only (H, CNOT, Controlled-Phase):
`h_all`, `bell_ghz`, `qft`, `grover`. (`qpe` and `steane_encode` were removed
from the experiment plan on 2026-10-03; their code remains in the firmware
source only.) See `pc/shared/circuit_ids.py` and
`pc/shared/timing_model.gate_counts()` for exact definitions.

---

## Repository layout

```
firmware/
  common/              portable simulator core (Cplx struct, no std::complex),
                        identical on all 3 boards AND the PC
  uno/ esp8266/ esp32/  src/ = Phase 2 firmware, src_offload/ = Phase 3 firmware,
                        platformio.ini injects N_QUBITS/CIRCUIT_ID/BAUD_RATE

pc/
  run.py               the manual runner (this doc's main entry point)
  run_test.py           mocked tests for run.py -- no hardware
  phase1_validate/      C++ runner: prints a state vector for Qiskit to check
  phase2_sweep/         one script per board -- build, flash, read serial,
                        climb n until failure
  phase3_offload/       serial server (answers frames with Qiskit) +
                        orchestrator, one script, --board selects
  shared/                circuit_ids.py, timing_model.py, paths.py (single
                        source of truth for every data/raw and data/figures
                        path), telemetry.py, resume.py, plot_style.py

analysis/               validation, statistics, figure generation, LA tooling

data/
  raw/phase{2,3}/<board>/<circuit>/   per-repetition measurements, one
                                       directory per (phase, board, circuit)
  processed/            aggregated summaries (currently just .gitkeep --
                        not yet regenerated for the REPS=100 dataset)
  figures/<board>/<circuit>/*.png     per-run diagnostic charts, PNG only
  archive/phase{2,3}/<board>/<circuit>/<timestamp>/   --fresh's archived
                        data, moved not deleted, MANIFEST.json per folder --
                        read by nothing in the pipeline, safe to delete

docs/
  analysis/<board>/     per-circuit + comparison write-ups (OBSERVED vs
                        INTERPRETATION, every claim cited by file:line)
  run/                  per-board runner command reference (this task)
  manual_run_guide.md   full manual command reference (pre-runner)
  preflight_report.md   pre-hardware findings (build matrix, fidelity, H1-H4)
  proposal/ report/ poster/ diagrams/   empty -- to be written from the
                        REPS=100 dataset once complete
```

The simulator core avoids `std::complex` (`avr-g++` has no full `libstdc++`)
and uses `struct Cplx { float re, im; }`. Qubit 0 = LSB of the state index
(Qiskit's convention). `firmware/common/` compiles unchanged on all four
targets; only the allocation policy differs per board, in each board's own
`main.cpp`.

---

## Setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` is pinned to the exact versions used for every number in
`docs/preflight_report.md` (Python 3.11.7, `qiskit==2.5.1`,
`qiskit-aer==0.17.2`, `numpy==2.4.6`, `pyserial==3.5`, full list in the
file) — this project's dependent variable is execution *time*, so an
unpinned `numpy`/`qiskit-aer` upgrade would silently change what Phase 3
measures. PlatformIO platforms are pinned separately, per board, in
`firmware/*/platformio.ini` (`atmelavr@5.3.0`, `espressif8266@4.2.1`,
`espressif32@7.0.1`).

Requires [PlatformIO](https://platformio.org/) (`pio`) on `PATH`, or set
`PIO_PATH` if it isn't.

**macOS notes:**
- Serial ports are `/dev/cu.usbmodem*` (Uno) or `/dev/cu.usbserial*` /
  `/dev/cu.wchusbserial*` / `/dev/cu.SLAB_USBtoUART*` (ESP8266/ESP32,
  driver-dependent). The Uno's port number can change mid-session
  (`usbmodem101` → `usbmodem1101`); the sweep scripts re-detect it
  automatically, you don't need to.
- Terminal.app / whatever runs `pio upload` needs Full Disk Access if you
  see `Operation not permitted` opening the port. Avoid running this repo
  from an iCloud-synced folder — sync can hold a file lock at the exact
  moment a sweep script tries to write a result row.
- Prevent sleep before any real collection: `caffeinate -dims` in a
  separate terminal (or `pc/run.py` will tell you if nothing is
  preventing it — see below).

---

## How to run

**The owner may run any algorithm on any board at any time with `pc/run.py`,
without waiting for approval** (standing decision, 2026-09-21 — see
`run_log.md`). This applies only to the owner's own direct use of the
runner; a task run through Claude Code still follows the one-algorithm-at-
a-time, stop-and-report workflow.

`pc/run.py` is a thin, validating front end — it contains **no** collection
logic of its own. It resolves the exact command it would run, prints it,
runs read-only preflight checks (git tree, port, sleep prevention, resume
state), asks for confirmation, and delegates to the real per-board sweep
script (`pc/phase2_sweep/<board>_sweep.py` or `pc/phase3_offload/sweep.py`).
Every flag/example on this page is real, read directly from `pc/run.py
--help` and its own source — nothing here is invented or carried over from
an older doc.

### a. One-time setup (each new terminal session)

```bash
# 1. Activate the venv -- your prompt should now start with "(.venv)".
#    That prefix IS the confirmation it worked; if you don't see it, the
#    venv isn't active and `python`/`pip` will resolve to the wrong
#    interpreter for the rest of this session.
source .venv/bin/activate

# 2. Keep the machine awake for the WHOLE session, in a SEPARATE terminal.
#    This command does not return while it's running -- that's normal,
#    not a hang. Leave that terminal open and don't touch it; Ctrl+C it
#    only when you're completely done for the day.
caffeinate -dims

# 3. Confirm the repo is in the state you expect before touching hardware.
git status
git describe --tags

# 4. Find your board's port. Do this EVERY session -- the exact number can
#    change for the SAME physical board/cable (e.g. usbmodem101 vs
#    usbmodem1101) after a reconnect, a reflash, or a reboot.
pio device list
```

`pio device list` prints every serial device currently attached, with a USB
vendor:product ID. This project has never recorded a confirmed VID:PID for
its own specific boards (no ESP8266/ESP32 hardware run has completed as of
this writing) — the table below states the *typical* ID for the chip family
each board type usually uses, **not a value verified against this repo's
own hardware**:

| Board | Typical port pattern (macOS) | Typical USB chip (unverified for this repo) |
|---|---|---|
| Uno R3 | `/dev/cu.usbmodemXXXX` | native USB (ATmega16U2) — commonly `2341:0043` or `2341:0001` |
| ESP8266 (NodeMCU) | `/dev/cu.usbserial-XXXX`, `/dev/cu.wchusbserial-XXXX`, or `/dev/cu.SLAB_USBtoUART` | CH340 (`1A86:7523`) or CP2102 (`10C4:EA60`), board-dependent |
| ESP32 DevKit | same three patterns as ESP8266 | usually CP2102 (`10C4:EA60`), sometimes CH340 |

Treat the VID:PID column as a sanity check only. **Always re-run
`pio device list` in the same session you're about to collect data and pass
`--port` whatever it shows right then** — never reuse a port string from an
earlier session, from these docs, or from your shell history.

### b. Full flag reference (from `pc/run.py --help`)

| Flag | Required | Purpose | Default | Applies to |
|---|---|---|---|---|
| `--board {uno,esp8266,esp32}` | **yes** | which board | — | all |
| `--algorithm {h_all,bell_ghz,qft,grover}` | **yes** | which circuit (one value, not a list) | — | all |
| `--phase {2,3}` | **yes** | Phase 2 (on-device) or Phase 3 (PC-offload) | — | all |
| `--port PORT` | **yes** | serial device path, e.g. `/dev/cu.usbmodem1101` — **never auto-guessed** | — | all |
| `--n-start N_START` | no | sweep starting `n`, passed through unchanged | non-fresh: the delegated script's own default (`2`); `--fresh`: the circuit's own minimum meaningful `n` (see "Fresh runs" below) | all |
| `--n-max N_MAX` | no | sweep ceiling `n`, passed through unchanged | phase 2: uno `14`, esp8266 `16`, esp32 `18`; phase 3: `22` on every board (`N_SAFETY_CAP`) | all |
| `--reps REPS` | no | **validation only, never passed through** — must equal `100` (`pc/shared/timing_model.REPS`, a compile-time firmware constant) or the run is refused | — | all |
| `--build-timeout BUILD_TIMEOUT` | no | max seconds per `pio run` (compile) or `pio run -t upload` call, passed through | `300` | all |
| `--upload-retry-settle-s UPLOAD_RETRY_SETTLE_S` | no | settle delay before retrying an upload-stage failure | `2.0` | **Uno Phase 2 only** — refused for every other board/phase |
| `--la` | no | enable Logic Analyzer capture (`sigrok-cli`) | off | **Uno Phase 2 only** — refused for every other board/phase; UNVERIFIED, never run against real `sigrok-cli` (see Limitations) |
| `--fresh` | no | archive existing data for this (board, algorithm, phase, la) to `data/archive/`, then start at the circuit's own minimum meaningful `n` | off | all |
| `--dry-run` | no | preview only — print the resolved command, the preflight checks, and (if `--fresh`) the planned archive destination; never touches hardware, never calls `pio`, never moves or writes a data file | off | all |
| `--yes` | no | skip the interactive y/n confirmation before touching hardware | off | all |

Every invocation of `pc/run.py` — dry-run, refused, real, interrupted — is
recorded in `data/run_history.jsonl`; see § "Checking results after a run"
below.

### c. Worked examples, every board × phase

Each block: the exact dry-run first, what to expect from it, then the exact
real command. **Replace `/dev/cu.usbmodem1101` / `/dev/cu.usbserial-0001` /
`/dev/cu.SLAB_USBtoUART` below with whatever `pio device list` showed you in
step (a.4) — these are illustrative examples, not values to copy blindly.**

**Uno, Phase 2** (the only board/phase with real hardware data so far):
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --dry-run
```
Expect: a `--- preflight ---` block (git clean/dirty state, sleep-prevention
status, resume state read from the existing `no_la/memory_wall.csv` if any),
the line `command: <python> pc/phase2_sweep/uno_sweep.py --port
/dev/cu.usbmodem1101 --circuits h_all`, then `port: [dry-run] skipping pio
device list / port checks -- no hardware access`, and finally `[dry-run]
stopping here -- no subprocess started, no file moved`. Exit code `0`.
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101
```

**Uno, Phase 3** — **UNVERIFIED: no Phase 3 session has completed on real
hardware yet, on any board** (see Limitations):
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 3 \
    --port /dev/cu.usbmodem1101 --dry-run
```
Expect the same preflight block, prefixed with the `*** UNVERIFIED: board='uno'
phase=3 has never been run against real hardware ... ***` banner (printed
for every Phase 3 run, on every board — not Uno-specific).
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 3 \
    --port /dev/cu.usbmodem1101
```

**ESP8266, Phase 2** — **UNVERIFIED: no ESP8266 session has completed on
real hardware yet** (see Limitations):
```bash
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 2 \
    --port /dev/cu.usbserial-0001 --dry-run
```
Expect the same `*** UNVERIFIED: board='esp8266' phase=2 ... ***` banner
(printed for every ESP8266/ESP32 run, any phase — the board itself is
unverified, not just Phase 3).
```bash
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 2 \
    --port /dev/cu.usbserial-0001
```

**ESP8266, Phase 3** — **UNVERIFIED** (both the board and Phase 3 itself):
```bash
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 3 \
    --port /dev/cu.usbserial-0001 --dry-run
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 3 \
    --port /dev/cu.usbserial-0001
```

**ESP32, Phase 2** — **UNVERIFIED: no ESP32 session has completed on real
hardware yet**:
```bash
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 2 \
    --port /dev/cu.SLAB_USBtoUART --dry-run
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 2 \
    --port /dev/cu.SLAB_USBtoUART
```

**ESP32, Phase 3** — **UNVERIFIED** (both the board and Phase 3 itself):
```bash
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 3 \
    --port /dev/cu.SLAB_USBtoUART --dry-run
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 3 \
    --port /dev/cu.SLAB_USBtoUART
```

Per-board command tables (exact commands, expected point counts, estimated
or measured times, expected walls) live in `docs/run/uno.md`,
`docs/run/esp8266.md`, `docs/run/esp32.md`, and `docs/run/phase3.md`. For
every flag the underlying sweep scripts support that isn't listed above
(there are a few, e.g. `--wdt-threshold-s`), see `docs/manual_run_guide.md`,
which documents the scripts directly and is the fallback if `pc/run.py`
doesn't cover your case.

---

## Fresh runs and the archive

**Exact worked example** (discard existing Uno `h_all` Phase 2 data and
start over from the circuit's own minimum meaningful `n`):
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --fresh --dry-run   # preview the archive destination first
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --fresh              # then run it for real
```
The dry-run's `archive: existing data (...) will be moved to <dest> (with
MANIFEST.json) before collection starts` line names the exact destination
before anything moves. Find it afterward the same way (it's also printed at
the end of the real run, under `--- fresh run summary ---`), or list
`data/archive/phase2/uno/h_all/` directly. Delete a specific archive folder
any time with:
```bash
rm -r data/archive/phase2/uno/h_all/<the-UTC-timestamp-shown>/
```
Deleting it affects nothing in the pipeline — proven below.

`--fresh` archives (moves, never deletes or copies) that (board, algorithm,
phase)'s existing `data/raw/`, `data/figures/`, and
`docs/analysis/<board>/<algorithm>.md` — whichever exist — to
`data/archive/phase<N>/<board>/<algorithm>/<UTC timestamp>/`, with a
`MANIFEST.json` (git commit/dirty flag/ref, the reason, the exact command,
and a sha256 + row count per moved file, computed **before** the move so a
failure never loses data). If the move or the manifest write fails for any
reason, everything already moved is rolled back and the run aborts before
any collection starts — proven in `pc/run_test.py`.

**Nothing in the pipeline reads from `data/archive/`** — not `pc/`, not
`analysis/`, not `resume.py`/`telemetry.py`, not the graph scripts, not the
cumulative chart. This is proven, not just asserted:
`pc/run_test.py`'s `test_archive_independence` greps the whole codebase (the
only "archive" references outside `pc/run.py` are the unrelated, pre-
existing `resume.archive_existing()`, an in-place `*.pre-fresh-<ts>.csv`
rename inside the same directory) and separately runs the real analysis
pipeline on a scratch copy, deletes `data/archive/` in that copy, and
confirms byte-identical output (sha256 of every generated figure) before
and after. **You can delete an archive folder at any time** with a plain
`rm -r data/archive/phase<N>/<board>/<algorithm>/<timestamp>/` — the runner
also prints this exact command at the end of every fresh run.
`data/archive/` is gitignored — nothing under it is ever committed.

**A fresh run starts at the circuit's own minimum *meaningful* `n`, not
always 2** — investigated read-only against `firmware/common/circuits.hpp`,
`analysis/phase1_compare.py`, and `pc/shared/timing_model.py` (full
citations in `run_log.md`'s 2026-09-21 entry). No circuit crashes the
firmware at n=1, but two of the four produce a degenerate, not-what-the-
name-implies circuit below a stated minimum:

| Circuit | Min `n` for `--fresh` | Why |
|---|---|---|
| `h_all` | 1 | 1-qubit superposition is a real, valid state |
| `qft` | 1 | 1-qubit QFT literally IS a single H gate |
| `bell_ghz` | 2 | n=1 runs (just H(0)) but produces no entanglement — not a Bell/GHZ state |
| `grover` | 2 | no control qubit left for the oracle's multi-controlled-Z (stated in both the firmware source and `phase1_compare.py`, independently) |

An explicit `--n-start` below this minimum is clamped up with a printed
notice on a `--fresh` run — never silently sent to the board, never logged
as a failure or a wall. **No circuit has ever been Phase 1 (Qiskit)
validated at n=1** — `analysis/phase1_compare.py`'s own default n-list
starts at 2 for everything. `pc/shared/timing_model.py` does have a working
timeout-budget estimate at n=1 for every circuit (verified by calling it —
no exceptions), so this isn't a blind guess, just an unvalidated one.

Non-fresh (resume/append) runs are **completely unchanged** by any of this —
no new default, no clamping, exactly the pre-2026-09-21 behavior.

---

## Data layout

```
data/raw/phase<N>/<board>/<circuit>/{no_la,with_la}/
  raw.csv            every repetition, 1 row per rep, 100 rows per ok point
  memory_wall.csv     Phase 2 only: 1 terminal row per (circuit, n) point
  session_log.csv      Phase 3 only: 1 terminal row per (circuit, n, baud) point
  points.csv          1 row per upload attempt (a retried point has >1 row)
  sessions.csv         1 row per script invocation
  env/<session_id>.json   toolchain versions, firmware_source_hash,
                        sleep_prevention, per session, la_used +
                        la_dir_bucket + la_dir_matches_flag (cross-check)
  la/                 with_la/ only — Logic Analyzer captures, capture_plan.csv,
                        capture_issues.log (can't exist without --la)

data/figures/<board>/<circuit>/{no_la,with_la}/{exec_time_vs_n,outcomes_vs_n,time_per_point}.png
data/figures/<board>/{no_la,with_la}/all_algorithms_so_far.png   cumulative, regenerated every run
```

**no_la vs with_la (2026-09-22).** Every point lives under `no_la/` (default,
plain `micros()` timing) or `with_la/` (collected with `--la` — Uno Phase 2
only, and only once sigrok-cli actually found a device; if `--la` was passed
but sigrok was unavailable, the point still lands under `no_la/`, since no
capture was actually attempted — see `pc/phase2_sweep/uno_sweep.py`'s
`la_active`). **The two are never mixed in analysis**: timing-only and
LA-cross-checked points are different measurements of the same circuit, not
interchangeable samples of the same thing — a sweep resuming a `no_la` run
never treats an existing `with_la` point (or vice versa) as already done,
and every plotting/summarize script reads from exactly one bucket per
invocation. Every point collected so far (all of it, prior to 2026-09-22)
was collected without `--la` and now lives under `no_la/` — migrated
losslessly with `git mv` (row counts + sha256 verified identical before and
after, see `run_log.md`), never rewritten. No `with_la/` data exists yet
anywhere in this repo (`--la` has never completed against real hardware).

**PNG only.** All figure-generation in this project (`pc/shared/plot_style.
save_figure_png_only`) writes PNG, never SVG, to this tree. (A separate,
older cross-board comparison tool, `analysis/phase2_plot.py`, targets a
different path — `data/figures/phase2/` — and still emits PNG+SVG; it has
not been run against the REPS=100 dataset and that path does not currently
exist on disk. Out of scope for this doc; see the script itself.)

`pc/shared/paths.py` is the single source of truth for every path above —
every sweep and analysis script imports it rather than building paths by
hand.

---

## Resume, interrupt, retry

**Ctrl+C** interrupts the delegated sweep script; `pc/run.py` catches it,
prints a note that resume will pick up where it left off, records
`event=interrupted` in `data/run_history.jsonl`, and exits with code `130`.

**Resume is always on, no flag needed — the exact re-run command is the
same command you just interrupted**, e.g.:
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101
```
**Telling a resume from a fresh point:** the delegated sweep script's own
first printed lines are the tell — `resume summary (<board>)` followed by
`already done: N/M point(s)` and one `skip (<circuit>, <n>): already <status>`
line per already-completed point means resume found prior work; `already
done: 0/M point(s)` means it's starting clean (either truly the first run,
or every previous point was swept away as an orphan — the script prints
`resume: purged N orphan raw row(s)...` when that happens). `git status`
itself won't show this — resume state lives in
`data/raw/.../no_la/memory_wall.csv`, not in what's staged/modified in git;
check that file directly (or `pc/run_history.py`, see below) if you want to
confirm before running.
- A point with a terminal row in `memory_wall.csv`/`session_log.csv` is
  skipped instantly, whether it recorded `ok` or a wall.
- A point that died mid-run (rows in `raw.csv` but no matching terminal
  row) is swept away and re-run from repetition 0 — never assume it
  resumes mid-point; trials from two different sessions aren't comparable
  samples.
- A circuit that already hit a positive-evidence wall (`build_overflow`)
  skips every higher `n` immediately, even ones with no prior record.
- **Never run two sweeps against the same port at once.** `pc/run.py`
  checks for this (via `lsof`) before starting; the underlying scripts do
  not, and this exact collision has corrupted a real run in this project's
  own history (concurrent processes fighting over one serial port produces
  garbled `avrdude` protocol errors that look like a hardware fault but
  aren't).

**Upload-stage failure retry:** the same `n` is retried immediately, up to
3 attempts total, each logged (attempt number, avrdude signature,
timestamps). Exhausting all 3 does **not** abandon the circuit — the sweep
continues to the next `n`. Two consecutive `n` values each exhausting all 3
attempts stops the whole run (exit code 2) — a likely cable/port/hardware
problem, not a data-collection decision.

**Memory Wall is recorded only on positive evidence** — compile-time RAM
> 100%, a build-time overflow, or (ESP8266/ESP32 only) the board reporting
`malloc_failed`. A hang or reset *without* that evidence is recorded as
`runtime_hang_or_reset` (or `watchdog_suspected` on ESP boards past their
estimated per-rep time), not a wall — it doesn't stop future runs from
retrying higher `n`. This distinction matters: on the Uno, `avr-ld` links
successfully even when compile-time RAM exceeds 100% (a real toolchain
quirk, `docs/preflight_report.md` finding L2), so a wall can only be
trusted from the RAM percentage, never from link success alone.

One algorithm at a time, `REPS=100`, `n` climbing from 2 until the first
wall or `n-max`. After each algorithm, the standing practice in this
project has been to generate and review graphs (see below) before moving
to the next one — see `run_log.md`'s "Standing Operator Decisions" section
for the full, dated record of every rule and why it was adopted.

---

## Checking results after a run

```bash
# raw trials, terminal-record summary, per-attempt log, session log, env metadata
head -3 data/raw/phase2/uno/h_all/no_la/raw.csv
cat data/raw/phase2/uno/h_all/no_la/memory_wall.csv
tail -1 data/raw/phase2/uno/h_all/no_la/points.csv
tail -1 data/raw/phase2/uno/h_all/no_la/sessions.csv
ls data/raw/phase2/uno/h_all/no_la/env/
```
Use `with_la/` instead of `no_la/` if you ran with `--la` and sigrok-cli
actually found a device (see § "no_la vs with_la" under Data layout below).

**A healthy status distribution** in `memory_wall.csv`, one terminal row per
`n` attempted: a run of consecutive `ok` rows for the low `n` values, then
exactly one wall-or-stop row where the sweep ended — either `build_overflow`
(positive RAM evidence, a real wall) or `malloc_failed` (ESP8266/ESP32
only), or a `runtime_hang_or_reset`/`watchdog_suspected`/`build_or_upload_fail`
row (not a wall — flagged for manual review, see § "Resume, interrupt,
retry" above). Any `skipped_resume`/`skipped_known_wall`/
`skipped_compute_infeasible` rows in `points.csv` are expected on a resumed
or `--fresh`-clamped run, not a problem.

**This run's own history entry:**
```bash
.venv/bin/python pc/run_history.py --board uno --algorithm h_all --phase 2
```
(`pc/run_history.py --help` for the full filter list — `--source
{live,backfill}`, `--since`/`--until` a `YYYY-MM-DD` or full ISO timestamp.
Run with no flags at all to see every invocation ever recorded.) Each
invocation prints as one line: timestamp, board/algorithm/phase/bucket,
`[live]` or `[backfill]`, and the terminal event
(`completed`/`failed`/`interrupted`/`dry_run`) with its duration and, for a
completed real run, the same point/status counts as `memory_wall.csv`. A
`started` line with no matching terminal line is flagged
`NO COMPLETION RECORDED` — see Troubleshooting below.

---

## Analysis and graphs

```bash
.venv/bin/python analysis/phase2_uno_run_plots.py --board uno --circuit <circuit>
```

Generates the three per-circuit charts plus regenerates the cumulative
`all_algorithms_so_far.png`, reading only from `data/raw/` (never writes
there). Older, board-wide comparison tools
(`analysis/phase2_summarize.py`, `analysis/phase2_plot.py`,
`analysis/timing_report.py`) exist and are read-only in the same way, but
have not been re-run against the fresh REPS=100 dataset — their own output
paths (`data/processed/phase2/`, `data/figures/phase2/`) are currently
empty except for `.gitkeep`.

**Graph review, as practiced in this project (not automated — a human/LLM
step):**
1. Generate that algorithm's graphs.
2. Check each image visually — pass/fail per chart, spot-check at least two
   values against the underlying CSV by hand.
3. Write the analysis into `docs/analysis/<board>/<circuit>.md`, keeping
   every OBSERVED number separate from any INTERPRETATION, and citing every
   gate-count or timing-model claim by `file:line`.
4. Only then write the run report.

This workflow caught two real bugs early (a telemetry-status filter bug
that under-reported a retried point's true cost, and a legend that
overlapped a data point on a single-point chart) — see `run_log.md` for
both.

---

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `avrdude: stk500_getsync() ... not in sync` | Transient upload glitch, **or** two processes are fighting over the same port | Let the built-in retry (up to 3 attempts) run. If it keeps happening, check `ps`/`lsof <port>` for a second process (`pio device monitor` left open, a second sweep, a second `pc/run.py`) — this exact collision has happened in this project |
| Port name changed mid-run (`usbmodem101` → `usbmodem1101`) | Uno re-enumerates during upload | Expected; the sweep scripts' own `find_uno_port()`/`find_port()` re-detect it automatically — don't edit the command |
| Port name is different from your last session (any board) | Normal — port numbering isn't stable across reconnects/reboots, only the sweep scripts' own mid-run re-detection is automatic | Re-run `pio device list` (step a.4 above) and pass whatever it shows **this session** — never reuse a port string from an earlier session or from these docs |
| `Operation not permitted` opening the port (macOS) | No Full Disk Access for your terminal, TCC blocking access to the repo's own directory (this happened twice early in this project — see `docs/preflight_report.md` finding M6, now resolved by moving the repo out of `~/Documents`), or another program (e.g. `pio device monitor`) holds the port | Grant Full Disk Access to your terminal; close any open serial monitor before running a sweep; if it's the repo directory itself (not the port), confirm the repo isn't under `~/Documents`/`~/Desktop`/`~/Downloads` |
| `git: DIRTY (...)` warning in preflight | Uncommitted changes in the working tree | **Not a refusal** under the current owner-run rules (2026-09-21) — the run continues; the exact commit hash and dirty flag are still recorded automatically in that session's environment JSON and in `data/run_history.jsonl`, so the exact code state is always traceable after the fact even if you don't commit first |
| Board goes silent, no `DONE`, `runtime_hang_or_reset` (no RAM evidence) | Genuine hang, transient glitch, or (rarely) a real wall the compile-time check didn't catch | **Not** automatically a Memory Wall — flagged for manual review, per standing decision. Check `failure_message`/`reset_count` in `points.csv` |
| A long session appears to have stalled or the laptop slept | Sleep not prevented | `caffeinate -dims` in a separate terminal before starting; `pc/run.py`'s preflight prints the current `pmset -g assertions` status either way |
| `error: --reps ... given, but REPS is fixed at 100` | Trying to change repetition count from the CLI | Not possible — `REPS` is a `#define` baked into the firmware at compile time (`pc/shared/timing_model.REPS`) |
| A file literally named after a flag shows up untracked in the repo root, e.g. `--dry-run` (`git status` shows `?? --dry-run`) | Not caused by this project's code (`pc/run.py`'s `--dry-run` is a normal `argparse` flag, parsed correctly, that never opens a file by that name — confirmed by reading its argument-parsing code) — almost certainly a shell-side accident: a stray output redirection (e.g. an errant `>` before the flag) or a copy/paste artifact in the terminal | Safe to delete — the leading `--` in the filename would otherwise be parsed as an option by `rm` itself, so tell it to stop parsing options: `rm -- --dry-run` (the `--` means "everything after this is a filename, not a flag") |

### If something looks wrong, stop and ask

A resume summary that skips more or fewer points than expected, a failure
status you don't recognize, a preflight warning you don't understand, or
any command in this doc producing output that doesn't match what's
described above — **stop before running the next command and ask**, the
same way every session on this project has been handled. Guessing and
continuing risks hours of hardware time producing data that can't later be
told apart from good data (see `run_log.md`'s "Standing Operator Decisions"
for the full reasoning). This is cheap to do and expensive to skip.

---

## Git tags

| Tag | Marks |
|---|---|
| `pre-run-schema-v1` | Telemetry `SCHEMA_VERSION` frozen at 1; `points.csv` stopped collapsing every skip reason into one generic `skipped` value, before any real hardware data existed |
| `pre-run-schema-v2` | Hardening before first hardware contact: build-timeout no longer misclassified as a wall, watchdog-suspected distinguished from a genuine hang, walls require positive evidence only, toolchain versions pinned and recorded per session |
| `pre-run-uno-v1` | Opt-in `--la` (Logic Analyzer, `sigrok-cli`) capture added to the Uno Phase 2 sweep — UNVERIFIED, never run against real `sigrok-cli` |
| `pre-run-uno-v2` | Uno upload-retry (up to 3 attempts, 2 consecutive-`n` stop rule) and the compile-RAM-wall-after-successful-build fix, addressing the two standing operator decisions that govern every Uno run since |
| `pre-run-uno-v3` | Per-run diagnostic plotting tool added (`analysis/phase2_uno_run_plots.py`) — 4 charts per algorithm |
| `pre-run-uno-v4` | `data/raw/`/`data/figures/` migrated to one directory per (board, algorithm); all four sweep scripts restructured so each circuit is a fully independent run |
| `pre-run-uno-v5` | Raw-data path order corrected to phase-outermost (`data/raw/phase<N>/<board>/<circuit>/`), matching the project's pre-existing phase-first convention |

Every tag and the reasoning behind it is described in full in `run_log.md`,
which is the append-only source of truth these one-liners summarize.

---

## Current status

**Restart 2026-10-03: no hardware data is currently committed under
`data/raw/phase2/` or `data/raw/phase3/`.** Everything collected before this
date (Uno h_all/bell_ghz/qft/qpe/steane_encode, partial Uno grover, partial
ESP32 runs) was moved, not deleted, to
`data/archive/restart_20261003T111500Z/` with a `MANIFEST.json`. Resume sees
an empty state for every board / circuit / phase. Phase 1 (PC-only) was
re-validated for every `n` of the new plan
(`data/raw/phase1/infidelity_tvd.<timestamp>.csv`). See `docs/experiment_plan.md`
for the predicted walls and `python pc/run.py --plan` for the time table.

---

## Limitations and known issues

- **Grover fidelity (H3):** the PC-side simulator's own Phase 1 check finds
  Grover's infidelity crosses the project's own `1e-3` acceptance criterion
  between `n=8` (3.6e-4) and `n=9` (1.5e-3), reaching `6.5e-3` at `n=10` —
  the Oracle's multi-controlled-phase decomposition grows circuit depth as
  `O(3^n)`, and float32 error accumulates accordingly. Report-only by
  instruction; not fixed, not hidden. See `docs/preflight_report.md` finding
  H3.
- **`micros()` resolution:** 4µs/tick on the Uno (timer0, prescale 64 @
  16MHz), 1µs on the ESP boards. At low `n`, this is a non-negligible
  fraction of the measured pulse width — plausible explanation for
  low-`n` measurement variability, not independently confirmed (see next
  point).
- **No Logic Analyzer data exists yet.** `--la` (Uno only) is implemented
  and unit-tested against mocks, but has never captured against real
  hardware, nor even against `sigrok-cli`'s own demo driver (`sigrok-cli`
  was not installed in the environment that wrote this integration). Every
  quantization-noise explanation for low-`n` variability in
  `docs/analysis/uno/*.md` is therefore INTERPRETATION, not verified.
- **ESP8266 and ESP32 have no real hardware data.** Every timing/wall
  number for them is a `timing_model.py` prediction or a compile-only
  build-matrix figure (`docs/preflight_report.md`), never a measurement.
- **Phase 3 (offload) has no real hardware data on any board.**
- **Firmware uses `float` (binary32) throughout**; Qiskit Aer's reference
  computation uses `complex128`. Residual infidelity in Phase 1's own
  ~10⁻⁷ pass cases is consistent with this precision difference, not an
  algorithmic error — but it means this project's own pass/fail numbers
  are relative to a float32 baseline, not an architecture-independent one.
- **`REFLASH_COST_S` (compile+upload time estimate) is a model constant**,
  not a full per-board measurement — only the Uno has real reflash-time
  data on disk; ESP8266/ESP32 estimates are unverified against real
  uploads (uploads were never timed in the compile-only preflight matrix).

---

## Citation

_Placeholder — add citation details here (paper/thesis reference, DOI, or
preferred citation format) once available._

## Contact

_Placeholder — add the maintainer's preferred contact channel here._
