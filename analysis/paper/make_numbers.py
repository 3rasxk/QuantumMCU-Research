#!/usr/bin/env python3
"""paper/numbers.tex and paper/tables/*.tex from the committed analysis outputs (read-only).

Every number in the paper text is a \\newcommand written here; the tables are written here too. Sources: data/processed/phase4/*.csv,
data/derived/*.csv, data/raw/**/env/*.json (clock only), analysis/common/weak.py and docs/phase4_report.md (only for the few values that exist
nowhere else; the pattern must match or the script stops, so a changed report cannot silently change the paper).

Macro names contain letters only (LaTeX). Board tags: Uno, EspLo (ESP8266), EspHi (ESP32).

    .venv/bin/python analysis/paper/make_numbers.py
"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis", "phase4"))
P = os.path.join(ROOT, "data", "processed", "phase4")
D = os.path.join(ROOT, "data", "derived")
OUT = os.path.join(ROOT, "paper")
os.makedirs(os.path.join(OUT, "tables"), exist_ok=True)
rd = lambda d, f: pd.read_csv(os.path.join(d, f))
TAG = {"uno": "Uno", "esp8266": "EspLo", "esp32": "EspHi"}
NAME = {"uno": "Uno R3", "esp8266": "ESP8266", "esp32": "ESP32"}
BOARDS = ("uno", "esp8266", "esp32")
CIRC = ("h_all", "bell_ghz", "qft", "grover")
REPORT = open(os.path.join(ROOT, "docs", "phase4_report.md"), encoding="utf-8").read()
M = {}      # macro name -> text


def put(name, val):
    assert re.fullmatch(r"[A-Za-z]+", name), name
    assert name not in M, name
    M[name] = str(val)


def f0(x):
    return f"{x:.0f}"


def f1(x):
    return f"{x:.1f}"


def f2(x):
    return f"{x:.2f}"


def f4(x):
    return f"{x:.4f}"


def sci(x, d=2):
    """$m\\times10^{e}$ as text for use in math-free context"""
    m, e = f"{x:.{d}e}".split("e")
    return f"${m}\\times10^{{{int(e)}}}$"


def thousands(x):
    return f"{int(round(x)):,}".replace(",", "\\,")


def grep(pat, text=REPORT, grp=1):
    m = re.search(pat, text)
    if not m:
        sys.exit(f"make_numbers: pattern not found in docs/phase4_report.md: {pat}")
    return m.group(grp)


# ------------------------------------------------------------------ scope constants
mem, ts, sens = rd(P, "memory_model.csv"), rd(P, "time_scores.csv"), rd(P, "time_sensitivity.csv")
ident, fit, cs = rd(P, "time_identifiability.csv"), rd(P, "time_fit.csv"), rd(P, "counter_summary.csv")
xo, ovl, dec = rd(P, "offload_crossover.csv"), rd(P, "offload_vs_local.csv"), rd(D, "phase3_decomposition.csv")
rng, rep, gf = rd(D, "phase3_pc_sim_range.csv"), rd(D, "reproducibility.csv"), rd(D, "grover_findings.csv")
cv, p1, pred = rd(D, "counter_validity.csv"), rd(P, "phase1_infidelity.csv"), rd(P, "time_predictions.csv")
fl = rd(P, "offload_floor.csv").set_index("board")
aud = rd(P, "audit_points.csv")
sel = cv[cv.selected.astype(bool)]

WEAK_MIN = int(grep(r"WEAK_MIN\s*=\s*(\d+)", open(os.path.join(ROOT, "analysis", "common", "weak.py")).read()))
put("WeakMin", WEAK_MIN)
put("Reps", int(aud[aud.phase == 2].reps.max()))
put("Baud", grep(r"baud rate \((\d+ \d+)\)").replace(" ", ""))
put("BaudSp", grep(r"baud rate \((\d+ \d+)\)").replace(" ", "\\,"))
put("PointCapS", grep(r"POINT_TIME_CAP_S raised above (\d+) s"))
put("PointCapH", int(grep(r"POINT_TIME_CAP_S raised above (\d+) s")) // 3600)
put("NSessions", grep(r"all (\d+) session sidecars"))
put("ProvDirty", grep(r"\*\*Provenance:\*\* (\d+) of \d+ sessions carry a dirty"))
put("ProvCommitted", grep(r"(\d+) have a firmware source hash equal to a committed tree"))
put("ProvUncommitted", grep(r"and (\d+) ran uncommitted firmware"))
put("AmpBytes", 8)   # complex float32 = 2 x 4 B (firmware/common/qsim.hpp Cplx); stated in the report as '8 bytes = complex float32'
assert "8 bytes = complex float32" in REPORT

# ------------------------------------------------------------------ memory
q = mem[mem.circuit == "qft"].set_index(["board", "predictor"])
pick = {"uno": ("uno", "static_ram"), "esp8266": ("esp8266", "total_free_heap"), "esp32": ("esp32", "largest_block")}
for b, key in pick.items():
    r = q.loc[key]
    put("MemWall" + TAG[b], int(r.wall_n))
    put("MemOk" + TAG[b], int(r.last_ok_n))
    put("MemPred" + TAG[b], int(r.n_max_pred))
    put("MemB" + TAG[b], thousands(r.B_bytes))
rt = q.loc[("esp32", "total_free_heap")]
put("MemPredEspHiTotal", int(rt.n_max_pred))
put("MemBEspHiTotal", thousands(rt.B_bytes))
put("MemStateAtWallEspHi", thousands(8 * 2 ** int(rt.wall_n)))
put("MemStateAtOkEspHi", thousands(8 * 2 ** int(rt.last_ok_n)))
uno_b = mem[(mem.board == "uno") & (mem.circuit != "grover")]
put("MemOverheadUnoMin", int(uno_b.overhead_bytes.min()))
put("MemOverheadUnoMax", int(uno_b.overhead_bytes.max()))
put("MemSramUno", thousands(float(uno_b.B_bytes.iloc[0] + uno_b.overhead_bytes.iloc[0])))
walled = mem[mem.wall_n.notna() & mem.circuit.isin(["h_all", "bell_ghz", "qft"])]
put("MemWallRows", int(walled.groupby(["board", "circuit"]).ngroups))
put("MemAgreeAll", int(walled[walled.predictor.isin(["static_ram", "total_free_heap"]) & (walled.board != "esp32")].match.all()
                       and walled[(walled.board == "esp32") & (walled.predictor == "largest_block")].match.all()))
# grover time limit: last ok n, reps and minutes per run (Phase 2, selected sessions)
for b in ("esp8266", "esp32"):
    g = pred[(pred.board == b) & (pred.circuit == "grover")].sort_values("n").iloc[-1]
    put("GroverLastN" + TAG[b], int(g.n))
    put("GroverLastReps" + TAG[b], int(g.reps))
    put("GroverLastMin" + TAG[b], f0(g.median_us / 6e7))
bound = {b: mem[(mem.board == b) & (mem.circuit == "grover")].n_max_pred.max() for b in ("esp8266", "esp32")}
put("GroverPredEspLo", int(mem[(mem.board == "esp8266") & (mem.circuit == "grover")].n_max_pred.iloc[0]))
put("GroverPredEspHi", int(mem[(mem.board == "esp32") & (mem.circuit == "grover") & (mem.predictor == "largest_block")].n_max_pred.iloc[0]))

# memory table
rows = []
for b in BOARDS:
    for pr in sorted(mem[mem.board == b].predictor.unique(), key=lambda s: s != pick[b][1]):
        m = mem[(mem.board == b) & (mem.predictor == pr) & mem.circuit.isin(["h_all", "bell_ghz", "qft"])]
        lo, hi = m.B_bytes.min(), m.B_bytes.max()
        bs = thousands(lo) if lo == hi else f"{thousands(lo)}--{thousands(hi)}"
        pr_lbl = {"static_ram": "static SRAM", "total_free_heap": "total free heap", "largest_block": "largest block"}[pr]
        pn = int(m.n_max_pred.iloc[0])
        ok = int(m.last_ok_n.iloc[0])
        wn = int(m.wall_n.iloc[0])
        mark = "" if (m.match.astype(str) == "True").all() else " (wrong)"
        rows.append(f"{NAME[b]} & {pr_lbl} & {bs} & {pn}{mark} & {ok} & {wn} & {m.wall_evidence.iloc[0].split(' ')[0].replace('_', chr(92) + '_')} \\\\")
open(os.path.join(OUT, "tables", "memory.tex"), "w").write(
    "\\begin{tabular}{@{}llrrrrl@{}}\n\\toprule\nBoard & $B$ from & $B$ (B) & Pred. $n_{\\max}$ & Last ok & First fail & Evidence \\\\\n\\midrule\n"
    + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ------------------------------------------------------------------ time models
def sc(model, scope, test, board):
    r = ts[(ts.model == model) & (ts.scope == scope) & (ts.test_set == test) & (ts.board == board)].iloc[0]
    return float(r.mape_pct), int(r.n_points)


PR, WK, CL = "primary (non-weak)", "secondary (weak included)", "clean (non-weak, hash class A)"
for mod, nm in (("M1", "One"), ("M2", "Two")):
    v, n = sc(mod, "all", PR, "all")
    put(f"Mape{nm}", f0(v))
    put(f"MapeDec{nm}", f1(v))
    put(f"NTest{nm}", n)
    v, n = sc(mod, "all", CL, "all")
    put(f"Mape{nm}Clean", f0(v))
    put(f"MapeDec{nm}Clean", f1(v))
    put(f"NClean{nm}", n)
    put(f"Mape{nm}Weak", f1(sc(mod, "all", WK, "all")[0]))
    put(f"NWeak{nm}", sc(mod, "all", WK, "all")[1])
    put(f"Mape{nm}NoGrover", f0(sc(mod, "no_grover", PR, "all")[0]))
    for b in BOARDS:
        put(f"Mape{nm}{TAG[b]}", f0(sc(mod, "all", PR, b)[0]))
        put(f"Mape{nm}{TAG[b]}Clean", f0(sc(mod, "all", CL, b)[0]))
put("MapeTwoIdent", f1(sc("M2", "identifiable", PR, "all")[0]))
put("NTwoIdent", sc("M2", "identifiable", PR, "all")[1])
put("MapeOneIdent", f1(sc("M1", "identifiable", PR, "all")[0]))
put("MapeOneCOne", f0(sc("M1c", "all", PR, "all")[0]))
put("NCOne", sc("M1c", "all", PR, "all")[1])
put("MapeTwoG", f0(sc("M2g", "all", PR, "all")[0]))
sv = sens.set_index(["n_test", "model", "scope"])
for k, nm in ((2, "Two"), (3, "Three"), (4, "Four")):
    put(f"SensTwoAll{nm}", f1(sv.loc[(k, "M2", "all")].mape_primary))
    put(f"SensTwoIdent{nm}", f1(sv.loc[(k, "M2", "identifiable")].mape_primary))
    put(f"SensOneAll{nm}", f1(sv.loc[(k, "M1", "all")].mape_primary))
    put(f"IdBoards{nm}", sv.loc[(k, "M2", "all")].identifiable_boards.replace("esp32", "ESP32").replace("esp8266", "ESP8266").replace("uno", "Uno").replace(",", ", "))
put("SensTwoIdentMin", f1(min(sv.loc[(k, "M2", "identifiable")].mape_primary for k in (2, 3, 4))))
put("SensTwoIdentMax", f1(max(sv.loc[(k, "M2", "identifiable")].mape_primary for k in (2, 3, 4))))
put("SensTwoAllMin", f1(min(sv.loc[(k, "M2", "all")].mape_primary for k in (2, 3, 4))))
put("SensTwoAllMax", f1(max(sv.loc[(k, "M2", "all")].mape_primary for k in (2, 3, 4))))
# gap between M2 weak-switch
put("WeakSwitchWith", f1(sc("M2", "all", WK, "all")[0]))
put("WeakSwitchWithout", f1(sc("M2", "all", PR, "all")[0]))
# fitted constants and the physical-plausibility check
mf = fit[fit.model == "M2"].set_index("board")
fcpu = {}
for b in BOARDS:
    f = [x for x in sorted(glob.glob(os.path.join(ROOT, "data", "raw", "phase2", b, "h_all", "with_ref", "env", "*.json"))) if not x.endswith(".ref.json")]
    fcpu[b] = float(json.load(open(f[0]))["f_cpu"]) / 1e6
    put("Fcpu" + TAG[b], f0(fcpu[b]))
put("CyclesCnotEspLo", f2(mf.loc["esp8266"].c_CNOT * fcpu["esp8266"]))
put("CnotEspLo", f4(mf.loc["esp8266"].c_CNOT))
put("ACallEspLo", f1(mf.loc["esp8266"].a_call))
for k in ("c_H", "c_CNOT", "c_CPHASE"):
    put("Cycles" + k.replace("c_", "").replace("CPHASE", "Cphase").replace("CNOT", "Cnot") + "EspHi", f0(mf.loc["esp32"][k] * fcpu["esp32"]))
for b in BOARDS:
    put("KernelRatio" + TAG[b], f2(ident[ident.board == b].M2_min_over_max_kernel_coef.iloc[0]))
put("CondMaxTwo", f1(ident.M2_board_cond.max()))
assert "condition-number cap (1e+04)" in REPORT
put("CondCap", "$10^{4}$")
# identifiability on single series
put("SeriesAloneIdent", int(ident.M2_series_alone_identifiable.sum()))

# time-model table
def row(model, lbl):
    cells = []
    for tst in (PR, CL):
        v, n = sc(model, "all", tst, "all")
        cells.append(f"{v:.1f} ({n})")
    for b in BOARDS:
        v, n = sc(model, "all", PR, b)
        cells.append(f"{v:.1f} ({n})")
    return f"{lbl} & " + " & ".join(cells) + " \\\\"


tt = ["\\begin{tabular}{@{}lccccc@{}}\n\\toprule\n & all & clean & Uno & ESP8266 & ESP32 \\\\\n\\midrule"]
for mo, lb in (("M1", "M1 (1 constant / board)"), ("M1c", "M1c (1 / board and circuit)"), ("M2", "M2 (per gate kind)"), ("M2g", "M2g (M2 without grover)")):
    tt.append(row(mo, lb))
tt.append("\\midrule\nheld out & M1 & M2 & M2, ident. & & \\\\")
for k in (2, 3, 4):
    c = [f"{sv.loc[(k, mo, 'all')].mape_primary:.1f} ({int(sv.loc[(k, mo, 'all')].n_primary)})" for mo in ("M1", "M2")]
    i = f"{sv.loc[(k, 'M2', 'identifiable')].mape_primary:.1f} ({int(sv.loc[(k, 'M2', 'identifiable')].n_primary)})"
    tt.append(f"largest {k} n & {c[0]} & {c[1]} & {i} & & \\\\")
tt.append("\\bottomrule\n\\end{tabular}")
open(os.path.join(OUT, "tables", "time.tex"), "w").write("\n".join(tt) + "\n")

# ------------------------------------------------------------------ counter
cn = cs[cs.subset == "median>=100us, not weak"].set_index("board")
for b in BOARDS:
    put("RatioMed" + TAG[b], f4(cn.loc[b].median_of_median_ratio))
    put("RatioN" + TAG[b], int(cn.loc[b].n_points))
    put("RatioLongS" + TAG[b], f"{cn.loc[b].longest_micros_us / 1e6:.3g}")
    p2 = sel[(sel.phase == 2) & (sel.board == b)]
    put("UsableN" + TAG[b], int(p2.usable.sum()))
    put("RecordedN" + TAG[b], len(p2))
cu = cs[cs.subset == "median>=100us"].set_index("board")
put("RatioMedEspHiAll", f4(cu.loc["esp32"].median_of_median_ratio))
put("EspHiWorstPct", f2((1 - cu.loc["esp32"].ratio_min) * 100))
put("UnoBelowPct", f1((1 - cu.loc["uno"].median_of_median_ratio) * 100))
put("EspHiLongest", f0(cs[(cs.board == "esp32")].longest_micros_us.max() / 1e6))
put("TMaxS", sci(float(cv.T_max_s.iloc[0]), 3))
put("TMaxDays", f1(float(cv.T_max_s.iloc[0]) / 86400))
put("WrapS", f"{float(grep(r'k x (53[.]d+) s'.replace('[.]d', chr(92) + '.' + chr(92) + 'd'))):.3f}")
put("PpmPc", grep(r"the (17\.5) ppm"))
put("SelfTestPass", grep(r"passed (\d+) of \d+ scenarios"))
put("SelfTestAll", grep(r"passed \d+ of (\d+) scenarios"))
put("SelfTestLo", grep(r"reads (\d\.\d) to \d\.\d us longer"))
put("SelfTestHi", grep(r"reads \d\.\d to (\d\.\d) us longer"))
put("RFiveLo", grep(r"outside \[(0\.5), 2\.0\]"))
put("RFiveHi", grep(r"outside \[0\.5, (2\.0)\]"))
put("RFiveMs", grep(r"within (\d) ms of k x"))
put("PairedMin", WEAK_MIN)
# timer resolution
put("UnoResUs", grep(r"Uno `micros\(\)` resolution is (\d) us"))
put("EspResUs", grep(r"ESP boards (\d) us"))
put("ModelFloorUs", grep(r"median >= (\d+) us is a fit point"))
put("CounterTickNs", f1(1e3 / float(grep(r"apb_hz` = (\d+) MHz"))))
put("ApbMHz", grep(r"apb_hz` = (\d+) MHz"))
put("DupNineRows", grep(r"ESP32 grover n=9: (\d+) rows"))
put("DupNineIndep", grep(r"ESP32 grover n=9: \d+ rows, (\d+) independent"))
put("DupTenIndep", grep(r"ESP32 grover n=10: \d+ rows, (\d+) independent"))

# ------------------------------------------------------------------ added after review
tq = pred[(pred.board == "uno") & (pred.circuit == "qft") & (pred.role == "test") & (pred.weak.astype(str) == "False")]
put("MapeTwoUnoQft", f0((abs(tq.pred_M2 - tq.median_us) / tq.median_us).mean() * 100))
for b in ("uno", "esp8266"):
    put("RatioMin" + TAG[b], f4(cn.loc[b].ratio_min))
    put("RatioMax" + TAG[b], f4(cn.loc[b].ratio_max))
put("PrevMtwoEspLo", grep(r"M2 test MAPE, ESP8266 \| ([\d.]+) %"))
put("PrevMoneEspHi", grep(r"M1 test MAPE, ESP32 \| ([\d.]+) %"))
put("GateSeqMax", grep(r"for all four circuits at n = 2\.\.(\d+) and grover n=(\d+)"))
put("GateSeqGrover", grep(r"for all four circuits at n = 2\.\.(\d+) and grover n=(\d+)", REPORT, 2))
put("KMaxN", grep(r"k is equal for every n = 2\.\.(\d+)"))
put("AerMaxN", grep(r"Aer up to n=(\d+)"))
# ------------------------------------------------------------------ offload
PROTO = open(os.path.join(ROOT, "pc", "phase3_offload", "protocol.py"), encoding="utf-8").read()
put("BitsPerByte", grep(r"frame bytes x (\d+) bit / baud"))
put("SelectDate", grep(r"set on (\d{4}-\d{2}-\d{2}) after the data and scores were known"))
put("ReqBytes", grep(r"Request \(MCU -> PC\), (\d+) bytes", PROTO))
put("RespBytes", grep(r"Response \(PC -> MCU\), (\d+) bytes", PROTO))
for b in BOARDS:
    put("FloorMs" + TAG[b], f1(ovl[(ovl.board == b) & (ovl.n <= 4)].median_us_offload.median() / 1000))
s3 = dec[dec.selected].copy()
put("NOffPoints", len(s3))
s3["iqr_rel"] = (s3.e2e_q3_us - s3.e2e_q1_us) / s3.e2e_us
put("IqrThresh", grep(r"exceeds (\d+) % in \d+ % of the"))
assert float(M["IqrThresh"]) == 20     # the code below uses 0.2
put("IqrOver", f0((s3.iqr_rel > 0.2).mean() * 100))
put("WireMs", f2(s3.wire_us.median() / 1000))
small = s3[s3.pc_sim_us < 20000]
put("ResidMed", f0(small.residual_us.median()))
put("ResidLo", f0(small.residual_us.quantile(.25)))
put("ResidHi", f0(small.residual_us.quantile(.75)))
put("SimSmallMs", 20)
r6 = rng[rng.n >= 6].assign(sp=lambda d: d.pc_sim_max_us / d.pc_sim_min_us)
put("SimSpreadMed", f2(r6.sp.median()))
put("SimSpreadMax", f2(r6.sp.max()))
put("SimSpreadAbout", f0(round(r6.sp.median())))
g9 = rng[(rng.circuit == "grover") & (rng.n == 9)].iloc[0]
put("GroverNineSimLo", f1(g9.pc_sim_min_us / 1e6))
put("GroverNineSimHi", f1(g9.pc_sim_max_us / 1e6))
put("GroverNineSessions", int(g9.pc_sim_sessions))
put("OffNMaxUno", int(s3[(s3.board == "uno")].n.max()))
put("OffNMaxEspLo", int(s3[(s3.board == "esp8266")].n.max()))
put("OffNMaxEspHi", int(s3[(s3.board == "esp32")].n.max()))
put("NCross", len(xo))
both = ((xo.fast_kind == "bracket") & (xo.slow_kind == "bracket")).sum()
put("CrossBoth", int(both))
put("CrossNone", int(((xo.fast_kind == "none") | (xo.slow_kind == "none")).sum()))
put("CrossBelow", int(((xo.fast_kind == "below") | (xo.slow_kind == "below")).sum()))
lab = pd.concat([xo.fast_labels, xo.slow_labels]).dropna().astype(str)
put("LabNoise", int(lab.str.contains("within noise").sum()))
put("LabWeak", int(lab.str.contains("weak").sum()))
put("CrossMinN", int(min(xo.n_fast_hi.min(), xo.n_slow_hi.min())))
put("CrossMaxN", int(max(xo.n_fast_hi.max(), xo.n_slow_hi.max())))
put("NOvl", len(ovl))
# crossover table
def brk(r, bd):
    lo, hi, kd = getattr(r, f"n_{bd}_lo"), getattr(r, f"n_{bd}_hi"), getattr(r, f"{bd}_kind")
    return f"{int(lo)}--{int(hi)}" if kd == "bracket" else (f"$\\le${int(hi)}" if kd == "below" else f"none")


def flag(r, bd):
    s = getattr(r, f"{bd}_labels")
    s = "" if not isinstance(s, str) else s
    out = ""
    if "within noise" in s:
        out += "$^{\\dagger}$"
    if "weak" in s:
        out += "$^{\\ddagger}$"
    return out


xrows = []
order = {"uno": 0, "esp8266": 1, "esp32": 2}
for r in sorted(xo.itertuples(), key=lambda r: (order[r.board], CIRC.index(r.circuit))):
    xrows.append(f"{NAME[r.board]} & {r.circuit.replace('_', chr(92) + '_')} & {int(r.n_first)}--{int(r.n_last)} & {brk(r, 'fast')}{flag(r, 'fast')} & {brk(r, 'slow')}{flag(r, 'slow')} \\\\")
open(os.path.join(OUT, "tables", "crossover.tex"), "w").write(
    "\\begin{tabular}{@{}llccc@{}}\n\\toprule\nBoard & Circuit & Measured $n$ & Fast PC & Slow PC \\\\\n\\midrule\n" + "\n".join(xrows) + "\n\\bottomrule\n\\end{tabular}\n")

# ------------------------------------------------------------------ reproducibility
r2 = rep[rep.phase == 2]
put("ReproPtwoN", len(r2))
put("ReproPtwoMaxPct", f4(r2.max_rel_diff.max() * 100))
put("ReproPtwoMedPct", f"{r2.max_rel_diff.median() * 100:.5f}")
r3 = rep[rep.phase == 3]
e, sm_ = r3[r3.quantity == "e2e_us"], r3[r3.quantity == "pc_sim_us"]
rs = r3[r3.quantity == "residual_us"]
put("ReproPthreeN", len(e))
put("ReproPthreeE", f0(e.max_rel_diff.median() * 100))
put("ReproPthreeEMax", f0(e.max_rel_diff.max() * 100))
put("ReproPthreeSim", f0(sm_.max_rel_diff.median() * 100))
put("ReproPthreeResid", f0(rs.max_abs_diff_us.median()))

# ------------------------------------------------------------------ Phase 1 and grover precision
for c in ("h_all", "bell_ghz", "qft"):
    a = p1[(p1.circuit == c)]
    put("PoneMax" + {"h_all": "Hall", "bell_ghz": "Bell", "qft": "Qft"}[c], sci(a.infidelity.max(), 2))
    put("PoneAllPass" + {"h_all": "Hall", "bell_ghz": "Bell", "qft": "Qft"}[c], int(a["pass_1e-3"].all()))
a = p1[p1.circuit == "grover"]
okg = a[a["pass_1e-3"]]
assert all(int(M["PoneAllPass" + k]) for k in ("Hall", "Bell", "Qft")), "the paper says h_all, bell_ghz and qft pass at every tested n"
put("PoneGroverLastPass", int(okg.n.max()))
put("PoneGroverFirstFail", int(a[~a["pass_1e-3"]].n.min()))
put("PoneGroverMaxPass", sci(okg.infidelity.max(), 2))
put("PoneGate", "$10^{-3}$")
tr = (p1.tvd / p1.infidelity)
put("TvdRatioMin", f4(tr.min()))
put("TvdRatioMax", f4(tr.max()))
assert 0.49 < tr.min() and tr.max() < 0.51, "the paper says TVD equals half of the infidelity in the Phase 1 data"
# sensitivity of the gate: last passing grover n and whether the other circuits still pass at a tighter and a looser threshold
for tag, thr, txt in (("Lo", 1e-4, "$10^{-4}$"), ("Hi", 1e-2, "$10^{-2}$")):
    put("PoneThresh" + tag, txt)
    put("PoneGroverLastPass" + tag, int(a[a.infidelity <= thr].n.max()))
    assert (p1[p1.circuit != "grover"].infidelity <= thr).all(), "the other circuits must pass at every threshold shown"
# primary Phase 1 criterion (set after the data were seen): infidelity of the NORMALISED float32 state (its direction) at the gate and at a tighter / looser value
for tag, thr in (("", 1e-3), ("Lo", 1e-4), ("Hi", 1e-2)):
    ok = gf[gf.f32_direction_infidelity <= thr]
    put("PoneDirLastPass" + tag, int(ok.n.max()))
put("PoneDirFirstFail", int(gf[gf.f32_direction_infidelity > 1e-3].n.min()))
assert int(M["PoneDirFirstFail"]) == int(M["PoneDirLastPass"]) + 1, "direction criterion must fail from one n on"
g = gf.set_index("n")
put("GroverTwelveRaw", f"{g.loc[12].f32_infid_vs_ideal_raw:.3f}")
put("GroverTwelvePm", f2(g.loc[12].f32_p_marked_raw))
put("GroverTwelveNH", thousands(g.loc[12].n_H))
put("GroverTwelveK", int(g.loc[12].k_firmware_float32))
put("DirMaxTwelve", sci(float(gf[gf.n <= 12].f32_direction_infidelity.max()), 1))
put("DirThirteen", sci(g.loc[13].f32_direction_infidelity, 1))
put("DirFourteen", sci(g.loc[14].f32_direction_infidelity, 1))
put("DirGate", "$10^{-3}$")
put("DoubleMax", sci(float(gf.f64_infid_vs_ideal_raw.abs().max()), 1))
put("AerMax", sci(float(gf[gf.n <= 12].aer_infid_vs_ideal_raw.abs().max()), 1))
ratio = gf[(gf.n >= 8) & (gf.n <= 13)].f32_predicted_over_measured_log_loss
put("LogLossLo", f2(ratio.min()))
put("LogLossHi", f2(ratio.max()))
put("LogLossOverPct", f0((ratio.mean() - 1) * 100))
put("LogLossFourteen", f2(g.loc[14].f32_predicted_over_measured_log_loss))
c32 = np.float32(0.70710677)
rel = float(c32) / (1 / np.sqrt(2)) - 1
put("ConstRelErr", sci(abs(rel), 2))
put("NormPerH", sci(abs(2 * float(c32) ** 2 - 1), 2))
put("GroverNminPtheory", int(gf.loc[gf[gf.n >= 3].p_theory_firmware_k.idxmin()].n))
put("GroverPtheoryMin", f4(gf[gf.n >= 3].p_theory_firmware_k.min()))
put("GateCrossN", grep(r"(\d+) of \d+ \(circuit, n\) pairs equal"))
put("GateCrossAll", grep(r"\d+ of (\d+) \(circuit, n\) pairs equal"))

put("PyVer", grep(r"Python \| (\d+\.\d+\.\d+)", open(os.path.join(ROOT, "README_REPRODUCE.md")).read()))
put("WeakFirst", {"10": "ten"}[grep(r"the first analysis used (\d+) repetitions")])
wk = pred[pred.weak.astype(str) == "True"]
for b in ("esp8266", "esp32"):
    ns = sorted(wk[(wk.board == b) & (wk.circuit == "grover")].n.astype(int))
    put("WeakPtwo" + TAG[b], ",".join(map(str, ns)))
w3 = dec[dec.selected & (dec.requests < WEAK_MIN) & (dec.circuit == "grover")]
for b in ("esp8266", "esp32"):
    put("WeakPthree" + TAG[b], ",".join(map(str, sorted(w3[w3.board == b].n.astype(int)))) or "none")
# ------------------------------------------------------------------ data scope (audit)
ser = rd(P, "audit_series.csv")
put("NSeries", len(aud.groupby(["board", "circuit"])))
p2ok = aud[(aud.phase == 2) & (aud.terminal_status == "ok")]
put("NPtwoPoints", len(p2ok))
put("NPthreePoints", len(aud[(aud.phase == 3) & (aud.terminal_status == "ok")]))
put("MixedPoints", int((aud[aud.terminal_status == "ok"].n_hashes > 1).sum()))

# ------------------------------------------------------------------ write
# only macros that the paper uses are written (an unused \\newcommand is a sign of a stale claim)
usedtxt = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(OUT, "sections", "*.tex")) + glob.glob(os.path.join(OUT, "tables", "*.tex"))
                  + [os.path.join(OUT, "main.tex")])
names = sorted(k for k in M if re.search(r"\\" + k + r"(?![A-Za-z])", usedtxt))
print("not used, not written:", sorted(set(M) - set(names)))
with open(os.path.join(OUT, "numbers.tex"), "w") as f:
    f.write("% generated by analysis/paper/make_numbers.py -- do not edit\n")
    for k in names:
        f.write(f"\\newcommand{{\\{k}}}{{{M[k]}}}\n")
print(f"{len(M)} macros -> paper/numbers.tex; tables: memory, time, crossover")
