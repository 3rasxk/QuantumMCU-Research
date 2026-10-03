# Uno — qft — analysis

Data: `data/raw/phase2/uno/qft/{raw.csv,memory_wall.csv,points.csv,sessions.csv}`,
commit `ee2474c` (per `sessions.csv`'s `git_commit` column). REPS=100. Charts:
`data/figures/uno/qft/{exec_time_vs_n,outcomes_vs_n,time_per_point}.png`.

Every number below is OBSERVED (read directly off the CSVs, or a git-line
citation) unless marked INTERPRETATION.

## Scaling

| n | median exec_time_us | IQR | model (expected_exec_time_us) | ratio measured/model |
|---|---|---|---|---|
| 2 | 292.0 | [292.0, 296.0] | 287.1 | 1.017 |
| 3 | 1932.0 | [1932.0, 1932.0] | 1018.2 | **1.897** |
| 4 | 4696.0 | [4692.0, 4696.0] | 3133.3 | 1.499 |
| 5 | 11012.0 | [11012.0, 11012.0] | 8878.3 | 1.240 |
| 6 | 25920.0 | [25916.0, 25920.0] | 23816.3 | 1.088 |
| 7 | 61424.0 | [61420.0, 61424.0] | 61424.0 | 1.000 |

(model values from `pc/shared/timing_model.expected_exec_time_us("uno","qft",n)`;
wall n=8 has no raw trials — see Wall section.)

OBSERVED: the ratio does **not** decrease monotonically the way h_all's and
bell_ghz's did — it *jumps* from 1.017 at n=2 to 1.897 at n=3 (the largest
deviation from the model seen across all three circuits collected so far,
h_all's/bell_ghz's ratios never exceeded 1.21), then decreases smoothly back
toward 1.0 by n=7. None of these cross the 2× flag threshold (highest is
1.897), so none are formally flagged, but 1.897 is close enough to the line
that it's called out explicitly here rather than left in a table.

n=3's median (1932.0µs) is not noisy — its IQR is degenerate
(`[1932.0, 1932.0]`, i.e. ≥50 of the 100 reps landed on the exact same
value) — so this is a real, stable measurement, not a fluke rep or two.

INTERPRETATION: `pc/shared/timing_model.py:180`'s three per-gate constants
(`k_h, k_cnot, k_cphase`) were fit from exactly **one data point per
circuit** — each circuit's own single highest-n measurement
(`pc/shared/timing_model.py:165-171`: "fit จากค่า median ที่วัดจริง...ที่ n
สูงสุดของแต่ละบอร์ด"), a 3-equations/3-unknowns system solved at n=7. That
guarantees the model is *exact* at n=7 by construction (ratio=1.000 here,
same as h_all/bell_ghz), but carries no information about whether the
model's gate-count formula actually holds at lower n. qft's gate count is
`(n, 0, n(n-1)/2)` (`pc/shared/timing_model.py:139-140`) — between n=2 and
n=3 the CPhase count *triples* (1→3) while `n_states` only doubles and the H
count only grows by one — the steepest per-step change in gate-type mix of
any transition in this circuit's whole n range. If `k_cphase`'s real,
physical per-amplitude cost isn't perfectly constant across n (e.g. if
there's a fixed per-call or per-loop-setup cost the linear model doesn't
capture), n=2→3 is exactly where that would show up most. This is a
plausible explanation for the gap, not a confirmed one — no independent
measurement of `k_cphase` in isolation exists in this repository to check it
against.

**Doubling ratio (successive n, measured):** n2→3: 6.616, n3→4: 2.431,
n4→5: 2.345, n5→6: 2.354, n6→7: 2.370 — the n2→3 ratio is a clear outlier
(next-highest step is 2.431); n3 onward is close to flat around 2.3-2.4×.

**Fitted slope of log2(median) vs n** (least-squares via `numpy.polyfit`,
n=2..7, all 6 points): slope ≈ 1.459 bits/qubit (≈2.75× per qubit) — the
steepest of the three circuits so far (h_all ≈2.46×, bell_ghz ≈2.19×),
driven mostly by the n=2→3 jump; a slope fit over just n=3..7 (5 points,
computed for this comparison only, not used elsewhere) gives ≈1.245
bits/qubit (≈2.37×/qubit) — much closer to bell_ghz's/h_all's range and
consistent with the model's own diminishing-ratio shape at higher n. The
headline slope above still uses all 6 points (n=2..7), per the same method
as h_all.md/bell_ghz.md — not silently dropping n=2.

## Variability

| n | rel. IQR (IQR/median) | min | max | distinct values (of 100) |
|---|---|---|---|---|
| 2 | 1.37% | 288.0 | 300.0 | 4 |
| 3 | 0.00% | 1916.0 | 1988.0 | 9 |
| 4 | 0.09% | 4680.0 | 5024.0 | 8 |
| 5 | 0.00% | 11004.0 | 11348.0 | 5 |
| 6 | 0.02% | 25916.0 | 26260.0 | 4 |
| 7 | 0.01% | 61420.0 | 61772.0 | 5 |

OBSERVED: same pattern as h_all/bell_ghz — tight distributions, degenerate
or near-zero IQR at several n. Uno's verified 4µs `micros()` tick
(`analysis/la_crosscheck.py:67-74`, see h_all.md) is 4/292 ≈ 1.4% of n=2's
median, matching the observed 1.37% rel. IQR almost exactly — same
quantization-noise interpretation, still unverified without a Logic
Analyzer capture.

**Warm-up effect (first 10 reps vs remaining 90) — this run makes the case
stronger:**

| n | first-10 mean | rest-90 mean | diff |
|---|---|---|---|
| 2 | 293.2 | 293.1 | +0.1 |
| 3 | 1966.8 | 1930.7 | +36.1 |
| 4 | 4723.6 | 4694.8 | +28.8 |
| 5 | 11045.6 | 11011.7 | +33.9 |
| 6 | 25953.2 | 25919.1 | +34.1 |
| 7 | 61456.8 | 61423.7 | +33.1 |

OBSERVED: unlike bell_ghz's inconsistent n=2-5 (h_all.md, bell_ghz.md), qft
shows a **remarkably consistent** +29 to +36µs offset at every n from 3
through 7 (n=2 is the only exception, near zero like h_all's and bell_ghz's
own n=2/3 rows were). `WARMUP_REPS` is still `0`
(`pc/shared/telemetry.py:489`), nothing excluded from any table above.

INTERPRETATION: this is the third circuit in a row to show a same-order-of-
magnitude (≈25-36µs) positive first-reps offset at mid-to-high n, and this
run's version of it is the tightest/most consistent seen yet. The open
question from h_all.md/bell_ghz.md ("does it repeat?") is answered **yes**
for n≥3-4 specifically — still not acted on (not raising `WARMUP_REPS`
without a decision recorded, per standing practice), but the evidence for a
genuine small warm-up transient is now stronger than "plausible" and
closer to "probable." Recommend the project owner decide explicitly on
`WARMUP_REPS` before the remaining three circuits, rather than deferring
again.

No bimodality observed.

## The wall

**n=8.** Evidence: `compile_ram_used_bytes=2248` / `TOTAL_SRAM_BYTES=2048`
= **109.8%** — essentially identical to h_all's 109.9% and bell_ghz's
110.1% (all three circuits' n=8 costs the same 2048 theoretical bytes,
independent of gate mix — see comparison.md). Uno linker exited 0 (L2
quirk). Point run once per standing decision 2: upload succeeded, board did
not print `DONE` within the 90s budget. `failure_message="reset_count=0"`,
**no** `hard_timeout=true` — same pattern as h_all's n=8 (read loop's own
deadline check exited normally), not bell_ghz's (which needed the hard
`signal.alarm`). Final status forced to `build_overflow`.

**Last ok n: 7, at 59.8% compile RAM** — again essentially identical to
h_all (59.9%) and bell_ghz (60.1%). Same reading as the other two: this
circuit does not run to completion on this board at n=8 under these
conditions, nothing more.

## Overhead and reliability

**Reflash time per point**, all 1 attempt each
(`data/figures/uno/qft/time_per_point.png`):

| n | compile_s | upload_s | total |
|---|---|---|---|
| 2 | 14.5 | 4.0 | 18.5 |
| 3 | 3.3 | 3.4 | 6.7 |
| 4 | 3.4 | 4.1 | 7.5 |
| 5 | 2.8 | 3.5 | 6.3 |
| 6 | 3.4 | 3.8 | 7.2 |
| 7 | 3.2 | 3.5 | 6.7 |
| 8 | 3.0 | 3.4 | 6.4 |

n=2's compile time (14.5s) is much higher than every other point in this
run — this is the first build of a fresh `uno_sweep.py --circuits qft`
process (cold PlatformIO dependency-tracking cache for this circuit's
`N_QUBITS=2` object files). Not a concern, reflected here for completeness
only.

**Zero upload retries, zero hard_timeout events, in this entire run** — every
`points.csv` row is `attempt_index=0`. The port-closing fix from
`pre-run-uno-v2` **still has no live confirmation after three circuits**:
h_all had one upload-sync retry but at n=2 (not after a hard_timeout);
bell_ghz had one hard_timeout but it landed on the wall/last point (no next
upload to observe); qft had neither a retry nor a hard_timeout at all. The
fix remains implemented and unit-tested (`pc/shared/uno_upload_retry_test.py`)
but not yet exercised by real hardware in the specific "hard_timeout on a
non-final n, then successfully build the next one" sequence it was written
for.

## Limitations

Single run, single board, REPS=100, `micros()`-only timing, timed window
exactly `firmware/uno/src/main.cpp:86-90`, no LA cross-check, no claims
about other boards/phases/energy — same as h_all.md/bell_ghz.md.

## Open questions / next algorithm

- The n=2→3 gap (1.897×) is the most notable finding of this run — worth
  checking whether qpe (which also uses CPhase gates,
  `pc/shared/timing_model.py:152-155`) shows a similar low-n jump, which
  would support the k_cphase-calibration interpretation above, or whether
  it's qft-specific.
- Warm-up effect: now observed consistently enough (3 circuits, tightest yet
  on qft) that it should be a decision point before qpe, not another
  "carried forward" note.
- Port-closing fix: still zero real hard_timeout-then-next-upload sequences
  observed. Continue watching qpe closely.
