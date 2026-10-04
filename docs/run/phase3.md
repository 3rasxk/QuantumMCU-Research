# Running Phase 3 — Offload Benchmark (all boards)

> **Restart 2026-10-03:** scope is `h_all`, `bell_ghz`, `qft`, `grover` only
> (`qpe`/`steane_encode` removed from the plan; `pc/run.py` refuses them) and all
> earlier hardware data was deleted on 2026-10-04 (recoverable from git history, commit
> `af40643`); this file keeps no measured values from it, only estimates and method.
> Current plan and predictions: `docs/experiment_plan.md`.

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
restarted dataset (`docs/system_design.md` discusses what the counter would add).

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

## What to check afterwards

`data/raw/phase3/<board>/<circuit>/no_la/` — always `no_la/`, Phase 3 has no
`--la` flag at all (`pc/phase3_offload/sweep.py`'s argparse has no such
option; see `pc/shared/paths.py`'s no_la/with_la split):
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
