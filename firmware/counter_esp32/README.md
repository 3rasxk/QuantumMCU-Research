# firmware/counter_esp32: pulse counter (protocol v2) — NOT YET FLASHED

**Flash status: never flashed.** Owner decision 2026-10-04 re-authorised S1 (ONE counter ESP32,
self-loopback only) but flashing waits for the owner's "plugged in" message and the self-test for
"jumper in place" (`docs/design/readiness.md`). Update this line when that happens.

- It is the timing reference. Never flash a target board with it.
- Builds with `pio run -d firmware/counter_esp32` (platform `espressif32@7.0.1`, same as `firmware/esp32`).
- Protocol v2 (`pc/counter/proto.py`): u32 `max_width_s`, `start_timeout_s`, ARM_ACK status (ok / busy /
  bad version / malformed), 64-bit microsecond heartbeat clock, PULSE with ticks + wrap count.
- Frame code and ARM field offsets are checked against the PC codec without hardware:
  `.venv/bin/python pc/counter/fw_parity_test.py`.

## Pins (ESP32 DevKit)

| Function | Pin | Notes |
|---|---|---|
| target pulse input (`IN_DUT`) | GPIO34 | input-only pad; used for target boards, NOT exercised by the self-test |
| self-test input (`IN_SELF`) | GPIO35 | input-only pad |
| self-test output (`GEN_OUT`) | GPIO25 | the only pin the firmware ever drives (besides the LED) |
| LED | GPIO2 | heartbeat blink |

Self-test wiring: **one jumper GPIO25 -> GPIO35.** Nothing on GPIO34.

## Self-test (self-loopback only)

`.venv/bin/python pc/counter/selftest.py --port <counter port> --out results.txt` runs five scenarios:
widths 100 us, 1 ms, 100 ms, 1 s, 10 s and 60 s (longer than the 53.7 s 32-bit wrap), then an induced glitch,
a missing pulse, a line held high at end, and a sequence gap (the PC drops one frame and asks for REPLAY).
It does **not** test clock accuracy (one crystal generates and measures) and does **not** exercise GPIO34.

## Known limits (draft)

WiFi/dashboard not implemented. Edge latching depends on the legacy MCPWM ISR (UNVERIFIED under load).
See `docs/design/counter_design.md` sections 13-14.
