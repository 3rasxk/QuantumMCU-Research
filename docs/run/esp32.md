# Running the ESP32 DevKit V1 (Phase 2)

> **Restart 2026-10-03:** scope is `h_all`, `bell_ghz`, `qft`, `grover` only
> (`qpe`/`steane_encode` removed from the plan; `pc/run.py` refuses them) and all
> earlier hardware data was deleted on 2026-10-04 (recoverable from git history, commit
> `af40643`); this file keeps no measured values from it, only estimates and method.
> Current plan and predictions: `docs/experiment_plan.md`.

**UNVERIFIED — no data has been collected for this board in the restarted dataset.** Every number below is a prediction from `pc/shared/timing_model.py`
or a compile-only build figure from `docs/preflight_report.md`. Do not
assume another board's behavior transfers here — ESP32 is the only board
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

`timing_model.BOARD_GATE_COST["esp32"]` is a prior fit (see the comment in
`pc/shared/timing_model.py`), not a measurement of the restarted dataset and not checked
against the pinned toolchain (`espressif32@7.0.1`, `firmware/esp32/platformio.ini`).
Every ESTIMATE below is to be refitted from the new data.

**One ESP32-specific build note that predates this repo's Phase 2
re-collection** (`firmware/esp32/platformio.ini`'s own comment): every
float literal in `firmware/common/*.hpp` must carry an `f` suffix (e.g.
`0.5f`) or it promotes to `double`, which the ESP32 FPU cannot handle in
hardware — silent software emulation ~10x slower. Verified present as of
Phase 1 per the same comment; not re-verified in this repository's current
state as part of this documentation task (no source file changes were made
here).

| Algorithm | `n` range planned | Points | ESTIMATE device time | ESTIMATE total | Wall prediction (UNVERIFIED) |
|---|---|---|---|---|---|
| `h_all` | 1–14 | 14 | 27.5s | 12.7min | malloc_failed at n=14 |
| `bell_ghz` | 2–14 | 13 | 26.0s | 11.9min | malloc_failed at n=14 |
| `qft` | 1–14 | 14 | 32.6s | 12.8min | malloc_failed at n=14 |
| `grover` | 2–14 | 13 | 49.5days | 49.5days | malloc_failed at n=14; **TIME-LIMITED from n=10** (device > 1 h per point); watchdog risk n=[9, 10, 11, 12, 13] |

All values ESTIMATE (`python pc/run.py --plan --board esp32 --phase 2` for the per-n table); derivation of the wall in `docs/experiment_plan.md`.

## What to check afterwards

Same file layout as `docs/run/uno.md` —
`data/raw/phase2/esp32/<circuit>/no_la/{raw.csv,memory_wall.csv,points.csv,sessions.csv}` — always `no_la/` (this board never supports `--la`, see pc/shared/paths.py's no_la/with_la split).
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
