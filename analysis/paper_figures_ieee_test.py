#!/usr/bin/env python3
# paper_figures_ieee_test.py -- tests for analysis/paper_figures_ieee.py on SYNTHETIC data in a temp dir only.
# No pytest (same style as pc/shared/*_test.py). Run: .venv/bin/python analysis/paper_figures_ieee_test.py

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "pc"))
import paper_figures_ieee as pf  # noqa: E402
from shared import plot_style as ps  # noqa: E402

PASSED = FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"FAIL: {name} {extra}")


def raises(fn, exc=pf.DataError):
    try:
        fn()
    except exc as e:
        return str(e)
    return None


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def fresh(tmp, name):
    root = Path(tmp) / name
    pf.make_synthetic(root)
    return root


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pf_test_"))
    try:
        # --- style: every circuit has its own marker AND linestyle AND ink (grayscale-safe)
        combos = {(ps.CIRCUIT_MARKER[c], ps.CIRCUIT_LINESTYLE[c]) for c in ps.CIRCUIT_ORDER}
        check("unique (marker, linestyle) per circuit", len(combos) == len(ps.CIRCUIT_ORDER))
        check("unique marker per circuit", len({ps.CIRCUIT_MARKER[c] for c in ps.CIRCUIT_ORDER}) == 4)
        check("unique linestyle per circuit", len({ps.CIRCUIT_LINESTYLE[c] for c in ps.CIRCUIT_ORDER}) == 4)
        check("unique ink per circuit", len({ps.CIRCUIT_INK[c] for c in ps.CIRCUIT_ORDER}) == 4)

        # --- IQR helper: single value -> no bar
        check("iqr of 1 value is None", pf.iqr([5.0]) is None)
        check("iqr of 5 values", pf.iqr([1, 2, 3, 4, 5]) == (2.0, 4.0))

        # --- loads synthetic data; single-value / partial points handled
        root = fresh(tmp, "ok")
        data = pf.load_exec_time(root)
        check("12 board/circuit groups", len(data) == 12)
        pts = data[("uno", "h_all")]["points"]
        check("last uno point is partial", pts.kind.iloc[-1] == "partial")
        d = pf.point_dir(root, "phase2", "uno", "h_all")
        raw = pd.read_csv(d / "raw.csv")
        last = raw.n.max()
        raw = pd.concat([raw[raw.n != last], raw[raw.n == last].head(1)])
        raw.to_csv(d / "raw.csv", index=False)
        data = pf.load_exec_time(root)
        one = data[("uno", "h_all")]["points"].iloc[-1]
        check("single-value point has no IQR", pd.isna(one.q1) and pd.isna(one.q3) and one.reps == 1)
        fig = pf.plot_exec_time(data)
        check("single-value point plots", fig is not None)
        check("fig1 is 7.16 in wide", abs(fig.get_size_inches()[0] - pf.DOUBLE_COL_IN) < 1e-6)
        pf.plt.close(fig)

        # --- refuses missing columns / inconsistent data
        for fname, col in (("raw.csv", "exec_time_us"), ("memory_wall.csv", "status")):
            r = fresh(tmp, f"miss_{col}")
            dd = pf.point_dir(r, "phase2", "esp32", "qft")
            pd.read_csv(dd / fname).drop(columns=[col]).to_csv(dd / fname, index=False)
            msg = raises(lambda r=r: pf.load_exec_time(r))
            check(f"refuses missing {col}", msg is not None and col in msg, msg)
        r = fresh(tmp, "miss_cmp")
        dd = pf.point_dir(r, "phase2", "esp32", "qft") / "ref"
        pd.read_csv(dd / "ref_compare.csv").drop(columns=["diff_us"]).to_csv(dd / "ref_compare.csv", index=False)
        msg = raises(lambda: pf.load_counter_diff(r))
        check("refuses missing diff_us in ref_compare", msg is not None and "diff_us" in msg, msg)

        r = fresh(tmp, "zero")
        dd = pf.point_dir(r, "phase2", "esp32", "qft")
        x = pd.read_csv(dd / "raw.csv")
        x.loc[0, "exec_time_us"] = 0
        x.to_csv(dd / "raw.csv", index=False)
        check("refuses non-positive time (log axis)", raises(lambda: pf.load_exec_time(r)) is not None)

        r = fresh(tmp, "orphan")
        dd = pf.point_dir(r, "phase2", "esp32", "qft")
        w = pd.read_csv(dd / "memory_wall.csv")
        w[w.n != 3].to_csv(dd / "memory_wall.csv", index=False)
        check("refuses raw rows without a memory_wall row", raises(lambda: pf.load_exec_time(r)) is not None)

        r = fresh(tmp, "walled_with_rows")
        dd = pf.point_dir(r, "phase2", "esp32", "qft")
        w = pd.read_csv(dd / "memory_wall.csv")
        w.loc[w.n == 3, "status"] = "malloc_failed"
        w.to_csv(dd / "memory_wall.csv", index=False)
        check("refuses raw rows at a recorded wall point", raises(lambda: pf.load_exec_time(r)) is not None)

        r = fresh(tmp, "baddiff")
        dd = pf.point_dir(r, "phase2", "esp32", "qft") / "ref"
        c = pd.read_csv(dd / "ref_compare.csv")
        c.loc[0, "diff_us"] += 5
        c.to_csv(dd / "ref_compare.csv", index=False)
        check("refuses diff_us != micros_us - counter_us", raises(lambda: pf.load_counter_diff(r)) is not None)

        # --- unknown statuses are not drawn as walls
        r = fresh(tmp, "status")
        dd = pf.point_dir(r, "phase2", "esp8266", "grover")
        w = pd.read_csv(dd / "memory_wall.csv")
        w.loc[w.n == w.n.max(), "status"] = "watchdog_suspected"
        w.to_csv(dd / "memory_wall.csv", index=False)
        ev = pf.load_exec_time(r)[("esp8266", "grover")]["events"]
        check("watchdog status is not drawn as a wall", "wall" not in set(ev.kind) or len(ev[ev.kind == "wall"]) == 0,
              str(ev))

        # --- counter provenance: simulator port excluded; sidecar missing excluded
        r = fresh(tmp, "sim")
        dd = pf.point_dir(r, "phase2", "uno", "qft")
        (dd / "env" / "s.ref.json").write_text(json.dumps({"counter_port": "SIM", "counter_fw_sha256": "00"}))
        data2, skipped = pf.load_counter_diff(r)
        check("simulator-port group excluded from fig2", ("uno", "qft") not in data2 and
              any(s[:2] == ("uno", "qft") for s in skipped))
        r = fresh(tmp, "nosidecar")
        dd = pf.point_dir(r, "phase2", "uno", "qft")
        (dd / "env" / "s.ref.json").unlink()
        data2, skipped = pf.load_counter_diff(r)
        check("group without counter sidecar excluded", ("uno", "qft") not in data2)

        # --- too few pairs: listed, not drawn
        r = fresh(tmp, "fewpairs")
        dd = pf.point_dir(r, "phase2", "esp32", "h_all") / "ref"
        c = pd.read_csv(dd / "ref_compare.csv")
        n2 = c.n.min()
        pd.concat([c[c.n != n2], c[c.n == n2].head(3)]).to_csv(dd / "ref_compare.csv", index=False)
        p = pd.read_csv(dd / "ref_compare_points.csv")
        p.loc[p.n == n2, "n_pairs"] = 3
        p.to_csv(dd / "ref_compare_points.csv", index=False)
        data2, skipped = pf.load_counter_diff(r)
        check("point with < MIN_PAIRS listed in skipped", any("only 3" in s[2] for s in skipped))
        check("point with < MIN_PAIRS absent from fig2 data", n2 not in set(data2[("esp32", "h_all")].n))

        # --- never writes under data/raw; raw tree untouched by a full run
        r = fresh(tmp, "rawguard")
        msg = raises(lambda: pf.save(pf.plot_exec_time(pf.load_exec_time(r)), r / "phase2" / "out", "x", r))
        check("refuses to write under the raw tree", msg is not None and "raw" in msg, msg)
        before = tree_hash(r)
        out = tmp / "out_ok"
        rc = pf.main(["--raw", str(r), "--out", str(out)])
        check("main on synthetic data exits 0", rc == 0)
        check("raw tree identical after a full run", tree_hash(r) == before)
        files = sorted(p.name for p in out.iterdir())
        check("outputs are DRAFT pdf+png only (no svg)",
              files == ["fig1_exec_time_vs_n_DRAFT.pdf", "fig1_exec_time_vs_n_DRAFT.png",
                        "fig2_micros_minus_counter_DRAFT.pdf", "fig2_micros_minus_counter_DRAFT.png"], str(files))
        rc = pf.main(["--raw", str(r), "--out", str(r / "phase2")])
        check("main refuses --out under raw", rc == 2)

        # --- metadata stripped, fonts embedded, no identifying strings
        for pdf in out.glob("*.pdf"):
            b = pdf.read_bytes()
            for needle in (b"/Creator", b"/Producer", b"/Author", b"/Title", b"Matplotlib", b"/Users/", b"thirasak",
                           b"/dev/", b"github", b"CreationDate"):
                check(f"{pdf.name} has no {needle!r}", needle not in b)
            if shutil.which("pdffonts"):
                fonts = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout.splitlines()[2:]
                check(f"{pdf.name} has fonts", len(fonts) > 0)
                check(f"{pdf.name} all fonts embedded", all(f.split()[-5] == "yes" for f in fonts), "\n".join(fonts))
                check(f"{pdf.name} no Type 3 fonts", all("Type 3" not in f for f in fonts))
        for png in out.glob("*.png"):
            b = png.read_bytes()
            check(f"{png.name} has no Software/Matplotlib/path text", b"Matplotlib" not in b and b"Software" not in b
                  and b"/Users/" not in b)
            from PIL import Image
            im = Image.open(png)
            check(f"{png.name} is 600 dpi", abs(im.info.get("dpi", (0, 0))[0] - 600) < 1, str(im.info.get("dpi")))
            im.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
