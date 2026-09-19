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
**Expected: ~13 min** (29 points; device time ~1.3 min, rest is build/upload overhead
— each point reflashes the board, that dominates at this end of the scale).

```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 13
```
**Expected: ~28 min** (49 points; device time ~7.8 min, rest is build/upload overhead).

```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 14
```
**Expected: ~23 min** (53 points; device time under a minute, entirely build/upload
overhead — ESP32 is so fast per-trial that reflashing dominates completely here).

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
**Expected: ~44 min** (6 points run, device time ~41 min; n=8 is skipped as
compute-infeasible — that's correct, not a bug, see the printed budget plan).

```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 14
```
**Expected: ~2 hours** (9 points run, device time ~1.9h; n=11+ skipped as
infeasible). The single most expensive point here is n=10 at ~1.7h — do not
interrupt the board mid-point unless you have to; if you do, the resume will
redo that whole point (up to another 1.7h), not top it up.

```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 13
```
**Expected: ~4.2 hours.** This is the longest single session in the whole
run (8 points run). n=9 alone is ~3.6h; n=10+ are skipped as infeasible
(n=10 would be 1.3 *days*). **Plan this one for overnight or a day you're not
touching the Uno/ESP32 setup** (different USB ports, shouldn't conflict, but
don't tempt fate).

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

**Cheap circuits, one command per board** (fast, PC-side cost is negligible):

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 8
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 13
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 14
```
**Expected: a few minutes each.**

**`grover`, one board per session, capped at n=10:**

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
    --circuits grover --n-start 2 --n-max 10
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
```
**Expected: ~1.1 hours each**, dominated entirely by n=10's uncached Aer
simulation (~40s × 100 reps). This cost is **the same on all three boards**
— it's PC-side, not board-side. n=12 is automatically skipped
(`skipped_sim_cost_infeasible`, ~20h/board — not attempted without your
explicit `--force-infeasible`, which is not recommended here).

**If it dies:** same story — rerun the identical command, resume picks up
per `(circuit, n, baud)`. Unlike Phase 2, a `session_incomplete` result here
is **not** auto-inferred as a wall for higher n (baud instability, not a
compute limit, can cause it) — so a resume will still *attempt* points after
one that failed. That's intentional; re-read the header of
`pc/phase3_offload/sweep.py` if you want the reasoning.

---

## Total budget

| Session | Expected |
|---|---|
| A (cheap × 3 boards) | ~64 min (13 + 28 + 23) |
| B (grover, Uno) | ~44 min |
| B (grover, ESP32) | ~2.0 h |
| B (grover, ESP8266) | ~4.2 h |
| C (cheap × 3 boards) | ~11 min |
| C (grover × 3 boards, n≤10) | ~3.3 h |
| **Total** | **~11.6 h**, dominated by Session B/ESP8266 and Session C/grover |

All sessions include a 25s/point build-upload-reflash assumption (not
separately measured anywhere in this repo — a placeholder pending a real
timed sample from this run). Phase 3 reflashes per data point
too (`N_QUBITS`/`CIRCUIT_ID`/`BAUD_RATE` are compile-time build flags on the
offload firmware, same as Phase 2), so Session C's real time will run a bit
above the PC-side-only numbers above — it just doesn't show up in the model
because `timing_model.py` only estimates PC simulation cost for Phase 3, not
build/upload. With ~14 cheap points × 3 boards and 3 grover points, expect
roughly another 10–15 min added to Session C from reflashing alone.

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
