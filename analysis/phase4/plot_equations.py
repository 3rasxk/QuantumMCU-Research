#!/usr/bin/env python3
"""Draws the equations of the paper (Eqs. 1-8, Method section) as one image: data/figures/phase4/equations.png

    .venv/bin/python analysis/phase4/plot_equations.py

The equations are the ones of paper/sections/method.tex and docs/phase4_report.md section 13.1 (checked against the code there); the constants 8 (bytes per
amplitude) and 10 (bits per byte) are read from analysis/phase4/tradeoff.py. matplotlib mathtext cannot typeset aligned blocks, so each equation is one row.
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tradeoff as TO  # noqa: E402

plt.rcParams.update({"mathtext.fontset": "cm", "font.family": "serif", "pdf.fonttype": 42})
A, BITS = TO.AMP_BYTES, TO.BITS_PER_BYTE
OUT = os.path.join(TO.C.ROOT, "data", "figures", "phase4", "equations.png")

ROWS = [
    ("(1)  Memory", rf"$M(n)={A}\cdot 2^{{n}}\ \mathrm{{bytes}},\qquad n_{{\max}}=\lfloor \log_2 (B/{A})\rfloor$",
     "complex float32; B = bytes available for the state (Uno: SRAM minus static use; ESP8266: free heap at n = 2; ESP32: largest free block)"),
    ("(2)  Local time, M1", r"$T_{\mathrm{local}}(n)=c_b\,G_c(n)\,2^{n}$",
     "one constant per board b;  G_c(n) = gate calls of circuit c (init sweep not counted)"),
    ("(3)  Local time, M2", r"$T_{\mathrm{local}}(n)=\sum_{k\in\{H,\mathrm{CNOT},\mathrm{CP}\}} c_{b,k}\,N_{c,k}(n)\,2^{n}+a_b\,G_c(n)$",
     "non-negative least squares on relative error; G_c = N_H + N_CNOT + N_CP"),
    ("(4)  Gate counts", r"$G_{\mathrm{h\_all}}=n,\quad G_{\mathrm{bell\_ghz}}=n,\quad G_{\mathrm{qft}}=n+\frac{n(n-1)}{2}$",
     ""),
    ("", r"$G_{\mathrm{grover}}=n+k(n)\,(16\cdot 3^{\,n-3}+8n-6)\ \ (n\geq 3),\qquad k(n)=\max(\lfloor \frac{\pi}{4}\sqrt{2^{n}}\rfloor,1)$",
     "closed form of the multi-controlled-gate recursion; k(n) in float32 as in the firmware"),
    ("(5)  Accuracy", r"$\mathrm{MAPE}=\frac{100}{N}\sum_{i=1}^{N}\frac{|T_i^{\mathrm{pred}}-T_i^{\mathrm{meas}}|}{T_i^{\mathrm{meas}}}$",
     "over the non-weak held-out points"),
    ("(6)  Offload time", rf"$T_{{\mathrm{{off}}}}(n)=T_{{\mathrm{{wire}}}}+T_{{\mathrm{{res}},b}}(n)+T_{{\mathrm{{pc}},c}}(n),\qquad T_{{\mathrm{{wire}}}}=\frac{{{BITS}\,L_{{\mathrm{{frame}}}}}}{{\mathrm{{baud}}}}$",
     "L_frame = request + response frame (bytes per request); T_pc = PC simulation, as a range [min, max] over the observed sessions"),
    ("(7)  Crossover", r"$n^{*}=\min\{\,n:\ T_{\mathrm{off}}(m)<T_{\mathrm{local}}(m)\ \ \forall\, m\geq n\ \mathrm{measured}\}$",
     "reported as a bracket of two measured n, for T_pc min (fast) and max (slow); no interpolation"),
    ("(8)  Grover reference", r"$P_{\mathrm{marked}}=\sin^{2}\left((2k+1)\theta\right),\qquad \theta=\arcsin\left(2^{-n/2}\right)$",
     "k = iteration count of the firmware"),
]


def main():
    H = 15.2
    fig, ax = plt.subplots(figsize=(11, H))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, H)
    ax.axis("off")
    y = H - 0.5
    for title, eq, note in ROWS:
        if title:
            ax.text(0.2, y, title, fontsize=12, color="gray", va="center")
            y -= 0.7
        ax.text(0.5, y, eq, fontsize=19, va="center")
        y -= 0.65
        if note:
            ax.text(0.5, y, note, fontsize=9.5, color="#444444", va="center")
            y -= 0.5
        y -= 0.45
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    print("wrote", os.path.relpath(OUT, TO.C.ROOT))


if __name__ == "__main__":
    main()
