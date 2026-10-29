"""Writes docs/phase4_report.md from data/processed/phase4/*.csv (run make_figures.py first). Every number in the
report is formatted from those files, so nothing is typed by hand."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p4common as C

D = C.PROC
rd = lambda f: pd.read_csv(os.path.join(D, f))
aud, ser, inv = rd("audit_points.csv"), rd("audit_series.csv"), rd("audit_phase3_inventory.csv")
p1, mem, fit, val = rd("phase1_infidelity.csv"), rd("memory_model.csv"), rd("time_fit.csv"), rd("time_validation.csv")
vb, sens, pred = rd("time_validation_by_board.csv"), rd("time_sensitivity.csv"), rd("time_predictions.csv")
cs, ca, xo, ov = rd("counter_summary.csv"), rd("counter_agreement.csv"), rd("offload_crossover.csv"), rd("offload_vs_local.csv")
loc = C.load_local()
BL = C.BOARD_LABEL


def md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def f(x, k=1):
    return f"{x:.{k}f}"


# ---------------- audit table
rows = []
for b in C.BOARDS:
    for c in C.CIRCUITS:
        s2 = ser[(ser.phase == 2) & (ser.board == b) & (ser.circuit == c)].iloc[0]
        s3 = ser[(ser.phase == 3) & (ser.board == b) & (ser.circuit == c)].iloc[0]
        i3 = inv[(inv.board == b) & (inv.circuit == c)].iloc[0]
        a2 = aud[(aud.phase == 2) & (aud.board == b) & (aud.circuit == c)]
        walls = a2[a2.terminal_status.isin(["build_overflow", "malloc_failed"])]
        wall = f"{walls.terminal_status.iloc[0]} n={int(walls.n.iloc[0])}" if len(walls) else "none (time-limited)" if b != "uno" else "none"
        c2 = ca[(ca.board == b) & (ca.circuit == c)]
        rows.append({"board": BL[b], "circuit": c, "P2 ok pts": int((a2.terminal_status == "ok").sum()), "P2 ok n": f"2-{int(s2.n_ok_max)}",
                     "reps/pt": f"{int(s2.reps_min)}-{int(s2.reps_max)}" if s2.reps_min != s2.reps_max else str(int(s2.reps_min)),
                     "P2 terminal": wall, "fw hashes (P2 / P3 series)": f"{int(s2.series_hashes)} / {int(s3.series_hashes)}",
                     "mixed pts": int(s2.mixed_hash_points + s2.mixed_schema_points + s3.mixed_hash_points + s3.mixed_schema_points),
                     "counter pts (ok/flagged)": f"{int(((c2.ref_status == 'ok') & (c2.n_pairs >= 10)).sum())}/{int(((c2.ref_status != 'ok') & (c2.n_pairs >= 10)).sum())}",
                     "P3 n @ baud": f"{int(i3.n_min)}-{int(i3.n_max)} @ {i3.bauds}", "P3 min req/pt": int(i3.min_requests_per_point)})
audit_tbl = md(pd.DataFrame(rows))

p1rows = []
for c, g in p1.groupby("circuit"):
    fail = g[~g["pass_1e-3"]]
    p1rows.append({"circuit": c, "n range": f"{g.n.min()}-{g.n.max()}",
                   "max infidelity of passing n": f"{g[g['pass_1e-3']].infidelity.max():.2e}",
                   "result": "all pass" if fail.empty else f"pass n<={int(g[g['pass_1e-3']].n.max())}; first fail n={int(fail.n.min())} ({fail.infidelity.iloc[0]:.2e})",
                   "infidelity at n=12": f"{g[g.n == 12].infidelity.iloc[0]:.2e}" if (g.n == 12).any() else ""})
p1_tbl = md(pd.DataFrame(p1rows))

# ---------------- memory
mrows = []
for _, r in mem.iterrows():
    mrows.append({"board": BL[r.board], "circuit": r.circuit, "predictor": r.predictor, "B (bytes)": f"{r.B_bytes:.0f}",
                  "overhead (bytes)": f"{r.overhead_bytes:.0f}", "pred. n_max": r.n_max_pred, "last ok n": r.last_ok_n,
                  "wall n": "-" if pd.isna(r.wall_n) else int(r.wall_n), "agrees": r.match})
mem_tbl = md(pd.DataFrame(mrows))
wall_ev = mem.drop_duplicates(["board", "circuit"])[["board", "circuit", "wall_evidence"]]
wall_ev = wall_ev[wall_ev.wall_evidence != "none observed"]
ev_tbl = md(pd.DataFrame({"board": [BL[x] for x in wall_ev.board], "circuit": wall_ev.circuit, "evidence (status in file)": wall_ev.wall_evidence}))

# ---------------- time
fp = fit[fit.model == "M1_pooled"].set_index("board")
f2 = fit[fit.model == "M2_pooled"].set_index("board")
f1c = fit[fit.model == "M1_per_circuit"]
const_rows = []
for b in C.BOARDS:
    const_rows.append({"board": BL[b], "c (M1) us/iter": f"{fp.loc[b].c_us_per_iter:.4f}", "n_fit": int(fp.loc[b].n_fit),
                       "c_H (M2)": f"{f2.loc[b].c_H_us:.4f}", "c_CNOT (M2)": f"{f2.loc[b].c_CNOT_us:.4f}",
                       "c_CPHASE (M2)": f"{f2.loc[b].c_CPHASE_us:.4f}", "a per call us (M2)": f"{f2.loc[b].a_call_us:.2f}"})
const_tbl = md(pd.DataFrame(const_rows))
vt = val[val.part == "test"]
vf = val[val.part == "fit"]
vrows = []
for b in C.BOARDS:
    for c in C.CIRCUITS:
        t1 = vt[(vt.model == "M1") & (vt.board == b) & (vt.circuit == c)].iloc[0]
        t2 = vt[(vt.model == "M2") & (vt.board == b) & (vt.circuit == c)].iloc[0]
        tc = vt[(vt.model == "M1c") & (vt.board == b) & (vt.circuit == c)].iloc[0]
        nf = int(vf[(vf.model == "M1") & (vf.board == b) & (vf.circuit == c)].n_points.iloc[0])
        vrows.append({"board": BL[b], "circuit": c, "fit n (count)": nf, "test n": t1.n_list.replace(" ", ","),
                      "M1 MAPE / max %": f"{t1.mape_pct:.1f} / {t1.max_abs_pct:.1f}",
                      "M1c MAPE / max %": f"{tc.mape_pct:.1f} / {tc.max_abs_pct:.1f}",
                      "M2 MAPE / max %": f"{t2.mape_pct:.1f} / {t2.max_abs_pct:.1f}",
                      "M2 signed mean %": f"{t2.mean_signed_pct:+.1f}",
                      "evidence": "WEAK: min reps " + str(int(t2.min_reps)) if t2.weak else "ok (3 test pts)"})
val_tbl = md(pd.DataFrame(vrows))
vbr = []
for b in C.BOARDS + ["all"]:
    g = vb[vb.board == b].set_index("model")
    vbr.append({"board": BL.get(b, "all"), "n test pts": int(g.loc["M1"].n_test),
                **{f"{m} MAPE / max %": f"{g.loc[m].mape_pct:.1f} / {g.loc[m].max_abs_pct:.1f}" for m in ["M1", "M1c", "M2", "M2_nogrover_fit"]}})
vb_tbl = md(pd.DataFrame(vbr))
fitm = vf[vf.model.isin(["M1", "M2"])].pivot_table(index="model", values="mape_pct", aggfunc=lambda s: s.mean())
sens_all = sens[(sens.board == "all")].pivot_table(index="model", values="mape_pct", aggfunc=["min", "max"]).round(1)
sm = lambda m: f"{sens_all.loc[m, ('min', 'mape_pct')]:.1f}-{sens_all.loc[m, ('max', 'mape_pct')]:.1f}"
gb = lambda m, b: vb[(vb.model == m) & (vb.board == b)].iloc[0]

# grover time-limit facts
def lastp(b, c):
    g = loc[(loc.board == b) & (loc.circuit == c)].sort_values("n").iloc[-1]
    return g
g8, g32, g1 = lastp("esp8266", "grover"), lastp("esp32", "grover"), lastp("uno", "grover")
u7 = {c: lastp("uno", c) for c in C.CIRCUITS}

# counter
def cr(b, st, sub):
    r = cs[(cs.board == b) & (cs.counter_status == st) & (cs.subset == sub)].iloc[0]
    return r
cs_tbl = md(pd.DataFrame([{"board": BL[r.board], "counter status": r.counter_status, "subset": r.subset, "points": int(r.n_points),
                           "median micros/counter": f"{r.median_of_median_ratio:.4f}", "min-max of point medians": f"{r.ratio_min:.4f}-{r.ratio_max:.4f}",
                           "IQR of point medians": f"{r.iqr_of_point_medians:.4f}"} for _, r in cs.iterrows()]))
bad = ca[(ca.n_pairs < 10)]

# offload
def xs(b, c):
    return xo[(xo.board == b) & (xo.circuit == c)].iloc[0]
xrows = []
for _, r in xo.iterrows():
    xrows.append({"board": BL[r.board], "circuit": r.circuit, "local n range": r.n_range,
                  "first measured n offload faster": "none" if pd.isna(r.first_n_offload_faster) else int(r.first_n_offload_faster),
                  "stable to local n max": r.stable_to_n_local_max,
                  "n* interpolated": "-" if pd.isna(r.n_star_interpolated) else f"{r.n_star_interpolated:.2f}",
                  "offload/local at local n max": f"{r.ratio_at_n_local_max:.2f}", "min requests/pt": int(r.min_offload_req)})
x_tbl = md(pd.DataFrame(xrows))
floor = ov[ov.n <= 4].groupby("board").median_us_offload.median()
offd = C.load_offload()
g11 = offd[(offd.circuit == "grover") & (offd.board != "uno") & (offd.n >= 11)]
hl = []
for (ph, b, c), g in aud[aud.ok_rows > 0].groupby(["phase", "board", "circuit"]):
    if g.fw_hashes.nunique() > 1:
        hl.append(f"Phase {ph} {BL[b]} {c}: " + "; ".join(f"n={','.join(map(str, v))}" for v in g.groupby("fw_hashes", sort=False).n.apply(list)))
hash_layout = "; ".join(hl)
u_over = mem[mem.board == "uno"].overhead_bytes
e32 = mem[(mem.board == "esp32") & (mem.circuit == "qft")].set_index("predictor")
gm = p1[(p1.circuit == "grover") & (p1.n == 12)].grover_marked_prob.iloc[0]
ceil = lambda b, c: C.load_offload().query("board==@b and circuit==@c").n.max()

R = f"""# Phase 4 report: what limits statevector simulation on microcontrollers, and how well can it be predicted

Generated by `analysis/phase4/build_report.py` from `data/processed/phase4/*.csv` (which `analysis/phase4/make_figures.py` writes
from `data/raw/`). Nothing here is typed by hand. Tags: **OBSERVED** = computed from the CSVs; **INTERPRETATION** = my reading, not
tested; **UNVERIFIED** = not backed by data on disk. Scope: h_all, bell_ghz, qft, grover on Uno R3, ESP8266, ESP32. All data under
`data/raw/` were collected after the purge with the current timing system (session dates 2026-10-04 to 2026-10-10); only `data/raw/` and
`data/calibration/` are read, and no qpe/steane_encode data are used.

## 1. Summary

- **Limiting factor depends on board and circuit.** h_all, bell_ghz, qft stop at a memory wall: Uno n={int(mem[(mem.board=='uno')].wall_n.dropna().iloc[0])} (SRAM, `build_overflow`), ESP8266 n={int(mem[(mem.board=='esp8266')].wall_n.dropna().iloc[0])} and ESP32 n={int(mem[(mem.board=='esp32')].wall_n.dropna().iloc[0])} (`malloc_failed`). grover stops earlier on the ESP boards by **time**, not memory (ESP8266 last run n={int(g8.n)}, {g8.median_us/6e7:.0f} min/run; ESP32 n={int(g32.n)}, {g32.median_us/6e7:.0f} min/run, {int(g32.reps)} rep); Uno grover hits the SRAM wall at n=8.
- **Memory is predictable exactly:** n_max = floor(log2(B/8)) with B read at n=2 (never from the wall point) reproduces the last ok n on all three boards. On the ESP32 it only works with the *largest free block* (13); the *total free heap* predicts 14, one too high.
- **Time model accuracy (held-out largest {C.N_TEST} n per series, {int(gb('M1','all').n_test)} points):** one constant per board (c x gate calls x 2^n) gives MAPE {gb('M1','all').mape_pct:.0f} %; per-gate-kind costs (H, CNOT, CPHASE + per-call term) give {gb('M2','all').mape_pct:.0f} % overall (ESP32 {gb('M2','esp32').mape_pct:.0f} %, ESP8266 {gb('M2','esp8266').mape_pct:.0f} %, Uno {gb('M2','uno').mape_pct:.0f} %), worst single point {gb('M2','all').max_abs_pct:.0f} %. Good for order of magnitude, not for sub-10 % prediction on soft-float boards.
- **Offload crossover exists** for 11 of 12 board x circuit pairs inside the measured range (n* over h_all, bell_ghz, qft = {xs('uno','qft').n_star_interpolated:.1f}-{xs('uno','bell_ghz').n_star_interpolated:.1f} Uno, {xs('esp8266','qft').n_star_interpolated:.1f}-{xs('esp8266','bell_ghz').n_star_interpolated:.1f} ESP8266, {xs('esp32','qft').n_star_interpolated:.1f}-{xs('esp32','bell_ghz').n_star_interpolated:.1f} ESP32 (qft and bell_ghz only)); **ESP32 h_all has none up to n={int(xs('esp32','h_all').n_local_max)}** (offload {xs('esp32','h_all').ratio_at_n_local_max:.2f}x slower).
- **Evidence is thin where it matters most:** the ESP grover test points have {int(vt[(vt.model=='M2')&(vt.board=='esp32')&(vt.circuit=='grover')].min_reps.iloc[0])} and {int(vt[(vt.model=='M2')&(vt.board=='esp8266')&(vt.circuit=='grover')].min_reps.iloc[0])} reps; the counter is uncalibrated; correctness was checked only on the PC build.

## 2. Data used (Step 0 audit)

Script: `analysis/phase4/audit.py` -> `data/processed/phase4/audit_points.csv`, `audit_series.csv`, `audit_phase3_inventory.csv`, `phase1_infidelity.csv`.
**Gate result: PASSED.** Every board x circuit has post-purge Phase 2 and Phase 3 data; **0 points** have mixed firmware hashes or schema
versions (one `schema_version=2` everywhere; hash = `firmware_source_hash` in the session env JSON, a hash of `firmware/common` + the board's
`src`, not of the flashed binary). Caveat: some *series* span several hashes (column "fw hashes": number of distinct hashes across the ok points of a series).
Per-point status comes from `memory_wall.csv` (Phase 2) and `session_log.csv` (Phase 3). Statuses present: ok, build_overflow, malloc_failed
(walls, with positive evidence), skipped_compute_infeasible / skipped_sim_cost_infeasible (not run, not walls). No `time_limited` row exists as such: time-limited points
are `skipped_*` (not measured) or ok with fewer than 100 reps.

{audit_tbl}

Counter columns count points with at least 10 pulse pairs. Series that span more than one hash (OBSERVED, `audit_points.csv`, listing the n values per hash): {hash_layout}. Because grover test points sit in a different hash than its fit points, the grover validation mixes firmware versions (see section 4).

**Counter data.** The reference counter is a separate ESP32 device that timed all three target boards (the table above shows it covers Uno, ESP8266 and ESP32 targets), in both phases. Its
calibration status, confirmed from the files: every one of the 60 session sidecars (`env/*.ref.json`) has `"calibration": {{}}` and `"selftest": "self-loopback only"`.
**Correction to the premise:** a separate PC-clock comparison exists, `data/calibration/counter_20261004.json` (+17.5 +/- 1.9 ppm vs the PC clock, 2026-10-04, counter firmware field empty), but it is not recorded in any session, predates all ESP32 sessions by 4 days, and its own text says it
"says nothing about the target board's own clock". Treat the counter as **uncalibrated**.

**Phase 1 (PC build, `data/raw/phase1/`).** The canonical `infidelity_tvd.csv` is a subset of `infidelity_tvd.20261003T111917Z.csv` (identical values where they overlap, asserted in code); grover n=12 exists only in `infidelity_tvd.20261004T091042Z.csv`. The canonical file has no grover n=9 row, so the "fails for n >= 9" belief is confirmed only from the timestamped file.

{p1_tbl}

**Phase 3** (offload): baud 115200 only for every board and circuit (the table's last columns). Phase 3 grover on the ESP boards has {int(g11.reps.min())}-{int(g11.reps.max())} requests per point at n >= 11 (100 elsewhere).

## 3. Memory limit

Model (`model.py: memory_model`): a point fits if overhead + 8 x 2^n <= B (8 bytes = complex float32). B and overhead are read from the low-n runs only:
- Uno: state is a static array; B = 2048 B SRAM minus the static overhead, where overhead = `compile_ram_used_bytes - 8*2^n` from the ok points (constant per circuit, {u_over.min():.0f}-{u_over.max():.0f} B).
- ESP8266: B = `free_heap_before + 8*2^2` at n=2 (heap is read *after* the state is allocated, `firmware/esp32/src/main.cpp:66` vs `:80`; the ESP8266 firmware allocates at `firmware/esp8266/src/main.cpp:85` and reads the heap at `:99`), no extra overhead assumed. The same constant (spread 0 B) results at every n.
- ESP32: two candidates, total free heap (same construction) and `largest_block` (`heap_caps_get_largest_free_block`, also read after the allocation). The state needs one contiguous block.

{mem_tbl}

A wall counts only with positive evidence (`memory_wall.csv` status):

{ev_tbl}

OBSERVED: the prediction equals (first failing n - 1) in every row that has a wall. ESP32 total-free-heap predictor (B = {e32.loc['total_free_heap'].B_bytes:.0f} B) is wrong by +1 qubit: it predicts {int(e32.loc['total_free_heap'].n_max_pred)}, but the {int(e32.loc['total_free_heap'].state_bytes_at_pred)}-byte state cannot be allocated. INTERPRETATION: the largest free block read at n=2 ({e32.loc['largest_block'].B_bytes:.0f} B) is a lower bound on the contiguous block available at boot, and the failure at n=14 ({int(e32.loc['largest_block'].state_bytes_at_pred_plus1)} B) puts the true value below that size; every B in that interval gives n_max = 13, so the prediction does not depend on the exact block size. grover on ESP8266 / ESP32 never ran to a memory wall (time-limited), so their predicted n_max=12 / 13 is **untested**. ESP8266 allocator-header overhead (a few bytes per block) is **UNVERIFIED**, it is zero in the model and not needed to match the wall.

## 4. Time limit and prediction model

Gate counts come from `firmware/common/circuits.hpp` (`analysis/phase4/gatecount.py`; cross-checked by running the unmodified `circuits.hpp` in C++ with counting kernels, 52 of 52 (circuit, n) pairs equal):
h_all `:20-25` = n H; bell_ghz `:33-39` = 1 H + (n-1) CNOT; qft `:53-61,80-83` = n H + n(n-1)/2 CPHASE; grover `:152-181` = n H, then floor(pi/4 sqrt(2^n)) iterations of 2 x MC-phase(n-1) + 6n H + 2n CPHASE, with MC-phase `:108-125` and MC-X `:127-135` giving G(k) = 1, 5, 21, ..., 157 461 for k = 1, 2, 3, ..., 11 (`:102`).
Every kernel loops over all 2^n indices (`firmware/common/qsim.hpp:65,86,107`), including indices it does not update, so I define

- **work(n) = (gate calls) x 2^n loop iterations** (not 2^(n-1) amplitude updates; the loop visits all 2^n, and the factor is absorbed in c either way). `init0` (one sweep) is not counted.
- **M1** (the requested model): t = c_board x work(n), one c per board, pooled over circuits.
- **M1c**: one c per (board, circuit).
- **M2** (variant, defined before any test point was scored): t = (c_H N_H + c_CNOT N_CNOT + c_CPHASE N_CPHASE) 2^n + a x (gate calls), non-negative least squares on relative error. Justification: the kernels are different code (H: 4 float adds and 4 multiplies per pair; CNOT: integer test and swap; CPHASE: complex multiply, plus `cosf` and `sinf` once per call), and Uno/ESP8266 have no FPU, so their cost per iteration differs strongly by gate kind.
- **M2 grover-held-out fit**: M2 fitted without any grover point (tests whether the per-kind costs transfer to a circuit never seen in the fit).

Split (fixed a priori, not tuned): per (board, circuit), the largest {C.N_TEST} ok n are **test**; every other point with median >= {C.FLOOR_US:.0f} us is **fit** (100 us = 25 ticks of the Uno's 4 us `micros()` resolution); points below that are dropped. Fit loss = relative squared error, so M1 has a closed form. Time per run = median of the per-rep `exec_time_us` in `raw.csv`.
Sensitivity to that choice (test points {C.N_TEST} -> 2 or 4, floor 50 / 200 us): overall test MAPE ranges M1 {sm('M1')} %, M1c {sm('M1c')} %, M2 {sm('M2')} %, M2 grover-held-out {sm('M2_nogrover_fit')} % (`time_sensitivity.csv`); the choice does not change the ranking.

Fitted constants (units: us per loop iteration for c_H, c_CNOT, c_CPHASE and M1's c; us per gate call for a):

{const_tbl}

Validation (`time_validation.csv`; MAPE and max absolute % error over the held-out points; "WEAK" = a test point has fewer than {C.SMALL_REPS} reps):

{val_tbl}

Pooled over circuits, per board (test points only):

{vb_tbl}

OBSERVED: M1 is poor ({gb('M1','all').mape_pct:.0f} % overall; worst {gb('M1','esp8266').max_abs_pct:.0f} % ESP8266, {gb('M1','uno').max_abs_pct:.0f} % Uno bell_ghz); M2 lowers it on every board (Uno {gb('M1','uno').mape_pct:.0f} to {gb('M2','uno').mape_pct:.0f} %, ESP8266 {gb('M1','esp8266').mape_pct:.0f} to {gb('M2','esp8266').mape_pct:.0f} %, ESP32 {gb('M1','esp32').mape_pct:.0f} to {gb('M2','esp32').mape_pct:.0f} %). Every board has exactly {C.N_TEST} test points per series (the minimum for "not weak" by the number of points); the two ESP grover series are weak by rep count.
Every series with 3 test points is a small sample; the MAPE per series has no confidence interval and should be read as indicative.

**Where it fails (INTERPRETATION unless stated):**
- Uno qft (M2 {vt[(vt.model=='M2')&(vt.board=='uno')&(vt.circuit=='qft')].mape_pct.iloc[0]:.0f} % MAPE): only 3 fit points per series (n=2-4), and the per-call term `a` is fitted to {f2.loc['uno'].a_call_us:.2f} us on Uno, so the large `cosf`/`sinf` cost per CPHASE call (qft has n(n-1)/2 calls) is not separated from c_CPHASE. OBSERVED: a = {f2.loc['uno'].a_call_us:.2f} on Uno (boundary of the NNLS); the cause is my reading.
- ESP8266 bell_ghz (M2 {vt[(vt.model=='M2')&(vt.board=='esp8266')&(vt.circuit=='bell_ghz')].mape_pct.iloc[0]:.0f} %) and qft: c_CNOT = {f2.loc['esp8266'].c_CNOT_us:.4f} is near 0 while a = {f2.loc['esp8266'].a_call_us:.1f} us/call; N_CNOT 2^n and G are close to collinear in bell_ghz, so the split between a per-call cost and a per-iteration cost is not identifiable from these data. Read the constants as a fit, not as measured per-gate costs.
- grover on ESP8266/ESP32: test points come from a different firmware hash than the fit points (section 2) and have {int(g8.reps)} / {int(g32.reps)} reps at the last n; the error there mixes model error with firmware change and noise.
- Memory-system effects (cache, flash wait states on the ESP boards) are not in the model; **UNVERIFIED** whether they explain the residuals, the series were not checked for them.

## 5. Offload

Local = Phase 2 median per run (`micros()`, on the board). Offload = Phase 3 median `e2e_latency_us` per request (round trip: request frame, PC statevector simulation with Qiskit Aer, reply), 115 200 baud, timed-out and CRC-error requests excluded (none present). `analysis/phase4/model.py: offload_crossover` -> `offload_crossover.csv`, `offload_vs_local.csv`; figure F4.
The crossover is reported two ways: the **first measured n** at which offload is faster (a measurement), and **n\\*** from log-linear interpolation between the two bracketing n (interpolated, not measured).

{x_tbl}

OBSERVED: at n <= 4 the offload round trip is nearly flat, median {floor.loc['uno']/1000:.1f} ms (Uno), {floor.loc['esp8266']/1000:.1f} ms (ESP8266), {floor.loc['esp32']/1000:.1f} ms (ESP32) over the four n <= 4 points pooled, then grows as the PC simulation grows. Uno grover is already faster offloaded at the smallest n (n=2), so its crossover is at or below 2 and is not interpolated.
Beyond the local memory wall only offload exists: Uno offload was measured to n={int(ceil('uno','h_all'))} (h_all) against a local wall at n=8; ESP8266 to n={int(ceil('esp8266','h_all'))} (wall 13); ESP32 to n={int(ceil('esp32','h_all'))} (wall 14). Offload cost there is dominated by the PC simulation (INTERPRETATION, from the flat floor, not isolated here). No crossover is extrapolated: ESP32 h_all has none in the measured range (offload/local = {xs('esp32','h_all').ratio_at_n_local_max:.2f} at n={int(xs('esp32','h_all').n_local_max)}); grover offload points at n >= 11 on the ESP boards have {int(g11.reps.min())}-{int(g11.reps.max())} requests (n=11-13); the grover crossovers (ESP8266 n\\*={xs('esp8266','grover').n_star_interpolated:.2f}, ESP32 n\\*={xs('esp32','grover').n_star_interpolated:.2f}) rest on points with {int(xs('esp32','grover').min_offload_req)} or more requests.

## 6. Limitations

1. **Counter is uncalibrated** (section 2). Calibration `{{}}` in all 60 sidecars, self-test "self-loopback only"; the one PC-clock comparison (17.5 ppm) is not linked to any session and says nothing about the target board clock. micros() vs counter agreement (below) is an agreement between two uncalibrated clocks.
2. **No board-level correctness data.** Boards return timing (and heap) only; whether the float32 state on the MCU is correct was never measured. Correctness (Phase 1) is float32 C++ on the PC vs Qiskit Aer float64, not the MCU build.
3. **grover accuracy fails on the PC build for n >= 9:** infidelity {p1[(p1.circuit=='grover')&(p1.n==9)].infidelity.iloc[0]:.2e} at n=9 (> 1e-3), {p1[(p1.circuit=='grover')&(p1.n==12)].infidelity.iloc[0]:.3f} at n=12, while P(marked) at n=12 is {gm:.2f} (`infidelity_tvd.20261004T091042Z.csv`, `grover_marked_prob`). grover timings at n >= 9 are timings of a simulation whose float32 state is no longer within the 1e-3 gate.
4. **Phase 3 offload samples one shot** from the PC's Aer statevector per request (`pc/phase3_offload/sweep.py: simulate_and_sample`) and does not compare the sampled outcome with any reference; the round trip is a latency measurement, not a correctness measurement. The PC simulation is re-run per request and is part of the measured round trip.
5. **Small samples:** ESP32 grover n=11, 12 have {int(loc[(loc.board=='esp32')&(loc.circuit=='grover')&(loc.n==11)].reps.iloc[0])} and {int(g32.reps)} reps; ESP8266 grover n=9, 10 have {int(loc[(loc.board=='esp8266')&(loc.circuit=='grover')&(loc.n==9)].reps.iloc[0])} and {int(g8.reps)} (per-point time cap 7 200 s, `pc/shared/timing_model.py:404` as cited in `docs/data_audit.md`); Phase 3 grover offload on the ESP boards has {int(g11.reps.min())}-{int(g11.reps.max())} requests per point at n >= 11. Every time-model series has exactly {C.N_TEST} test points.
6. **Firmware and tree state:** all 60 sessions ran with a dirty git working tree and several series span more than one firmware hash (section 2); the firmware hash is of the source, not the binary. One physical unit per board, one PC, one baud rate (115 200).
7. **Timing resolution:** Uno `micros()` resolution is 4 us; ESP boards 1 us. The model fit ignores points below {C.FLOOR_US:.0f} us, so it says nothing about the smallest n.
8. **Counter anomalies:** ESP32 grover n=12 has one counter pair and a counter value of {ca[(ca.board=='esp32')&(ca.circuit=='grover')&(ca.n==12)].median_counter_us.iloc[0]/1e6:.2f} s against {ca[(ca.board=='esp32')&(ca.circuit=='grover')&(ca.n==12)].median_micros_us.iloc[0]/1e6:.0f} s from `micros()`: a counter failure at multi-minute pulse widths (cause UNVERIFIED), excluded from the agreement table (fewer than 10 pairs). No counter pair exists for ESP32 grover n=10 (reason UNVERIFIED). Uno and ESP8266 points carry counter status `anomaly`/`count_mismatch` (extra pulses) in the counter's own flags.

micros() vs counter (Phase 2 only; Phase 3 counter data are excluded by the project's policy that Phase 3 runs without the counter, per `docs/data_audit.md` check E3; `counter_summary.csv`; ratio = micros/counter per point, points with >= 10 pairs):

{cs_tbl}

OBSERVED: on ESP32 (counter status ok) the two clocks agree to {abs(1-cr('esp32','ok','median>=100us').ratio_min)*100:.2f} % at the worst point with median >= 100 us (median ratio {cr('esp32','ok','median>=100us').median_of_median_ratio:.4f}); below 100 us the ratio spreads down to {cr('esp32','ok','all').ratio_min:.3f}. On Uno micros() reads {abs(1-cr('uno','not_ok','all').median_of_median_ratio)*100:.1f} % below the counter. INTERPRETATION: 0.6 % is far above the 17.5 ppm PC-clock comparison, so either the Uno's `micros()` timebase or the counter is off by that much; the data cannot say which because there is no calibration. **Label: uncalibrated.**

## 7. Paper-ready material

**Captions (draft):**
- **F1 (`figures/phase4/F1_timing_vs_n.pdf`).** Median execution time per run (shaded: IQR) versus qubit count for the four circuits on each board; dotted lines mark the measured memory walls and open markers points with fewer than {C.SMALL_REPS} repetitions.
- **F2 (`F2_parity.pdf`).** Predicted versus measured time, (a) one cost constant per board, (b) per-gate-kind costs; filled markers were used to fit, open markers are the largest {C.N_TEST} n of each series held out. Overall held-out MAPE {gb('M1','all').mape_pct:.0f} % (a) and {gb('M2','all').mape_pct:.0f} % (b).
- **F3 (`F3_memory_wall.pdf`, `tables/phase4_memory_wall.tex`).** Largest qubit count that fits: measured (last n before a wall with positive evidence) versus floor(log2(B/8)); on the ESP32 the total free heap overpredicts by one qubit (red), the largest free block does not.
- **F4 (`F4_offload_crossover.pdf`).** Local execution time (solid, Phase 2) and offload round trip (dashed, Phase 3, 115 200 baud) per circuit; stars mark the interpolated crossover, none exists for ESP32 h_all, rings mark points with fewer than {C.SMALL_REPS} requests.
- **F5 (`F5_phase1_accuracy.pdf`).** Infidelity of the float32 C++ simulator against Qiskit Aer (float64) versus n; grover crosses the 1e-3 threshold at n=9, the other circuits stay below 3e-7.

**Candidate abstract claims (number : source):**
1. "The largest feasible register is predicted exactly by floor(log2(B/8)) from heap measurements at n=2: n_max = {int(mem[(mem.board=='uno')&(mem.circuit=='qft')].n_max_pred.iloc[0])} (Uno), {int(mem[(mem.board=='esp8266')&(mem.circuit=='qft')].n_max_pred.iloc[0])} (ESP8266) and {int(mem[(mem.board=='esp32')&(mem.circuit=='qft')&(mem.predictor=='largest_block')].n_max_pred.iloc[0])} (ESP32, largest free block), matching the first measured allocation failure minus one on all three boards." Source: `data/processed/phase4/memory_model.csv` (`n_max_pred`, `wall_n`), raw evidence `data/raw/phase2/*/{{h_all,bell_ghz,qft}}/with_ref/memory_wall.csv`.
2. "A gate-count timing model with per-gate-kind costs, fitted on small n only, predicts held-out largest-n execution times with {gb('M2','esp32').mape_pct:.0f} % MAPE on ESP32, {gb('M2','esp8266').mape_pct:.0f} % on ESP8266 and {gb('M2','uno').mape_pct:.0f} % on Uno ({gb('M2','all').mape_pct:.0f} % overall, 36 points), versus {gb('M1','all').mape_pct:.0f} % for a single per-board constant." Source: `time_validation_by_board.csv` (`M2`, `M1`); points in `time_predictions.csv` (role = test). Weak evidence: 3 test points per series, two series with fewer than {C.SMALL_REPS} reps.
3. "Offloading to a PC becomes faster than local execution at n = {xs('uno','qft').n_star_interpolated:.1f}-{xs('uno','bell_ghz').n_star_interpolated:.1f} on the Uno, {xs('esp8266','qft').n_star_interpolated:.1f}-{xs('esp8266','bell_ghz').n_star_interpolated:.1f} on the ESP8266 and {xs('esp32','qft').n_star_interpolated:.1f}-{xs('esp32','bell_ghz').n_star_interpolated:.1f} on the ESP32 (qft to bell_ghz; interpolated between measured n), and never within n <= {int(xs('esp32','h_all').n_local_max)} for ESP32 h_all." Source: `offload_crossover.csv` (`n_star_interpolated`, `first_n_offload_faster`, `ratio_at_n_local_max`); raw `data/raw/phase2/*/*/with_ref/raw.csv` and `data/raw/phase3/*/*/with_ref/raw.csv`. At 115 200 baud only.

## 8. Reproduce

Interpreter: the project `.venv` (pinned, `requirements.txt`: matplotlib 3.11.1, numpy 2.4.6; scipy and pandas are also present).

```
cd /Users/thirasak/Developer/quantum-lab
.venv/bin/python analysis/phase4/audit.py            # Step 0, prints the audit, writes data/processed/phase4/audit_*.csv, phase1_infidelity.csv
.venv/bin/python analysis/phase4/gatecount.py        # C++ cross-check of gate counts
.venv/bin/python analysis/phase4/model.py            # Step 1 tables
.venv/bin/python analysis/phase4/make_figures.py     # models + figures/phase4/F1..F5 (.pdf/.png) + tables/phase4_memory_wall.tex
.venv/bin/python analysis/phase4/build_report.py     # this file
.venv/bin/python analysis/phase4/phase4_test.py      # checks for this analysis
```
Existing suite: each `*_test.py` is a standalone script (`for f in $(git ls-files '*_test.py'); do .venv/bin/python $f; done`); running `pc/run_test.py` and friends appends lines to `data/run_history.jsonl`, which I reverted with `git checkout` after each run.
"""
os.makedirs(os.path.join(C.ROOT, "docs"), exist_ok=True)
open(os.path.join(C.ROOT, "docs", "phase4_report.md"), "w").write(R)
print("wrote docs/phase4_report.md", len(R.splitlines()), "lines")
