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
