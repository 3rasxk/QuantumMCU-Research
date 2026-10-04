# firmware/counter_esp32: UNFLASHED DRAFT

**Status (owner decision 2026-10-04): never flashed, S1 hardware work cancelled for now.**
This is the ESP32 pulse-counter firmware draft for `docs/counter_design.md` (stage S1 content).
It compiles (`pio run -d firmware/counter_esp32`, platform `espressif32@7.0.1`, same as
`firmware/esp32`) but has **no hardware result**: nothing in it has ever run on a board.

- Do **not** flash a target board with it. It is the timing reference, not a board under test.
- Do not flash the counter ESP32 until the owner approves the stage (see `docs/system_design.md` section f).
- Known gaps against the design are listed in `docs/counter_design.md` section 13 (`max_width_s` is u16,
  heartbeat time is whole seconds, no ARM start timeout, no ACK handling, no WiFi/dashboard).
- Frame format is checked byte for byte against `pc/shared/counter_proto.py` without hardware:
  `.venv/bin/python pc/shared/counter_fw_parity_test.py`.
- Pins: capture input GPIO34 (DUT), self-test input GPIO35, self-test output GPIO25, LED GPIO2.
