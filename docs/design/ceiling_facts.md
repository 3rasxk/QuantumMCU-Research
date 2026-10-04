# Ceiling facts (no decision): grover, phase 2

ESTIMATE only. No measured value is used. Model: `pc/shared/timing_model.py` (gate counts from
`firmware/common/circuits.hpp` x a prior-fit per-gate-per-amplitude cost, fitted at small n and
extrapolated; per-rep time grows about 8x per n for grover, so the error band widens with n),
plus per point: compile + upload + fixed boot/serial overhead (`COMPILE_S_ESTIMATE`,
`UPLOAD_S_ESTIMATE`, `DEVICE_OVERHEAD_S_ESTIMATE`, bases in that file). Assumptions: 100 reps,
one point at a time, no retries, no operator pauses, no USB drops, WiFi off, no thermal effects.
The owner decision on a ceiling is still open; the current recorded decision is
"no ceiling, run to the memory wall".

Cumulative = sum of all points from n=2 up to and including that n (the sweep runs n ascending).

## esp8266 grover

 n | per rep | point time | cumulative | per-rep vs WDT | flags
---|---|---|---|---|---
2 | 0.0s | 1.1min | 1.1min | 0.0 s vs 6.0 s | 
3 | 0.0s | 1.1min | 2.2min | 0.0 s vs 6.0 s | 
4 | 0.0s | 1.1min | 3.4min | 0.0 s vs 6.0 s | 
5 | 0.0s | 1.2min | 4.5min | 0.0 s vs 6.0 s | 
6 | 0.2s | 1.5min | 6.1min | 0.2 s vs 6.0 s | 
7 | 1.8s | 4.1min | 10.2min | 1.8 s vs 6.0 s | 
8 | 15.6s | 27.1min | 37.3min | 15.6 s vs 6.0 s | WDT risk
9 | 2.2min | 3.6h | 4.3h | 130.5 s vs 6.0 s | WDT risk
10 | 19.1min | 1.3days | 1.5days | 1144.0 s vs 6.0 s | >6h, >24h, WDT risk
11 | 2.7h | 11.1days | 12.6days | 9585.9 s vs 6.0 s | >6h, >24h, >72h, WDT risk
12 | 22.8h | 95.0days | 107.6days | 82089.6 s vs 6.0 s | >6h, >24h, >72h, WDT risk
13 | - | 2.6min | 107.6days | - | predicted WALL point (memory), no device time

Cumulative time passes: 1 day at n=10, 1 week at n=11, 1 month (30 d) at n=12.

## esp32 grover

 n | per rep | point time | cumulative | per-rep vs WDT | flags
---|---|---|---|---|---
2 | 0.0s | 48.0s | 48.0s | 0.0 s vs 5.0 s | 
3 | 0.0s | 48.0s | 1.6min | 0.0 s vs 5.0 s | 
4 | 0.0s | 48.0s | 2.4min | 0.0 s vs 5.0 s | 
5 | 0.0s | 48.2s | 3.2min | 0.0 s vs 5.0 s | 
6 | 0.0s | 49.3s | 4.0min | 0.0 s vs 5.0 s | 
7 | 0.1s | 57.5s | 5.0min | 0.1 s vs 5.0 s | 
8 | 0.8s | 2.2min | 7.2min | 0.8 s vs 5.0 s | 
9 | 7.0s | 12.5min | 19.7min | 7.0 s vs 5.0 s | WDT risk
10 | 1.0min | 1.7h | 2.1h | 61.7 s vs 5.0 s | WDT risk
11 | 8.6min | 14.4h | 16.4h | 517.5 s vs 5.0 s | >6h, WDT risk
12 | 1.2h | 5.1days | 5.8days | 4433.2 s vs 5.0 s | >6h, >24h, >72h, WDT risk
13 | 10.5h | 43.7days | 49.5days | 37764.1 s vs 5.0 s | >6h, >24h, >72h, WDT risk
14 | - | 2.3min | 49.5days | - | predicted WALL point (memory), no device time

Cumulative time passes: 1 day at n=12, 1 week at n=13, 1 month (30 d) at n=13.

