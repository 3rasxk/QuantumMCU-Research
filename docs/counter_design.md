# ESP32 pulse counter: design (replaces the Logic Analyzer)

Status: **design only. No firmware, no hardware touched, no code changed.**
Facts about the ESP32, ESP-IDF and Arduino-ESP32 are marked **UNVERIFIED**: they
come from general knowledge, not from this repo or a datasheet read in this
session. Facts about this repo carry `file:line`.

## 1. What is being replaced, and why it stays a reference

Every firmware raises `GPIO_TIMING_PIN` around `run_circuit()` once per rep
(`firmware/uno/src/main.cpp:27,86-90` pin 7; `firmware/esp8266/src/main.cpp:27,83-89`
pin 5 = D1; `firmware/esp32/src/main.cpp:28,81-85` pin 4). One rep = one pulse whose
width is the circuit time. The reference measures that width independently of the
board's own `micros()` and is joined to `raw.csv` by pulse order
(`analysis/la_crosscheck.py` header: sequence join, refuses unclean captures).
The counter keeps exactly that contract. Only the instrument changes.

## 2. Hardware

### 2.1 Pins on the counter ESP32 (DevKit)

| Function | Pin | Why |
|---|---|---|
| DUT pulse input (`IN_DUT`) | GPIO34 | input-only pad (UNVERIFIED: GPIO34-39 are input-only), so firmware **cannot** drive the DUT line, even by mistake |
| Self-test input (`IN_SELF`) | GPIO35 | second input-only pad |
| Self-test generator out | GPIO25 | permanent jumper GPIO25 -> GPIO35; never wired to GPIO34 |
| Status LED | GPIO2 | on-board LED |
| Ground | GND | common with the DUT (mandatory) |

The counter is powered from its own USB port. Its 3V3 is **not** connected to the
DUT. Only signal + GND cross.

### 2.2 Level matching

| DUT | Pin | Level | Wiring to GPIO34 |
|---|---|---|---|
| ESP8266 | GPIO5 (D1) | 3.3 V | direct, plus 330 ohm series resistor (fault-current limit) |
| ESP32 | GPIO4 | 3.3 V | direct, plus 330 ohm series resistor |
| Uno | D7 | **5 V** | resistor divider (below). The ESP32 pad is not 5 V tolerant (UNVERIFIED, abs. max about 3.6 V) |

Uno divider: **R1 = 2.2 kohm (D7 to node), R2 = 3.9 kohm (node to GND)**, node to
GPIO34 through the 330 ohm. Vout = 5 V x 3.9 / 6.1 = 3.20 V (3.0 V if the Uno supply
sags to 4.7 V); ESP32 VIH is 0.75 x VDD = 2.5 V (UNVERIFIED), so both are above it.
RC delay: Thevenin R = 2.2k || 3.9k = 1.41 kohm, +330 ohm = 1.74 kohm; pad + wire
C = 20 pF worst case (UNVERIFIED) -> tau = 35 ns. Time to the 50 % threshold:
rising 0.725 tau = 25 ns, falling 0.662 tau = 23 ns. The two edges differ by about 2 ns,
so the **width error is about 2-4 ns** (the common delay cancels); against the shortest
Uno pulse in the plan (h_all n=1-2, tens of microseconds) that is below 0.01 %.
A BSS138 bidirectional level-shifter module also works and is not needed.

### 2.3 Hardware list

| Item | Qty | Note |
|---|---|---|
| ESP32 DevKit (counter) | 1 | **2 when the ESP32 is the board under test** (DUT + counter) |
| USB cables | 2 | one per board, separate ports or a powered hub |
| Jumper wires, breadboard | few | GND, signal, loopback |
| 330 ohm resistors | 2 | series protection |
| 2.2 kohm and 3.9 kohm resistors | 1 each | Uno divider (or one BSS138 shifter) |
| Laptop with Wi-Fi | 1 | dashboard client, joins the counter's own AP |

## 3. Capture method

Compared for this job:

| Method | Resolution | Fits 130 s pulses? | Edge loss risk | Verdict |
|---|---|---|---|---|
| **MCPWM capture** (hardware timestamp on edge) | 12.5 ns (80 MHz APB, 32-bit; UNVERIFIED) | with coarse+fine unwrap, yes | none for timestamp, ISR only drains | **recommended** |
| RMT RX | configurable, but each item is a 15-bit duration (UNVERIFIED) | no: max about 100 ms per item at the slowest tick | idle/threshold tricks needed | no |
| PCNT | counts edges, no time | no | none | use as an **independent edge count**, not as the timer |
| GPIO interrupt + `esp_timer_get_time()` | 1 us timer, ISR latency jitter | yes (64-bit) | edges lost if ISR is late | **fallback** and coarse clock |

Recommended design: **MCPWM capture on two channels fed by the same pad** (UNVERIFIED
that one pad can feed two capture channels through the GPIO matrix): CAP0 = rising
edges only, CAP1 = falling edges only. Each channel holds one timestamp until the
next edge of the same polarity, so ISR latency only has to be shorter than one pulse
*period*, not one pulse *width*. The DUT period is at least the print time of one
row (`firmware/uno/src/main.cpp:84-` prints inside the rep loop), tens of microseconds
at best, which is why Wi-Fi activity must stay off the capture core (section 6).

Overflow for long pulses: the 32-bit timer at 80 MHz wraps every 53.7 s. A 130 s pulse
spans 2.4 wraps. In each capture ISR read `esp_timer_get_time()` as the **coarse**
clock. Then `width_ticks = ((fall32 - rise32) mod 2^32) + k x 2^32`, with
`k = round((coarse_width_ticks - fine_mod) / 2^32)`. The coarse clock only has to be
right to within about 26 s, which it is by orders of magnitude. Width is stored as
u64 nanoseconds. Same scheme works up to the 64-bit limit.

Independent count: PCNT counts rising edges in hardware (glitch filter off for narrow
pulses). `isr_count != pcnt_count` raises the **count mismatch / ISR overrun** anomaly.

No flash writes (SPIFFS/NVS) while armed: they stall the cache and can delay the ISR.
ISRs live in IRAM.

## 4. Anomaly detection

| Code | Anomaly | Rule |
|---|---|---|
| 1 | missing pulse | `pulses < reps` at END, or no rising edge for `max_width` after the previous pulse |
| 2 | extra pulse | `pulses > reps` |
| 3 | glitch | width below `min_width_ns` (set by PC, default 500 ns), or gap below `min_gap_ns` |
| 4 | still high at end | level is high when END is processed, or no falling edge within `max_width` |
| 5 | count mismatch | `isr_count != pcnt_count`, or rising count != falling count |
| 6 | sequence gap | PC saw a `seq` jump, requests REPLAY |
| 7 | never started | no first rising edge within a start timeout |
| 8 | counter clock fault | self-test or calibration out of tolerance |
| 9 | ring overflow | record ring full before the PC ACKed |

Nothing is silently dropped: anomalous pulses are still recorded with a flag, and the
PC decides. This mirrors `analysis/la_pulses.py`, which refuses to join an unclean
capture rather than guess an offset (`analysis/la_crosscheck.py` header).

## 5. PC link (serial) and who records

The **PC is the recorder.** The counter streams every pulse to the PC immediately,
keeps the unacknowledged ones in a RAM ring (4096 records), and re-sends on REPLAY.
The Wi-Fi dashboard is a view only and has no authority.

Framing reuses `firmware/common/protocol.hpp`: fixed start marker, fixed layouts,
multi-byte fields big-endian (as the `outcome` field, `protocol.hpp:8`), and
**CRC-8/SMBUS, poly 0x07, init 0x00** over every preceding byte (`crc8`,
`protocol.hpp:23-36`, mirrored by `pc/phase3_offload/protocol.py:13`). Frame:
`[marker][type][len][payload...][crc8]`. 115200 baud is enough (pulse rate is at most
thousands per second); 921600 if the dashboard-forwarding load grows (UNVERIFIED need).

| Dir | Marker/type | Payload |
|---|---|---|
| PC -> C | `0xC0 ARM` | session u32, board u8 (0 uno, 1 esp8266, 2 esp32), circuit u8 (`CIRCUIT_IDS`: 0-3), n u8, reps u16, min_width_ns u32, max_width_s u16 |
| PC -> C | `0xC1 END` | session u32 |
| PC -> C | `0xC2 ACK` | session u32, last_seq u16 |
| PC -> C | `0xC3 REPLAY` | session u32, from_seq u16 |
| PC -> C | `0xC4 REFVAL` | session u32, seq u16, micros_exec_us u32 (DUT `micros()` for dashboard diff, best effort) |
| PC -> C | `0xC5 SELFTEST` / `0xC6 STATUS` | pattern id / none |
| C -> PC | `0xD0 PULSE` | seq u16, rise_us u64, width_ns u64, flags u8 |
| C -> PC | `0xD1 ANOMALY` | seq u16, code u8, detail u32 |
| C -> PC | `0xD2 REPORT` | session u32, status u8, pulses u16, anomaly_mask u16, min/max/sum width_ns u64, pcnt_count u16, overruns u16 |
| C -> PC | `0xD3 HEARTBEAT` | uptime_s u32, state u8, ring_depth u16, dropped u16, ws_clients u8, free_heap u32, last_seq u16 |
| C -> PC | `0xD4 ARM_ACK`, `0xD5 SELFTEST_RESULT` | session + accept/refuse; pattern + measured vs expected |

Sequence per point (replacing `pc/shared/la_capture.py`'s arm-before-reflash order,
`la_capture.py` header): ARM -> ARM_ACK -> reflash + run DUT -> stream PULSE -> PC reads
the DUT's rows -> END -> REPORT. Pulses before the DUT really starts (reset glitches,
UNVERIFIED whether the uploader toggles D7) are recorded and flagged by rule 3/2, never
discarded.

Join: unchanged. Pulse i pairs with `raw.csv` rep i (sequence join); an unclean point
is refused, not guessed.

## 6. Wi-Fi dashboard (never on the capture path)

- Wi-Fi runs only on the **counter**: its own access point (no router needed). The
  DUT never enables Wi-Fi: `WiFi.mode(WIFI_OFF)` on ESP32 (`firmware/esp32/src/main.cpp:56`)
  and `WiFi.mode(WIFI_OFF); WiFi.forceSleepBegin()` on ESP8266
  (`firmware/esp8266/src/main.cpp:56-57`). The counter design adds no wire to the DUT
  other than signal + GND, and the firmware under test stays byte-identical.
- Core split: capture ISRs allocated from a task pinned to core 1; web server and
  WebSocket on core 0, lowest priority (UNVERIFIED that Wi-Fi tasks default to core 0).
- The capture path is lock-free: ISR -> single-producer/single-consumer ring -> serial
  task. It touches no Wi-Fi structure.
- Dashboard sends **latest-value snapshots at most 4 Hz**; intermediate states are
  coalesced, a slow client is dropped, never waited for.
- A dropped Wi-Fi connection loses nothing: data lives in the ring and on the PC. On
  reconnect the page requests a snapshot plus the last N pulses.
- WebSocket JSON (example): `{"t":..., "state":"armed", "board":"esp32", "circuit":"grover",
  "n":8, "pulse":37, "reps":100, "width_us":90743210, "median_us":..., "iqr_us":[..],
  "micros_diff_us":..., "anomalies":["glitch@12"], "eta_s":..., "heartbeat_age_s":...}`.
  Panels: progress, live widths, running median/IQR, `width - micros()` difference,
  anomalies, ETA, counter health.

## 7. Self-test, health, clock

- **Self-test:** the generator on GPIO25 (hardware timer/LEDC/RMT, UNVERIFIED which is
  best per width) drives known widths (2 us, 10 us, 100 us, 1 ms, 100 ms, 1 s, 60 s) and
  a fault set (missing pulse, glitch, stuck high) into `IN_SELF` through the permanent
  loopback. `IN_DUT` is untouched, so a self-test is safe with a DUT attached. Pass =
  measured within tolerance of expected and each injected fault raises its anomaly code.
- **Heartbeat:** 1 Hz frame; the PC marks counter data unreliable (not the DUT data) if
  it misses 3 in a row.
- **Clock tolerance:** a 40 MHz XTAL is typically +-10-20 ppm (UNVERIFIED), i.e. +-2.6 ms
  on a 130 s pulse, far below any micros() difference of interest. Self-test cannot
  detect a clock error (same oscillator), so **calibration** compares the counter's
  64-bit microsecond clock (carried in each heartbeat) against the PC's monotonic clock
  by regression over >= 10 minutes (resolves about 2 ppm at 1 ms jitter); result and
  ppm are written into the session metadata; fail above 50 ppm. Expect the **Uno's own
  `micros()`** to disagree with the counter by up to its resonator error (about 0.5 %,
  UNVERIFIED): that is the DUT's clock, and it is exactly what the cross-check
  exposes.

## 8. PC-side integration (what would change)

`with_la/` -> `with_ref/`, `--la` -> `--counter`. **Confirmed: no `with_la` data exists**
(`find` over the working tree finds no `with_la`; the restart MANIFEST has 0 hits), so
the rename is path-only.

| File | Change |
|---|---|
| `pc/shared/la_capture.py` | replace with `pc/shared/counter_client.py` (serial client, frames, ARM/END/ACK/REPLAY, calibration); drop sigrok-cli |
| `pc/shared/la_capture_test.py` | replace with `counter_client_test.py` using a simulated counter |
| `analysis/la_pulses.py` | delete (no capture-file parsing; anomalies come as records) or reduce to a record validator |
| `analysis/la_capture_plan.py`, `capture_plan.csv` | delete: no sample-rate plan (fixed 12.5 ns); only the expected reps (`REPS`) are needed |
| `analysis/la_crosscheck.py` | rename `ref_crosscheck.py`; keep the sequence join and micros() comparison, read counter records instead of files |
| `analysis/la_test.py` | replace with `ref_crosscheck_test.py` (also: this suite already fails one check at the pre-restart commit `8fa119f`, `crosscheck: clean point not flagged`) |
| `pc/shared/paths.py` | `_la_bucket`/`la` -> `with_ref`/`ref`; `la_dir` -> `ref_dir`; every caller's `la=` kwarg |
| `pc/shared/telemetry.py` | `la` field in the environment JSON and SESSION header (`SCHEMA_VERSION = 2`, `telemetry.py:62`) -> `ref`; **schema bump to 3** |
| `pc/shared/run_history.py`, `pc/run_history.py`, `pc/backfill_run_history.py` | `la` key in the `started` line -> `ref`/`counter` (ledger is append-only: old lines keep `la`) |
| `pc/phase2_sweep/uno_sweep.py` | `--la`, `la_active`, `lac.*` -> `--counter` |
| `pc/phase2_sweep/esp32_sweep.py`, `esp8266_sweep.py` | **add** `--counter` (today only the Uno has `--la`) |
| `pc/run.py` | `LA_SUPPORTED` -> counter-supported boards (all three, Phase 2), `--la` -> `--counter`, preflight line for the counter port, ETA table adds counter arm cost |
| `pc/run_test.py`, `pc/run_history_test.py`, `pc/shared/paths_test.py`, `pc/shared/uno_upload_retry_test.py`, `pc/shared/telemetry_test.py` | rename expectations |
| `analysis/phase2_uno_run_plots.py`, `analysis/phase2_exec_time_pub.py` | `with_la`/`no_la` buckets and subtitle text |
| `README.md`, `README.th.md`, `run_checklist.md`, `docs/manual_run_guide.md`, `docs/run/*.md`, `docs/preflight_report.md` | see section 10 |
| new | `firmware/counter/` (separate PlatformIO project, **not** under the DUT firmware), `pc/shared/counter_sim.py` (simulator), dashboard page |
| **not changed** | `firmware/uno|esp8266|esp32/**` (the pin toggle already exists; source hash stays), `firmware/common/**` |

## 9. Staged implementation (each stage testable without a target board)

| Stage | Deliverable | Test (no DUT) | Done when |
|---|---|---|---|
| S0 | frame codec + `counter_sim.py` (synthetic pulses, faults) in Python | unit tests, CRC against `protocol.py` | all anomaly codes reproducible in the simulator |
| S1 | counter firmware skeleton: serial frames, heartbeat, state machine | host talks to the real counter, no pulses yet | ARM/END/STATUS round trip, CRC rejects corrupt frames |
| S2 | GPIO-ISR capture + generator + loopback self-test | 2 us to 60 s widths via GPIO25 -> GPIO35 | width error table, 0 lost pulses over 1e6 |
| S3 | MCPWM two-channel capture + coarse/fine unwrap + PCNT count | same loopback, plus 130 s pulses | <= 100 ns error, wrap handled, counts agree |
| S4 | anomaly injection | generator injects missing/glitch/stuck/extra | each code raised exactly when injected |
| S5 | Wi-Fi AP + WebSocket dashboard, throttled | self-test running while 3 clients connect/drop | 0 count mismatch and 0 overruns with Wi-Fi under load |
| S6 | `counter_client.py` + `ref_crosscheck.py` + `--counter` against the simulator, then the real counter on loopback | run_test-style mocked suites | sweep dry flow joins synthetic `raw.csv` |
| S7 | calibration soak (>= 10 min) | PC vs counter clock | ppm recorded, < 50 |
| S8 | **first DUT contact (needs owner approval)**: Uno via divider, then ESP8266, ESP32 | one point, compare to `micros()` | pulse count = 100, diff within DUT clock error |

Collect the restarted dataset only after S8 passes, so every point has both `micros()`
and counter timing.

## 10. Docs that still name the Logic Analyzer as the timing reference

(file:line; all to be reworded when the counter lands; none changed now)

- `README.md:27-29` (what is measured), `:87` (analysis/ description), `:240` (`--la` flag), `:419-440` (data layout, `with_la/`), `:528`, `:622` (tag `pre-run-uno-v1`), `:661` (limitations)
- `README.th.md:112`, `:210`, `:305-307`
- `run_checklist.md:16`, `:48-55`, `:114-117`, `:583-740` (whole "Logic Analyzer procedure" section), `:914-941`
- `docs/manual_run_guide.md:39`, `:50-51`, `:69`, `:105`, `:120`, `:158-162`, `:182`, `:190`, `:245`, `:320`, `:374-430` (section "run with/without Logic Analyzer"), `:443`
- `docs/preflight_report.md:530`
- `docs/run/uno.md:11,15,18`, `docs/run/esp32.md:17`, `docs/run/esp8266.md:17`
- Code comments that say the same: `pc/shared/paths.py:1,20,23,61,63,104`, `pc/shared/telemetry.py:25,460,534-538`, `analysis/phase2_uno_run_plots.py:40,69-73,321,379`, and the firmware comments `firmware/uno/src/main.cpp:27,86`, `firmware/esp8266/src/main.cpp:27`, `firmware/esp32/src/main.cpp:28`. The firmware comments **stay**: editing them changes the firmware source hash.

## 11. Recommendation

Capture: **MCPWM two-channel hardware capture + coarse `esp_timer` unwrap + PCNT cross-count**, GPIO-ISR as fallback. Level: direct for the 3.3 V boards, **2.2k/3.9k divider** for the Uno. Record vs view: **PC records over serial with seq + CRC-8 + replay; Wi-Fi dashboard is a throttled, best-effort view.** Hardware: one extra ESP32 (two if the ESP32 is under test), two USB cables, a few resistors.
