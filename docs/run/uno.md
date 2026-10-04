# Running the Arduino Uno R3 (Phase 2)

> **Restart 2026-10-03:** scope is `h_all`, `bell_ghz`, `qft`, `grover` only
> (`qpe`/`steane_encode` removed from the plan; `pc/run.py` refuses them) and all
> earlier hardware data was deleted on 2026-10-04 (recoverable from git history, commit
> `af40643`); this file keeps no measured values from it, only estimates and method.
> Current plan and predictions: `docs/design/experiment_plan.md`.

`GPIO_TIMING_PIN = D7` (`firmware/uno/src/main.cpp:27`), logic **5V** (the ESP32 counter needs the
2.2k/3.9k divider, `docs/design/wiring.md`), UART0 on D0/D1 (never connect the counter there).

**no_ref vs with_ref (renamed 2026-10-04):** every path below has an implicit `no_ref/`
or `with_ref/` bucket (`pc/shared/paths.py`) — `no_ref/` for `--ref none` (not valid for official runs),
`with_ref/` for `--ref counter --counter-port PORT` (official runs require it; UNVERIFIED on hardware). The two
buckets are never mixed in analysis. No data exists yet; see `docs/design/readiness.md`.

Official form of the command (copy-paste, replace the ports; add `--dry-run` first):
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --ref counter --counter-port /dev/cu.usbserial-110
```

```bash
.venv/bin/python pc/run.py --board uno --algorithm <circuit> --phase 2 \
    --port /dev/cu.usbmodem1101
```

`pc/run.py`'s own default `--n-max` for this board/phase is **14**
(`pc/phase2_sweep/uno_sweep.py`'s own argparse default, line 326). The wall is predicted at `n=8` for every circuit, so a run with the default
`--n-max` should climb past it harmlessly (the wall stops the circuit
before `n=14` is ever reached) — pass `--n-max 8` yourself if you want a
tighter, faster command for a circuit you already expect to wall at 8.

**`--fresh` changed 2026-09-21** (see `README.md`'s "Fresh runs and the
archive" and `run_log.md`'s 2026-09-21 entry): it now archives existing
data to `data/archive/` (moved, not deleted) instead of the delegated
script's own in-place rename, and defaults `--n-start` to each circuit's own
minimum *meaningful* `n` instead of a uniform 2:

| Algorithm | Fresh default `--n-start` |
|---|---|
| `h_all`, `qft` | 1 |
| `bell_ghz`, `grover` | 2 |

An explicit `--n-start` below that minimum is clamped up with a notice on a
`--fresh` run; non-fresh runs are unaffected (still default to 2 if
omitted, exactly as before). The Uno's own wall is structural
(`theoretical_bytes = 2^n * 8`, independent of circuit), so n=1 vs n=2 makes
no difference to whether or where the wall lands — this only changes how
low a fresh sweep starts, not the ceiling.

| Algorithm | `n` range planned | Points | ESTIMATE device time | ESTIMATE total (incl. compile/upload/hang) | Wall (prediction, UNVERIFIED) |
|---|---|---|---|---|---|
| `h_all` | 1–8 | 8 | 18.5s | 3.3min | build_overflow at n=8 (predicted) |
| `bell_ghz` | 2–8 | 7 | 13.4s | 3.1min | build_overflow at n=8 (predicted) |
| `qft` | 1–8 | 8 | 23.9s | 3.4min | build_overflow at n=8 (predicted) |
| `grover` | 2–8 | 7 | 41.5min | 44.3min | build_overflow at n=8 (predicted) |

All values are ESTIMATE from `pc/shared/timing_model.py` (`python pc/run.py --plan --board uno --phase 2`
prints the per-n table; rows turn MEASURED automatically once the new run has ok points).
The wall point costs compile + upload + the 90 s hang budget, because the board may never
print `DONE` when the static array overflows RAM. The wall is structural
(`theoretical_bytes = 2^n * 8` against 2048 B SRAM, `firmware/uno/src/main.cpp:30`) and
predicted at n=8 for every circuit; derivation in `docs/design/experiment_plan.md`.

## What to check afterwards

- `data/raw/phase2/uno/<circuit>/no_ref/raw.csv` (or `with_ref/` for a `--ref counter` run): exactly 100 rows per `n` with
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
