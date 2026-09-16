# QuantumMCU Research — Quantum Lab

Comparative Performance Benchmarking of Quantum Micro-Simulators Across Diverse
Microcontroller Architectures for Edge Computing

**Research question:** for a given circuit and qubit count, should a microcontroller
simulate the quantum circuit *locally*, or *offload* it to a PC running Qiskit Aer?

The answer is two numbers per board: the **Memory Wall** (largest `n` the board can run
at all) and the **Crossover Point** (the `n` above which offloading is faster than
computing locally). This repository contains the simulator, the firmware, the automated
sweep harness that measures both, and the analysis scripts that turn raw measurements
into summaries and figures. Written documents (report, proposal, poster, diagrams) are
being rewritten from scratch once the REPS=100 dataset exists.

Report text and source comments are in Thai; identifiers, protocol names, and CLI
commands are in English.

---

## Boards under test

| Class | Board | Word size | FPU | Clock | SRAM | Allocation policy |
|---|---|---|---|---|---|---|
| A | Arduino Uno R3 (ATmega328P) | 8-bit | no | 16 MHz | 2 KB | static array only |
| B | NodeMCU ESP8266 (ESP-12E) | 32-bit | no | 80 MHz | 80 KB | dynamic (`malloc`) |
| C | ESP32 DevKit V1 | 32-bit | **yes** | 240 MHz | 320 KB | dynamic (`malloc`) |

Three test circuits, built from three gates only (H, CNOT, Controlled-Phase):

- `h_all` — Hadamard on every qubit (uniform superposition, no entanglement)
- `bell_ghz` — Bell state at `n=2`, extended to a GHZ state by a CNOT chain for `n>2`
- `qft` — Quantum Fourier Transform without the trailing SWAP layer (`do_swaps=False`)

---

## Headline results

> **Dataset reset in progress.** The n=30 tables below are the *previous* run and no
> longer back any file in this working tree — see [`run_log.md`](run_log.md). A fresh
> REPS=100 rerun (Phase 2 and Phase 3) is planned but not yet executed; these numbers
> are kept here as the last-known result, recoverable from git history.

**Memory Wall** — largest `n` that runs reliably
(`data/processed/phase2/memory_wall_summary.csv`, once regenerated):

| Board | Theoretical max `n` | Measured max safe `n` | First failing `n` |
|---|---|---|---|
| Arduino Uno R3 | 8 | **7** | 8 |
| NodeMCU ESP8266 | 13 | **12** | 13 |
| ESP32 DevKit V1 | 15 | **13** | 14 |

Every board falls 1–2 qubits short of theory; the network/RTOS stack takes the
difference. ESP32, which carries both WiFi and Bluetooth stacks, loses the most.

**Crossover Point** — first `n` at which offload beats local
(`data/processed/phase3/crossover_summary.csv`, once regenerated):

| Circuit | Uno | ESP8266 | ESP32 |
|---|---|---|---|
| `qft` | 4 | 7 | 12 |
| `h_all` | 5 | 8 | 13 |
| `bell_ghz` | 6 | 10 | 13 |

Two findings drive the decision framework:

1. **Offload latency is essentially flat — roughly 1.6–14 ms across every board, every
   `n`, and every baud rate.** The protocol frames are a fixed 4 and 6 bytes, so almost
   all of the measured latency is fixed PC/OS/driver overhead. Raising the baud rate
   does not meaningfully reduce it for a payload this small.
2. **Crossover varies inversely with local compute speed and with circuit gate count.**
   A slow board (Uno) benefits from offloading at low `n`; the FPU-equipped ESP32 only
   benefits near its own Memory Wall. `qft` (O(n²) gates) always crosses over first.

---

## Repository layout

```
firmware/
  common/            portable core — identical on all 3 boards AND the PC
    qsim.hpp           state-vector simulator over a raw Cplx* buffer
    circuits.hpp       the 3 test circuits, built from H/CNOT/CPhase only
    protocol.hpp       Phase 3 serial frame + CRC-8 (mirrors protocol.py)
  uno/ esp8266/ esp32/
    src/               Phase 2 firmware — local benchmark
    src_offload/       Phase 3 firmware — offload benchmark
    platformio.ini     N_QUBITS / CIRCUIT_ID / BAUD_RATE injected via sysenv

pc/
  phase1_validate/   C++ runner: prints a state vector for Qiskit to check
  phase2_sweep/      per-board sweep: build, flash, read serial, repeat for n+1
  phase3_offload/    serial server (answers frames with Qiskit) + orchestrator
  shared/            circuit_ids.py — CIRCUIT_IDS/CIRCUIT_NAMES, single source
                      of truth imported by every sweep script
                     plot_style.py — board palette/markers/labels + figure
                      save helper, imported by every plotting script

analysis/            validation, statistics, and figure generation

data/
  raw/               per-repetition measurements straight off the board, per phase
  processed/         aggregated summaries (memory wall, crossover) derived from raw/
  figures/           generated figures (300 DPI PNG + SVG), per phase

docs/
  proposal/          (empty — to be rewritten from the REPS=100 data)
  report/            (empty — to be rewritten from the REPS=100 data)
  poster/            (empty — to be rewritten from the REPS=100 data)
  diagrams/          (empty — to be rewritten from the REPS=100 data)
```

The simulator core avoids `std::complex` and uses a plain `struct Cplx { float re, im; }`
because `avr-g++` does not ship a full `libstdc++`. Bit-ordering convention throughout is
**qubit 0 = LSB** of the state index, matching Qiskit's little-endian ordering.

`firmware/common/` compiles unchanged on all four targets. Only the allocation policy
differs per board, and it lives in each board's `main.cpp`, never in the core.

---

## Experiment phases

### Phase 1 — System Validation

Proves the hand-written C++ simulator agrees with Qiskit Aer before it is trusted to
measure anything. Same circuit, same gate order, gate by gate, on both sides.

```bash
pc/phase1_validate/build.sh
.venv/bin/python analysis/phase1_compare.py
.venv/bin/python analysis/phase1_plot.py
```

Pass criterion: Infidelity ≤ 10⁻³ for every circuit and every `n`. Measured infidelity
is ~10⁻⁷ across all 21 cases — the residual is the float32-vs-float64 difference, not an
algorithmic error. Toolchain versions are logged automatically to
`data/raw/phase1/phase1_metadata.csv`. Deterministic per (circuit, n) pair — rerun once,
no repetitions needed.

### Phase 2 — Edge Benchmark

Sweeps `n` upward one qubit at a time until the board fails, recording execution time
(REPS repetitions per data point, currently 100) and the exact failure mode.

```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py     --port /dev/cu.usbmodemXXXX
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX
.venv/bin/python pc/phase2_sweep/esp32_sweep.py   --port /dev/cu.usbserialXXXX
.venv/bin/python analysis/phase2_summarize.py
.venv/bin/python analysis/phase2_plot.py
```

Each data point is a fresh `pio run -t upload`, because `N_QUBITS` is a compile-time
constant — required on the Uno, where the state vector is a static array and cannot be
resized at runtime.

Failure modes differ by allocation policy, and both are recorded separately:

- **static (Uno)** — may fail at link time (caught before deployment) *or* hang silently
  at runtime when `.bss` collides with the stack. No warning in the second case.
- **dynamic (ESP8266/ESP32)** — `malloc` returns `NULL`, so OOM is detected cleanly.
  ESP32 additionally logs `heap_caps_get_largest_free_block`, which exposes the case
  where total free heap is sufficient but too fragmented to serve one large block.

### Phase 3 — Offload Benchmark

The MCU asks the PC to simulate the circuit and measures end-to-end latency. The PC
re-simulates from scratch on every request (no caching) so the measurement reflects the
true cost of offloading.

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --bauds 115200 460800
.venv/bin/python analysis/phase3_summarize.py
.venv/bin/python analysis/phase3_crossover_plot.py
```

Wire protocol (`firmware/common/protocol.hpp` ↔ `pc/phase3_offload/protocol.py`, which
must stay byte-for-byte identical):

```
Request  (MCU -> PC), 4 bytes:  [0xAA] [n_qubits] [circuit_type] [CRC8]
Response (PC -> MCU), 6 bytes:  [0x55] [outcome : uint32 big-endian] [CRC8]
```

CRC-8/SMBUS, polynomial `0x07`, init `0x00`. Frames are kept this small because the Uno's
serial RX buffer is only 64 bytes. A bad CRC is deliberately left unanswered so the MCU
records a real timeout rather than a synthesised one.

`sweep.py` is both the serial server and the orchestrator in one file, because both
halves must hold the same serial port. It demultiplexes a single byte stream: a leading
`0xAA` starts a binary frame, anything else is text accumulated until `\n` (the CSV
summary the firmware prints after all 30 exchanges finish).

### Phase 4 — Decision Framework

Synthesises Phases 2 and 3 into rules expressed in terms of board *characteristics*
rather than a lookup table for these three boards:

```
Memory Wall:  n_max = floor( log2( B / 8 ) )
    B = largest contiguous free block, measured (e.g. heap_caps_get_largest_free_block)
    if B cannot be measured:  B ≈ total SRAM / 2   (i.e. one qubit below raw theory)

Crossover:    n*(new board) ≈ n*(reference board, same class)
                            + log2(clock_new / clock_ref)
                            + architecture adjustment
    8-bit -> 32-bit, no FPU either side:  +1 qubit
    adding a hardware FPU to 32-bit:      +2 to +3 qubits
```

```bash
.venv/bin/python analysis/phase4_flowchart.py
```

Boards carrying a large network or RTOS stack should be derated by more than one qubit
when `B` cannot be measured directly. The adjustment constants come from only two board
pairs and are rough estimates, not physical laws. They were derived from the superseded
n=30 dataset and must be re-derived from the REPS=100 rerun before being cited.

---

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r analysis/requirements.txt
```

Requires [PlatformIO](https://platformio.org/) for the firmware. The sweep scripts
resolve `pio` via `shutil.which("pio")`, or the `PIO_PATH` environment variable if set
(e.g. `export PIO_PATH=/path/to/pio` when `pio` isn't on `PATH`).

Pinned versions (`analysis/requirements.txt`): `qiskit==2.5.1`, `qiskit-aer==0.17.2`,
`numpy==2.4.6`, `matplotlib==3.11.1`, `pandas==3.0.5`, `pyserial==3.5`.

Figures are labelled in English (the written report stays in Thai) and use matplotlib's
bundled DejaVu Sans, so no extra font is needed. Board colours, markers, labels and the
save helper (300 DPI PNG + SVG per figure) are defined once in `pc/shared/plot_style.py`;
every script under `analysis/` imports them instead of hardcoding colours.

---

## Notes on the measurement harness

Several defensive measures in the sweep scripts exist because of failures observed during
the actual runs, and are documented here so they are not mistaken for over-engineering:

- **Hard `signal.alarm` deadlines** wrap every serial read. pyserial's `readline()`
  timeout alone did not reliably return when the Uno's USB-CDC port dropped — one
  observed hang exceeded 16 minutes with `timeout=2` set.
- **The serial port is re-scanned before every operation.** The Uno re-enumerates during
  upload and changes path (`/dev/cu.usbmodem101` → `/dev/cu.usbmodem1101`); the
  previously used path is treated as a hint only.
- **A repeated CSV header on the serial line means the board reset mid-run** (watchdog,
  brown-out, or stack overflow). Captured rows are discarded and the reset is counted.
- **Failing at the first `n` of a baud rate is treated differently from failing at a high
  `n`.** The former indicates a cabling or baud problem and skips that baud rate
  entirely; the latter is a genuine computational limit and only ends that circuit.
- **The offload firmware buffers all 30 results in RAM** and prints its CSV only after
  the last frame is exchanged. Any `Serial.print` mid-exchange would corrupt the byte
  stream the PC is parsing frames from.
- **WiFi is disabled explicitly on both ESP boards** so the network stack does not compete
  for the heap being measured.
- **Every float literal in `firmware/common/` carries an `f` suffix.** Without it the
  value is promoted to `double`, which the ESP32 FPU cannot handle in hardware — the
  result is silent software emulation roughly 10× slower.

---

## Status

All four phases previously completed for all three boards at REPS=30; that dataset was
deleted and superseded in preparation for a fresh REPS=100 rerun (`data/` is currently
empty except for `.gitkeep` placeholders). See [`run_log.md`](run_log.md) for the run
history and git history for the last-known n=30 numbers. All prior documents under
`docs/` (report, proposal, poster, diagrams) were deleted as stale; they will be written
from scratch once the rerun completes.
