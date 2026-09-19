# REPS=100 Run Checklist

Operator checklist for the actual hardware run. Read this, not `run_log.md`,
while running — `run_log.md` is where you write down what happened *after*.

**Resume is on by default in every script below.** If a session dies (USB
drop, laptop sleep, you need to stop for the night), the fix is almost always:
**run the exact same command again.** It will print a resume summary showing
what it's skipping, then continue from where it left off. Do not delete or
edit the CSVs by hand to "help" — the scripts read them to decide what's done.

If a resume summary looks wrong (skips something it shouldn't, or the
remaining-point count doesn't match what you expect), **stop and look at the
`*_memory_wall.csv` / `*_session_log.csv` file before re-running** — don't
force through it with `--fresh` on a hunch, that archives real data.

---

## 0. Before you start

- [ ] `pio` on PATH (`which pio`), or `PIO_PATH` env var set
- [ ] `.venv/bin/python` has `qiskit`, `qiskit_aer`, `pyserial`, `numpy` (Phase 3 needs
      the first two; all sweeps need pyserial)
- [ ] Note down each board's port now, ports can renumerate mid-run:
  - Uno: `/dev/cu.usbmodem*`
  - ESP8266 / ESP32: `/dev/cu.usbserial*`, `/dev/cu.wchusbserial*`, or `/dev/cu.SLAB_USBtoUART*`
- [ ] `data/raw/phase2/` and `data/raw/phase3/` — check what's already there before
      session A. If this is truly the first run, they should be empty or absent.

---

## Session order and why

1. **Cheap circuits, all 3 boards** — `h_all bell_ghz qft qpe steane_encode`.
   Fast (minutes), banks 5 of 6 circuits everywhere before touching the
   expensive one.
2. **`grover`, one board per session** — kept separate because ESP8266's
   grover alone is longer than everything else in step 1 combined across all
   3 boards.
3. **Phase 3, split by circuit** — same reasoning; the cheap circuits take
   seconds, `grover` at n=10 takes over an hour *per board* on the PC side
   alone, uncached, on purpose (see `pc/phase3_offload/sweep.py` header).

Do not run two sessions against the same board/file pair concurrently —
resume logic assumes one writer at a time.

---

## Run day checklist

One linear pass through everything below. The detailed sections further down
(Session A/B/C) have the actual commands and expected durations — this is
the order to hit them in, plus what to check between each one.

**Prerequisites (before touching any board):**
- [ ] `git status` clean, or at least nothing uncommitted you'd mind losing —
      `pc/shared/telemetry.py`'s environment metadata records the commit hash
      and dirty flag per session, so a dirty tree at data-collection time is
      captured either way, but a clean one is one less thing to explain later
- [ ] Host sleep prevention on: macOS, run the whole day's commands under
      `caffeinate -s -- <command>`, or start `caffeinate -s` in its own
      terminal and leave it running for the day. Confirm with
      `pmset -g assertions | grep PreventUserIdleSystemSleep` before
      starting Session B (session lengths there make a mid-run sleep
      expensive to redo) — this is the same check
      `tel.check_sleep_prevention()` makes automatically per session, but
      checking it yourself *before* a multi-hour session starts is cheaper
      than discovering it failed in the metadata JSON afterward
- [ ] Each board's port identified and written down (ports can renumerate
      when boards are re-plugged or after a reflash) — see § 0 above
- [ ] Decide LA-connected-or-not for this run. If connected: confirm wiring
      per the Logic Analyzer procedure below and do the "First real capture
      checklist" on one point before Session A starts. If not connected yet:
      proceed with Sessions A/B/C now, the LA cross-check is a fully
      separate, later pass over already-collected `*_raw.csv` files — it
      does not need to run concurrently with data collection
- [ ] `data/raw/phase2/` and `data/raw/phase3/` checked per § 0 — confirm
      resume state matches what you expect (empty for a true first run,
      or existing files if this is a continuation)

**Session order** (rationale in "Session order and why" above, and see
"Grover run order" below Session B for why boards run in this specific
sequence within step 2):
1. [ ] Session A — cheap circuits, all 3 boards (any order within this step)
2. [ ] Session B — `grover`, one board at a time, **in this order: Uno,
       then ESP32, then ESP8266** (cheapest full board first, most
       expensive last — see rationale below)
3. [ ] Session C — Phase 3, split by circuit, same board order logic applies

**After each session:**
- [ ] Check the printed resume/session summary — point count matches what
      that session's expected count says (Session A/B/C sections below give
      the exact numbers per command)
- [ ] Spot-check the terminal-record file (`*_memory_wall.csv` or
      `*_session_log.csv`) for the board just run — new rows present, no
      unexpected `build_or_upload_fail`/`malloc_failed` at an n lower than
      the known wall (would indicate a regression, not just "reached the
      wall as expected")
- [ ] If anything looks wrong, stop here and investigate before starting the
      next session — don't chain sessions blindly on a bad prior result

**Stop conditions (stop and investigate, don't push through):**
- A resume summary skips more or fewer points than you expect for that
  exact command
- A point fails with `build_or_upload_fail` at an n where a *previous*
  session already succeeded (regression, not a new wall)
- The host's sleep-prevention check reports `prevented: false` partway
  through a long Session B run (check the environment metadata JSON for
  that session — if sleep occurred, that session's timing is suspect and
  should be treated as unreliable, not just slow)
- Any point's `failure_type` is something other than the expected set for
  its circumstance (e.g. `crc` or `sim` appearing during Phase 2, which
  only Phase 3 should ever produce)
- You are not sure *why* something happened. Guessing and continuing risks
  hours of data that can't be told apart from good data later — stopping to
  check now is cheap by comparison

---

## Session A — cheap circuits, all boards

Run these three back to back (or in any order — independent files):

```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 8
```
**Expected: ~11 min** (29 points — device ~1.3 min + reflash ~9.7 min. Reflash
at 20s/point [UNMEASURED, see § Reflash cost below] is ~90% of this session).

```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 13
```
**Expected: ~32 min** (49 points — device ~7.8 min + reflash ~24.5 min at 30s/point).

```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 14
```
**Expected: ~27 min** (53 points — device <1 min + reflash ~26.5 min at 30s/point.
ESP32 is so fast per-trial that reflashing is essentially all of this session).

**If one dies:** rerun the identical command. Check the "resume summary" line
count at the top — it should show most points already done.

---

## Session B — `grover`, one board at a time

Run these as **three separate sessions**, not one after another in a single
sitting unless you have the time budgeted — ESP8266's alone is ~4 hours.

### Grover run order — why Uno, then ESP32, then ESP8266

`grover` is ~83% of the whole run's estimated time, so its internal ordering
matters more than any other circuit's. Two ordering questions, both already
answered by the commands below, spelled out here so the reasoning survives
if these numbers are ever re-measured and the order needs re-checking:

1. **Within one board's session, shortest points already run first** — the
   sweep loop walks `n` ascending (`n_values_for_sweep`), and `grover`'s
   per-point cost grows roughly ~7-10x per step in `n` (see the per-n
   durations in "Total budget" below). This means an interruption at *any*
   point in a board's grover session has already banked every cheaper point
   for that board — the only point ever at risk of being lost to an
   interruption is the single most expensive one in progress, never a
   cheap one waiting behind it. No change needed here; this falls out of
   the existing n-ascending sweep order for free.

2. **Across the three boards' sessions, run cheapest-total-board first:
   Uno (~43 min) → ESP32 (~2.0h) → ESP8266 (~4.2h).** This is the order the
   commands are already listed in below — the reasoning: if the run gets
   cut short after Session B starts (schedule, hardware issue, anything),
   this order guarantees the *maximum number of complete board datasets*
   for the *minimum elapsed time*. Two boards' full grover scaling curves
   (Uno + ESP32, ~2.7h combined) are a genuinely analyzable result on their
   own — a cross-board comparison missing only the slowest board — whereas
   spending that same 2.7h budget starting with ESP8266 would leave it
   *still incomplete* (2.7h in, ESP8266 alone needs 4.2h) and both other
   boards untouched: strictly worse under any stopping point.

**If cross-board comparison at *matched* n matters more than any board's
*complete* curve** (e.g. you want an early n=2..8 comparison across all
three boards specifically, and can live with Uno/ESP32 being "done" only up
to whatever n ESP8266 has reached so far): run single-n slices interleaved
across boards instead — `--n-start K --n-max K` for the same `K` on all
three boards before moving to `K+1`. This costs no extra reflashes (a
reflash already happens once per `(circuit, n)` regardless of how wide a
range `--n-max` spans in one invocation — see "Reflash cost" below), it's
purely a different sequencing of the same commands, and resume handles the
resulting partial per-board state exactly like any other interruption. This
alternative is **not** the default recommendation — most analysis on this
kind of scaling data benefits more from complete per-board curves than
from early matched-n snapshots — but it's the right call if the priority
for this specific run is early cross-board comparison over per-board
completeness. Not implemented as a script option; if chosen, run the
commands below with `--n-max` set to a single value at a time, in board
round-robin, by hand.

```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
    --circuits grover --n-start 2 --n-max 8
```
**Expected: ~43 min** (6 points run, 1 skipped — device ~41.3 min + reflash
~2 min. n=8 is skipped as compute-infeasible, that's correct, not a bug).

```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 14
```
**Expected: ~2.0 hours** (9 points run, 4 skipped — device ~1.9h + reflash
~4.5 min; reflash is negligible here, device time dominates). The single
most expensive point is n=10 at ~1.7h — do not interrupt the board mid-point
unless you have to; if you do, the resume will redo that whole point (up to
another 1.7h), not top it up.

```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 13
```
**Expected: ~4.2 hours** (8 points run, 4 skipped — device ~4.1h + reflash
~4 min, reflash negligible). This is the longest single session in the whole
run. n=9 alone is ~3.6h; n=10+ are skipped as infeasible (n=10 would be
1.3 *days*). **Plan this one for overnight or a day you're not touching the
Uno/ESP32 setup** (different USB ports, shouldn't conflict, but don't tempt
fate).

**If it dies partway through n=9 (the 3.6h point):** rerunning the same
command redoes that entire point from scratch — the resume logic discards
partial trials rather than mixing sessions (see `run_log.md`, 2026-09-19
entry, for why). There's no way around re-paying that cost; budget for it
when deciding when to start this session.

**If it dies on an earlier, cheap point:** resume picks up almost instantly,
no real cost.

---

## Session C — Phase 3 (offload), split by circuit

The offload server runs *on this machine* and needs the venv active
(`qiskit_aer`). Same board/port notes as above, plus `--bauds` (defaults to
just 115200 if omitted — pass explicitly if you want to test multiple).

**Phase 3 reflashes per data point too** — `pc/phase3_offload/sweep.py` calls
`build_and_upload()` once per `(circuit, n, baud)` before the 100-rep
exchange, same as Phase 2. This is **not** incidental: `N_QUBITS`/
`CIRCUIT_ID`/`BAUD_RATE` are `#define`d build flags in
`firmware/*/src_offload/main_offload.cpp`, baked into the request frame at
compile time — the offload protocol's request frame *does* carry
`n_qubits`/`circuit_type` per-request already (`firmware/common/protocol.hpp`),
and the PC side (`simulate_and_sample()`) already builds a fresh circuit from
whatever it receives, so the PC side could sweep many points over one
connection — but the current MCU firmware has no runtime mechanism (no serial
command, no config) to change what it sends; each flashed image asks the same
question 100 times. Fixing that would cut Phase 3's reflash count from
"per point" to "per board" but is a firmware/protocol change, out of scope
here — noted for later.

**Cheap circuits, one command per board:**

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 8
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 13
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 14
```
**Expected: ~12 min (Uno), ~29 min (ESP8266), ~31 min (ESP32)** — PC-side
simulation cost is a few minutes each; reflash (29/49/53 points × 20–30s) is
most of it, same pattern as Session A.

**`grover`, one board per session, capped at n=10:**

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
    --circuits grover --n-start 2 --n-max 10
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
```
**Expected: ~1.5 hours each on all three boards** — this is the **full
session (n=2 through n=10, 9 points, none skipped)**, not just the n=10
point. n=10 alone is ~1.1h of that (uncached Aer simulation, ~40s × 100
reps) and is the same cost on every board since it's PC-side, not
board-side; n=9 adds another ~15 min; reflash adds ~3–4.5 min on top. n=12
is automatically skipped (`skipped_sim_cost_infeasible`, ~20h/board — not
attempted without `--force-infeasible`, not recommended here).

**If it dies:** same story — rerun the identical command, resume picks up
per `(circuit, n, baud)`. Unlike Phase 2, a `session_incomplete` result here
is **not** auto-inferred as a wall for higher n (baud instability, not a
compute limit, can cause it) — so a resume will still *attempt* points after
one that failed. That's intentional; re-read the header of
`pc/phase3_offload/sweep.py` if you want the reasoning.

---

## Total budget

Generated by `pc/shared/timing_model.session_total_s()` — device time and
reflash time are tracked as **separate line items**, never summed before
being shown, so the reflash assumption's contribution stays visible and
auditable instead of disappearing into a single blended number.

| Session | Device | Reflash | Total |
|---|---|---|---|
| A: Uno cheap | 1.3 min | 9.7 min | 10.9 min |
| A: ESP8266 cheap | 7.8 min | 24.5 min | 32.3 min |
| A: ESP32 cheap | 41.9 s | 26.5 min | 27.2 min |
| B: Uno grover | 41.3 min | 2.0 min | 43.3 min |
| B: ESP8266 grover | 4.1 h | 4.0 min | 4.2 h |
| B: ESP32 grover | 1.9 h | 4.5 min | 2.0 h |
| C: Uno cheap | 2.4 min | 9.7 min | 12.1 min |
| C: ESP8266 cheap | 4.2 min | 24.5 min | 28.7 min |
| C: ESP32 cheap | 4.5 min | 26.5 min | 31.0 min |
| C: Uno grover (n≤10) | 1.5 h | 3.0 min | 1.5 h |
| C: ESP8266 grover (n≤10) | 1.5 h | 4.5 min | 1.5 h |
| C: ESP32 grover (n≤10) | 1.5 h | 4.5 min | 1.5 h |
| **Phase 2 total (A+B)** | | | **8.1 h** |
| **Phase 3 total (C)** | | | **5.8 h** |
| **GRAND TOTAL** | | | **13.9 h** |

### Reflash cost — currently an unmeasured placeholder

`REFLASH_COST_S = {"uno": 20, "esp8266": 30, "esp32": 30}` in
`pc/shared/timing_model.py` is a **reasoned estimate, not a measurement** —
compile time (full rebuild every point, since `N_QUBITS`/`CIRCUIT_ID` are
`#define`s) plus upload time, reasoned from typical avrdude/esptool/
PlatformIO behavior for a project this small. It has never been timed on
real hardware.

This matters more than it might look: for the cheap-circuit sessions
(A and C's non-grover rows), device time is often under a minute and
**reflash is 90%+ of the session** — meaning most of this checklist's
duration estimate rests on a number nobody has actually clocked. Before
trusting the 13.9h total, time one real build+upload cycle per board
(`time pio run -e <env> -t upload --upload-port <port>` with the usual
`N_QUBITS`/`CIRCUIT_ID` env vars set) and update `REFLASH_COST_S` with the
real number. This was not done as part of producing this checklist — it
requires touching hardware, which this session was not authorized to do.

---

## Logic Analyzer procedure (for when the loaned LA arrives)

Analysis tooling for this already exists and is tested against synthetic
captures (`analysis/la_pulses.py`, `analysis/la_crosscheck.py` — see
`run_log.md`). Nothing below has been run against a real capture yet — verify
against one real file before trusting the tool on a full session.

**Wiring:**
- [ ] LA channel probe → the board's `GPIO_TIMING_PIN`: **Uno pin 7**,
      **ESP8266 pin 5 (D1 on NodeMCU)**, **ESP32 pin 4** (each board's own
      `firmware/<board>/src/main.cpp` — different pin per board, confirm
      against that file if it's ever changed)
- [ ] LA ground → common GND with the board (share ground with the USB/serial
      connection already in use, don't add a second ground path)
- [ ] **Check LA input voltage tolerance before connecting anything.** Uno's
      GPIO is 5V logic; ESP8266/ESP32 are 3.3V logic. If your LA is a 3.3V-only
      input (many cheap 8-channel 24MHz clones are, or have a fixed threshold
      that doesn't tolerate 5V), connecting it directly to the Uno's pin 7 can
      damage the LA input. Confirm the datasheet/spec explicitly before the
      first Uno capture — if in doubt, use a level shifter or a resistor
      divider, don't assume a "5V tolerant" claim without checking the source.

**Trigger:** rising edge on the timing pin, one-shot per capture (not
repeating/streaming trigger) — the pin only toggles predictably within a
single sweep-script invocation's 100-rep loop.

**Capture: one file per data point**, saved as:
```
data/raw/la/<board>_<circuit>_n<N>.csv
```
e.g. `data/raw/la/uno_h_all_n2.csv`, `data/raw/la/esp32_grover_n10.csv` — this
naming convention is load-bearing: `la_crosscheck.py` parses board/circuit/n
directly from the filename, no other metadata is read.

**Export format:** two are supported (auto-detected by `la_pulses.py`, see its
module docstring for the exact byte-level format of each):
- **FORMAT A** — `sigrok-cli -O csv` default (raw, one sample per line at full
  rate).
- **FORMAT B** — PulseView's "changes only" CSV export (one row per edge, not
  per sample). Smaller for anything but the shortest points.

### Generate the capture plan first — don't use 24MHz/100-reps for every point

The cross-check validates `micros()`, which is only ever accurate to ~1µs —
capturing a multi-minute pulse at 24MHz to get nanosecond resolution buys
nothing. `analysis/la_capture_plan.py` picks the **lowest sample rate** that
still resolves each point's pulse to within 0.1% (or hits a minimum
sample-per-pulse floor, whichever binds), and drops to a handful of reps for
pulses long enough that 100 full-length captures would be wasteful:

```bash
.venv/bin/python analysis/la_capture_plan.py
```

This prints a table and writes `data/raw/la/capture_plan.csv` — `n_reps_to_capture`
and `recommended_sample_rate_hz` for every point, one row per `(board, circuit, n)`.
`la_crosscheck.py` reads this file automatically (via `--plan`, defaulted to
this path) to know how many reps to expect per point, so generate it before
running any real capture, then re-check with `analysis/timing_report.py`
once real device timings replace the estimates it's currently built from.

**Summary from the current plan** (154 points across all three boards, all six
circuits; regenerate after the REPS=100 run to refresh the pulse-width inputs):

| Sample rate | Points |
|---|---|
| 24 MHz | 29 |
| 12 MHz | 8 |
| 6 MHz | 24 |
| 1 MHz | 38 |
| 100 kHz | 33 |
| 10 kHz | 22 |

- **8 points** get reduced reps (5 instead of 100) — all `grover` at high n,
  where a single pulse already runs seconds to minutes.
  For those: **capture only the first 5 reps**, stop the LA before rep 6
  starts (watch the firmware's own device-side clock, not a fixed wall-clock
  guess — see the reduced-capture procedure below).
- **24 points** are flagged `resolution_insufficient` — pulses only a few
  microseconds wide (mostly `qft`/`qpe`/`grover` at their smallest n on ESP32)
  where even 24MHz can't hit 0.1% relative resolution. This is expected and
  not a blocker: 24MHz still gives ~42ns absolute resolution, far finer than
  `micros()`'s own 1µs granularity — the 0.1%-relative target just doesn't
  apply meaningfully to sub-10µs pulses. Use FORMAT A there regardless of
  the "prefer FORMAT B" default below, since duration is trivial anyway.
- **Total capture size across all 154 points: ~0.10 GB in FORMAT A, ~0.6 MB
  in FORMAT B.** This replaces the previous estimate (up to 627 GB for a
  single ESP8266 `grover` n=9 point at a flat 24MHz/100-reps) — the fix was
  rate and rep selection, not a sub-sampling scheme layered on top.
- **0 points exceed the size limit** (default 50MB/point) at the plan's
  chosen rate/reps. If you tighten `--max-size-bytes` or add circuits with
  longer pulses later, re-run the plan and check the `exceeds_size_limit`
  column before assuming this still holds.

**Reduced-rep procedure (the 8 flagged points):**
1. Look up `n_reps_to_capture` and `recommended_sample_rate_hz` for that point
   in `capture_plan.csv`.
2. Start the LA capture, then start the sweep for just that `(circuit, n)`.
3. Stop the capture after exactly `n_reps_to_capture` pulses (watch the LA's
   live trace, don't wait for the firmware's `DONE` — that only fires after
   all 100 reps). The captured file will have fewer pulses than the full
   session; that's expected and required, not an error.
4. Run `la_crosscheck.py` normally — it reads `n_reps_to_capture` from the
   plan and joins against the **first** N reps of that point's `*_raw.csv`
   (see the "join reduced captures" comment in `la_crosscheck.py` for why
   that's a safe assumption here specifically, not a general one).
5. If the pulse count you actually captured doesn't match the plan's
   `n_reps_to_capture` exactly (missed the cutoff, or a glitch), the tool
   still refuses to join rather than guessing — recapture that point, don't
   force it with `--expected-reps` set to whatever you happened to get.

### sigrok-cli command lines — UNVERIFIED

`sigrok-cli` is not installed in the environment these scripts were written
in, so **none of the following has been run, not even against sigrok's
hardware-free `demo` driver.** Confirm the flag names against
`sigrok-cli --help` and `sigrok-cli -O csv:help` once it's installed, before
trusting these on a real point.

Full-rate, full-reps point (e.g. `uno_h_all_n2`, 24MHz, FORMAT A one-shot):
```bash
# UNVERIFIED
sigrok-cli -d <driver-name> --config samplerate=24m --triggers D0=r \
    --samples 10000000 -O csv -o data/raw/la/uno_h_all_n2.csv
```
Low-rate point from the plan (e.g. 100kHz, still full 100 reps):
```bash
# UNVERIFIED
sigrok-cli -d <driver-name> --config samplerate=100k --triggers D0=r \
    --time 2s -O csv -o data/raw/la/esp8266_qft_n12.csv
```
Reduced-rep point (e.g. `esp8266_grover_n9`: 10kHz, 5 reps — stop manually,
don't rely on `--samples`/`--time` matching exactly, see procedure above):
```bash
# UNVERIFIED
sigrok-cli -d <driver-name> --config samplerate=10k --triggers D0=r \
    --continuous -O csv -o data/raw/la/esp8266_grover_n9.csv
# Ctrl-C after ~5 pulses are visible in a live view / on-device counter
```
FORMAT B ("changes only") export — **the actual sigrok-cli flag for this is
unconfirmed.** PulseView's GUI has a "Compression" option on CSV export;
sigrok-cli's CSV output module may or may not expose the same thing under a
different name (possibly `-O csv:compress=on`, unverified). If sigrok-cli
can't produce FORMAT B directly, capture with FORMAT A and use PulseView's
GUI export instead for anything long enough to matter — the plan's FORMAT A
sizes above are small enough (~0.10 GB total) that this may not even be
necessary in practice.

**`--driver <driver-name>`** is also a placeholder — it depends on which LA
model actually gets loaned. Run `sigrok-cli --scan` once it's connected to
find the right driver string; don't guess from the device's marketing name.

## First real capture checklist

Do this before touching any other point, on whichever board is easiest to
access first (Uno is simplest — 5V logic, no WiFi to interfere, `h_all` n=2 is
a ~284µs pulse well within a trivial FORMAT A capture):

- [ ] Wire per the section above, double-check voltage tolerance for the
      specific board
- [ ] Capture `data/raw/la/uno_h_all_n2.csv` (full 100 reps, no reduction needed)
- [ ] `.venv/bin/python analysis/la_pulses.py data/raw/la/uno_h_all_n2.csv`
- [ ] Confirm: `format:` line shows the format you actually exported (if it
      says `raw` but you exported FORMAT B, or vice versa, the tool guessed
      wrong — **stop, don't proceed to other points until this is understood**;
      auto-detection was written against the *documented* format, not a
      verified real export, exactly the caveat carried over from the last
      session)
- [ ] Confirm: `pulses (clean): 100 / expected 100` and `is_clean: True`
- [ ] Confirm: reported `width_us` values are in the right ballpark (tens to
      hundreds of µs for `h_all` n=2, not micro- or milli-orders of magnitude
      off — a wrong sample rate parsed from the header would show up here as
      an obviously wrong width, same failure mode tested synthetically in
      `analysis/la_test.py`)
- [ ] Only once all of the above look right, run
      `.venv/bin/python analysis/la_crosscheck.py` and confirm the one row it
      produces has a small `median_relative_diff` and `flagged=False`
- [ ] If **anything** here doesn't match — wrong pulse count, implausible
      widths, a parse error, an unexpected format — **do not adjust
      `la_pulses.py`'s format detection to force it through.** Get the real
      export file into the analysis session that has hardware access, fix
      the parser against the actual bytes, and only then continue to the
      other 153 points. A parser that silently misparses a format it wasn't
      actually tested against is worse than one that fails loudly.

Once the first point checks out, proceed through the rest of the plan in
`capture_plan.csv` — normal points first (100 reps at the recommended rate),
the 8 reduced-rep `grover` points last since they need the manual stop-early
procedure above.

## After everything

```bash
.venv/bin/python analysis/phase2_summarize.py
.venv/bin/python analysis/phase3_summarize.py
```
Both now **refuse to run** (exit 1, clear error naming the group) if any
`(board, circuit, n[, baud])` group has more than 100 rows — that means two
sessions wrote to the same file, or `--fresh` was used against the wrong
path. Fix the raw CSV before re-running, don't argue with the error.

Then add a row to `run_log.md` for this run, same as every prior run.
