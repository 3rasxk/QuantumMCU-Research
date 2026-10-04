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

## Full Uno h_all sweep (23:03 Bangkok, `--ref counter`, n=2..8, about 2 minutes)
Target: n=2..7 `ok` (100 `micros()` rows each), n=8 `build_overflow` at 100 % RAM (upload skipped, recorded as the wall). The ETA lines printed live (`[ETA] n=3 ok in 12.1s ...`).
Reference: every point `count_mismatch` (comparison refused): 200 pulses for n=2..5 (two runs plus 13 ns artefacts), 168 for n=6 and 132 for n=7 (the
sweep stops reading before the second run finishes), 0 for n=8 (`no_target_run`, as designed).

Clean-pulse medians (pulses >= 0.5 us only; NOT a join, because the pairing is refused) against the `micros()` median of the same point:

| n | micros() median (us) | counter clean median (us) | difference (us) | ratio |
|---|---|---|---|---|
| 2 | 284 | 289.8 | +5.8 | 1.020 |
| 3 | 812 | 824.5 | +12.5 | 1.015 |
| 4 | 2 088 | 2 103.9 | +15.9 | 1.0076 |
| 5 | 4 912 | 4 941.6 | +29.6 | 1.0060 |
| 6 | 11 468 | 11 529.3 | +61.3 | 1.0053 |
| 7 | 26 308 | 26 445.8 | +137.8 | 1.0052 |

A straight line through n=5..7 gives counter = 1.0051 x micros() + 4.7 us. Reading (UNVERIFIED, one run, counter not calibrated, counter-side noise
unexplained): a constant offset of about 5 us (the two `digitalWrite` calls inside the pulse but outside the `micros()` bracket) plus a **0.5 % scale
difference**, i.e. either the Uno's `micros()` clock runs about 0.5 % slow or the counter clock is 0.5 % off; the ceramic resonator of an Uno R3 is
typically +-0.5 % (UNVERIFIED), so the Uno is the likely source. The clock calibration of the counter (`pc/counter/calibration.py`) is needed to separate the two.

## Second full sweep after the 100 uF capacitor on VIN-GND, with run splitting (23:55 Bangkok)
- 13 ns artefacts fell from 14-19 per point to 0-2 per point after the 100 uF capacitor was added across the counter's VIN-GND (UNVERIFIED which part of
  the change did it; the divider may have been changed too). Likely cause of the earlier noise: supply ripple from the counter's WiFi transmissions.
- `pc/counter/crosscheck.split_runs` splits the pulse stream where the idle gap is > 0.5 s and > 50x the in-run gap and pairs the LAST run (the Uno restarts
  after upload and again when the sweep opens its port; the first run is cut short). n=1,2,3,4,7 now have 100 clean pairs; n=5,6 have 99 (one artefact) and are refused.
- Per-point difference, micros() minus counter (negative: counter reads longer), 100 pairs each:

| n | median diff (us) | % | std (us) | IQR (us) |
|---|---|---|---|---|
| 1 | -7.65 | -65.7 (fixed overhead on a 4 us tick) | 0.82 | 0.01 |
| 2 | -7.91 | -2.67 | 1.64 | 3.99 |
| 3 | -10.39 | -1.27 | 1.80 | 4.00 |
| 4 | -15.91 | -0.76 | 1.43 | 0.03 |
| 7 | -135.43 | -0.51 | 1.74 | 3.69 |

Per-rep fit for n>=4 (200 pairs): counter = 1.00491 x micros() + 6.15 us, the same scale as the first sweep (1.0051): reproducible. The constant part
(about 6 us) is the two `digitalWrite` calls plus micros() overhead; the scale part (0.49 %) is a clock difference between the Uno and the counter. Which clock
is off needs the counter calibration (`pc/counter/calibration.py`); the Uno resonator is typically +-0.5 % (UNVERIFIED).

## Counter clock calibration (2026-10-04, 30 min over WiFi, `data/calibration/counter_20261004.json`)
Counter heartbeat clock vs the PC monotonic clock: **+17.5 ppm** (stated standard error 1.9 ppm, 1782 pairs, 17 spike outliers dropped). The estimate
moved from +49 ppm at 10 min to +15..+18 ppm from 25 min on, and WiFi latency jitter is large (residual rms 41 ms), so the realistic uncertainty is
a few ppm, not 1.9 (UNVERIFIED). The reference is the PC's own quartz clock (tolerance UNVERIFIED), so this is a relative figure.
Consequence for the Uno finding: 17.5 ppm = 0.00175 %, far below the 0.49 % scale difference between counter and `micros()`. So the **Uno's `micros()` clock
runs about 0.49 % slow** (i.e. reports about 0.49 % fewer microseconds than elapsed), within the +-0.5 % resonator tolerance typical of an Uno R3 (UNVERIFIED),
unless the PC clock itself were 0.49 % off, which is not plausible for a quartz clock.
