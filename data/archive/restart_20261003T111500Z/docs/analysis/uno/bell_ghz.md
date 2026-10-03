# Uno — bell_ghz — analysis

Data: `data/raw/phase2/uno/bell_ghz/{raw.csv,memory_wall.csv,points.csv,sessions.csv}`,
commit `6d00ce8` (per `sessions.csv`'s `git_commit` column). REPS=100. Charts:
`data/figures/uno/bell_ghz/{exec_time_vs_n,outcomes_vs_n,time_per_point}.png`.

Every number below is OBSERVED (read directly off the CSVs, or a git-line
citation) unless marked INTERPRETATION.

## Scaling

| n | median exec_time_us | IQR | model (expected_exec_time_us) | ratio measured/model |
|---|---|---|---|---|
| 2 | 148.0 | [148.0, 152.0] | 137.2 | 1.079 |
| 3 | 348.0 | [344.0, 352.0] | 313.9 | 1.109 |
| 4 | 772.0 | [771.0, 772.0] | 706.9 | 1.092 |
| 5 | 1704.0 | [1700.0, 1704.0] | 1571.9 | 1.084 |
| 6 | 3556.0 | [3552.0, 3560.0] | 3459.9 | 1.028 |
| 7 | 7556.0 | [7552.0, 7560.0] | 7552.0 | 1.001 |

(model values from `pc/shared/timing_model.expected_exec_time_us("uno","bell_ghz",n)`;
wall n=8 has no raw trials — see Wall section.)

OBSERVED: ratio is flatter across n than h_all's (1.079–1.109, dropping to
1.001 only at n=7) rather than h_all's smooth monotonic decrease from 1.209.
No ratio exceeds 2x — none of these are flagged.

**Doubling ratio (successive n, measured):** n2→3: 2.351, n3→4: 2.218,
n4→5: 2.207, n5→6: 2.087, n6→7: 2.126 — closer to 2.0× throughout than
h_all's (2.86→2.29), and less monotonic (n5→6 dips below n6→7).

**Fitted slope of log2(median) vs n** (least-squares via `numpy.polyfit`,
n=2..7, all 6 points): slope ≈ 1.131 bits/qubit (≈2.19× per qubit) —
closer to the naive "roughly doubling per qubit" statevector expectation
than h_all's 1.296 bits/qubit, and this is explained by gate count, not
board behaviour: see comparison.md.

## Variability

| n | rel. IQR (IQR/median) | min | max | distinct values (of 100) |
|---|---|---|---|---|
| 2 | 2.70% | 148.0 | 164.0 | 5 |
| 3 | 2.30% | 344.0 | 356.0 | 4 |
| 4 | 0.13% | 764.0 | 776.0 | 4 |
| 5 | 0.23% | 1696.0 | 1708.0 | 4 |
| 6 | 0.22% | 3552.0 | 3736.0 | 7 |
| 7 | 0.11% | 7544.0 | 7864.0 | 6 |

OBSERVED: same pattern as h_all — tight distributions, rel. IQR highest at
low n (2.70% at n=2) and falling by an order of magnitude by n=4. Uno's
4µs `micros()` tick (verified: `analysis/la_crosscheck.py:67-74`, see
h_all.md) is 4/148 ≈ 2.7% of n=2's median — close to the observed rel. IQR
there, same quantization-noise interpretation as h_all (unverified without
a Logic Analyzer capture).

**Warm-up effect (first 10 reps vs remaining 90):**

| n | first-10 mean | rest-90 mean | diff |
|---|---|---|---|
| 2 | 152.4 | 151.4 | +1.0 |
| 3 | 347.2 | 348.8 | −1.6 |
| 4 | 769.6 | 771.9 | −2.3 |
| 5 | 1703.2 | 1701.9 | +1.3 |
| 6 | 3586.4 | 3555.5 | +30.9 |
| 7 | 7579.2 | 7556.3 | +22.9 |

OBSERVED: unlike h_all, no consistent warm-up offset at low/mid n (signs
flip, magnitudes are within the noise floor at n=2-5) — only n=6 and n=7
show a positive offset of similar size to h_all's (≈23–31µs). `WARMUP_REPS`
is `0` (`pc/shared/telemetry.py:489`), nothing excluded. INTERPRETATION:
the n=6/n=7 offset here is consistent with the same effect flagged in
h_all.md, but bell_ghz's own n=2-5 rows argue against it being a strong,
reliable effect at low n specifically — treated as the same open question,
not a new one.

## The wall

**n=8.** Evidence: `compile_ram_used_bytes=2254` / `TOTAL_SRAM_BYTES=2048`
= **110.1%**. Uno linker exited 0 (L2 quirk, same as h_all). Point was run
once per standing decision 2: upload succeeded, board did not print `DONE`
within the 90s budget. Unlike h_all's n=8, this one's `failure_message` is
`"hard_timeout=true,reset_count=0"` — the hard `signal.alarm` interrupt
(`pc/phase2_sweep/uno_sweep.py:266-267,289-290`) actually fired, meaning
the blocking `readline()` call did not return via the loop's own deadline
check the way h_all's n=8 did. `device_exec_s=100.017s`, matching the
alarm's `timeout_s + 10` deadline (`uno_sweep.py:267`) almost exactly (90 +
10 = 100). Final status forced to `build_overflow`.

**Last ok n: 7, at 60.1% compile RAM.** Same integer-n gap as h_all (n=7→8
doubles `theoretical_bytes`, no intermediate point exists).

Same reading as h_all's wall: this circuit does not run to completion on
this board at n=8 under these conditions — nothing more.

## Overhead and reliability — the first real test of the port-closing fix

**Reflash time per point**, all 1 attempt each
(`data/figures/uno/bell_ghz/time_per_point.png`):

| n | compile_s | upload_s | total |
|---|---|---|---|
| 2 | 3.8 | 3.5 | 7.4 |
| 3 | 2.8 | 3.2 | 6.0 |
| 4 | 2.9 | 3.2 | 6.1 |
| 5 | 2.9 | 3.3 | 6.2 |
| 6 | 2.9 | 3.2 | 6.1 |
| 7 | 7.6 | 3.9 | 11.6 |
| 8 | 3.1 | 3.4 | 6.4 |

No upload retries occurred anywhere in this run (every `retry_count=0`).

**bell_ghz's n=8 is this project's first hard_timeout=true event since the
2026-09-20 port-closing/settle fix landed — but it is NOT yet a live test
of the fix working**, for a specific, disclosed reason: n=8 is both the
wall (stops climbing) *and* the last n in this circuit's planned range, so
`wall_found=True` broke the n-loop immediately after this point and the
process exited without ever calling `build_and_upload()` again
(`pc/phase2_sweep/uno_sweep.py`: the `if wall_found: break` at the very end
of the per-n loop). `pending_settle` was correctly set
(`uno_sweep.py:720-722` in the pre-migration numbering — see
`_sweep_body`'s `if "hard_timeout=true" in note:` branch) but never
consumed, because there was no next `build_and_upload()` call within this
process to protect. This was already flagged in the h_all/bell_ghz-cycle
report and remains true: **the fix's first genuine live test is the first
upload of qft**, since qft starts as a fresh process with no `pending_settle`
state carried over (it never carries across process boundaries, only across
n within one process — see `uno_sweep.py`'s module docstring) and its first
point (n=2) is not itself a wall, so a hard_timeout mid-circuit (if qft hits
one) would have a real next upload to observe.

## Limitations

Same as h_all.md: single run, single board, REPS=100, `micros()`-only
timing, timed window is exactly `firmware/uno/src/main.cpp:86-90`, no LA
cross-check, no claims about other boards/phases/energy.

## Open questions / next algorithm

- Confirmed carried over from h_all.md: does the warm-up offset repeat at
  qft's higher-n points?
- The h_all n=8 vs bell_ghz n=8 hard_timeout discrepancy (see h_all.md) is
  unresolved — watch qft/qpe/steane_encode/grover's own wall points for a
  pattern.
- The port-closing fix's live test is still pending — watch qft's first
  build_and_upload closely and report explicitly whether any hard_timeout
  occurs mid-circuit (not at the final n).
