# firmware/counter_esp32: pulse counter (protocol v2) — NOT YET FLASHED

**Flash status: FLASHED 2026-10-04**, ESP32-D0WD-V3 (MAC 8c:94:df:6c:a3:b8, `/dev/cu.usbserial-110`), **WiFi build** (config in the git-ignored `src/wifi_config.h`).
Verified without any pulse input: USB heartbeat at 115200 baud; WiFi link to `pc/counter/bridge.py` (counter joined `oasnnp_2.4GHz`, 192.168.1.145,
TCP :5055, 42 heartbeats / 0 bad frames in about 35 s, `localhost:8080/status` JSON); ARM -> ARM_ACK ok, END -> REPORT with code 7
(never started, as expected: no pulses), bad-version ARM refused, all over WiFi. The 5 GHz SSID is invisible to the ESP32 (2.4 GHz only).
Link check without wiring (`pc/counter/wifi_link_check.py`, 2026-10-04): 90 s soak 90 heartbeats / 0 bad frames (PC-side gap median 1.01 s, max 2.43 s), STATUS round trip 40/40 (median 17 ms, p95 111 ms, one 1.6 s spike), counter reconnected 0.8 s after the server restarted and about 8 s after a counter reboot.
**Self-test not run** (waits for the GPIO25-GPIO35 jumper).

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
