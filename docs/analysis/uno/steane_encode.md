# Uno — steane_encode — analysis

Data: `data/raw/phase2/uno/steane_encode/{raw.csv,memory_wall.csv,points.csv,sessions.csv}`,
commit `cc18d1e` (per `sessions.csv`'s `git_commit` column). REPS=100. Charts:
`data/figures/uno/steane_encode/{exec_time_vs_n,outcomes_vs_n,time_per_point}.png`.

Every number below is OBSERVED (read directly off the CSVs, or a git-line
citation) unless marked INTERPRETATION.

## A structurally different circuit: single fixed n, not a sweep

Unlike the four prior circuits, steane_encode does not climb n. It encodes
the Steane `[[7,1,3]]` code, which is defined on exactly 7 physical qubits
regardless of any logical-qubit-count parameter — `FIXED_N_CIRCUITS =
{"steane_encode": 7}` (`pc/shared/circuit_ids.py:14`, mirrored in
`pc/shared/plot_style.py:61`), and its gate count is a constant `(3, 9, 0)`
— 3 Hadamard, 9 CNOT, 0 CPhase — independent of n
(`pc/shared/timing_model.py:156-157`: `if circuit == "steane_encode": return
(3, 9, 0)  # คงที่ ไม่ขึ้นกับ n`). One data point exists for this circuit,
period; there is no scaling curve, no doubling ratio, no wall (see below).

## The one point

| n | median exec_time_us | IQR | model (expected_exec_time_us) | ratio measured/model |
|---|---|---|---|---|
| 7 | 16952.0 | [16948.0, 16956.0] | 16965.4 | 0.999 |

(model value from `pc/shared/timing_model.expected_exec_time_us("uno","steane_encode",7)`.)

OBSERVED: **the closest measured/model match of any point collected in this
project so far** — 0.08% off, and for the first time the measured value
sits *fractionally below* the model rather than above it. This is not a
result of steane_encode being an out-of-sample test the way qpe.md's model
check was: steane_encode's gate types are exactly H and CNOT, the same two
types h_all's and bell_ghz's own n=7 measurements were used to fit
(`pc/shared/timing_model.py:165-178`), and it introduces no new gate type
the fit didn't already calibrate against (unlike qpe's CPhase mix). The
near-exact match is expected given that, not a new finding about the
model's generalization.

n=7's IQR is degenerate-adjacent (`[16948.0, 16956.0]`, span 8µs on a
16952µs median — 0.05% relative), min/max span 16936–17220µs (7 distinct
values of 100) — same tight-distribution pattern as every other circuit's
own n=7 row.

**Warm-up effect (first 10 reps vs remaining 90):** first-10 mean
16971.6µs, rest-90 mean 16951.2µs, diff **+20.4µs**. OBSERVED: same sign and
same order of magnitude as h_all's/qft's/qpe's own warm-up offsets at their
own n≥3-4 points (≈24-34µs), though only one n exists here so nothing can
be said about whether it's *consistent across n* the way the other three
circuits' multi-n data could show. `WARMUP_REPS` is still `0`
(`pc/shared/telemetry.py:489`), nothing excluded. This is now the **fifth**
circuit-level data point (across 4 sweep circuits + this one fixed point)
showing the same-direction, same-order-of-magnitude effect — no circuit
collected so far has shown a *negative* offset at n≥3.

No bimodality observed.

## No wall

steane_encode's only point is n=7, at **60.3% compile RAM**
(`compile_ram_used_bytes=1234`/`TOTAL_SRAM_BYTES=2048`) — comfortably below
the ~110% threshold that walled every other circuit's n=8. Because the
circuit is fixed at n=7 by its own physical definition, no n=8 attempt is
ever made (`circuit_ids.n_values_for_sweep` ignores `--n-max` for
fixed-n circuits per its own docstring) — **there is no memory wall for
this circuit to hit under this project's sweep design**, not "it happened
not to fail." 60.3% is close to but not identical to the other four
circuits' own n=7 readings (59.8%–60.1%) — the +9-10-byte difference comes
from steane_encode's different, larger, fixed gate sequence needing
slightly more RAM at the same n=7 state-vector size, not measurement noise
(compile RAM is deterministic given a fixed source + N_QUBITS).

## Overhead and reliability — second live confirmation of the settle mechanism

**Reflash time**, both attempts (`data/figures/uno/steane_encode/time_per_point.png`):

| n | attempts | compile_s | upload_s | total |
|---|---|---|---|---|
| 7 | 2 | 7.678 | 10.403 | 18.081 |

**One upload-stage retry occurred.** Attempt 1 failed the avrdude
`stk500_getsync` signature (`is_upload_sync_failure`,
`pc/phase2_sweep/uno_sweep.py:131-133`) after 10 sync attempts; the settle
mechanism fired (`-- settling 2.0s before the next build_and_upload`,
`-- port re-enumeration check: found`) and attempt 2 succeeded, `retry_count=1`
on the terminal `memory_wall.csv` row. **No `hard_timeout=true` anywhere in
this run.**

This is the **second** live confirmation of the port-closing settle
mechanism actually protecting a real retry (the first was h_all's n=2,
`docs/analysis/uno/h_all.md`) — both are upload-stage-failure retries, not
the specific "`hard_timeout=true` then a real next `build_and_upload()`"
sequence the fix was originally written for (that specific sequence is
still unconfirmed after 5 circuits — see comparison.md). The mechanism
triggers on *either* condition per its own logic
(`pc/phase2_sweep/uno_sweep.py`'s `_sweep_body`: `pending_settle` set on
`hard_timeout=true` **or** an upload-stage failure) — this run is real
evidence the upload-stage-failure branch works correctly on hardware, which
is a narrower but still meaningful confirmation than none at all.

## Limitations

Single point (structural, not a limitation of this run — see above), single
board, REPS=100, `micros()`-only timing, timed window exactly
`firmware/uno/src/main.cpp:86-90`, no LA cross-check, no claims about other
boards/phases/energy — same as the other four circuits' docs.

## Open questions / next algorithm

- Warm-up: now 5 for 5 data points (4 multi-n circuits + this one fixed
  point) showing the same-direction offset at n≥3-4. No circuit has shown a
  counterexample. This should be decided (`WARMUP_REPS`) before grover,
  the last remaining circuit.
- The settle-after-upload-failure mechanism now has 2 live confirmations
  (h_all n=2, steane_encode n=7); the settle-after-hard_timeout branch
  still has 0 after 5 circuits. Grover is the last chance in this run set
  to observe it, if a hard_timeout lands on a non-final n.
- steane_encode's near-exact model match (0.999×) is reassuring but
  expected, not a new generalization result — qpe.md's held-out CPhase-type
  test remains the more informative one for judging the model's
  extrapolation quality.
