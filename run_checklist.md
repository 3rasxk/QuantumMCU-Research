# REPS=100 Run Checklist

> **Restart 2026-10-03:** scope is `h_all`, `bell_ghz`, `qft`, `grover` only
> (`qpe`/`steane_encode` removed from the plan; `pc/run.py` refuses them) and all
> earlier hardware data was deleted on 2026-10-04 (recoverable from git history, commit
> `af40643`); this file keeps no measured values from it, only estimates and method.
> Current plan and predictions: `docs/design/experiment_plan.md`.

Operator checklist for the actual hardware run. Read this, not `run_log.md`,
while running — `run_log.md` is where you write down what happened *after*.

`pc/run.py` (see `README.md`'s "Quick start", `docs/run/<board>.md`) wraps
the per-command preflight steps this checklist walks through by hand
(port, sleep prevention, resume state) for the common case of one
algorithm/board/phase at a time. This checklist remains the full manual
reference, including session planning. The timing-reference (counter) workflow is in
`docs/design/readiness.md` and `docs/design/wiring.md`.

**2026-09-21: the owner may run anything, anytime, via `pc/run.py`, without
waiting for approval** — the strict "one algorithm at a time, stop and wait
for go" workflow below now applies specifically to tasks run through Claude
Code, not the owner's own direct use of the runner. A dirty git tree is now
a warning for the owner's own runs (`pc/run.py`), not a refusal — the exact
commit/dirty flag is still recorded automatically in the session's
environment JSON either way. `--fresh` also changed: it now archives
existing data to `data/archive/` (moved, not deleted, with a manifest)
instead of the in-place rename described below, and defaults to each
circuit's own minimum *meaningful* `n` rather than always 2 — see
`README.md`'s "Fresh runs and the archive" and `run_log.md`'s 2026-09-21
entry for the full per-circuit table and citations.

**Resume is on by default in every script below.** If a session dies (USB
drop, laptop sleep, you need to stop for the night), the fix is almost always:
**run the exact same command again.** It will print a resume summary showing
what it's skipping, then continue from where it left off. Do not delete or
edit the CSVs by hand to "help" — the scripts read them to decide what's done.

If a resume summary looks wrong (skips something it shouldn't, or the
remaining-point count doesn't match what you expect), **stop and look at
that `(board, circuit)`'s own `memory_wall.csv` / `session_log.csv` file
(`data/raw/phase<N>/<board>/<circuit>/{no_ref,with_ref}/`, see
`pc/shared/paths.py`) before re-running** — don't force through it with
`--fresh` on a hunch, that archives real data.

**no_ref vs with_ref (renamed 2026-10-04).** Every path under `data/raw/` and
`data/figures/` in this checklist has an implicit `no_ref/` or `with_ref/` bucket:
`no_ref/` for commands that omit the counter (`--ref none`, not valid for official runs),
`with_ref/` for `--ref counter --counter-port PORT` (official runs REQUIRE it). Resume
never crosses this boundary. **Never mix the two buckets in one analysis.** No data of
either bucket exists in the restarted dataset yet.

---

## 0. Before you start

- [ ] `pio` on PATH (`which pio`), or `PIO_PATH` env var set
- [ ] `.venv/bin/python` has `qiskit`, `qiskit_aer`, `pyserial`, `numpy` (Phase 3 needs
      the first two; all sweeps need pyserial)
- [ ] Note down each board's port now, ports can renumerate mid-run:
  - Uno: `/dev/cu.usbmodem*`
  - ESP8266 / ESP32: `/dev/cu.usbserial*`, `/dev/cu.wchusbserial*`, or `/dev/cu.SLAB_USBtoUART*`
- [ ] `data/raw/phase2/` and `data/raw/phase3/` — check what's already there before
      session A. If this is truly the first run, they should be empty or absent.

---

## Session order and why

1. **Cheap circuits, all 3 boards** — `h_all bell_ghz qft`.
   Fast (minutes), banks 5 of 6 circuits everywhere before touching the
   expensive one.
2. **`grover`, one board per session** — kept separate because ESP8266's
   grover alone is longer than everything else in step 1 combined across all
   3 boards.
3. **Phase 3, split by circuit** — same reasoning; the cheap circuits take
   seconds, `grover` at n=10 takes over an hour *per board* on the PC side
   alone, uncached, on purpose (see `pc/phase3_offload/sweep.py` header).

Do not run two sessions against the same board/file pair concurrently —
resume logic assumes one writer at a time.

---

## Run day checklist

One linear pass through everything below. The detailed sections further down
(Session A/B/C) have the actual commands and expected durations — this is
the order to hit them in, plus what to check between each one.

**Prerequisites (before touching any board):**
- [ ] `git status` clean, or at least nothing uncommitted you'd mind losing —
      `pc/shared/telemetry.py`'s environment metadata records the commit hash
      and dirty flag per session, so a dirty tree at data-collection time is
      captured either way, but a clean one is one less thing to explain later
- [ ] Host sleep prevention on: macOS, run the whole day's commands under
      `caffeinate -s -- <command>`, or start `caffeinate -s` in its own
      terminal and leave it running for the day. Confirm with
      `pmset -g assertions | grep PreventUserIdleSystemSleep` before
      starting Session B (session lengths there make a mid-run sleep
      expensive to redo) — this is the same check
      `tel.check_sleep_prevention()` makes automatically per session, but
      checking it yourself *before* a multi-hour session starts is cheaper
      than discovering it failed in the metadata JSON afterward
- [ ] Each board's port identified and written down (ports can renumerate
      when boards are re-plugged or after a reflash) — see § 0 above
- [ ] Official run: `docs/design/readiness.md` ticked (counter self-test, calibration, wiring checked) and the counter
      port written down next to the target port. Every command below then gets
      `--ref counter --counter-port <counter port>` (sweep scripts take the same flags).
- [ ] `data/raw/phase2/` and `data/raw/phase3/` checked per § 0 — confirm
      resume state matches what you expect (empty for a true first run,
      or existing files if this is a continuation)

**Session order** (rationale in "Session order and why" above, and see
"Grover run order" below Session B for why boards run in this specific
sequence within step 2):
1. [ ] Session A — cheap circuits, all 3 boards (any order within this step)
2. [ ] Session B — `grover`, one board at a time, **in this order: Uno,
       then ESP32, then ESP8266** (cheapest full board first, most
       expensive last — see rationale below)
3. [ ] Session C — Phase 3, split by circuit, same board order logic applies

**After each session:**
- [ ] Check the printed resume/session summary — point count matches what
      that session's expected count says (Session A/B/C sections below give
      the exact numbers per command)
- [ ] Spot-check the terminal-record file (`memory_wall.csv` or
      `session_log.csv`, under that `(board, circuit)`'s own directory) for
      the board just run — new rows present, no
      unexpected `build_or_upload_fail`/`malloc_failed` at an n lower than
      the known wall (would indicate a regression, not just "reached the
      wall as expected")
- [ ] If anything looks wrong, stop here and investigate before starting the
      next session — don't chain sessions blindly on a bad prior result

**Stop conditions (stop and investigate, don't push through):**
- A resume summary skips more or fewer points than you expect for that
  exact command
- A point fails with `build_or_upload_fail` at an n where a *previous*
  session already succeeded (regression, not a new wall)
- The host's sleep-prevention check reports `prevented: false` partway
  through a long Session B run (check the environment metadata JSON for
  that session — if sleep occurred, that session's timing is suspect and
  should be treated as unreliable, not just slow)
- Any point's `failure_type` is something other than the expected set for
  its circumstance (e.g. `crc` or `sim` appearing during Phase 2, which
  only Phase 3 should ever produce)
- You are not sure *why* something happened. Guessing and continuing risks
  hours of data that can't be told apart from good data later — stopping to
  check now is cheap by comparison

---

## Session A — cheap circuits, all boards

Run these three back to back (or in any order — independent files):

```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --n-max 8
```
**ESTIMATE only** (no data collected in the restarted dataset yet): run
`python pc/run.py --plan --board uno --phase 2` for the per-point table. Each row is
relabelled MEASURED automatically once this board/phase has ok points in the new run.


```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --n-max 13
```
**Expected: ~32 min** (49 points — device ~7.8 min + reflash ~24.5 min at 30s/point).

```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --n-max 14
```
**Expected: ~27 min** (53 points — device <1 min + reflash ~26.5 min at 30s/point.
ESP32 is so fast per-trial that reflashing is essentially all of this session).

**If one dies:** rerun the identical command. Check the "resume summary" line
count at the top — it should show most points already done.

---

## Session B — `grover`, one board at a time

Run these as **three separate sessions**, not one after another in a single
sitting unless you have the time budgeted — ESP8266's alone is ~4 hours.

### Grover run order — why Uno, then ESP32, then ESP8266

`grover` is ~83% of the whole run's estimated time, so its internal ordering
matters more than any other circuit's. Two ordering questions, both already
answered by the commands below, spelled out here so the reasoning survives
if these numbers are ever re-measured and the order needs re-checking:

1. **Within one board's session, shortest points already run first** — the
   sweep loop walks `n` ascending (`n_values_for_sweep`), and `grover`'s
   per-point cost grows roughly ~7-10x per step in `n` (see the per-n
   durations in `python pc/run.py --plan`). This means an interruption at *any*
   point in a board's grover session has already banked every cheaper point
   for that board — the only point ever at risk of being lost to an
   interruption is the single most expensive one in progress, never a
   cheap one waiting behind it. No change needed here; this falls out of
   the existing n-ascending sweep order for free.

2. **Across the three boards' sessions, run cheapest-total-board first:
   Uno → ESP32 → ESP8266 (ESTIMATE totals: `python pc/run.py --plan`).** This is the order the
   commands are already listed in below — the reasoning: if the run gets
   cut short after Session B starts (schedule, hardware issue, anything),
   this order guarantees the *maximum number of complete board datasets*
   for the *minimum elapsed time*. Two boards' full grover scaling curves
   (Uno + ESP32) are a genuinely analyzable result on their
   own — a cross-board comparison missing only the slowest board — whereas
   spending that same 2.7h budget starting with ESP8266 would leave it
   *still incomplete* (2.7h in, ESP8266 alone needs 4.2h) and both other
   boards untouched: strictly worse under any stopping point.

**If cross-board comparison at *matched* n matters more than any board's
*complete* curve** (e.g. you want an early n=2..8 comparison across all
three boards specifically, and can live with Uno/ESP32 being "done" only up
to whatever n ESP8266 has reached so far): run single-n slices interleaved
across boards instead — `--n-start K --n-max K` for the same `K` on all
three boards before moving to `K+1`. This costs no extra reflashes (a
reflash already happens once per `(circuit, n)` regardless of how wide a
range `--n-max` spans in one invocation — see "Reflash cost" below), it's
purely a different sequencing of the same commands, and resume handles the
resulting partial per-board state exactly like any other interruption. This
alternative is **not** the default recommendation — most analysis on this
kind of scaling data benefits more from complete per-board curves than
from early matched-n snapshots — but it's the right call if the priority
for this specific run is early cross-board comparison over per-board
completeness. Not implemented as a script option; if chosen, run the
commands below with `--n-max` set to a single value at a time, in board
round-robin, by hand.

```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
    --circuits grover --n-start 2 --n-max 8
```
**Expected: ~43 min** (6 points run, 1 skipped — device ~41.3 min + reflash
~2 min. n=8 is skipped as compute-infeasible, that's correct, not a bug).

```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 14
```
**Expected: ~2.0 hours** (9 points run, 4 skipped — device ~1.9h + reflash
~4.5 min; reflash is negligible here, device time dominates). The single
most expensive point is n=10 at ~1.7h — do not interrupt the board mid-point
unless you have to; if you do, the resume will redo that whole point (up to
another 1.7h), not top it up.

```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 13
```
**Expected: ~4.2 hours** (8 points run, 4 skipped — device ~4.1h + reflash
~4 min, reflash negligible). This is the longest single session in the whole
run. n=9 alone is ~3.6h; n=10+ are skipped as infeasible (n=10 would be
1.3 *days*). **Plan this one for overnight or a day you're not touching the
Uno/ESP32 setup** (different USB ports, shouldn't conflict, but don't tempt
fate).

**If it dies partway through n=9 (the 3.6h point):** rerunning the same
command redoes that entire point from scratch — the resume logic discards
partial trials rather than mixing sessions (see `run_log.md`, 2026-09-19
entry, for why). There's no way around re-paying that cost; budget for it
when deciding when to start this session.

**If it dies on an earlier, cheap point:** resume picks up almost instantly,
no real cost.

---

## Session C — Phase 3 (offload), split by circuit

The offload server runs *on this machine* and needs the venv active
(`qiskit_aer`). Same board/port notes as above, plus `--bauds` (defaults to
just 115200 if omitted — pass explicitly if you want to test multiple).

**Phase 3 reflashes per data point too** — `pc/phase3_offload/sweep.py` calls
`build_and_upload()` once per `(circuit, n, baud)` before the 100-rep
exchange, same as Phase 2. This is **not** incidental: `N_QUBITS`/
`CIRCUIT_ID`/`BAUD_RATE` are `#define`d build flags in
`firmware/*/src_offload/main_offload.cpp`, baked into the request frame at
compile time — the offload protocol's request frame *does* carry
`n_qubits`/`circuit_type` per-request already (`firmware/common/protocol.hpp`),
and the PC side (`simulate_and_sample()`) already builds a fresh circuit from
whatever it receives, so the PC side could sweep many points over one
connection — but the current MCU firmware has no runtime mechanism (no serial
command, no config) to change what it sends; each flashed image asks the same
question 100 times. Fixing that would cut Phase 3's reflash count from
"per point" to "per board" but is a firmware/protocol change, out of scope
here — noted for later.

**Cheap circuits, one command per board:**

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --n-max 8
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --n-max 13
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft --n-start 2 --n-max 14
```
**Expected: ~12 min (Uno), ~29 min (ESP8266), ~31 min (ESP32)** — PC-side
simulation cost is a few minutes each; reflash (29/49/53 points × 20–30s) is
most of it, same pattern as Session A.

**`grover`, one board per session, capped at n=10:**

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
    --circuits grover --n-start 2 --n-max 10
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
```
**Expected: ~1.5 hours each on all three boards** — this is the **full
session (n=2 through n=10, 9 points, none skipped)**, not just the n=10
point. n=10 alone is ~1.1h of that (uncached Aer simulation, ~40s × 100
reps) and is the same cost on every board since it's PC-side, not
board-side; n=9 adds another ~15 min; reflash adds ~3–4.5 min on top. n=12
is automatically skipped (`skipped_sim_cost_infeasible`, ~20h/board — not
attempted without `--force-infeasible`, not recommended here).

**If it dies:** same story — rerun the identical command, resume picks up
per `(circuit, n, baud)`. Unlike Phase 2, a `session_incomplete` result here
is **not** auto-inferred as a wall for higher n (baud instability, not a
compute limit, can cause it) — so a resume will still *attempt* points after
one that failed. That's intentional; re-read the header of
`pc/phase3_offload/sweep.py` if you want the reasoning.

---

## Total budget

Generated by `python pc/run.py --plan` (full output in `docs/design/plan_output.txt`), never
written by hand here. Every number is an **ESTIMATE** (model in
`pc/shared/timing_model.py`: prior-fit gate costs, compile/upload/boot estimates with
stated bases). Device time and overhead are separate columns in that output. As soon
as the new run has ok points for a board and phase, `pc/run.py` shows those rows as
**MEASURED** (from that board's own `points.csv`) and re-estimates the rest from them.

### Reflash cost

`REFLASH_COST_S` and the `COMPILE_S_ESTIMATE` / `UPLOAD_S_ESTIMATE` /
`DEVICE_OVERHEAD_S_ESTIMATE` tables in `pc/shared/timing_model.py` are reasoned
estimates (bases in the comments there): compile time from compile-only runs without a
board, upload time from image size / upload baud. They are replaced by measured
medians in the ETA output once the new run has data. Before trusting the ESP portions
of any plan total, time one real build+upload per ESP board in the first official run
and compare with `analysis/timing_report.py` (it only reports, never edits).

---

## Telemetry schema (frozen at SCHEMA_VERSION 2, tag `pre-run-schema-v2`)

`pc/shared/telemetry.py` defines the schema for `sessions.csv`, `points.csv`,
and each session's `env/<session_id>.json` — written under
`data/raw/phase<N>/<board>/<circuit>/`, one directory per `(phase, board,
circuit)` since `pre-run-uno-v4`/`v5` (`pc/shared/paths.py`), not a single
shared `data/raw/telemetry/` directory as in an earlier layout.
**This schema is frozen as of the `pre-run-schema-v2` tag, before any real
hardware data is collected**, so every row of the REPS=100 run shares one
schema — do not add, remove, rename, or repurpose a column without bumping
`SCHEMA_VERSION` in `pc/shared/telemetry.py` first.

*v2 (this version) added the `build_timeout` and `watchdog_suspected`
`failure_type` values and changed which statuses count as a Memory Wall; the
column names did not change, which is exactly why the guard below also checks
the `schema_version` **value**, not just the header.*

**Enforcement, not just convention:** `SCHEMA_VERSION` is written as the
first column of both CSVs and as a field in every environment JSON. If a
sweep script is run against an existing `sessions.csv`/`points.csv` whose
header doesn't match the current field list exactly (including because
`SCHEMA_VERSION` changed), `telemetry._ensure_csv` raises
`SchemaMismatchError` and refuses to append — it never silently mixes rows
from two schema versions in one file. It also reads the `schema_version`
**value** out of the first data row and refuses if it differs from the
running code's, because a version bump that only changes what values *mean*
(v1 → v2 did exactly that) leaves the header identical and would otherwise
go unnoticed. Fix: archive the old file (see
`pc/shared/resume.archive_existing`, or move it aside by hand, or use
`--fresh`) and start a new one for that `(board, circuit)` under the new
schema, or roll back the code.

**`data/raw/phase1/` is not affected by the bump.** Those two files
(`infidelity_tvd.csv`, `phase1_metadata.csv`) are written by
`analysis/phase1_compare.py`, not by `telemetry.py`; they have no
`schema_version` column and never did, so v1 and v2 code read and write them
identically. They were verified byte-identical (sha256) across every test and
dry run in this work.

**`sessions.csv` columns:** `schema_version`, `session_id`, `phase`, `board`,
`circuits`, `start_utc`, `end_utc`, `wall_clock_s`, `device_time_s_sum`,
`reflash_time_s_sum`, `n_points_ok`, `n_points_failed`,
`n_points_skipped_resume`, `n_points_skipped_known_wall`,
`n_points_skipped_compute_infeasible`, `n_points_skipped_sim_cost_infeasible`,
`time_lost_to_interruption_s`, `estimated_total_s`, `actual_total_s`,
`ratio_actual_over_estimated`, `resumed_from_previous`, `env_json_path`,
`git_commit`, `notes`.

**`points.csv` columns:** `schema_version`, `session_id`, `phase`, `board`,
`circuit`, `n`, `baud`, `attempt_index`, `start_utc`, `end_utc`, `wall_s`,
`build_compile_s`, `upload_s`, `boot_wait_s`, `device_exec_s` (Phase 2),
`pc_sim_s_total`, `pc_sim_s_median`, `serial_transfer_s_total`,
`avg_round_trip_latency_s`, `crc_error_count`, `bytes_transferred` (Phase 3
only — blank on Phase 2 rows), `retry_count`, `timeout_hit`, `failure_type`,
`failure_message`, `status`.

**`status` allowed values** (`telemetry.STATUS_TYPES`) — a point-level
outcome, one row per attempt:
- `ok` — completed successfully
- `failed` — terminal failure for this attempt (see `failure_type` for why;
  also covers Phase 3's `session_incomplete` — no `DONE` or zero rows
  captured within budget — which points.csv folds into `failed` rather than
  keeping as a separate value, since `session_incomplete` is really "why it
  failed," recorded instead in `failure_type`/`failure_message` and in the
  richer `session_log.csv` row for that point)
- `retrying` — attempt 0 of a point that will be retried once (Phase 2's
  retry-once-on-transient-failure policy, budget ≤ 600s only); not a
  terminal status, only ever seen on a non-final attempt row
- `skipped_resume` — this point already had a terminal record from a
  previous session; this session's row exists only to record that this
  session, too, chose to skip it
- `skipped_known_wall` — this point's `n` is above a wall already found for
  this circuit in a previous session (Phase 2 only — Phase 3 has no
  known-wall inference, see "Session order and why")
- `skipped_compute_infeasible` — Phase 2 only: expected device time exceeds
  the timeout ceiling, never attempted
- `skipped_sim_cost_infeasible` — Phase 3 only: expected PC-side (uncached
  Aer) simulation time exceeds the ceiling, never attempted

Before this freeze, all four `skipped_*` reasons collapsed into a single
generic `"skipped"` value, and `skipped_resume`/`skipped_known_wall` points
had no `points.csv` row at all — both are what this freeze fixes.
`analysis/timing_report.py`'s `report_skip_reasons()` prints the per-reason
totals across a run; none of the four contribute to its actual-time totals
(their timing fields are always blank).

**`failure_type` allowed values** (`telemetry.FAILURE_TYPES`): `none`,
`build`, `build_timeout`, `malloc`, `hang`, `watchdog_suspected`, `serial`,
`crc`, `sim`.

- `build` — `pio run` returned a real error (linker, syntax, missing flag).
  Deterministic, never retried.
- `build_timeout` *(v2)* — `pio run` exceeded `--build-timeout`
  (`timing_model.BUILD_TIMEOUT_S`, default **300 s**). A host/toolchain
  problem, not a board problem: it **is** retried once under the same
  ≤ 600 s budget rule as a transient hang, and it is **never** a wall.
- `hang` — no `DONE` within the point's timeout budget, on a point whose
  estimated per-rep time is below the board's watchdog threshold.
- `watchdog_suspected` *(v2)* — same silence, but on a point whose estimated
  per-rep time exceeds `timing_model.WDT_PER_REP_THRESHOLD_S` for that board
  (ESP8266 6 s, ESP32 5 s, Uno none — **assumptions, UNVERIFIED against
  hardware**). Recorded separately precisely so it is never published as a
  Memory Wall.

### A Memory Wall may only be recorded on positive evidence

This rule exists because the most expensive points in the run are also the
ones most likely to be mis-attributed (see `docs/preflight_report.md` H1).
`pc/shared/resume.is_wall_status()` returns true for exactly two statuses:

| Status | Evidence |
|---|---|
| `build_overflow` | the linker said so — `region … overflowed`, `section … will not fit`, or a reported RAM figure over 100 % |
| `malloc_failed` | the board itself reported `MALLOC_FAILED` over the protocol |

Everything else — `runtime_hang_or_reset`, `watchdog_suspected`,
`build_timeout`, `build_or_upload_fail` — is **not** a wall, no matter how
plausible it looks. A third route exists and is deliberately manual: **an
explicit operator decision**, recorded in `run_log.md` with the reasoning, is
the only way a hang or a watchdog reset ever becomes a published wall.

Two separate consequences, deliberately not conflated:
- *Within a session*, any failure stops the sweep from climbing to higher `n`
  for that circuit (`resume.stops_climbing()`), because higher `n` is always
  more expensive. That is a time-saving decision, not a scientific claim.
- *Across sessions*, only a positive-evidence wall makes `resume.known_wall_n()`
  skip higher `n` permanently. A timeout or a watchdog reset is retried by the
  next run, which is the whole point: a slow compile or a WDT reset must never
  silently truncate the dataset.

**`crc` and `sim` are defined but never set by any code path today.** Phase 3 is the
only place CRC exists at all, and a CRC-corrupted request frame is already
counted (`crc_error_count`, `dropped` in the console log) — but a Phase 3
point that fails (`session_incomplete`: no `DONE`, or zero rows, within the
session budget) is tagged `failure_type="serial"` unconditionally, whether
or not any CRC errors occurred during that session. This is a deliberate
decision, not an oversight: `crc_error_count` is a *cumulative* count for
the whole session, not a record of what the *last* thing to happen was
before the session gave up — a point can have a handful of harmless CRC
retries early on and then hang for an unrelated reason (or vice versa), and
the current exchange logic in `run_offload_session()`
(`pc/phase3_offload/sweep.py`) has no way to tell those apart after the
fact. Guessing `failure_type="crc"` from `crc_error_count > 0` would be
exactly the kind of misleading-but-plausible-looking data this schema is
trying to avoid. Telling them apart for real would need a logic change (not
made here, per this task's scope) — e.g. the exchange loop tracking
"consecutive CRC errors immediately before giving up," or the MCU itself
reporting a reason code when it gives up. `crc_error_count` remains
available as its own honest, independent number for anyone who wants to
eyeball high-CRC-error `session_incomplete` points by hand.

---

## Timing reference: ESP32 counter procedure

Replaces the Logic Analyzer procedure (removed 2026-10-04, recoverable at git commit `422216c`). Everything here is
**UNVERIFIED on hardware**: the counter has never been flashed.

1. Wire per `docs/design/wiring.md` (Uno: divider; ESP boards: direct; common GND; pre-power checklist in section 6 there).
2. Counter standalone self-test and calibration: `docs/design/readiness.md` section A.
3. Official commands (copy-paste, replace the ports):

```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodemXXXX --ref counter --counter-port /dev/cu.usbserialYYYY \
    --counter-cal calibration.json --dry-run
```
   Remove `--dry-run` only after the readiness page is complete. The sweep scripts accept the same
   `--ref counter --counter-port` flags directly.
4. After a point: `data/raw/phase2/<board>/<circuit>/with_ref/ref/ref_compare_points.csv` has `median_diff_us` and
   `flagged`; `ref_issues.log` lists reference problems (they never change `micros()` data or point status).

## First hardware contact

**Read this before plugging in the first board.** Everything above assumes
hardware that already works; this section is the one-time bring-up, ordered
from least to most risky. One board at a time, starting with the Uno (5V
logic, simplest toolchain, cheapest failure). Do not skip ahead — each step
exists to catch a specific failure before it can cost a long session or
pollute `data/raw/`.

Commands marked **UNVERIFIED** could not be run when this checklist was
written (no hardware was connected, by instruction): the flags are read from
the scripts' own `--help` and source, but their real-world behaviour against
a board has never been observed here. Treat a surprise from any of them as a
checklist bug, not as your mistake.

### (a) Physical inspection — no USB connection yet

- [ ] Inspect the board: no bent pins, no debris bridging the headers, no
      visible damage to the USB connector.
- [ ] Use a **data-capable** USB cable, not a charge-only one. This is the
      single most common bring-up failure: a charge-only cable powers the
      LED so the board looks alive, but no port ever appears.
- [ ] Prefer a direct port on the Mac over a hub. If a hub is unavoidable,
      use a powered one — ESP boards draw current spikes on WiFi radio
      init that an unpowered hub can brown out (the firmware disables WiFi,
      but only *after* boot).
- [ ] Note which physical port you used and keep the board in that port for
      the whole run. Ports re-enumerate; `find_uno_port()` tolerates that,
      but a stable port makes the logs easier to read.
- [ ] **LA must stay disconnected** for steps (a)-(e). It is introduced in
      step (f), on purpose, so that if something breaks you know whether
      the board or the LA wiring caused it.

### (b) Port detection only — no flash

```bash
ls /dev/cu.*
pio device list          # UNVERIFIED: enumerates ports; does NOT open one
```
- **Expected:** exactly one new entry appears when the board is plugged in
  and disappears when unplugged. Uno: `/dev/cu.usbmodem*`. ESP8266/ESP32:
  `/dev/cu.usbserial*`, `/dev/cu.wchusbserial*`, or `/dev/cu.SLAB_USBtoUART*`.
- **Bad result:** no new entry (dead cable, missing CH340/CP210x driver, or
  a dead board); or several new entries at once (you cannot tell which is
  the board — unplug everything else first).
- **Stop condition:** no port, or an ambiguous port. Do not guess a path and
  do not proceed to flashing — every later step needs the right `--port`.

### (c) Flash the standard Phase 2 firmware once, verify boot

```bash
# UNVERIFIED (compile step verified; upload step never run here)
cd firmware/uno && N_QUBITS=2 CIRCUIT_ID=0 pio run -e uno -t upload --upload-port /dev/cu.usbmodemXXXX
```
Then watch the boot output once:
```bash
# UNVERIFIED — this is the only step in this checklist that opens a serial
# monitor by hand; close it again before step (d), or the sweep cannot open
# the port.
pio device monitor -p /dev/cu.usbmodemXXXX -b 115200
```
- **Expected:** the CSV header line `board,circuit,n,rep,exec_time_us,free_heap_before,free_heap_after`,
  then 100 rows of `uno,h_all,2,<rep>,...`, then `DONE`. At n=2 the whole
  thing finishes in well under a second.
- **Bad result:** no output at all (wrong baud, wrong port, or the board
  never left the bootloader); garbage characters (baud mismatch — firmware
  and every script agree on 115200, so garbage means the monitor's `-b` is
  wrong); repeated header lines (the board is resetting mid-run — power or
  brown-out problem).
- **Stop condition:** anything other than a clean single header + 100 rows +
  `DONE`. **Close the monitor before continuing** — an open monitor holds
  the port and the sweep will fail to open it.

### (d) One shortest data point end-to-end, counter still disconnected

```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
    --circuits h_all --n-start 2 --n-max 2          # UNVERIFIED against real hardware
```
- **Expected:** a budget plan, a resume summary showing `remaining: 1/1`,
  then `n= 2 ... OK compile_ram=...% trials_captured=100`.
- **Bad result:** `trials_captured` below 100 (serial dropping data);
  `runtime_hang_or_reset` (board reset or never answered); `build_or_upload_fail`
  (toolchain, not board — see the known-issue note below about slow first
  compiles).
- **Stop condition:** anything that is not a clean `OK` with exactly 100
  trials. Diagnose before running a second point: a fault here repeats 154
  times later.

### (e) Verify the outputs and that measured time is sane

```bash
head -3 data/raw/phase2/uno/h_all/no_ref/raw.csv
cat data/raw/phase2/uno/h_all/no_ref/memory_wall.csv
tail -1 data/raw/phase2/uno/h_all/no_ref/points.csv
tail -1 data/raw/phase2/uno/h_all/no_ref/sessions.csv
ls data/raw/phase2/uno/h_all/no_ref/env/
```
(`no_ref/` because this example command has no `--ref counter` — swap for `with_ref/`
if you're checking a `--ref counter` run, see § "no_ref vs with_ref" at the top)
(paths updated for the per-`(phase, board, circuit)` directory layout,
`pre-run-uno-v4`/`v5` — see `pc/shared/paths.py`; each circuit now has its
own `raw.csv`/`memory_wall.csv`/`points.csv`/`sessions.csv`/`env/`, not one
shared file per board)
- **Expected:**
  - `raw.csv`: header + exactly 100 rows for `(h_all, 2)`, `exec_time_us`
    values clustered tightly (the n=30 dataset's IQR was very narrow).
  - `memory_wall.csv`: one row, `status=ok`.
  - `points.csv`: one row, `schema_version=2`, `status=ok`,
    `failure_type=none`, with `build_compile_s` / `upload_s` / `device_exec_s`
    populated.
  - `sessions.csv`: one row, `schema_version=2`, `n_points_ok=1`.
  - `env/<session_id>.json`: exists, `schema_version: 2`, non-empty
    `firmware_source_hash`, and `sleep_prevention.prevented: true`.
- [ ] **Compare measured against estimated.** `python pc/run.py --plan` gives the
      ESTIMATE per point (model in `pc/shared/timing_model.py`). Run:
```bash
.venv/bin/python analysis/timing_report.py
```
      and read the measured `build_compile_s + upload_s` median off it.
- **Bad result:** measured device time off by more than ~2x from the estimate
  (the gate costs are a prior fit, not a measurement of this run — a large miss
  means the board, the build flags, or the model is not what you think it is);
  or a measured reflash cost wildly different from the estimate, which changes
  the whole plan budget and should be fixed in the `*_ESTIMATE` tables before
  committing to a schedule.
- **Stop condition:** outputs missing, `schema_version` absent, or a
  `SchemaMismatchError` (means an old-schema telemetry file is present —
  archive it, do not delete it).

### (f) First counter pilot

- [ ] Power everything down before touching wiring.
- [ ] Wire per `docs/design/wiring.md`, tick `docs/design/readiness.md` completely, then run the pilot defined in its section E.
- [ ] Re-run the `h_all n=2` point and confirm the *device* numbers are unchanged from step (d) (the counter is an input only;
      if attaching it changes `exec_time_us`, the wiring is loading the pin: stop).

### (g) First full session

Only now run Session A for the Uno (§ Session A). After it completes, repeat
steps (a)-(e) for the ESP8266, then the ESP32, before giving either of them a
full session.

### Per-board wiring notes

| | Uno R3 | NodeMCU ESP8266 | ESP32 DevKit V1 |
|---|---|---|---|
| Logic level | **5 V** | 3.3 V | 3.3 V |
| `GPIO_TIMING_PIN` | D7 (PD7) | GPIO5 (= **D1** on the NodeMCU silkscreen) | GPIO4 |
| Serial | 115200, UART0 on D0/D1 — **never wire the LA to D0/D1** | 115200, UART0 on GPIO1/GPIO3 | 115200, UART0 on GPIO1/GPIO3 |

- **LA input levels:** the Uno drives its timing pin at **5 V**. Confirm the
  logic analyzer's inputs are 5 V-tolerant before connecting it to the Uno.
  Many cheap 3.3 V LAs are not; a series resistor or a level shifter is the
  usual fix. The ESP boards are 3.3 V and safe for any 3.3 V LA.
- **Common ground is mandatory.** Connect LA GND to board GND. Without a
  shared reference the captured edges are meaningless (and you can damage
  something). One ground wire per board, not a daisy chain through other
  equipment.
- **Power:** all three boards are USB-powered for this run — do not also feed
  VIN/5V from a bench supply while USB is connected.
- **NodeMCU pin naming:** the silkscreen says `D1`, the firmware says
  `GPIO_TIMING_PIN 5`, and both mean the same physical pin. Probe by GPIO
  number, not by the D-number, if there is any doubt.

### Rollback

- **Reflash a known-good state:** every firmware image is reproducible from
  source plus two build flags — there is no binary to restore. To put a board
  back to a known state, rebuild the smallest point for it, e.g.
  ```bash
  # UNVERIFIED
  cd firmware/uno && N_QUBITS=2 CIRCUIT_ID=0 pio run -e uno -t upload --upload-port /dev/cu.usbmodemXXXX
  ```
  Record the `git describe --tags` you built from (`pre-run-schema-v1` or
  later); the environment JSON records the firmware source hash per session,
  so a mismatch is detectable after the fact.
- **Discard a bad pilot point without polluting `data/raw/`:** the sweep
  files are append-only, so a bad point is a *row* problem, not a file
  problem. Preferred, in order:
  1. If the whole pilot should not count, use `--fresh` on the next run: it
     **renames** that `(board, circuit)`'s own `raw.csv` / `memory_wall.csv`
     to `raw.pre-fresh-<timestamp>.csv` / `memory_wall.pre-fresh-<timestamp>.csv`
     in place and starts clean. It never deletes.
  2. To drop one point by hand, delete *both* its `raw.csv` rows and its
     `memory_wall.csv` row. Deleting only the terminal record leaves
     orphan raw rows — resume will purge those automatically on the next run
     (that is the designed behaviour), but doing it deliberately is cleaner.
  3. Never hand-edit a file to "fix" a value. `phase2_summarize.py` and
     `phase3_summarize.py` refuse to run if any group exceeds 100 rows,
     which is the guard against exactly this.
- **Telemetry:** `points.csv` / `sessions.csv` rows for a discarded pilot can
  be left in place — every row carries its own `session_id`, so a discarded
  session is identifiable rather than needing removal. If you do want them
  gone, move that `(board, circuit)`'s whole
  `data/raw/phase<N>/<board>/<circuit>/` directory aside; do not delete
  individual rows (the schema-mismatch guard assumes intact headers).

---

## After everything

```bash
.venv/bin/python analysis/phase2_summarize.py
.venv/bin/python analysis/phase3_summarize.py
```
Both now **refuse to run** (exit 1, clear error naming the group) if any
`(board, circuit, n[, baud])` group has more than 100 rows — that means two
sessions wrote to the same file, or `--fresh` was used against the wrong
path. Fix the raw CSV before re-running, don't argue with the error.

Then add a row to `run_log.md` for this run, same as every prior run.
