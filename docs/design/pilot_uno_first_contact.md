# First Uno pilot contact (2026-10-04): what the counter saw

Command: `pc/run.py --board uno --algorithm h_all --phase 2 --n-start 2 --n-max 2 --ref counter --counter-port tcp:5055`
(counter powered from the Uno 5V -> VIN, data over WiFi, divider variant B on pin 7). Data: `data/raw/phase2/uno/h_all/with_ref/`.

## Result
- Target side OK: build, upload, 100 `micros()` rows (280/284/288 us, median 284), point status `ok`.
- Counter side: 200 pulses reported (two runs of the Uno firmware, see below), PCNT rising-edge count 217, anomaly codes 2, 3, 5.
  The comparison was **refused** (`refused_count_mismatch`: 183 usable pulses, 17 glitches, 100 reps). micros() data and the point status were
  not touched. This is the designed behaviour.

## Findings (measured, one point; interpretation marked)
1. **Two runs, not one.** Pulses 0-99 and 100-199 are separated by a 2.34 s gap. The Uno firmware restarts when the sweep opens its serial port
   (DTR reset) after the restart caused by the upload, so the counter saw both. Only the last run's rows are read by the sweep. Needed: split the
   stream at long gaps and pair the **last** run (rule to be implemented; today the join refuses).
2. **183 of 200 pulses are clean**: widths 289.83 us (124), 295.9 us (57), 296.2 us (2).
3. **17 pulses are 13 ns wide (1 capture tick)**, all in regular time slots (rise spacing >= 2.18 ms). PCNT counted 217 rising edges for 200 reported pulses.
   Reading: fast noise edges on GPIO34 (UNVERIFIED: not seen on a scope). The input is a high-impedance divider node (about 12 kohm) with a jumper
   wire and the MCPWM capture has no glitch filter.
4. **The +6.1 us step** (32 % of clean pulses are 6.1 us longer) matches the Arduino timer0 overflow interrupt (every 1.024 ms) landing inside
   the pulse (UNVERIFIED mechanism). `micros()` (4 us tick) hides it.
5. **counter - micros() is about +6 to +10 us** (counter 289.8-295.9 us vs micros() 280-288 us): the pin is raised before `t0` and lowered after `t1`
   in `firmware/uno/src/main.cpp:86-90`, so the pulse includes two `digitalWrite` calls that the micros() bracket excludes.
6. **Power from the Uno worked** through the run (counter did not reset; WiFi link stayed up).

## Next steps
- Reduce input noise: a 100 pF-1 nF capacitor from GPIO34 to GND at the counter, shorter wires, or a lower-impedance divider; re-run the same point.
- Implement run splitting (finding 1) and an explicit glitch policy for 13 ns events (drop pairs shorter than a threshold, keep the count in the report).
- Do not compare micros() and counter widths until the 17 artefacts are explained.
