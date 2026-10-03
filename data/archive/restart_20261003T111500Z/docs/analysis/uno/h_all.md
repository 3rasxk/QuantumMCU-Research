# Uno — h_all — analysis

Data: `data/raw/phase2/uno/h_all/{raw.csv,memory_wall.csv,points.csv,sessions.csv}`,
commit `ef1546b` (per `sessions.csv`'s `git_commit` column). REPS=100. Charts:
`data/figures/uno/h_all/{exec_time_vs_n,outcomes_vs_n,time_per_point}.png`.

Every number below is OBSERVED (read directly off the CSVs, or a git-line
citation) unless marked INTERPRETATION.

## Scaling

| n | median exec_time_us | IQR | model (expected_exec_time_us) | ratio measured/model |
|---|---|---|---|---|
| 2 | 284.0 | [280.0, 288.0] | 234.9 | 1.209 |
| 3 | 812.0 | [812.0, 816.0] | 704.7 | 1.152 |
| 4 | 2088.0 | [2088.0, 2088.0] | 1879.1 | 1.111 |
| 5 | 4912.0 | [4908.0, 4912.0] | 4697.9 | 1.046 |
| 6 | 11468.0 | [11464.0, 11468.0] | 11274.9 | 1.017 |
| 7 | 26308.0 | [26304.0, 26312.0] | 26308.0 | 1.000 |

(model values from `pc/shared/timing_model.expected_exec_time_us("uno","h_all",n)`,
computed live from `pc/shared/timing_model.py:252-257`; wall n=8 has no raw
trials — see Wall section.)

OBSERVED: the ratio decreases monotonically from 1.209 (n=2) to 1.000 (n=7),
trending toward 1 as n grows.

INTERPRETATION: consistent with a roughly-constant additive per-point
overhead (e.g. `micros()` call overhead, loop bookkeeping, `digitalWrite()`
pin toggles either side of the timed region — `firmware/uno/src/main.cpp:86-90`)
on top of the model's per-gate-per-amplitude cost — a fixed offset shrinks
toward zero as a fraction of a fast-growing multiplicative term. Not
independently verified against a separate overhead measurement; stated as
interpretation only.

**Doubling ratio (successive n, measured):** n2→3: 2.859, n3→4: 2.571,
n4→5: 2.353, n5→6: 2.335, n6→7: 2.294 — decreasing, approaching but not
reaching 2.0× within this range.

**Fitted slope of log2(median) vs n** (least-squares via `numpy.polyfit`,
n=2..7, all 6 points): slope ≈ 1.296 bits/qubit (≈2.46× per qubit), not the
naive 2.0×/qubit ("roughly doubling") a pure `2^n`-amplitude statevector
cost would predict.

INTERPRETATION: this is *expected*, not an anomaly — `h_all`'s own gate
count is `(n, 0, 0)` (n Hadamard gates, `pc/shared/timing_model.py:135-136`),
so the model itself is `n · k_h · 2^n`, not `k · 2^n` — the extra linear-in-n
factor from applying one H per qubit adds ≈`log2(n)` bits of slope on top of
the pure-doubling term over this n range, which is why the model's own
ratio between successive n (3.00, 2.667, 2.50, 2.40, 2.333 — computed from
`expected_exec_time_us`) is *also* above 2.0× and matches the measured
trend's shape closely (measured ratios are uniformly slightly below the
model's own ratios at every step, consistent with the additive-overhead
point above).

## Variability

| n | rel. IQR (IQR/median) | min | max | distinct values (of 100) |
|---|---|---|---|---|
| 2 | 2.82% | 280.0 | 288.0 | 3 |
| 3 | 0.49% | 808.0 | 820.0 | 4 |
| 4 | 0.00% | 2080.0 | 2140.0 | 9 |
| 5 | 0.08% | 4896.0 | 5232.0 | 6 |
| 6 | 0.03% | 11464.0 | 11792.0 | 5 |
| 7 | 0.03% | 26304.0 | 26636.0 | 4 |

OBSERVED: extremely tight distributions (rel. IQR ≤ 2.82%, and 0% at n=4 —
the IQR box itself is degenerate, meaning ≥50% of the 100 reps landed on the
exact same value). Each n has only 3–9 distinct observed values out of 100
reps.

**micros() resolution on Uno: 4µs/tick** — timer0, prescale 64 @ 16MHz.
VERIFIED in-repo (not just recalled): `analysis/la_crosscheck.py`'s
`DEFAULT_ABS_FLOOR_US = {"uno": 4.0, ...}` with comment citing "timer0
prescale 64 @ 16MHz นับทีละ 4us ต่อ tick" (`analysis/la_crosscheck.py:67-74`).
This resolution is a *significant* fraction of the median at n=2 (4µs / 284µs
≈ 1.4%) and n=3 (4µs / 812µs ≈ 0.5%), matching the observed small distinct-value
counts and non-zero rel. IQR at low n almost exactly — most of the "spread"
visible at n=2/n=3 is plausibly quantization noise, not genuine execution-time
variance, though this isn't separately verified (no Logic Analyzer
cross-check has been run — see Limitations). By n=4 the pulse width (≈2088µs)
is ≈522 ticks, and quantization becomes negligible relative to the signal.

**Warm-up effect (first 10 reps vs remaining 90):**

| n | first-10 mean | rest-90 mean | diff |
|---|---|---|---|
| 2 | 284.8 | 283.9 | +0.9 |
| 3 | 813.2 | 813.1 | +0.1 |
| 4 | 2121.2 | 2087.7 | +33.5 |
| 5 | 4934.4 | 4910.0 | +24.4 |
| 6 | 11499.2 | 11467.4 | +31.8 |
| 7 | 26340.4 | 26308.6 | +31.8 |

OBSERVED: a small, consistent positive offset in the first 10 reps at n=4-7
(≈24–34µs, ≈0.1–1.6% of the median), absent (or negligible) at n=2/3.
`WARMUP_REPS` is currently `0` (`pc/shared/telemetry.py:489`), so no reps are
excluded from any statistic above or in the plotted chart. INTERPRETATION:
plausibly a genuine (if small) warm-up transient — not large enough on this
one run to justify raising `WARMUP_REPS` off its current value without a
second run to confirm it repeats; flagged as an open question below, not
acted on.

No bimodality observed — each n's distinct values cluster tightly (see
distinct-value counts above), not split into two separated clusters.

## The wall

**n=8.** Evidence: `compile_ram_used_bytes=2250` / `TOTAL_SRAM_BYTES=2048`
= **109.9%**, recorded in `data/raw/phase2/uno/h_all/memory_wall.csv`. The
Uno linker (avr-ld) exited 0 anyway — this is the documented L2 toolchain
quirk (`docs/preflight_report.md`) — so per standing decision 2 the point
was still run once for the observed behaviour: upload succeeded, but the
board never printed `DONE` within its 90s budget (`points.csv`:
`timeout_hit=True`, `failure_message="reset_count=0"` — no board reset
observed, no hard_timeout signal fired either, see Overhead section). Final
status forced to `build_overflow` regardless of that runtime outcome
(`uno_sweep.py`'s `compile_ram_wall` branch).

**Last ok n: 7, at 59.9% compile RAM** (`memory_wall.csv` row for n=7,
`compile_ram_pct=59.9`). There is a large gap between the last-known-safe
point (59.9%) and the first-known-overflow point (109.9%) — n=7→8 doubles
`theoretical_bytes` from 1024 to 2048, so no intermediate n exists to narrow
this further within the sweep's integer-n resolution.

A wall here means exactly: **this circuit does not run to completion on
this board at n=8 under these conditions** (this firmware build, this
toolchain, `micros()` timing only). It is not a claim about any other board,
any other circuit, or a claim that n=8 is impossible in principle on
different firmware.

## Overhead and reliability

**Reflash (compile+upload) time per point**, summed across all attempts
(`data/figures/uno/h_all/time_per_point.png`, `points.csv`):

| n | attempts | compile_s | upload_s | total |
|---|---|---|---|---|
| 2 | 2 | 11.0 | 14.5 | 25.5 |
| 3 | 1 | 3.4 | 3.7 | 7.1 |
| 4 | 1 | 3.6 | 4.7 | 8.3 |
| 5 | 1 | 3.0 | 3.3 | 6.3 |
| 6 | 1 | 3.8 | 7.0 | 10.8 |
| 7 | 1 | 3.5 | 3.2 | 6.7 |
| 8 | 1 | 3.0 | 3.1 | 6.1 |

**One upload retry occurred, at n=2.** Attempt 1's avrdude output matched
the `stk500_getsync`/"not in sync" signature (`is_upload_sync_failure`,
`pc/phase2_sweep/uno_sweep.py:131-133`) — the exact Session A failure
mode this session's earlier hardening targeted. The settle+re-enumeration
mechanism fired (2.0s settle, port re-enumeration found), and attempt 2
succeeded. `retry_count=1` recorded on the terminal `memory_wall.csv` row
for n=2.

**No `hard_timeout=true` event occurred anywhere in this run.** n=8's failure
message is `reset_count=0` with no `hard_timeout=true` prefix — meaning the
`read_serial_trials()` read loop's own deadline check
(`while time.time() < deadline`, `pc/phase2_sweep/uno_sweep.py:273`) exited
normally when the 90s budget elapsed, rather than needing the hard
`signal.alarm` interrupt (`uno_sweep.py:266-267,289-290`) to force it. This
is worth flagging precisely because bell_ghz's n=8 *did* hit `hard_timeout=true`
(see `docs/analysis/uno/bell_ghz.md`) under what looks like the same kind
of failure (compile RAM wall, no DONE) — the two points didn't fail via the
same code path at the serial-read layer, even though both are classified
identically as `build_overflow`. Not fully explained by data collected so
far; noted as an open question.

Nothing else unexpected: no port change, no board reset during this circuit
(`reset_count=0` on every terminal row).

## Limitations

- Single run, single board (Uno), REPS=100, `micros()` timing only.
- The timed window is exactly `run_circuit()` in
  `firmware/uno/src/main.cpp:86-90` (between the `digitalWrite(...HIGH)` and
  the following `digitalWrite(...LOW)`, which is also the `GPIO_TIMING_PIN`
  pulse a Logic Analyzer would see) — it does **not** include
  `freeMemory()` heap sampling or the `Serial.print(...)` reporting, both of
  which happen after `t1`.
- No Logic Analyzer cross-check exists yet for any of these points
  (`--la` was not used this run) — the quantization-noise interpretation in
  the Variability section is plausible but unverified against an independent
  timing source.
- No claims made here about ESP8266, ESP32, Phase 3, or energy/power —
  none of that data exists in this run.

## Open questions / next algorithm

- Does the small first-10-reps warm-up offset (≈24–34µs at n=4-7) repeat on
  qft's run? If it repeats consistently across circuits, it's worth raising
  `WARMUP_REPS` above 0 as a deliberate decision — not done here on one
  run's evidence alone.
- Why did n=8 not trigger `hard_timeout=true` here while bell_ghz's n=8 did?
  Worth checking whether it recurs on qft/qpe/steane_encode/grover's own
  wall points once collected.
