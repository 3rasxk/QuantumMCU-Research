# Uno — cross-algorithm comparison

Updated after each algorithm. Currently covers: h_all, bell_ghz.

## Per-n time ratio, h_all / bell_ghz

| n | h_all median (µs) | bell_ghz median (µs) | ratio h_all/bell_ghz |
|---|---|---|---|
| 2 | 284.0 | 148.0 | 1.919 |
| 3 | 812.0 | 348.0 | 2.333 |
| 4 | 2088.0 | 772.0 | 2.705 |
| 5 | 4912.0 | 1704.0 | 2.883 |
| 6 | 11468.0 | 3556.0 | 3.226 |
| 7 | 26308.0 | 7556.0 | 3.482 |

OBSERVED: the ratio grows steadily with n, from 1.9× at n=2 to 3.5× at n=7
— h_all gets relatively *more* expensive than bell_ghz as n increases, not
just uniformly more expensive.

INTERPRETATION, tied to gate counts read from the timing model source (not
guessed): `pc/shared/timing_model.gate_counts()` returns `(n, 0, 0)` for
h_all and `(1, n-1, 0)` for bell_ghz (`pc/shared/timing_model.py:135-138`)
— h_all applies **n Hadamard gates**, bell_ghz applies **1 Hadamard + (n-1)
CNOT gates**. The fitted per-gate costs for Uno are
`k_h=29.36µs, k_cnot=4.94µs` per gate per amplitude
(`pc/shared/timing_model.py:180`, `BOARD_GATE_COST["uno"]`) — H is
**≈5.9× more expensive than CNOT on this board**, with the model's own
comment attributing this to the ATmega328P having no hardware FPU: H does
real floating-point trigonometric arithmetic per amplitude, CNOT is just an
index/struct swap (`pc/shared/timing_model.py:182-184`). Since h_all's cost
grows as `n · k_h · 2^n` while bell_ghz's grows as
`(k_h + (n-1) · k_cnot) · 2^n` — a much smaller per-n increment
(`k_cnot=4.94` vs `k_h=29.36`) — h_all's relative cost necessarily pulls
ahead as n grows. This is a property of the **gate mix**, not a Uno-specific
anomaly in the collected data; the model was fit at n=7 on a prior dataset
(`pc/shared/timing_model.py:169`) and both algorithms' measured/model
ratios in their own docs stay within 1.0–1.2×, so the gate-count
explanation is consistent with, not contradicted by, this run's numbers.

## Scaling comparison

| | h_all | bell_ghz |
|---|---|---|
| fitted slope, log2(median) vs n (n=2-7) | ≈1.296 bits/qubit (≈2.46×/qubit) | ≈1.131 bits/qubit (≈2.19×/qubit) |
| doubling ratio range (successive n) | 2.29×–2.86× | 2.09×–2.35× |
| wall n | 8 (both) | 8 (both) |
| wall evidence (compile_ram_pct) | 109.9% | 110.1% |
| last ok n compile_ram_pct | 59.9% (n=7) | 60.1% (n=7) |

Both circuits hit their wall at the same n (8) with almost identical RAM
evidence (109.9% vs 110.1%) — expected, since `theoretical_bytes = 2^n * 8`
(`pc/phase2_sweep/uno_sweep.py`: `theoretical_bytes = (1 << n) * 8`) does
not depend on which circuit is running, only on n and the fixed per-amplitude
state size. The wall is a **state-vector memory limit**, not a
circuit-specific one — both algorithms allocate the same `2^n`-amplitude
array regardless of gate mix.

## Reliability so far

- h_all: 1 upload-stage retry (n=2, avrdude sync failure, settled+succeeded
  on attempt 2). No `hard_timeout=true`.
- bell_ghz: 0 upload retries. 1 `hard_timeout=true` (n=8, the wall/last
  point — not yet a live test of the port-closing fix, see bell_ghz.md).
- No two-consecutive-n upload exhaustion, no `ConsecutiveUploadFailuresError`,
  in either run.

## Limitations

Two circuits, one board, one run each, REPS=100, `micros()`-only timing.
No claims about ESP8266, ESP32, Phase 3, ordering effects between circuits
(each ran as a fully separate process — see `pc/shared/paths.py`'s
per-algorithm layout), or energy.

## Open questions carried forward

- Warm-up offset (h_all.md, bell_ghz.md): does it repeat at qft?
- hard_timeout discrepancy between h_all's and bell_ghz's n=8 (both same
  failure classification, different serial-read code path) — watch for a
  pattern across the remaining four circuits.
- Port-closing fix still has no live confirmation — watch qft's first
  upload closely.
