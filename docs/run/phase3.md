# Running Phase 3 — Offload Benchmark (all boards)

> **Restart 2026-10-03:** scope is `h_all`, `bell_ghz`, `qft`, `grover` only
> (`qpe`/`steane_encode` removed from the plan; `pc/run.py` refuses them) and all
> earlier hardware data was deleted on 2026-10-04 (recoverable from git history, commit
> `af40643`); this file keeps no measured values from it, only estimates and method.
> Current plan and predictions: `docs/design/experiment_plan.md`.

**UNVERIFIED — Phase 3 has never been run against real hardware, on any
board, in this project.** Every number below is a `pc/shared/timing_model.py`
prediction. Unlike Phase 2, Phase 3's bottleneck is **PC-side Qiskit Aer
simulation time** (re-simulated from scratch on every single request, no
caching), not board speed — so these estimates don't share Phase 2's
uncertainty about board-specific `BOARD_GATE_COST` constants; they come
from a different, simulation-time model (`timing_model.pc_sim_time_s()`).
They are still unverified against a real board/PC/serial round trip.

One script serves all three boards: `pc/phase3_offload/sweep.py`
(`--board` selects). It is both the serial server (answers frames with
Qiskit Aer) and the orchestrator in the same process — it must hold the
serial port exclusively.

```bash
.venv/bin/python pc/run.py --board <uno|esp8266|esp32> --algorithm <circuit> \
    --phase 3 --port <PORT>
```

`--n-max` has **no fixed per-board default** for Phase 3 — if omitted, the
underlying script climbs `n` until a real error, capped only at
`N_SAFETY_CAP = 22` (`pc/phase3_offload/sweep.py`, chosen so the *PC's own
memory* for a `2^22`-amplitude Aer statevector, ~64MB, stays safe — not
tied to any board's memory at all, since the board never allocates a
statevector in Phase 3). `pc/run.py` reports this as `22` in its own
preflight summary for consistency, but you almost always want to pass an
explicit `--n-max` — see the ranges below, matched to
`docs/manual_run_guide.md`'s own established session split.

**`--fresh` changed 2026-09-21** — see `docs/run/uno.md`'s own note and
`README.md`'s "Fresh runs and the archive". The per-circuit minimum-`n`
defaults are the same ones used for Phase 2 (`h_all`/`qft`=1,
`bell_ghz`/`grover`=2) — Phase 3's own
per-request cost model doesn't change what n=1 *means* for a circuit, only
how expensive simulating it is.

| Circuit set | `n` range | Points (per board) | ESTIMATE: PC-side sim time only |
|---|---|---|---|
| Cheap (`h_all`, `bell_ghz`, `qft`), `--n-max 8` | Uno | 29 | 2.4 min |
| Cheap, `--n-max 13` | ESP8266 | 49 | 4.2 min |
| Cheap, `--n-max 14` | ESP32 | 53 | 4.5 min |
| `grover`, `--n-max 10` | any board | 9 | **1.5h — identical across all three boards**, because Phase 3's cost is PC-side simulation, not the board |

`grover` at `n≥12` is `skipped_sim_cost_infeasible` under the default
budget — PC-side Aer cost, not a board limit.

**Grover's cross-board identical estimate above is the whole point of
Phase 3**: since the PC does all the computing regardless of which board
asked, the *board's own speed becomes almost irrelevant to Phase 3's own
cost* — the number that does vary by board is round-trip *latency*, not
simulation time. No latency value is stated here: it is not yet collected in the
restarted dataset (`docs/design/system_design.md` discusses what the counter would add).

## Per-point cap: 2 h, and running to `--n-max` (2026-10-07)

Same rule as Phase 2 (`timing_model.POINT_TIME_CAP_S = 7200`), applied to the time the PC spends serving requests:

- Reps per point are planned from the model (`phase3_point_reps`): 100 if they fit in 2 h, otherwise as many as fit, and
  the board firmware is built with exactly that many (`-D REPS=k`). The point is recorded `ok` with
  `failure_message = time_capped reps=k/100 cap_s=7200` in `points.csv`.
- If even one request would pass 2 h (grover n>=14 on the model), the point is skipped
  (`skipped_sim_cost_infeasible`) and the run **continues with the next n**, up to `--n-max`.
- The firmware response timeout is no longer a fixed 5 s: `max(5 s, 3 x the model's request time)`
  (`phase3_response_timeout_ms`, built in as `-D RESPONSE_TIMEOUT_MS`). A fixed 5 s turned half of the grover n=9
  requests into timeouts (first run, 2026-10-07). The counter's max pulse width follows (timeout + 60 s).
- Limits: the planned reps come from the UNVERIFIED model (on the first run it was about 20 % above the measured time at
  grover n=8), so a capped point may take a little less than 2 h; the board's `micros()` wraps at 71.6 min, so one request
  must stay below that (model: grover n=13 about 51 min).
- Model plan for the ESP8266 grover by the 2 h cap alone: n<=10 100 reps, n=11 42, n=12 9, n=13 2, n=14-15 skipped; but see the
  PC memory wall below: n>=12 is skipped on an 8.6 GB PC. Check with `pc/run.py --plan` / `--dry-run`.
- A point already recorded in `session_log.csv` is skipped on resume even if it had a high error rate; use `--fresh` to redo.

Counter noise bursts (2026-10-07, ESP8266 grover n=10): a few minutes into the point the counter reported hundreds of
extra pulses (width ~0 or exactly 2^32 ticks = 53.687 s, anomaly codes 3/5/9, dropped frames) while the real 33-56 s
round trips were still measured correctly (the counter handles pulses longer than the 53.7 s timer wrap). Cause not found
(not verified: line noise vs capture-path artefact; counter firmware not reflashed, its USB port was not connected). Phase 3
joins now fall back to `crosscheck.align_by_width`: each board round trip is matched in order to the next counter pulse of
the same width (200 µs / 0.02 %), extra pulses (the cut-short pulse before the ESP8266 restart, noise) are ignored, and the
point is joined if at least 90 % of the reps match (`partial: aligned by width` in the notes when some reps found no pulse).
Phase 3 no longer splits the counter's pulses into runs by gap (a noise spike at the end of a 26 s pulse once split grover n=10
into 14 + 86 pulses). `ref_status` is `ok` when every rep matched. Real data (grover n=2-10, h_all n=2-15) all re-joined this way:
100/100 reps, micros() minus counter -2 us (h_all) to -1.1 ms (grover n=10, -0.004 %).

**Reaching `--n-max` past the cap (`--force-infeasible`)**: `pc/run.py ... --phase 3 --force-infeasible` also runs the points
the 2 h cap skips (one request already above 2 h: grover n>=14), with **1 rep** each, recorded `cap_exceeded reps=1/100` in
`points.csv`. Documented exception: no IQR, hours per point (model, ESTIMATE: n=14 about 2-3 h, n=15 about 10-12 h per request).
The offload firmware now keeps the round trip in 64 bits (`micros()` wraps every 71.6 min; before this fix any request longer
than that would have been reported modulo 71.6 min). The session timeout of a forced point is 2.5 x the model's request time.

Counter frame budget (firmware, 2026-10-07): per point the counter sends at most 4 ANOMALY frames per code and 4 glitch PULSE frames;
the anomaly mask / REPORT still carry everything and the debug line `supp=` counts what was not sent. This keeps a burst of line
spikes from flooding the link. Hardware advice if spikes recur: 1 nF from GPIO34 to GND at the counter, short twisted signal/GND wires.

**PC memory wall (2026-10-08, grover n=12)**: the PC rebuilds the whole gate list as a Qiskit circuit for every request. The
sweep process was SIGKILLed (returncode -9, the system's low-memory reaper) twice, both times as the first n=12 request started
(15.75 M gates). Measured: 161 bytes per gate for the circuit alone (grover n=10: 876,660 gates, +142 MB); Aer then copies it.
On this 8.6 GB Mac: n=11 (3.7 M gates, about 0.6 GB of circuit) ran, n=12 about 2.5 GB circuit and was killed, n=13 about 11 GB,
n=14 about 46 GB, **n=15 about 195 GB (1.2 billion gates)**. The plan now skips a point whose circuit would need more than 60 % of
the PC's RAM (`phase3_pc_memory_ok`, factor 4 over the measured 161 B/gate is an ESTIMATE) and says so (`SKIP — PC memory ...`),
so grover on this PC ends at n=11 whatever `--n-max` says; `--force-infeasible` bypasses the check and will be killed again.
Reaching n=15 for grover needs a different PC-side circuit (e.g. native multi-controlled gates instead of the gate-by-gate
list the MCU also executes), which changes what the offload cost measures: an owner decision, not made here.

## Wire protocol (for reference, not something `pc/run.py` changes)

```
Request  (MCU -> PC), 4 bytes:  [0xAA] [n_qubits] [circuit_type] [CRC8]
Response (PC -> MCU), 6 bytes:  [0x55] [outcome : uint32 big-endian] [CRC8]
```

CRC-8/SMBUS, polynomial `0x07`, init `0x00`
(`firmware/common/protocol.hpp` must stay byte-for-byte identical to
`pc/phase3_offload/protocol.py`). A bad CRC is deliberately left
unanswered so the MCU records a genuine timeout rather than a synthesized
one.

## Timing the round trip with the counter (`--ref counter`)

Since 2026-10-07 the offload firmware raises `GPIO_TIMING_PIN` (Uno D7, ESP8266 GPIO5, ESP32 GPIO4) for exactly
one request/response round trip, so the ESP32 counter measures the same interval as `e2e_latency_us`.
Wiring is the Phase 2 wiring (`docs/design/wiring.md`). UNVERIFIED on hardware.

```bash
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 3 \
    --port /dev/cu.usbserialXXXX --n-max 13 --ref counter --counter-port tcp:5055
```

Data goes to `with_ref/` (`ref/` holds the counter pulses and the micros-vs-counter comparison). The comparison
column is `e2e_latency_us`, not `exec_time_us`. A timed-out rep (5 s) still produces a pulse.

**Figures** are generated automatically when a Phase 3 run finishes (`pc/run.py` calls `analysis/phase3_run_plots.py`), into
`data/figures/phase3/<board>/<circuit>/<no_ref|with_ref>/`: `latency_vs_n`, `outcomes_vs_n`, `time_per_point`, and with
`--ref counter` also `micros_vs_counter`. By hand: `.venv/bin/python analysis/phase3_run_plots.py --board esp8266 --circuit h_all --ref`.
Run `sweep.py` directly and no figures are made; run the command above.

Counter pairing note (2026-10-07, first real run): the ESP8266 restarts when the sweep opens the serial port, so the
counter sees one cut-short pulse (~1.9 s) before the 100 real ones; `CounterSession` splits the runs with
`gap_factor=5` in Phase 3 (reps are ~20 ms apart) and pairs the last run.

## What to check afterwards

`data/raw/phase3/<board>/<circuit>/no_ref/` (or `with_ref/` when run with `--ref counter`, see below):
- `raw.csv`: 100 rows per `n` for an ok point, same as Phase 2.
- `session_log.csv` (Phase 3's terminal-record file — **not**
  `memory_wall.csv`, different schema, see `pc/shared/paths.py`'s
  `session_log_csv_path`): one row per `(circuit, n, baud)` point.
- `points.csv`/`sessions.csv`: same schema as Phase 2, shared across every
  phase/board (`SCHEMA_VERSION` stays 2).
- Latency-specific columns worth checking: `avg_round_trip_latency_s`,
  `crc_error_count`, `bytes_transferred` — none of these exist in Phase 2's
  rows.

## Known pitfalls (predicted, not yet observed)

- **`--bauds`** (not exposed through `pc/run.py`; use
  `pc/phase3_offload/sweep.py` directly if you need it) defaults to
  `[115200]` only — any higher rate (e.g. `250000`) is explicitly
  UNVERIFIED per `docs/manual_run_guide.md`, never tested against real
  hardware.
- The offload firmware buffers all results in RAM and prints its CSV only
  after every exchange finishes — any `Serial.print` mid-exchange would
  corrupt the byte stream the PC is parsing frames from (per firmware
  source; this is a design constraint of the current protocol, not
  something `pc/run.py` can detect or work around).
- Same single-port-at-a-time rule as Phase 2 — Phase 3 additionally *is*
  the serial server, so a second process opening the port doesn't just
  collide with an upload, it collides with every in-flight request.
- `N_SAFETY_CAP = 22` protects the PC's own RAM, not the board's — don't
  raise it without understanding that a `2^22`-amplitude `complex128`
  Aer statevector is already ~64MB, and grows by 2x per additional qubit.
