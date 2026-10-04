# Readiness: go / no-go before the first target-board pilot (Uno)

Fill this in by hand and copy the result into `run_log.md`. **Every box must be ticked; one open box is a no-go.**
Nothing here has been executed yet: all boxes are open.

## A. Counter (S1, one ESP32, no target)

- [ ] A1. `pio device list` showed exactly one ESP32 and nothing else; flashed `firmware/counter_esp32` (the counter, not a target firmware). Commit/sha256 of `src/main.cpp` recorded.
- [ ] A2. Self-loopback self-test passed (jumper GPIO25 -> GPIO35): `.venv/bin/python pc/counter/selftest.py --port <counter> --out results.txt`; all five scenarios PASS, no CRC errors, no dropped records. Result file committed. **Caveat acknowledged:** one crystal generates and measures; this does not prove clock accuracy and does not exercise GPIO34.
- [ ] A3. Clock calibration done (>= 30 min): `.venv/bin/python pc/counter/calibration.py --port <counter> --minutes 30 --out calibration.json`; `within_50ppm` true; JSON kept for `--counter-cal`.
- [ ] A4. Counter firmware flash status updated in `firmware/counter_esp32/README.md`.

## B. Input path (S2, counter + known source)

- [ ] B1. A known pulse source on GPIO34 through the **real** wiring (`docs/design/wiring.md` section 3): widths measured within tolerance, no phantom pulses at source reset.
- [ ] B2. Uno divider built and checked with a multimeter, Vout 3.0-3.4 V (`wiring.md` section 4); pre-power checklist (`wiring.md` section 6) ticked.

## C. Software state

- [ ] C1. `git status` clean; HEAD tagged (state the tag); `data/run_history.jsonl` has no dangling live `started` line.
- [ ] C2. All suites pass; counts recorded in `run_log.md`; `.venv/bin/python pc/counter/default_unchanged_check.py` prints SAME for all three boards.
- [ ] C3. `data/raw/phase2` and `phase3` empty (or only the new dataset); no `no_ref` / `with_ref` folders anywhere.
- [ ] C4. Dry run clean: `.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 --port <target> --ref counter --counter-port <counter> --dry-run` prints the `with_ref` bucket, the counter line and the ETA table.
- [ ] C5. `python pc/run.py --plan` read by the owner; ceiling decision recorded (current: none, run to the memory wall).

## D. Run environment

- [ ] D1. Target and counter device files written down and **confirmed by the owner** (the runner never guesses; two ESP32-like ports must not be swapped).
- [ ] D2. Sleep prevention on (`caffeinate -s` or `pmset` check shown in the preflight), powered USB hub, laptop on mains.
- [ ] D3. Operator knows Ctrl+C: the sweep disarms the counter and closes both ports; re-running the same command resumes inside the same bucket.

## E. Pilot definition (first target contact)

- Board: **Uno** only. Command: `.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 --port <target> --n-start 2 --n-max 4 --ref counter --counter-port <counter> --counter-cal calibration.json`
- Expected: 3 points (n=2,3,4), 100 pulses each, `ref_status ok`, `ref_compare_points.csv` with `micros() - counter` per point. The Uno `micros()` tick is 4 us, so differences of one tick are quantisation, not error.
- Stop and report if: any `ref_status` other than ok, any anomaly code, pulse count != 100, difference above 5 % AND above one tick, or the counter heartbeat drops.
- Not part of the pilot: ESP8266, ESP32 targets, Phase 3, any `n` above 4.
