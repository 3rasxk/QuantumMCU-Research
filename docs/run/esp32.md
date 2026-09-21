# Running the ESP32 DevKit V1 (Phase 2)

**UNVERIFIED — this board has never been run against real hardware in this
project.** Every number below is a prediction from `pc/shared/timing_model.py`
or a compile-only build figure from `docs/preflight_report.md`. Do not
assume the Uno's measured behavior transfers here — ESP32 is the only board
in this project with a hardware FPU, which changes the relative cost of H
vs CNOT vs CPhase in ways the Uno's own data cannot predict.

`GPIO_TIMING_PIN = GPIO4` (`firmware/esp32/src/main.cpp`), logic **3.3V**,
UART0 on GPIO1/GPIO3 (never connect a Logic Analyzer there). `--la` is
**not implemented** for this board — passing it is refused by `pc/run.py`.

```bash
.venv/bin/python pc/run.py --board esp32 --algorithm <circuit> --phase 2 \
    --port /dev/cu.usbserialXXXX
```

`pc/run.py`'s default `--n-max` for this board/phase is **18**
(`pc/phase2_sweep/esp32_sweep.py`'s own argparse default, line 211).

**`--fresh` changed 2026-09-21** — see `docs/run/uno.md`'s own note and
`README.md`'s "Fresh runs and the archive". The per-circuit minimum-`n`
defaults are board-independent, so they apply here identically.

## The same BOARD_GATE_COST caveat as ESP8266

`timing_model.BOARD_GATE_COST["esp32"]` traces to the same deleted,
REPS=30-era `docs/report/chapter4_results_th.md` reference as ESP8266's
(`pc/shared/timing_model.py:169-170`) — not verified against this project's
real hardware or pinned toolchain (`espressif32@7.0.1`,
`firmware/esp32/platformio.ini`). Every ESTIMATE below is doubly
unverified. See `docs/run/esp8266.md` for the full explanation and
`README.md`'s Limitations section.

**One ESP32-specific build note that predates this repo's Phase 2
re-collection** (`firmware/esp32/platformio.ini`'s own comment): every
float literal in `firmware/common/*.hpp` must carry an `f` suffix (e.g.
`0.5f`) or it promotes to `double`, which the ESP32 FPU cannot handle in
hardware — silent software emulation ~10x slower. Verified present as of
Phase 1 per the same comment; not re-verified in this repository's current
state as part of this documentation task (no source file changes were made
here).

| Algorithm | `n` range (`--n-start 2`, default `--n-max 18`) | Expected points | ESTIMATE total device time | Expected wall |
|---|---|---|---|---|
| `h_all` | 2–18 | 17 | 1.2 min | UNVERIFIED — old (REPS=30-era) measured-safe `n` was 13 (`timing_model.MEASURED_WALL_N["esp32"]`); compile-only build matrix shows RAM flat at 13.2–13.3% through n=14 (`docs/preflight_report.md` P2-8) — far below any threshold, no compile-time signal predicts a wall here at all. Expect a runtime `malloc` failure if one occurs, not a build-time one. |
| `bell_ghz` | 2–18 | 17 | 1.5 min | same caveat |
| `qft` | 2–18 | 17 | 6.7 min | same caveat |
| `qpe` | 2–18 | 17 | 7.9 min | same caveat |
| `steane_encode` | fixed at 7 | 1 | <0.1s | none expected |
| `grover` | 2–18 (`n≥11` auto-skipped) | 9 real + skipped | 1.9h — heaviest point predicted ~1.7h at `n=10` alone | `run_checklist.md`: **do not interrupt mid-`n=10`** if avoidable — resume re-runs that whole point from scratch, not from where it stopped |

## What to check afterwards

Same file layout as `docs/run/uno.md` —
`data/raw/phase2/esp32/<circuit>/{raw.csv,memory_wall.csv,points.csv,sessions.csv}`.
ESP32 has both a hardware watchdog (ESP-IDF task WDT, ~5s default per
`timing_model.WDT_PER_REP_THRESHOLD_S["esp32"]`) and dynamic allocation —
same `watchdog_suspected` vs `malloc_failed`/build-RAM-over-100%
distinction as ESP8266 applies here (see `docs/run/esp8266.md`).

## Known pitfalls (predicted, not yet observed)

- Same port-naming ambiguity as ESP8266 (`/dev/cu.usbserial*` /
  `/dev/cu.wchusbserial*` / `/dev/cu.SLAB_USBtoUART*`).
- `run_checklist.md`'s recommended `grover` session order places ESP32
  second (after Uno, before ESP8266) — derived for the old dataset, not
  re-verified against real ESP32 timing.
- WiFi is disabled explicitly in firmware so the network stack does not
  compete for the heap being measured (per the firmware source, not
  independently re-verified as part of this documentation task).
