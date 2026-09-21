# Running the Arduino Uno R3 (Phase 2)

The only board with real hardware data in this project. `GPIO_TIMING_PIN =
D7` (`firmware/uno/src/main.cpp:27`), logic 5V, UART0 on D0/D1 (never
connect a Logic Analyzer there).

```bash
.venv/bin/python pc/run.py --board uno --algorithm <circuit> --phase 2 \
    --port /dev/cu.usbmodem1101
```

`pc/run.py`'s own default `--n-max` for this board/phase is **14**
(`pc/phase2_sweep/uno_sweep.py`'s own argparse default, line 326). Every
circuit's real wall so far has landed at `n=8`, so a run with the default
`--n-max` climbs past the wall harmlessly (the wall stops the circuit
before `n=14` is ever reached) — pass `--n-max 8` yourself if you want a
tighter, faster command for a circuit you already expect to wall at 8.

| Algorithm | `n` range (`--n-start 2`, default `--n-max`) | Expected points | ESTIMATE (device time only, `timing_model.py`, naive) | MEASURED device time: n=2..7 ok points / the n=8 wall attempt itself | Wall |
|---|---|---|---|---|---|
| `h_all` | 2–8 (wall), 9–14 never reached | 7 real + up to 6 skipped-by-wall | 20.8 min | **15.98s / 90.74s** (`data/raw/phase2/uno/h_all/points.csv`) | `build_overflow` at n=8, **109.9%** compile RAM |
| `bell_ghz` | 2–8 (wall) | 7 real | 4.8 min | **13.03s / 100.02s** | `build_overflow` at n=8, **110.1%** compile RAM |
| `qft` | 2–8 (wall) | 7 real | 1.3h | **21.84s / 91.94s** | `build_overflow` at n=8, **109.8%** compile RAM |
| `qpe` | 2–8 (wall) | 7 real | 1.6h | **27.51s / 100.01s** | `build_overflow` at n=8, **109.8%** compile RAM |
| `steane_encode` | fixed at 7 (ignores `--n-start`/`--n-max` except range membership) | 1 | 1.7s | **3.56s total** (2 upload attempts — 1 retry occurred; `data/raw/phase2/uno/steane_encode/points.csv`) | none — never reaches the RAM threshold |
| `grover` | 2–8 (`n=8` auto-skipped, `expected 5.1h > 4h ceiling`) | 6 real + 1 skipped (`skipped_compute_infeasible`) | 41.3 min | collected once, **not currently committed** — see `README.md`'s status table | not observed under the default 4h budget ceiling; would need `--force-infeasible` |

The "n=8 wall attempt" column is almost entirely the 90–100s serial-read
timeout wait (the board never prints `DONE`), not real computation — it's
the single biggest chunk of wall-clock time in every one of these runs
except `grover`'s (whose own infeasibility check keeps it away from `n=8`
under the default budget). A full run's real elapsed time is dominated by
reflash overhead (compile+upload per point, a few seconds each) plus this
one ~90–100s wait at the end, not by the tiny device execution times
themselves.

"ESTIMATE (naive)" above is `timing_model.expected_point_time_s()` summed
across every `n` in range **as if every point ran to completion** — it does
not know about the wall in advance, so it overstates real elapsed time for
every circuit except `grover` (whose own infeasibility check already
excludes `n≥8`) and `steane_encode` (one point only). In practice a real
run stops at the wall, so actual elapsed time is close to the MEASURED
column plus one reflash-and-timeout cycle at the wall itself
(compile+upload+90s timeout, ≈2 minutes).

**All four non-fixed, non-`grover` circuits wall at exactly `n=8` with RAM
evidence in a tight 109.8–110.1% band** — confirms the wall is a
state-vector memory limit (`theoretical_bytes = 2^n * 8`), independent of
which circuit is running. See `docs/analysis/uno/comparison.md`.

## What to check afterwards

- `data/raw/phase2/uno/<circuit>/raw.csv`: exactly 100 rows per `n` with
  `status=ok` in `memory_wall.csv`.
- `memory_wall.csv`: one terminal row per `n` attempted. `status=ok` is
  good; `status=build_overflow` with `compile_ram_pct` > 100% is a real,
  positive-evidence wall; anything else (`runtime_hang_or_reset`,
  `build_or_upload_fail`) needs manual review — it is **not** automatically
  a wall.
- `points.csv`: one row per upload attempt. `retry_count=0` on the terminal
  row means it succeeded first try; `retry_count>0` means the built-in
  upload retry fired (up to 3 attempts) — check `failure_message` for the
  avrdude signature that triggered it.
- `sessions.csv` / `env/<session_id>.json`: toolchain versions and
  `firmware_source_hash` — confirm these match the tag/commit you expect
  before trusting a comparison against older data.

## Known pitfalls

- **Never run two sweeps against this port at once.** `pc/run.py` checks
  for this via `lsof` before starting; the underlying `uno_sweep.py` does
  not. This exact collision (two processes both calling `--fresh` and both
  trying to upload) corrupted a real run in this project — see `run_log.md`,
  the grover cycle entry.
- `--fresh` archives (never deletes) the circuit's existing `raw.csv` /
  `memory_wall.csv` as `*.pre-fresh-<timestamp>.csv` and starts over from
  `n-start`. Only use it when you genuinely want to discard the current
  run's points, not "just in case."
- The Uno's port re-enumerates during upload (e.g.
  `/dev/cu.usbmodem101` → `/dev/cu.usbmodem1101`) — `uno_sweep.py`'s own
  `find_uno_port()` re-detects it automatically every time; you never need
  to update `--port` mid-run.
- `avr-ld` links successfully even when compile-time RAM exceeds 100%
  (`docs/preflight_report.md` finding L2) — this is exactly why the wall
  check reads `compile_ram_pct` from the build output, not the linker's own
  exit code.
