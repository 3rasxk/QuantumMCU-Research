# Uno — qpe — analysis

Data: `data/raw/phase2/uno/qpe/{raw.csv,memory_wall.csv,points.csv,sessions.csv}`,
commit `91a55b3` (per `sessions.csv`'s `git_commit` column). REPS=100. Charts:
`data/figures/uno/qpe/{exec_time_vs_n,outcomes_vs_n,time_per_point}.png`.

Every number below is OBSERVED (read directly off the CSVs, or a git-line
citation) unless marked INTERPRETATION.

## Scaling — the first genuine out-of-sample test of the timing model

**qpe is the first circuit in this run set whose model comparison is not
exact-by-construction at any n.** `BOARD_GATE_COST["uno"]` was fit from
exactly three data points — h_all's, bell_ghz's, and qft's own n=7
measurements, a 3-equations/3-unknowns system (`pc/shared/timing_model.py:165-178`,
comment states this explicitly: "fit ... (h_all, bell_ghz, qft) ที่ n สูงสุด").
qpe's gate formula (`pc/shared/timing_model.py:152-155`: `(2+2(n-1), 0,
1+(n-1)+(n-1)(n-2)/2)`) was never part of that fit — every ratio below is a
real prediction check, not a guaranteed-1.000-somewhere artifact the way
h_all's/bell_ghz's/qft's own n=7 ratios were.

| n | median exec_time_us | IQR | model (expected_exec_time_us) | ratio measured/model |
|---|---|---|---|---|
| 2 | 1312.0 | [1312.0, 1316.0] | 574.3 | **2.285** |
| 3 | 3196.0 | [3192.0, 3196.0] | 1827.4 | 1.749 |
| 4 | 7476.0 | [7476.0, 7480.0] | 5221.5 | 1.432 |
| 5 | 17224.0 | [17224.0, 17228.0] | 13994.2 | 1.231 |
| 6 | 40024.0 | [40024.0, 40028.0] | 35927.2 | 1.114 |
| 7 | 93364.0 | [93364.0, 93368.0] | 89404.2 | 1.044 |

(model values from `pc/shared/timing_model.expected_exec_time_us("uno","qpe",n)`;
wall n=8 has no raw trials — see Wall section.)

OBSERVED: the ratio decreases monotonically from 2.285 (n=2) to 1.044
(n=7) — the same *shape* as h_all's monotonic decrease, but starting and
ending noticeably higher (h_all: 1.209→1.000; qpe: 2.285→1.044). Unlike
qft, there is no jump/outlier step here — every successive ratio is smaller
than the last, and the doubling ratios below are correspondingly smooth
(2.30×–2.44×, no n=2→3 spike).

INTERPRETATION: the model still gets close (1.04× at n=7, 13% at n=6) even
though this exact circuit's data never entered the fit, which is a modest
positive result for the model's generalization. But the low-n gap (2.29× at
n=2, 1.75× at n=3) is larger than any ratio seen in h_all or bell_ghz
(which never exceeded 1.21×) and is broadly consistent with — though not
proof of — the same additive-constant-overhead explanation offered for
h_all (`docs/analysis/uno/h_all.md`'s Scaling section): a roughly-constant
per-point overhead (µs-level `micros()`/loop/pin-toggle cost) is a larger
fraction of a small circuit's total time, and qpe's own total time at low n
is smaller than qft's was at the same n (compare: qpe n=2 = 1312µs vs qft
n=2 = 292µs — qpe is *larger* here, so this alone doesn't explain the gap
directly; a fixed-overhead story would need that overhead to already be
several hundred µs, which is not independently confirmed by anything
measured in this project). Stated as an open question below, not resolved
here.

**Doubling ratio (successive n, measured):** n2→3: 2.436, n3→4: 2.339,
n4→5: 2.304, n5→6: 2.324, n6→7: 2.333 — smooth throughout, no low-n outlier
the way qft had one.

**Fitted slope of log2(median) vs n** (least-squares via `numpy.polyfit`,
n=2..7, all 6 points): slope ≈ 1.226 bits/qubit (≈2.34× per qubit) —
between h_all's ≈2.46×/qubit and bell_ghz's ≈2.19×/qubit, close to qft's
own n=3-7-only slope (≈2.37×/qubit, per qft.md). Excluding n=2 changes the
fit only marginally here (≈1.216 bits/qubit, ≈2.32×/qubit) — unlike qft,
n=2 is not an outlier point for qpe, so there is little difference between
the all-6-points and n=3-7-only fits.

## Variability

| n | rel. IQR (IQR/median) | min | max | distinct values (of 100) |
|---|---|---|---|---|
| 2 | 0.30% | 1312.0 | 1320.0 | 3 |
| 3 | 0.13% | 3184.0 | 3376.0 | 7 |
| 4 | 0.05% | 7468.0 | 7820.0 | 6 |
| 5 | 0.02% | 17216.0 | 17560.0 | 5 |
| 6 | 0.01% | 40024.0 | 40368.0 | 4 |
| 7 | 0.00% | 93364.0 | 93716.0 | 6 |

OBSERVED: same pattern as the prior three circuits — tight distributions,
rel. IQR falling by roughly an order of magnitude every couple of n, small
distinct-value counts (3–7 of 100). Uno's verified 4µs `micros()` tick
(`analysis/la_crosscheck.py:67-74`, see h_all.md) is 4/1312 ≈ 0.30% of n=2's
median — matches the observed 0.30% rel. IQR at n=2 exactly, same
quantization-noise interpretation as the other three circuits (still
unverified without a Logic Analyzer capture).

**Warm-up effect (first 10 reps vs remaining 90) — fourth circuit in a
row, same shape as qft's:**

| n | first-10 mean | rest-90 mean | diff |
|---|---|---|---|
| 2 | 1314.4 | 1314.0 | +0.4 |
| 3 | 3229.2 | 3194.8 | +34.4 |
| 4 | 7506.0 | 7478.2 | +27.8 |
| 5 | 17258.8 | 17224.7 | +34.1 |
| 6 | 40060.0 | 40026.2 | +33.8 |
| 7 | 93401.6 | 93367.6 | +34.0 |

OBSERVED: n=3 through n=7 all show a +28 to +34µs offset — closely matching
qft's own +29 to +36µs range at the same n's — while n=2 is again near-zero
(+0.4µs), same as every circuit's own n=2/n=3 row so far. This is the
**fourth** circuit to show this same-order-of-magnitude, same-n-range
effect. `WARMUP_REPS` is still `0` (`pc/shared/telemetry.py:489`), nothing
excluded from any table above.

INTERPRETATION: with 4 of 4 circuits collected so far showing the same
effect at the same n's and the same rough magnitude, "probably real" from
qft.md's assessment is now the more conservative reading — the pattern has
not failed to repeat once it starts appearing at n≥3. Still not acted on
this cycle (no `WARMUP_REPS` change made without an explicit decision, per
standing practice) — carried forward again, but this is now the strongest
evidence yet for making that decision before steane_encode/grover.

No bimodality observed.

## The wall

**n=8.** Evidence: `compile_ram_used_bytes=2248` / `TOTAL_SRAM_BYTES=2048`
= **109.8%** — matches qft's n=8 evidence exactly (same bytes, same
percentage) and is within 0.3 points of h_all's (109.9%) and bell_ghz's
(110.1%). Uno linker exited 0 (L2 quirk). Point run once per standing
decision 2: upload succeeded, board did not print `DONE` within the 90s
budget. `failure_message="hard_timeout=true,reset_count=0"` — the hard
`signal.alarm` interrupt fired here, matching **bell_ghz's** pattern (not
h_all's or qft's plain `reset_count=0`). This is now a 2-2 split across the
four circuits collected so far (h_all, qft: plain; bell_ghz, qpe:
hard_timeout=true) — still not explained, no visible correlation with
circuit type, gate count, or execution time found.

**Last ok n: 7, at 59.8% compile RAM** — identical to h_all's and qft's own
59.8%/59.9% last-ok-n readings. Same reading as the other three circuits:
this circuit does not run to completion on this board at n=8 under these
conditions, nothing more.

## Overhead and reliability

**Reflash time per point**, all 1 attempt each
(`data/figures/uno/qpe/time_per_point.png`):

| n | compile_s | upload_s | total |
|---|---|---|---|
| 2 | 3.4 | 4.3 | 7.7 |
| 3 | 2.5 | 3.4 | 5.9 |
| 4 | 2.0 | 3.3 | 5.3 |
| 5 | 1.8 | 3.2 | 5.0 |
| 6 | 2.1 | 3.4 | 5.5 |
| 7 | 2.1 | 3.2 | 5.3 |
| 8 | 2.2 | 3.2 | 5.4 |

**Zero upload retries in this run** — every `points.csv` row is
`attempt_index=0`. **One `hard_timeout=true` event, at n=8 (the wall/last
point of this circuit)** — same situation as bell_ghz's: `wall_found=True`
breaks the per-n loop immediately after a positive-evidence wall, so there
was no subsequent `build_and_upload()` call within this process for the
settle mechanism to protect. The port-closing fix (`pre-run-uno-v2`) has
now gone **four circuits** without a live confirmation: h_all had a retry
but not after a hard_timeout; bell_ghz and qpe both had a hard_timeout but
it landed on the final/wall point; qft had neither. The fix remains
implemented and unit-tested only (`pc/shared/uno_upload_retry_test.py`).
The only way this gets a live test is a `hard_timeout=true` on a
**non-final** n — has not happened in 4 circuits, 27 total points.

## Limitations

Single run, single board, REPS=100, `micros()`-only timing, timed window
exactly `firmware/uno/src/main.cpp:86-90`, no LA cross-check, no claims
about other boards/phases/energy — same as h_all.md/bell_ghz.md/qft.md.

## Open questions / next algorithm

- **qpe's low-n model gap (2.29× at n=2, 1.75× at n=3) is the first
  genuine out-of-sample miss seen in this project** — the model was never
  fit to qpe's own data. Worth deciding whether the model needs a fourth
  term (a constant additive overhead per point) before steane_encode/grover
  are run, rather than assuming the existing 3-parameter gate-count-only
  form will keep generalizing.
- Warm-up effect: 4 for 4 circuits now show it at n≥3, same magnitude
  range each time. This should be an explicit `WARMUP_REPS` decision before
  steane_encode, not another "carried forward" line.
- hard_timeout=true is now 2 of 4 (bell_ghz, qpe) vs plain reset_count=0 in
  the other 2 (h_all, qft) — no pattern found yet correlating with gate
  count, circuit shape, or timing. Watch steane_encode/grover's n=8 (or
  wherever their own walls land) for a tie-breaker.
- Port-closing fix: still zero real hard_timeout-then-next-upload
  sequences after 4 circuits / 27 points. Continue watching.
