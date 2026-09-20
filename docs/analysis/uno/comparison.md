# Uno — cross-algorithm comparison

Updated after each algorithm. Currently covers: h_all, bell_ghz, qft, qpe,
steane_encode.

**steane_encode is structurally different** from the other four: it is a
single fixed point at n=7 (Steane `[[7,1,3]]` code, defined on exactly 7
physical qubits), not a sweep — see `docs/analysis/uno/steane_encode.md`.
It has no doubling ratio, no fitted slope, and no wall (its only point
never reaches the ~110% RAM threshold). It appears in the per-n tables
below only at n=7, and is excluded from the "Scaling comparison" table's
slope/doubling-ratio/wall rows, which don't apply to it.

## Per-n time, all circuits (steane_encode at n=7 only)

| n | h_all (µs) | bell_ghz (µs) | qft (µs) | qpe (µs) | steane_encode (µs) |
|---|---|---|---|---|---|
| 2 | 284.0 | 148.0 | 292.0 | 1312.0 | — |
| 3 | 812.0 | 348.0 | 1932.0 | 3196.0 | — |
| 4 | 2088.0 | 772.0 | 4696.0 | 7476.0 | — |
| 5 | 4912.0 | 1704.0 | 11012.0 | 17224.0 | — |
| 6 | 11468.0 | 3556.0 | 25920.0 | 40024.0 | — |
| 7 | 26308.0 | 7556.0 | 61424.0 | 93364.0 | 16952.0 |

At n=7, steane_encode (16952.0µs) sits **below h_all** (26308.0µs) and
**above bell_ghz** (7556.0µs) — cheaper than every circuit except bell_ghz
at this n, despite steane_encode's fixed gate count (3 H + 9 CNOT = 12
gates total) being larger than bell_ghz's own n=7 count (1 H + 6 CNOT = 7
gates) and comparable to h_all's (7 H). This is consistent with gate mix,
not anomalous: CNOT is far cheaper than H on Uno
(`k_cnot=4.94µs` vs `k_h=29.36µs`, `pc/shared/timing_model.py:179`),
and steane_encode's 9-CNOT/3-H mix costs less per the model than h_all's
7-H/0-CNOT mix at the same n=7 amplitude count.

## Per-n ratios (sweep circuits only — steane_encode has one n, not compared here)

| n | h_all/bell_ghz | qft/h_all | qft/bell_ghz | qpe/h_all | qpe/bell_ghz | qpe/qft |
|---|---|---|---|---|---|---|
| 2 | 1.919 | 1.028 | 1.973 | 4.620 | 8.865 | 4.493 |
| 3 | 2.333 | 2.379 | 5.552 | 3.936 | 9.184 | 1.654 |
| 4 | 2.705 | 2.249 | 6.083 | 3.580 | 9.684 | 1.592 |
| 5 | 2.883 | 2.242 | 6.462 | 3.507 | 10.108 | 1.564 |
| 6 | 3.226 | 2.260 | 7.289 | 3.490 | 11.255 | 1.544 |
| 7 | 3.482 | 2.335 | 8.129 | 3.549 | 12.356 | 1.520 |

OBSERVED: qpe is the most expensive circuit at every n, by a wide and
growing margin against bell_ghz (8.9×→12.4×) and a large, roughly-flat
margin against h_all (3.5×–4.6×). qpe/qft flattens to ~1.5×-1.6× from n=4
onward — both circuits have quadratic gate-count terms, so their ratio
settling while h_all's/bell_ghz's linear-gate ratios keep growing is
consistent with both sharing the same asymptotic shape.

INTERPRETATION, tied to gate counts read from the timing model source (not
guessed): `pc/shared/timing_model.gate_counts()` returns `(n, 0, 0)` for
h_all, `(1, n-1, 0)` for bell_ghz, `(n, 0, n(n-1)/2)` for qft,
`(2+2(n-1), 0, 1+(n-1)+(n-1)(n-2)/2)` for qpe, and the constant `(3, 9, 0)`
for steane_encode (`pc/shared/timing_model.py:135-157`). qpe applies more
Hadamards than qft at the same n (qpe: `2n-2`; qft: `n`) plus a CPhase
count in the same quadratic family, consistent with qpe costing more than
qft at every n once both are past their own low-n idiosyncrasies.

## Scaling comparison (sweep circuits only)

| | h_all | bell_ghz | qft | qpe |
|---|---|---|---|---|
| fitted slope, log2(median) vs n (n=2-7) | ≈1.296 bits/qubit (≈2.46×/qubit) | ≈1.131 bits/qubit (≈2.19×/qubit) | ≈1.459 bits/qubit (≈2.75×/qubit; ≈1.245/≈2.37×/qubit for n=3-7) | ≈1.226 bits/qubit (≈2.34×/qubit; ≈1.216/≈2.32×/qubit for n=3-7) |
| doubling ratio range (successive n) | 2.29×–2.86× | 2.09×–2.35× | 2.35×–6.62× (n2→3 outlier; 2.35×–2.43× excluding it) | 2.30×–2.44× (smooth, no outlier) |
| measured/model ratio range | 1.00×–1.21× | 1.00×–1.11× | 1.00×–1.90× | 1.04×–2.29× |
| fit to this circuit's own data? | yes (n=7 anchor) | yes (n=7 anchor) | yes (n=7 anchor) | no — held out, genuine prediction |
| wall n | 8 (all four) | 8 (all four) | 8 (all four) | 8 (all four) |
| wall evidence (compile_ram_pct) | 109.9% | 110.1% | 109.8% | 109.8% |
| last ok n compile_ram_pct | 59.9% (n=7) | 60.1% (n=7) | 59.8% (n=7) | 59.8% (n=7) |

All four sweep circuits hit their wall at the same n (8) with
near-identical RAM evidence (109.8–110.1%) and near-identical last-ok-n
evidence (59.8–60.1%) — confirmed a fourth time: `theoretical_bytes = 2^n *
8` (`pc/phase2_sweep/uno_sweep.py`: `theoretical_bytes = (1 << n) * 8`)
does not depend on which circuit is running. The wall is a **state-vector
memory limit**, not a circuit-specific one. steane_encode, fixed at n=7
(60.3% RAM, `docs/analysis/uno/steane_encode.md`), never reaches this
threshold by construction — its RAM use is close to but not identical to
the sweep circuits' own n=7 readings (60.3% vs 59.8-60.1%), the small
difference coming from its own larger fixed gate sequence, not noise.

**qpe is the first circuit whose model ratios are a genuine out-of-sample
check, not exact-by-construction at n=7.** `BOARD_GATE_COST["uno"]`
(`pc/shared/timing_model.py:173-182`) was fit from exactly h_all's,
bell_ghz's, and qft's own n=7 measurements — qpe's own data never entered
that fit, so its n=7 ratio (1.044×) is a real prediction result. It came
reasonably close (4.4% off at n=7) but its low-n ratios (2.29× at n=2,
1.75× at n=3) are larger than anything seen in the three circuits the model
was fit to. **steane_encode, by contrast, uses only the H/CNOT gate types
already calibrated by h_all/bell_ghz and matched the model almost exactly**
(0.999×, `docs/analysis/uno/steane_encode.md`) — the two out-of-sample
checks collected so far diverge sharply in how well the model
extrapolates, and the difference tracks whether new gate-type combinations
(qpe's CPhase-heavy mix) or only familiar ones (steane_encode's H+CNOT)
are involved.

## Reliability so far

- h_all: 1 upload-stage retry (n=2, avrdude sync failure, settled+succeeded
  on attempt 2). No `hard_timeout=true`.
- bell_ghz: 0 upload retries. 1 `hard_timeout=true` (n=8, the wall/last
  point — not a live test of the port-closing fix, see bell_ghz.md).
- qft: 0 upload retries, 0 `hard_timeout=true` events at all.
- qpe: 0 upload retries. 1 `hard_timeout=true` (n=8, the wall/last point —
  same non-test situation as bell_ghz's).
- steane_encode: 1 upload-stage retry (its only point, n=7, avrdude sync
  failure, settled+succeeded on attempt 2). No `hard_timeout=true`.
- No two-consecutive-n/point upload exhaustion, no
  `ConsecutiveUploadFailuresError`, in any of the five runs.
- `hard_timeout=true` is a 2-3 split across the five circuits (bell_ghz,
  qpe: yes; h_all, qft, steane_encode: no) at the serial-read layer, all
  five otherwise classified identically where relevant. No correlation
  with gate count, circuit shape, or execution time found yet.
- **The port-closing settle mechanism now has 2 live confirmations** —
  both upload-stage-failure retries (h_all's n=2, steane_encode's n=7),
  both settled correctly and succeeded on the next attempt. **The
  hard_timeout-specific branch still has zero live confirmations after 5
  circuits / 28 total points** — both `hard_timeout=true` events
  (bell_ghz's, qpe's) landed on their circuit's wall/last point, with no
  subsequent upload in-process to observe. Only grover remains to test it.

## Warm-up effect — five for five data points now

| | h_all | bell_ghz | qft | qpe | steane_encode |
|---|---|---|---|---|---|
| consistent across n? | n=4-7 only | n=6-7 only (n=2-5 noisy/mixed sign) | n=3-7 (tight) | n=3-7 (tight, matches qft closely) | n/a (1 point) |
| typical offset | ≈24-34µs | ≈23-31µs (where present) | ≈29-36µs | ≈28-34µs | +20.4µs (1 point) |

OBSERVED: every circuit collected so far shows a small positive first-10-reps
offset of similar magnitude (order 20-36µs) at n≥3-4 — no circuit and no n≥3
point has shown a negative offset. `WARMUP_REPS` remains `0` for all five
(`pc/shared/telemetry.py:489`).

INTERPRETATION: five consecutive data points showing the same-direction,
same-order-of-magnitude effect, with zero counterexamples once n≥3, is
strong evidence for a genuine (if small) warm-up transient. This should be
an explicit decision before grover (the last remaining circuit), not
deferred again.

## Limitations

Five circuits (four sweeps + one fixed point), one board, one run each,
REPS=100, `micros()`-only timing. No claims about ESP8266, ESP32, Phase 3,
ordering effects between circuits (each ran as a fully separate process —
see `pc/shared/paths.py`'s per-algorithm layout), or energy.

## Open questions carried forward

- **Decide `WARMUP_REPS`** before grover — the effect has now repeated in
  all five data points collected, with consistent magnitude and direction.
- qpe's low-n model gap (2.29× at n=2) vs steane_encode's near-exact match
  (0.999×) — the difference tracks whether new gate-type combinations are
  involved; watch grover (which uses both CNOT and CPhase, plus X gates not
  yet seen in this project's model) for a third out-of-sample data point.
- hard_timeout discrepancy is now 2-3 (bell_ghz/qpe vs h_all/qft/steane_encode)
  — still no hypothesis that explains the split; grover's wall point is the
  last chance to see whether a pattern emerges.
- Port-closing fix's hard_timeout-specific branch still has no live
  confirmation after 5 circuits/28 points (the upload-stage-failure branch
  now has 2). Watch grover's uploads closely, specifically for any
  hard_timeout on a non-final n.
