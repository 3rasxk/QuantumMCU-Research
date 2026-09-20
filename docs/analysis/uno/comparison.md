# Uno — cross-algorithm comparison

Updated after each algorithm. Currently covers: h_all, bell_ghz, qft.

## Per-n time ratio, h_all / bell_ghz / qft

| n | h_all (µs) | bell_ghz (µs) | qft (µs) | h_all/bell_ghz | qft/h_all | qft/bell_ghz |
|---|---|---|---|---|---|---|
| 2 | 284.0 | 148.0 | 292.0 | 1.919 | 1.028 | 1.973 |
| 3 | 812.0 | 348.0 | 1932.0 | 2.333 | 2.379 | 5.552 |
| 4 | 2088.0 | 772.0 | 4696.0 | 2.705 | 2.249 | 6.083 |
| 5 | 4912.0 | 1704.0 | 11012.0 | 2.883 | 2.242 | 6.462 |
| 6 | 11468.0 | 3556.0 | 25920.0 | 3.226 | 2.260 | 7.289 |
| 7 | 26308.0 | 7556.0 | 61424.0 | 3.482 | 2.335 | 8.129 |

OBSERVED: h_all/bell_ghz grows steadily with n (1.9×→3.5×, already noted).
qft/bell_ghz grows even faster and further (2.0×→8.1×) — qft is by far the
most expensive of the three circuits at every n≥3. qft/h_all is roughly flat
from n=3 onward (2.24×–2.38×, no clear trend), after a much lower n=2 value
(1.03×) — the same n=2→3 jump flagged in qft.md as an outlier shows up here
too, as a step change in qft/h_all from 1.03× to 2.38×.

INTERPRETATION, tied to gate counts read from the timing model source (not
guessed): `pc/shared/timing_model.gate_counts()` returns `(n, 0, 0)` for
h_all, `(1, n-1, 0)` for bell_ghz, and `(n, 0, n(n-1)/2)` for qft
(`pc/shared/timing_model.py:135-140`) — qft applies **n Hadamard gates plus
n(n-1)/2 controlled-phase gates**, a quadratic gate count that neither
h_all (linear) nor bell_ghz (linear) has. Uno's fitted per-gate costs are
`k_h=29.36µs, k_cnot=4.94µs, k_cphase=13.06µs`
(`pc/shared/timing_model.py:180`) — CPhase costs sit between CNOT and H, but
qft's gate *count* grows quadratically in n while h_all's/bell_ghz's stay
linear, so qft's relative cost against both necessarily grows with n. This
is consistent with, not contradicted by, the gate-count model — though
qft.md flags that the model itself under-predicts qft specifically at low n
(n=2→3), so the *absolute* gap here is partly gate-mix (expected) and partly
this open, unexplained low-n deviation (not expected, not yet resolved).

## Scaling comparison

| | h_all | bell_ghz | qft |
|---|---|---|---|
| fitted slope, log2(median) vs n (n=2-7) | ≈1.296 bits/qubit (≈2.46×/qubit) | ≈1.131 bits/qubit (≈2.19×/qubit) | ≈1.459 bits/qubit (≈2.75×/qubit) |
| doubling ratio range (successive n) | 2.29×–2.86× | 2.09×–2.35× | 2.35×–6.62× (n2→3 outlier; 2.35×–2.43× excluding it) |
| measured/model ratio range | 1.00×–1.21× | 1.00×–1.11× | 1.00×–1.90× |
| wall n | 8 (all three) | 8 (all three) | 8 (all three) |
| wall evidence (compile_ram_pct) | 109.9% | 110.1% | 109.8% |
| last ok n compile_ram_pct | 59.9% (n=7) | 60.1% (n=7) | 59.8% (n=7) |

All three circuits hit their wall at the same n (8) with near-identical RAM
evidence (109.8–110.1%) and near-identical last-ok-n evidence
(59.8–60.1%) — expected and now confirmed a third time: `theoretical_bytes
= 2^n * 8` (`pc/phase2_sweep/uno_sweep.py`: `theoretical_bytes = (1 << n) *
8`) does not depend on which circuit is running. The wall is a
**state-vector memory limit**, not a circuit-specific one.

qft stands out as the only circuit whose measured/model ratio reaches
nearly 2× (1.897 at n=3) — h_all and bell_ghz never exceeded 1.21×. See
qft.md for the interpretation (single-point-per-circuit model fit,
quadratic CPhase-count growth concentrated at low n).

## Reliability so far

- h_all: 1 upload-stage retry (n=2, avrdude sync failure, settled+succeeded
  on attempt 2). No `hard_timeout=true`.
- bell_ghz: 0 upload retries. 1 `hard_timeout=true` (n=8, the wall/last
  point — not a live test of the port-closing fix, see bell_ghz.md).
- qft: 0 upload retries, 0 `hard_timeout=true` events at all.
- No two-consecutive-n upload exhaustion, no `ConsecutiveUploadFailuresError`,
  in any of the three runs.
- **Port-closing fix (`pre-run-uno-v2`) still has no live confirmation after
  three circuits.** The specific sequence it protects — a `hard_timeout=true`
  on a non-final n, followed by a real next `build_and_upload()` in the same
  process — has not occurred yet. Keep watching qpe.

## Warm-up effect — now observed on all three circuits

| | h_all | bell_ghz | qft |
|---|---|---|---|
| consistent across n? | n=4-7 only | n=6-7 only (n=2-5 noisy/mixed sign) | n=3-7 (tightest yet) |
| typical offset | ≈24-34µs | ≈23-31µs (where present) | ≈29-36µs |

OBSERVED: all three runs show a small positive first-10-reps offset of
similar magnitude (order 25-36µs) at mid-to-high n, though h_all's and
bell_ghz's versions are less consistent across their own n ranges than
qft's. `WARMUP_REPS` remains `0` for all three (`pc/shared/telemetry.py:489`).
INTERPRETATION: three repeats of a same-order-of-magnitude effect makes
"probably real" a fairer characterization than "plausible" now — flagged in
qft.md as a decision point for the project owner before qpe, not deferred
again silently.

## Limitations

Three circuits, one board, one run each, REPS=100, `micros()`-only timing.
No claims about ESP8266, ESP32, Phase 3, ordering effects between circuits
(each ran as a fully separate process — see `pc/shared/paths.py`'s
per-algorithm layout), or energy.

## Open questions carried forward

- **Decide `WARMUP_REPS`** before qpe — the effect has now repeated three
  times with consistent magnitude.
- qft's n=2→3 model deviation (1.897×) — check whether qpe (also uses
  CPhase gates) shows a similar low-n jump.
- hard_timeout discrepancy between h_all's and bell_ghz's n=8 (both same
  failure classification, different serial-read code path; qft's n=8 matched
  h_all's pattern, not bell_ghz's) — watch for which pattern qpe/steane_encode/
  grover follow.
- Port-closing fix still has no live confirmation — watch qpe's first
  upload closely, and specifically for any hard_timeout on a non-final n.
