# Wiring: target board -> ESP32 counter

Status: **design. Nothing is wired and nothing has run on hardware.** General electrical statements
(datasheet limits, pad capacitance, pull resistor presence, strapping pins) are marked **UNVERIFIED**:
they come from general knowledge, not from a datasheet read in this repo. Repo facts carry `file:line`.

## 1. Signals

Each target firmware raises `GPIO_TIMING_PIN` just before `run_circuit()` and lowers it right after, once per
rep (100 pulses per point). The counter measures that pulse. Only **signal + GND** cross between the boards.

| Target board | Pin the target drives | Source | Logic level | Counter input |
|---|---|---|---|---|
| Arduino Uno | D7 (`GPIO_TIMING_PIN 7`) | `firmware/uno/src/main.cpp:27` | **5 V** | GPIO34, through the divider |
| NodeMCU ESP8266 | GPIO5 = D1 (`GPIO_TIMING_PIN 5`) | `firmware/esp8266/src/main.cpp:27` | 3.3 V | GPIO34, direct (series resistor) |
| ESP32 DevKit | GPIO4 (`GPIO_TIMING_PIN 4`) | `firmware/esp32/src/main.cpp:28` | 3.3 V | GPIO34, direct (series resistor); the counter is a **second** ESP32 |

Never use the target's UART pins (Uno D0/D1, ESP8266 GPIO1/3, ESP32 GPIO1/3) for the timing signal.

## 2. Counter pins (ESP32 DevKit, `firmware/counter_esp32`)

| Function | Pin | Check (UNVERIFIED general knowledge) |
|---|---|---|
| Target pulse input `IN_DUT` | **GPIO34** | input-only pad (GPIO34-39 have no output driver): the counter cannot drive the target line by mistake. No internal pull-up/down, so an external pull-down is needed |
| Self-test input `IN_SELF` | GPIO35 | input-only pad |
| Self-test output `GEN_OUT` | GPIO25 | ordinary output (also DAC1, unused); the only pin the firmware drives besides the LED |
| LED | GPIO2 | strapping pin (boot mode): used only as an output after boot, nothing wired to it |
| Avoided | GPIO6-11 (flash bus), strapping 0, 2, 5, 12, 15 for signals | |

The self-test wire is **GPIO25 -> GPIO35, one jumper, permanent**. It never touches GPIO34, so the self-test cannot disturb
a connected target, and the self-test does **not** exercise the GPIO34 pad (that is bring-up step 2).

## 3. 3.3 V targets (ESP8266, ESP32): direct

```
target GPIO ----[330 ohm]----+---- counter GPIO34
                             |
                          [10 kohm]
                             |
target GND ------------------+---- counter GND (common)
```
- 330 ohm series: limits fault current if both pins were ever driven (inputs only here, so it is a safety margin).
- 10 kohm pull-down at the counter: keeps the line low while the target resets or uploads (its pin floats then) so no phantom
  pulses are counted.
- RC: 330 ohm x 20 pF (pad + wiring, UNVERIFIED) = 6.6 ns time constant. Negligible against microsecond pulses.

## 4. 5 V Uno: resistor divider (never connect 5 V to the counter)

ESP32 pads are **not 5 V tolerant** (absolute maximum about 3.6 V, UNVERIFIED). Use a divider; the Uno side is R1, the counter side R2:

```
Uno D7 ----[R1]----+----[330 ohm]---- counter GPIO34
                   |
                 [R2]
                   |
Uno GND -----------+---- counter GND (common)
```

Two E-series options, both computed here (Uno high level 5.0 V, 4.7-5.25 V range from USB, UNVERIFIED):

| | R1 / R2 | Vout at 5.0 V | Vout at 4.7 V | Vout at 5.25 V | Margin to 3.6 V | Divider current at 5 V |
|---|---|---|---|---|---|---|
| **Recommended** | 2.2 kohm / 3.9 kohm | 3.20 V | 3.00 V | 3.36 V | 0.24 V | 0.82 mA |
| Alternative | 10 kohm / 20 kohm (2 x 10k in series) | 3.33 V | 3.13 V | 3.50 V | 0.10 V | 0.17 mA |

ESP32 input-high threshold is 0.75 x VDD = 2.5 V (UNVERIFIED): both options are above it with margin. The recommended pair keeps
more headroom to the 3.6 V limit if the Uno supply is high. The Uno pin sources 0.82 mA, far below its per-pin limit (20 mA
recommended, UNVERIFIED).

**RC edge delay** (C = 20 pF total, UNVERIFIED; the 330 ohm series is included):

| | Source resistance seen by the pad | tau | 10-90 % rise | delay to 50 % rising | delay to 50 % falling | width error (rise delay - fall delay) |
|---|---|---|---|---|---|---|
| 2.2k / 3.9k | 1.41 k + 0.33 k = 1.74 k | 35 ns | 76 ns | 25 ns | 23 ns | about 2 ns |
| 10k / 20k | 6.67 k + 0.33 k = 7.0 k | 140 ns | 308 ns | 96 ns | 98 ns | about 2.5 ns |

The common delay cancels in a width; only the difference between the two edges matters, a few ns, against the shortest Uno pulse
in the plan (tens of microseconds, h_all n=1): below 0.01 %. A 4-microsecond `micros()` tick on the Uno is far larger than any
of this.

## 4b. Power and data over WiFi (owner choice 2026-10-04: one USB port only)

With one PC USB port the **Uno takes the USB port** and the counter sends its data over **WiFi** (TCP to this PC; firmware
`firmware/counter_esp32`, config `src/wifi_config.h`, run flag `--counter-port tcp:5055`). The counter then needs power only:

```
Uno 5V  -----------------> counter VIN (the 5V/VIN pin of the DevKit, NOT 3V3)
Uno GND -----+------------> counter GND      (this same wire is also the signal ground)
Uno D7 --[divider, section 4]--> counter GPIO34
```

- The Uno must be powered from the PC USB, so its 5V pin is live. The counter's own USB cable stays **unplugged** while VIN is fed
  from the Uno (feeding both may damage a board, UNVERIFIED). Flash the counter over its own USB cable first, alone, then unplug.
- Current: the Uno 5V pin on USB power supplies roughly 500 mA minus the Uno's own use (UNVERIFIED); an ESP32 with WiFi peaks at
  roughly 240-350 mA (UNVERIFIED). If the counter resets or drops WiFi, add a 100-470 uF capacitor VIN to GND at the counter or move
  to a separate USB power source. The Uno's 3.3 V pin (about 50 mA) cannot power the counter.
- Trade-off: the counter now loads the Uno's supply. Check in the pilot that `exec_time_us` does not change when the counter is attached.
- WiFi: the counter joins the same network as the PC and connects to the PC's IP, port 5055. The PC and the counter must be on one
  network that allows device-to-device traffic (some school networks do not; a phone hotspot or the PC's own hotspot does).
  The target board never enables WiFi.

## 5. Common ground, power, shielding

- **Common GND** between target and counter: mandatory; use a short dedicated wire.
- **Power:** each board from its own USB port (powered hub preferred). The counter's 3V3 and VIN are **never** connected to the target.
- Keep the signal wire short (< 20 cm) and away from the target's USB cable; a long wire adds capacitance and noise.
- If both boards share one hub, the grounds are already joined through the hub: still wire GND explicitly.

## 6. Pre-power checklist (before connecting USB to either board)

1. Divider built for the Uno: multimeter between the divider node and GND with the **Uno powered alone** reads 3.0-3.4 V with D7 high (run a blink sketch only if the owner allows; otherwise check resistor values with the meter, power off).
2. **No 5 V net touches any counter pin.** Trace every wire: counter GPIO34 sees only the divider node or the 3.3 V target pin.
3. GND wire present; no wire to the counter's 3V3 or VIN.
4. 10 kohm pull-down (or the divider's R2) present on GPIO34.
4b. If powering the counter from the Uno: Uno 5V goes to the counter's **VIN** only, the counter's USB cable is unplugged, nothing on 3V3.
5. The loopback jumper GPIO25 -> GPIO35 is in place and nothing else is on GPIO25/35.
6. Counter on its own USB port, target on a different one; both device files noted (never swap them).
7. The board you are about to flash is the **target** (target firmware) or the **counter** (counter firmware): never the other way round.

## 7. Bring-up order

1. **Counter standalone** (S1): one ESP32, self-loopback only (jumper GPIO25-GPIO35). No target, no GPIO34 wiring.
2. **Counter + known pulse source** (S2): any spare MCU or function generator (3.3 V) on GPIO34 through the real wiring; known widths.
3. **Counter + Uno pilot:** divider, h_all n=2..4 only, `--ref counter`; compare `micros()` with the counter by hand.
4. **ESP8266**, then **ESP32** targets (3.3 V direct).

Go/no-go page for step 3: `docs/design/readiness.md`.
