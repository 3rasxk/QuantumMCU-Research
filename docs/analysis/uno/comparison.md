# Uno — cross-algorithm comparison

Updated after each algorithm. Currently covers: h_all, bell_ghz, qft, qpe.

## Per-n time, all four circuits

| n | h_all (µs) | bell_ghz (µs) | qft (µs) | qpe (µs) |
|---|---|---|---|---|
| 2 | 284.0 | 148.0 | 292.0 | 1312.0 |
| 3 | 812.0 | 348.0 | 1932.0 | 3196.0 |
| 4 | 2088.0 | 772.0 | 4696.0 | 7476.0 |
| 5 | 4912.0 | 1704.0 | 11012.0 | 17224.0 |
| 6 | 11468.0 | 3556.0 | 25920.0 | 40024.0 |
| 7 | 26308.0 | 7556.0 | 61424.0 | 93364.0 |

## Per-n ratios

| n | h_all/bell_ghz | qft/h_all | qft/bell_ghz | qpe/h_all | qpe/bell_ghz | qpe/qft |
|---|---|---|---|---|---|---|
| 2 | 1.919 | 1.028 | 1.973 | 4.620 | 8.865 | 4.493 |
| 3 | 2.333 | 2.379 | 5.552 | 3.936 | 9.184 | 1.654 |
| 4 | 2.705 | 2.249 | 6.083 | 3.580 | 9.684 | 1.592 |
| 5 | 2.883 | 2.242 | 6.462 | 3.507 | 10.108 | 1.564 |
| 6 | 3.226 | 2.260 | 7.289 | 3.490 | 11.255 | 1.544 |
| 7 | 3.482 | 2.335 | 8.129 | 3.549 | 12.356 | 1.520 |

OBSERVED: **qpe is the most expensive circuit at every n**, by a wide and
growing margin against bell_ghz (8.9×→12.4×) and a large, roughly-flat
margin against h_all (3.5×–4.6×, dipping after n=2 then flattening around
3.5×). qpe/qft starts high (4.5× at n=2, driven by qft's own low-n dip
noted in qft.md) then drops and flattens around 1.5×–1.6× from n=4 onward —
qpe and qft are the two circuits with quadratic (`n(n-1)/2`-shaped) gate
terms (CPhase for qft, a mix of H+CPhase for qpe — see gate counts below),
so their ratio settling down while h_all's/bell_ghz's linear-gate ratios
keep growing is consistent with both having the same asymptotic shape.

INTERPRETATION, tied to gate counts read from the timing model source (not
guessed): `pc/shared/timing_model.gate_counts()` returns `(n, 0, 0)` for
h_all, `(1, n-1, 0)` for bell_ghz, `(n, 0, n(n-1)/2)` for qft, and
`(2+2(n-1), 0, 1+(n-1)+(n-1)(n-2)/2)` for qpe (`pc/shared/timing_model.py:135-155`).
qpe applies **more Hadamards than qft at the same n** (qpe: `2n-2`; qft:
`n`) and a CPhase count in the same quadratic family, which is consistent
with qpe costing more than qft at every n once both are past their own
low-n idiosyncrasies (qft's own low-n model gap, qpe's own low-n model gap
— see qpe.md). Both circuits' relative cost against h_all/bell_ghz grows
with n because both have quadratic gate counts against h_all's/bell_ghz's
linear ones — expected, not anomalous.

## Scaling comparison

| | h_all | bell_ghz | qft | qpe |
|---|---|---|---|---|
| fitted slope, log2(median) vs n (n=2-7) | ≈1.296 bits/qubit (≈2.46×/qubit) | ≈1.131 bits/qubit (≈2.19×/qubit) | ≈1.459 bits/qubit (≈2.75×/qubit; ≈1.245/≈2.37×/qubit for n=3-7) | ≈1.226 bits/qubit (≈2.34×/qubit; ≈1.216/≈2.32×/qubit for n=3-7) |
| doubling ratio range (successive n) | 2.29×–2.86× | 2.09×–2.35× | 2.35×–6.62× (n2→3 outlier; 2.35×–2.43× excluding it) | 2.30×–2.44× (smooth, no outlier) |
| measured/model ratio range | 1.00×–1.21× | 1.00×–1.11× | 1.00×–1.90× | 1.04×–2.29× |
| fit to this circuit's own data? | yes (n=7 anchor) | yes (n=7 anchor) | yes (n=7 anchor) | **no — held out, genuine prediction** |
| wall n | 8 (all four) | 8 (all four) | 8 (all four) | 8 (all four) |
| wall evidence (compile_ram_pct) | 109.9% | 110.1% | 109.8% | 109.8% |
| last ok n compile_ram_pct | 59.9% (n=7) | 60.1% (n=7) | 59.8% (n=7) | 59.8% (n=7) |

All four circuits hit their wall at the same n (8) with near-identical RAM
evidence (109.8–110.1%) and near-identical last-ok-n evidence
(59.8–60.1%) — confirmed a fourth time: `theoretical_bytes = 2^n * 8`
(`pc/phase2_sweep/uno_sweep.py`: `theoretical_bytes = (1 << n) * 8`) does
not depend on which circuit is running. The wall is a **state-vector
memory limit**, not a circuit-specific one.

**qpe is the first circuit whose model ratios are a genuine out-of-sample
check, not exact-by-construction at n=7.** `BOARD_GATE_COST["uno"]`
(`pc/shared/timing_model.py:173-182`) was fit from exactly h_all's,
bell_ghz's, and qft's own n=7 measurements (a 3-equations/3-unknowns
system, explicitly documented at `pc/shared/timing_model.py:165-178`) —
qpe's own data never entered that fit, so its n=7 ratio (1.044×) is a real
prediction result, not guaranteed to land near 1.0. It came reasonably
close (4.4% off at n=7, 13% at n=6) but its low-n ratios (2.29× at n=2,
1.75× at n=3) are larger than anything seen in the three circuits the model
was fit to — see qpe.md for the interpretation (open question, not
resolved).

## Reliability so far

- h_all: 1 upload-stage retry (n=2, avrdude sync failure, settled+succeeded
  on attempt 2). No `hard_timeout=true`.
- bell_ghz: 0 upload retries. 1 `hard_timeout=true` (n=8, the wall/last
  point — not a live test of the port-closing fix, see bell_ghz.md).
- qft: 0 upload retries, 0 `hard_timeout=true` events at all.
- qpe: 0 upload retries. 1 `hard_timeout=true` (n=8, the wall/last point —
  same non-test situation as bell_ghz's).
- No two-consecutive-n upload exhaustion, no `ConsecutiveUploadFailuresError`,
  in any of the four runs.
- **`hard_timeout=true` is now a 2-2 split** (bell_ghz, qpe: yes; h_all,
  qft: no) at the serial-read layer, all four otherwise classified
  identically as `build_overflow`. No correlation with gate count, circuit
  shape, or execution time found yet.
- **Port-closing fix (`pre-run-uno-v2`) still has no live confirmation
  after four circuits / 27 total points.** The specific sequence it
  protects — a `hard_timeout=true` on a non-final n, followed by a real
  next `build_and_upload()` in the same process — has not occurred. Both
  `hard_timeout=true` events so far landed on their circuit's wall/last
  point, with no subsequent upload in-process to observe. Keep watching
  steane_encode/grover.

## Warm-up effect — four for four circuits now

| | h_all | bell_ghz | qft | qpe |
|---|---|---|---|---|
| consistent across n? | n=4-7 only | n=6-7 only (n=2-5 noisy/mixed sign) | n=3-7 (tight) | n=3-7 (tight, matches qft closely) |
| typical offset | ≈24-34µs | ≈23-31µs (where present) | ≈29-36µs | ≈28-34µs |

OBSERVED: all four runs show a small positive first-10-reps offset of
similar magnitude (order 24-36µs) at mid-to-high n; qft's and qpe's
versions are the tightest and most consistent (both n=3-7, both near-zero
at n=2). `WARMUP_REPS` remains `0` for all four
(`pc/shared/telemetry.py:489`).

INTERPRETATION: four consecutive circuits showing the same-order-of-
magnitude effect at the same n-range, with zero circuits failing to show it
once n≥3, makes this the strongest evidence yet for a genuine (if small)
warm-up transient. Flagged in qpe.md as a decision point that should not be
deferred a further time before steane_encode/grover.

## Limitations

Four circuits, one board, one run each, REPS=100, `micros()`-only timing.
No claims about ESP8266, ESP32, Phase 3, ordering effects between circuits
(each ran as a fully separate process — see `pc/shared/paths.py`'s
per-algorithm layout), or energy.

## Open questions carried forward

- **Decide `WARMUP_REPS`** before steane_encode/grover — the effect has now
  repeated in all four circuits collected, with consistent magnitude.
- **qpe's low-n model gap (2.29× at n=2)** is the first true out-of-sample
  model miss in this project — consider whether a 4th (additive-overhead)
  model term is needed before trusting timeout budgets for
  steane_encode/grover at low n, or whether it's benign (model still lands
  within ~4% by n=7).
- hard_timeout discrepancy is now 2-2 (bell_ghz/qpe vs h_all/qft) — watch
  steane_encode/grover's own wall points for a tie-breaker; still no
  hypothesis that explains the split.
- Port-closing fix still has no live confirmation after 4 circuits/27
  points — watch steane_encode's first upload closely, specifically for
  any hard_timeout on a non-final n.
