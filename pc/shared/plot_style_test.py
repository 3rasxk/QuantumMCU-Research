#!/usr/bin/env python3
# plot_style_test.py -- tests for the clean plot style helper (pc/shared/plot_style.py) on SYNTHETIC data in a temp dir.
# Nothing here reads data/raw or writes under the real data/. No pytest (same style as the other *_test.py files).
# Run: .venv/bin/python pc/shared/plot_style_test.py

import getpass
import itertools
import os
import re
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import plot_style as ps  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
PASSED = FAILED = 0
GRAY_MIN_DIFF = 0.04     # min mean |gray diff| (0..1) per ink pixel between any two rendered series styles


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"FAIL: {name} {extra}")


def render_style(color, ls, marker, path_or_none=None):
    """One series (a rising line with markers) alone on a fixed small canvas, as a grayscale float array."""
    fig, ax = plt.subplots(figsize=(2.4, 1.6), dpi=100)
    ax.axis("off")
    xs = np.arange(2, 9)
    ax.plot(xs, 1.2 ** xs, color=color, linestyle=ls, marker=marker, markersize=ps.MARKER_SIZE, linewidth=ps.LINE_WIDTH)
    ax.set_xlim(1, 9)
    ax.set_ylim(0, 6)
    fig.canvas.draw()
    rgb = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].astype(float) / 255
    plt.close(fig)
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def hex_gray(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


def pair_contrast(a, b):
    """Mean absolute grayscale difference over the pixels where either image has ink (not white)."""
    ink = (a < 0.97) | (b < 0.97)
    return float(np.abs(a - b)[ink].mean())


def test_unique_series_styles():
    ps.apply_clean_style(False)
    styles = [ps.style_for_series(i) for i in range(12)]
    check("12 generic series: unique (color, linestyle, marker)", len(set(styles)) == 12)
    check("12 generic series: unique marker each", len({s[2] for s in styles}) == 12)
    check("60 generic series still unique triples", len({ps.style_for_series(i) for i in range(60)}) == 60)
    fixed = ps.all_fixed_styles()
    check("7 boards+circuits have unique (linestyle, marker)", len(set(fixed.values())) == len(fixed) == 7, str(fixed))
    outcome_markers = {"X", "v", "P", "*", "s"}      # wall, watchdog, hang, time-limited, failed (run charts)
    circuit_markers = set(ps.CIRCUIT_MARKER.values())
    check("circuit markers never reuse a run-chart outcome marker", not (circuit_markers & outcome_markers))
    check("circuit markers differ from board markers", not (circuit_markers & set(ps.BOARD_MARKER.values())))
    check("board_style / circuit_style stable", ps.board_style("esp32") == ps.board_style("esp32")
          and ps.circuit_style("qft") == (ps.CIRCUIT_INK["qft"], ps.CIRCUIT_LINESTYLE["qft"], ps.CIRCUIT_MARKER["qft"]))
    check("CIRCUIT_LINESTYLE kept", ps.CIRCUIT_LINESTYLE == {"h_all": "-", "bell_ghz": "--", "qft": ":", "grover": "-."})


def srgb_to_lab(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    X = 0.4124 * c[0] + 0.3576 * c[1] + 0.1805 * c[2]
    Y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    Z = 0.0193 * c[0] + 0.1192 * c[1] + 0.9505 * c[2]
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    fx, fy, fz = f(X / 0.95047), f(Y), f(Z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def test_colour_only():
    cols = {**{f"circuit:{c}": v for c, v in ps.CIRCUIT_COLOR.items()}, **{f"board:{b}": v for b, v in ps.BOARD_COLOR.items()}}
    check("circuit colours are 4 distinct values", len(set(ps.CIRCUIT_COLOR.values())) == 4)
    worst = min((sum((a - b) ** 2 for a, b in zip(srgb_to_lab(cols[x]), srgb_to_lab(cols[y]))) ** 0.5, x, y)
                for x, y in itertools.combinations([k for k in cols if k.startswith("circuit:")], 2))
    check(f"circuit colours pairwise dE >= 15 (min {worst[0]:.1f}: {worst[1]} vs {worst[2]})", worst[0] >= 15)
    worst = min((sum((a - b) ** 2 for a, b in zip(srgb_to_lab(cols[x]), srgb_to_lab(cols[y]))) ** 0.5, x, y)
                for x, y in itertools.combinations([k for k in cols if k.startswith("board:")], 2))
    check(f"board colours pairwise dE >= 15 (min {worst[0]:.1f})", worst[0] >= 15)


def test_ticks():
    ps.apply_clean_style(False)
    fig, ax = plt.subplots()
    ax.plot([2, 14], [1, 2])
    ps.style_axes(ax)
    fig.canvas.draw()
    ticks = [t for t in ax.get_xticks() if ax.get_xlim()[0] <= t <= ax.get_xlim()[1]]
    check("every integer from 2 to 14 has a tick", all(n in ticks for n in range(2, 15)), str(ticks))
    check("tick marks are long and thick enough to see", matplotlib.rcParams["xtick.major.size"] >= 5 and matplotlib.rcParams["xtick.major.width"] >= 1.0)
    check("tick labels >= 9 pt, axis labels >= 10 pt", matplotlib.rcParams["xtick.labelsize"] >= 9 and matplotlib.rcParams["axes.labelsize"] >= 10)
    plt.close(fig)
    fig, ax = plt.subplots()
    ax.plot([0, 100], [1, 2])
    ps.style_axes(ax)
    fig.canvas.draw()
    check("wide axis thins the integer ticks (<= 25 labels)", len(ax.get_xticks()) <= 26, str(len(ax.get_xticks())))
    plt.close(fig)
    f = ps.plain_number_formatter()
    check("symlog formatter: plain numbers with a real minus", [f(v, 0) for v in (-10, 0, 0.1, 100)] == ["\u221210", "0", "0.1", "100"])


def test_grayscale():
    ps.apply_clean_style(False)
    imgs = {}
    for b in ps.BOARD_ORDER:
        imgs[f"board:{b}"] = render_style(*ps.board_style(b))
    for c in ps.CIRCUIT_ORDER:
        imgs[f"circuit:{c}"] = render_style(*ps.circuit_style(c))
    for i in range(12):
        imgs[f"series{i}"] = render_style(*ps.style_for_series(i))
    # boards and circuits never share an axes with generic series, so compare within each family
    families = {"boards": [k for k in imgs if k.startswith("board:")],
                "circuits": [k for k in imgs if k.startswith("circuit:")],
                "boards+circuits": [k for k in imgs if k.startswith(("board:", "circuit:"))],
                "generic": [k for k in imgs if k.startswith("series")]}
    for fam, keys in families.items():
        worst = min(((pair_contrast(imgs[a], imgs[b]), a, b) for a, b in itertools.combinations(keys, 2)))
        check(f"grayscale contrast, every pair of {fam} styles distinguishable (min {worst[0]:.3f} {worst[1]} vs {worst[2]})",
              worst[0] >= GRAY_MIN_DIFF)
        print(f"  grayscale min pair contrast, {fam}: {worst[0]:.3f} ({worst[1]} vs {worst[2]}), threshold {GRAY_MIN_DIFF}")
    # fill colour alone (what a greyscale print loses): report, not a pass/fail, because markers+linestyles carry identity
    g = sorted((hex_gray(c), c) for c in ps.BOARD_COLOR.values())
    print(f"  board colour luminance (0..1): {[(c, round(v, 2)) for v, c in g]}")


def test_save_png_and_guards(tmp):
    ps.apply_clean_style(False)
    fig, ax = plt.subplots(figsize=(3, 2))
    ax.plot([1, 2, 3], [1, 2, 3])
    out = tmp / "data" / "figures" / "x" / "a.png"
    p = ps.save_png(fig, out, close=False)
    check("save_png writes the PNG", p.exists() and p.suffix == ".png")
    with Image.open(p) as im:
        check("PNG has no Software metadata", "Software" not in im.info, str(im.info))
        check("non-paper PNG is 300 dpi", abs(im.info.get("dpi", (0, 0))[0] - 300) < 1, str(im.info.get("dpi")))
    check("no svg/pdf written next to it", [f.suffix for f in out.parent.iterdir()] == [".png"])
    for bad in (tmp / "data" / "figures" / "a.svg", tmp / "data" / "figures" / "a.pdf"):
        try:
            ps.save_png(fig, bad, close=False)
            check(f"save_png refuses {bad.suffix}", False)
        except ValueError:
            check(f"save_png refuses {bad.suffix}", not bad.exists())
    for sub in ("raw", "archive"):
        target = tmp / "data" / sub / "phase2" / "a.png"
        try:
            ps.save_png(fig, target, close=False)
            check(f"save_png refuses data/{sub}", False)
        except ValueError:
            check(f"save_png refuses data/{sub}", not target.exists())
        try:
            ps.save_pdf(fig, target.with_suffix(".pdf"), close=False)
            check(f"save_pdf refuses data/{sub}", False)
        except ValueError:
            check(f"save_pdf refuses data/{sub}", True)
    q = ps.save_figure_png_only(fig, tmp / "data" / "figures" / "y", "b")
    check("save_figure_png_only -> one png", [x.name for x in q] == ["b.png"])
    q = ps.save_figure(fig, tmp / "data" / "figures" / "z", "c")
    check("save_figure (old name) is PNG-only now", sorted(f.name for f in (tmp / "data" / "figures" / "z").iterdir()) == ["c.png"])
    plt.close(fig)
    svgs = list(tmp.rglob("*.svg"))
    check("no SVG anywhere in the test output", not svgs)
    check("nothing written under the raw-data or archived-data tree of the temp tree",
          not (tmp / "data" / "raw").exists() and not (tmp / "data" / "archive").exists())


def test_paper(tmp):
    ps.apply_clean_style(True)
    rc = matplotlib.rcParams
    check("paper: serif family", rc["font.family"] == ["serif"], str(rc["font.family"]))
    check("paper: pdf/ps fonttype 42", rc["pdf.fonttype"] == 42 and rc["ps.fonttype"] == 42)
    check("paper: label 8 pt, tick 7 pt, legend 7 pt", (rc["axes.labelsize"], rc["xtick.labelsize"], rc["legend.fontsize"]) == (8, 7, 7))
    check("paper: no grid, full box, ticks bottom/left only", not rc["axes.grid"] and rc["axes.spines.top"] and rc["axes.spines.right"]
          and not rc["xtick.top"] and not rc["ytick.right"])
    fig, ax = plt.subplots(figsize=(ps.IEEE_SINGLE_COL_IN, 2.3), layout="constrained")
    for i in range(3):
        c, ls, mk = ps.style_for_series(i)
        ax.plot([2, 3, 4], [1 + i, 2 + i, 4 + i], color=c, linestyle=ls, marker=mk, label=f"s{i}")
    ax.set_xlabel("n")
    ax.set_ylabel("t")
    ax.legend()
    ps.add_panel_label(ax, "(a)")
    check("paper: suptitle is a no-op", ps.suptitle(fig, "A TITLE") is None and fig._suptitle is None)
    ps.add_footnote(fig, "FOOTNOTE")
    check("paper: footnote is a no-op", not any(t.get_text() == "FOOTNOTE" for t in fig.texts))
    pdf = ps.save_pdf(fig, tmp / "paper" / "f.pdf", close=False)
    png = ps.save_png(fig, tmp / "paper" / "f.png", close=False)
    data = pdf.read_bytes()
    check("PDF embeds TrueType fonts (FontFile2), no Type3", b"/FontFile2" in data and b"/Type3" not in data)
    check("PDF has no Creator/Producer/dates/Author", not re.search(rb"/(Creator|Producer|CreationDate|ModDate|Author|Title)\s*[(<]", data))
    with Image.open(png) as im:
        check("paper PNG is 600 dpi", abs(im.info.get("dpi", (0, 0))[0] - 600) < 1, str(im.info.get("dpi")))
        check("paper PNG has no text chunks", not im.info.get("Software") and not any(k in im.info for k in ("Comment", "Author", "Title")))
    png_bytes = png.read_bytes()
    leaks = [str(tmp).encode(), str(Path.home()).encode(), str(REPO).encode(), getpass.getuser().encode(), b"/Users/", b"github", b"http", b"/dev/"]
    check("no path/user/URL/port string in the PDF or PNG bytes", not any(s in data or s in png_bytes for s in leaks),
          str([s for s in leaks if s in data or s in png_bytes]))
    # width at final size
    check("single column figure is 3.5 in wide", abs(fig.get_size_inches()[0] - 3.5) < 1e-6)
    plt.close(fig)
    ps.apply_clean_style(False)
    f2 = plt.figure()
    t = ps.suptitle(f2, "Title", tag=False)
    check("non-paper: suptitle draws", t is not None and t.get_text() == "Title")
    plt.close(f2)


def test_no_minor_ticks(tmp):
    ps.apply_clean_style(False)
    fig, ax = plt.subplots()
    ax.plot([2, 8], [1, 1e6])
    ax.set_yscale("log")
    ps.save_png(fig, tmp / "m" / "m.png", close=False)
    fig.canvas.draw()
    check("log axis has no minor ticks after save_png", len(ax.yaxis.get_minorticklocs()) == 0 and len(ax.xaxis.get_minorticklocs()) == 0)
    plt.close(fig)


def test_band():
    ps.apply_clean_style(False)
    fig, ax = plt.subplots()
    n = ps.iqr_band(ax, [2, 3, 4, 5, 6], [1, 1.5, None, 2, None], [2, 2.5, None, 3, None], "C0")
    check("iqr_band: run of 2 + isolated 1 = 2 pieces, single-value points skipped", n == 2, str(n))
    check("iqr_band: no band when every point is single-valued", ps.iqr_band(ax, [2, 3], [None, None], [None, None], "C0") == 0)
    check("SHOW_REPS defaults to False", ps.SHOW_REPS is False)
    plt.close(fig)


def main():
    before = sum(1 for _ in (REPO / "data" / "raw").rglob("*")) if (REPO / "data" / "raw").exists() else 0
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_unique_series_styles()
        test_colour_only()
        test_ticks()
        test_grayscale()
        test_save_png_and_guards(tmp)
        test_paper(tmp)
        test_no_minor_ticks(tmp)
        test_band()
    after = sum(1 for _ in (REPO / "data" / "raw").rglob("*")) if (REPO / "data" / "raw").exists() else 0
    check("real data/raw untouched (entry count unchanged)", before == after)
    print(f"{PASSED + FAILED} checks, {FAILED} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
