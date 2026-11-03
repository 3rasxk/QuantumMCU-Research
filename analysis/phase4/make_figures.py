"""Phase 4 figures F1-F5 + tables/phase4_memory_wall.tex. One entry point:  python3 analysis/phase4/make_figures.py

Recomputes every model from data/raw (via model.py), then draws. Output is byte-identical across runs
(no timestamps in PDF/PNG metadata). Style: serif, Computer Modern mathtext, TrueType (type 42) fonts, white background.
"""
import os
import sys

os.environ.setdefault("SOURCE_DATE_EPOCH", "1767225600")  # fixed, so no library stamps the wall-clock into the output
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

logging.getLogger("fontTools").setLevel(logging.ERROR)  # fontTools warns about the fixed SOURCE_DATE_EPOCH
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

import p4common as C
import model as M
import timemodel as TM

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"], "mathtext.fontset": "cm",
    "pdf.fonttype": 42, "ps.fonttype": 42, "figure.facecolor": "white", "axes.facecolor": "white",
    "savefig.facecolor": "white", "font.size": 7, "axes.labelsize": 7.5, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
    "legend.fontsize": 6.5, "axes.linewidth": 0.6, "lines.linewidth": 1.0, "lines.markersize": 3.4,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "axes.grid": False, "figure.dpi": 100,
})
COL = {"uno": "#0072B2", "esp8266": "#E69F00", "esp32": "#009E73"}      # Okabe-Ito: colour-blind safe, fixed per board
MRK = {"h_all": "o", "bell_ghz": "s", "qft": "^", "grover": "D"}        # fixed per circuit
W1, W2 = 3.5, 7.16                                                       # IEEE single / double column width, inches

META_PDF = {"Creator": "", "Producer": "", "CreationDate": None, "Title": ""}
META_PNG = {"Software": None}


def save(fig, name):
    os.makedirs(C.FIG, exist_ok=True)
    fig.savefig(os.path.join(C.FIG, name + ".pdf"), metadata=META_PDF)
    fig.savefig(os.path.join(C.FIG, name + ".png"), dpi=300, metadata=META_PNG)
    plt.close(fig)


WEAK_NOTE = f"Hollow markers: weak evidence (fewer than {C.SMALL_REPS} independent repetitions or requests); not fitted, not in the primary error."


def footnote(fig, text=WEAK_NOTE):
    fig.text(0.01, 0.004, text, fontsize=5.6, ha="left", va="bottom", color="0.25")


def log_ticks(ax):
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.LogFormatterMathtext())


def board_handles():
    return [Line2D([], [], color=COL[b], lw=1.4, label=C.BOARD_LABEL[b]) for b in C.BOARDS]


def circ_handles(fill="k"):
    return [Line2D([], [], color="k", marker=MRK[c], ls="", mfc=fill, label=c) for c in C.CIRCUITS]


# ------------------------------------------------------------------------------------------------ F1
def f1_timing(loc, mem):
    fig, axs = plt.subplots(2, 2, figsize=(W2, 4.5), sharex=True)
    walls = {}
    for _, r in C.load_walls().iterrows():
        walls.setdefault((r.board, r.circuit), r.n)
    for ax, c in zip(axs.flat, C.CIRCUITS):
        for b in C.BOARDS:
            g = loc[(loc.board == b) & (loc.circuit == c)]
            ax.fill_between(g.n, g.q1_us, g.q3_us, color=COL[b], alpha=0.25, lw=0)
            ax.plot(g.n, g.median_us, color=COL[b], lw=0.8)
            small = g.reps < C.SMALL_REPS
            ax.plot(g.n[~small], g.median_us[~small], ls="", marker=MRK[c], color=COL[b], mfc=COL[b])
            ax.plot(g.n[small], g.median_us[small], ls="", marker=MRK[c], color=COL[b], mfc="white", mew=0.9, ms=4.4)
            if (b, c) in walls:
                w = walls[(b, c)]
                ax.axvline(w, color=COL[b], ls=":", lw=1.0)
                ax.annotate(f"wall $n={w}$", (w, 0.0), xycoords=("data", "axes fraction"),
                            xytext=(-2.5, 3), textcoords="offset points", rotation=90, ha="right", va="bottom",
                            fontsize=6, color=COL[b])
        log_ticks(ax)
        ax.set_xlim(1.5, 14.5)
        ax.set_xticks(range(2, 15, 2))
        ax.text(0.03, 0.95, c, transform=ax.transAxes, ha="left", va="top", fontsize=8)
    for ax in axs[1]:
        ax.set_xlabel("Qubits $n$")
    for ax in axs[:, 0]:
        ax.set_ylabel(r"Execution time per run ($\mu$s)")
    hs = board_handles() + [Line2D([], [], color="gray", marker="o", ls="", mfc="white", label=f"weak: $<{C.SMALL_REPS}$ reps"),
                            Line2D([], [], color="gray", ls=":", label="memory wall")]
    fig.legend(handles=hs, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    footnote(fig)
    save(fig, "F1_timing_vs_n")


# ------------------------------------------------------------------------------------------------ F2
def f2_parity(P):
    fig, axs = plt.subplots(1, 2, figsize=(W2, 3.5))
    lim = (30, 1e10)
    for ax, (mod, title) in zip(axs, [("M1", "(a) $t=c_{\\rm board}\\,W(n)$"), ("M2", "(b) per-gate-kind costs")]):
        col = "pred_" + mod
        for b in C.BOARDS:
            for c in C.CIRCUITS:
                g = P[(P.board == b) & (P.circuit == c)]
                fit = g[g.role == "fit"]
                tst = g[g.role == "test"]
                ax.plot(fit[col], fit.median_us, ls="", marker=MRK[c], color=COL[b], mfc=COL[b], mew=0.9, ms=3.6)
                ok = tst[~tst.weak]
                ax.plot(ok[col], ok.median_us, ls="", marker=MRK[c], color=COL[b], mfc="white", mew=0.9, ms=4.6)
                wk = tst[tst.weak]
                ax.plot(wk[col], wk.median_us, ls="", marker=MRK[c], color="0.55", mfc="white", mew=0.7, ms=4.6)
        ax.plot(lim, lim, color="0.4", lw=0.7)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(*lim); ax.set_ylim(*lim)
        ax.set_aspect("equal")
        ax.set_xlabel(r"Predicted time ($\mu$s)"); ax.set_ylabel(r"Measured median time ($\mu$s)")
        r = TM.score(P, mod)
        ax.text(0.97, 0.04, f"{title}\ntest MAPE $={r['mape']:.0f}\\,\\%$\n({r['n']} held-out points, weak excluded)",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=6.8)
    hs = board_handles() + circ_handles() + [Line2D([], [], color="k", marker="o", ls="", mfc="k", label="fit"),
                                             Line2D([], [], color="k", marker="o", ls="", mfc="white", label="held-out test"),
                                             Line2D([], [], color="0.55", marker="o", ls="", mfc="white", label="held-out, weak (not scored)")]
    fig.legend(handles=hs, loc="lower center", ncol=10, frameon=False, columnspacing=0.9, handletextpad=0.3, fontsize=6, bbox_to_anchor=(0.5, 0.035))
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    footnote(fig, "Hollow grey markers: weak (fewer than %d repetitions); excluded from the fit and from the primary MAPE." % C.SMALL_REPS)
    save(fig, "F2_parity")


# ------------------------------------------------------------------------------------------------ F3
def f3_memory(mem):
    walls = C.load_walls()
    base = mem[mem.circuit != "grover"]   # h_all, bell_ghz, qft agree on every board (checked below)
    rows = []
    for b in C.BOARDS:
        g = base[base.board == b]
        assert g.last_ok_n.nunique() == 1 and g.wall_n.nunique() == 1, "circuits disagree on the wall"
        for pr, gg in g.groupby("predictor", sort=False):
            assert gg.n_max_pred.nunique() == 1
            rows.append(dict(board=b, predictor=pr, pred=int(gg.n_max_pred.iloc[0]), last_ok=int(g.last_ok_n.iloc[0]),
                             wall=int(g.wall_n.iloc[0]), B=float(gg.B_bytes.iloc[0]), over=float(gg.overhead_bytes.iloc[0])))
    R = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(W1, 2.5))
    x = np.arange(len(C.BOARDS))
    ax.bar(x - 0.27, [R[R.board == b].last_ok.iloc[0] for b in C.BOARDS], 0.26, color=[COL[b] for b in C.BOARDS],
           edgecolor="k", lw=0.5)
    for i, b in enumerate(C.BOARDS):
        v = R[R.board == b].last_ok.iloc[0]
        ax.text(i - 0.27, v + 0.2, str(v), ha="center", va="bottom", fontsize=6.5)
        sub = R[R.board == b]
        for j, (_, r) in enumerate(sub.iterrows()):
            xp = i + 0.0 + 0.27 * j
            ok = r.pred == r.last_ok
            ax.bar(xp, r.pred, 0.26, color=COL[b], alpha=0.45, edgecolor="k", lw=0.5, hatch="//")
            ax.text(xp, r.pred + 0.2, str(r.pred), ha="center", va="bottom", fontsize=6.5, color="k" if ok else "#B00020")
            tag = {"static_ram": "SRAM", "total_free_heap": "free heap", "largest_block": "largest\nblock"}[r.predictor]
            ax.text(xp, 0.3, tag, rotation=90, ha="center", va="bottom", fontsize=5.6,
                    bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.8))
    ax.set_xticks(x); ax.set_xticklabels([C.BOARD_LABEL[b] for b in C.BOARDS])
    ax.set_ylabel(r"Largest $n$ that fits")
    ax.set_ylim(0, 16.5)
    ax.legend(handles=[matplotlib.patches.Patch(fc="0.8", ec="k", lw=0.5, label="measured (last $n$ before wall)"),
                       matplotlib.patches.Patch(fc="0.8", ec="k", lw=0.5, hatch="//", label="predicted $\\lfloor\\log_2(B/8)\\rfloor$")],
              loc="upper left", frameon=False, fontsize=6)
    fig.tight_layout()
    save(fig, "F3_memory_wall")
    return R


def memory_table(mem, R):
    ev = {"uno": "build\\_overflow", "esp8266": "malloc\\_failed", "esp32": "malloc\\_failed"}
    pretty = {"static_ram": "static SRAM $-$ overhead", "total_free_heap": "total free heap",
              "largest_block": "largest free block"}
    lines = [r"\begin{tabular}{llrrrrl}", r"\hline",
             r"Board & Predictor $B$ & $B$ (bytes) & Pred. $n_{\max}$ & Last ok $n$ & First failing $n$ & Evidence \\", r"\hline"]
    for _, r in R.iterrows():
        mark = "" if r.pred == r.last_ok else r" (wrong)"
        lines.append(f"{C.BOARD_LABEL[r.board]} & {pretty[r.predictor]} & {int(r.B):,} & {r.pred}{mark} & {r.last_ok} & {r.wall} & {ev[r.board]} \\\\".replace(",", "{,}"))
    g = mem[mem.circuit == "grover"].drop_duplicates("board")
    lines += [r"\hline", r"\end{tabular}"]
    note = ("% h_all, bell_ghz, qft share these values on every board. grover: Uno wall at n=8 (build_overflow), same as above;"
            " ESP8266 and ESP32 grover were never run to a memory wall (time-limited at n=10 and n=12), so their predicted n_max is untested.\n")
    os.makedirs(C.TAB, exist_ok=True)
    open(os.path.join(C.TAB, "phase4_memory_wall.tex"), "w").write(note + "\n".join(lines) + "\n")


# ------------------------------------------------------------------------------------------------ F4
def f4_series(m=None):
    """what F4 plots, per (board, circuit): the rows of the band table (selected Phase 2 local statistics + selected Phase 3 offload band). Used by the coverage test."""
    if m is None:
        m, _ = M.offload_crossover()
    return {(b, c): m[(m.board == b) & (m.circuit == c)].sort_values("n") for b in C.BOARDS for c in C.CIRCUITS}


def f4_offload(m, X):
    """local median with IQR (solid, Phase 2); offload band between the fastest and the slowest observed PC simulation (shaded) with the measured offload
    median (dashed); crossover brackets as bars from n_lo to n_hi at the local time of n_hi (solid = fast bound, dotted = slow bound)"""
    fig, axs = plt.subplots(2, 2, figsize=(W2, 4.8), sharex=True)
    series = f4_series(m)
    for ax, c in zip(axs.flat, C.CIRCUITS):
        for b in C.BOARDS:
            g = series[(b, c)]
            if not len(g):
                continue
            ax.fill_between(g.n, g.q1_us, g.q3_us, color=COL[b], alpha=0.30, lw=0)
            ax.plot(g.n, g.median_us, color=COL[b], lw=1.0, marker=MRK[c], mfc=COL[b], ms=3.0)
            ax.fill_between(g.n, g.fast_us, g.slow_us, color=COL[b], alpha=0.18, lw=0, hatch="////", edgecolor=COL[b])
            ax.plot(g.n, g.e2e_us, color=COL[b], lw=0.9, ls="--")
            wk = g[g.weak_point]                                   # weak: hollow marker on the local median
            if len(wk):
                ax.plot(wk.n, wk.median_us, ls="", marker=MRK[c], mfc="white", mec=COL[b], mew=0.9, ms=4.6)
            row = X[(X.board == b) & (X.circuit == c)].iloc[0]
            for bound, ls_ in (("fast", "-"), ("slow", ":")):
                lo, hi, kind = row[f"n_{bound}_lo"], row[f"n_{bound}_hi"], row[f"{bound}_kind"]
                if kind == "bracket":
                    y = float(g[g.n == int(hi)].median_us.iloc[0])
                    ax.plot([lo, hi], [y, y], color=COL[b], lw=2.4, ls=ls_, solid_capstyle="butt", zorder=5)
                elif kind == "below":
                    y = float(g[g.n == int(hi)].median_us.iloc[0])
                    ax.annotate("", xy=(hi, y), xytext=(hi - 0.9, y), arrowprops=dict(arrowstyle="->", color=COL[b], lw=1.2, ls=ls_))
        log_ticks(ax)
        ax.set_xlim(1.5, 14.5)
        ax.set_xticks(range(2, 15, 2))
        ax.text(0.03, 0.95, c, transform=ax.transAxes, ha="left", va="top", fontsize=8)
    for ax in axs[1]:
        ax.set_xlabel("Qubits $n$")
    for ax in axs[:, 0]:
        ax.set_ylabel(r"Time per run ($\mu$s)")
    from matplotlib.patches import Patch
    hs = board_handles() + [Line2D([], [], color="gray", lw=1, label="local median, IQR shaded (Phase 2)"),
                            Patch(facecolor="gray", alpha=0.25, hatch="////", edgecolor="gray", label="offload band: fastest to slowest PC simulation"),
                            Line2D([], [], color="gray", lw=1, ls="--", label="offload, measured session"),
                            Line2D([], [], color="gray", lw=2.4, label="crossover bracket, fast bound"),
                            Line2D([], [], color="gray", lw=2.4, ls=":", label="crossover bracket, slow bound"),
                            Line2D([], [], color="gray", marker="o", mfc="white", ls="", ms=5, label=f"weak: $<{C.SMALL_REPS}$ reps / requests")]
    fig.legend(handles=hs, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.4)
    fig.tight_layout(rect=(0, 0.07, 1, 0.90))
    footnote(fig, "The offload band reflects the speed of the host PC (the Aer simulation time varies between sessions).\n"
                  "Bars: bracket between two measured n; arrow: offload already faster at the smallest measured n; no bar: no crossover up to the largest measured n.")
    save(fig, "F4_offload_crossover")


# ------------------------------------------------------------------------------------------------ F5
def f5_accuracy(p1, gd=None):
    fig, ax = plt.subplots(figsize=(W1, 2.5))
    sty = {"h_all": "0.15", "bell_ghz": "0.45", "qft": "0.15", "grover": "#B00020"}
    for c in C.CIRCUITS:
        g = p1[p1.circuit == c]
        ax.plot(g.n, g.infidelity, marker=MRK[c], color=sty[c], lw=0.8, mfc="white" if c in ("qft",) else sty[c],
                label=c)
    if gd is not None:
        gg = gd[gd.f32_infid_vs_ideal_normalised.notna()]
        ax.plot(gg.n, gg.f32_infid_vs_ideal_normalised.clip(lower=1e-9), marker="D", color="#B00020", mfc="white", ls=":", lw=0.8,
                label="grover, normalised")
    ax.axhline(1e-3, color="k", ls="--", lw=0.8)
    ax.text(1.0, 1.4e-3, r"$10^{-3}$ threshold", fontsize=6.3, va="bottom")
    log_ticks(ax)
    ax.set_xlabel("Qubits $n$"); ax.set_ylabel(r"Infidelity of the float32 state")
    ax.set_xlim(0.5, 14.5); ax.set_ylim(1e-8, 1)
    ax.set_xticks(range(2, 15, 2))
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=6.3, bbox_to_anchor=(0.0, 1.0))
    fig.tight_layout()
    save(fig, "F5_phase1_accuracy")


def main():
    mem = M.memory_model()
    P, ident, S, V, sens = TM.run_all()
    D = M.counter_agreement()
    M.counter_summary(D)
    m, X = M.offload_crossover()
    loc = C.load_local()
    import audit
    p1 = audit.phase1()
    gdp = os.path.join(C.ROOT, "data", "derived", "grover_diagnosis.csv")
    gd = pd.read_csv(gdp) if os.path.exists(gdp) else None
    f1_timing(loc, mem)
    f2_parity(P)
    R = f3_memory(mem)
    memory_table(mem, R)
    f4_offload(m, X)
    f5_accuracy(p1, gd)
    print("wrote", sorted(os.listdir(C.FIG)))


if __name__ == "__main__":
    main()
