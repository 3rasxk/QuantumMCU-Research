#!/usr/bin/env python3
"""One entry point: rebuild every Phase 1-4 paper figure, table and the Phase 4 report from data/raw (read-only).

    .venv/bin/python analysis/reproduce.py            # about 2 minutes
    .venv/bin/python analysis/reproduce.py --full     # also re-runs the PC-only grover C++ builds n = 2..12 against Aer (about 15 minutes)
    make paper-figures                                # same as the first line

Steps (each is a script that can be run alone, see README_REPRODUCE.md):
  1 Phase 1  data/raw/phase1 -> data/derived/phase1 via analysis/phase4/audit.py (infidelity table), F5 below
  2 Phase 2/3 coverage, counter validity table and flag explanation, firmware hash audit, session provenance
  3 Phase 4  gate counts (C++ cross-check), grover diagnosis summary, models, figures F1-F5, tables/phase4_memory_wall.tex
  4 legacy micros()-vs-counter charts (usable counter points only)
  5 docs/phase4_report.md
Prints the sha256 of every output so two runs can be compared.
"""
import argparse
import hashlib
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable
P4 = os.path.join(ROOT, "analysis", "phase4")


def run(args, **kw):
    print("\n$", " ".join(os.path.relpath(a, ROOT) if os.path.isabs(a) else a for a in args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="re-run the PC-only grover builds against Aer for n = 2..12")
    a = ap.parse_args()
    env = dict(os.environ, SOURCE_DATE_EPOCH="1767225600")
    run([PY, os.path.join(P4, "audit.py")], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(P4, "gatecount.py")])
    run([PY, os.path.join(ROOT, "analysis", "audit_coverage.py")], stdout=subprocess.DEVNULL) if os.path.exists(os.path.join(ROOT, "analysis", "audit_coverage.py")) else None
    ns = list(map(str, range(2, 13) if a.full else range(2, 9)))
    run([PY, os.path.join(P4, "grover_diagnosis.py"), "--ns", *ns], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(P4, "grover_findings.py")])
    run([PY, os.path.join(P4, "firmware_hash_audit.py")], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(P4, "provenance.py")])
    run([PY, os.path.join(P4, "counter_report.py")], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(P4, "make_figures.py")], env=env)
    run([PY, os.path.join(P4, "recollection_plan.py")], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(ROOT, "analysis", "phase2", "plot_timer_vs_counter.py")], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(ROOT, "analysis", "phase2", "plot_timer_vs_counter.py"), "--phase", "3"], stdout=subprocess.DEVNULL)
    run([PY, os.path.join(P4, "build_report.py")])
    outs = []
    for d in ("figures/phase4", "tables"):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            outs.append(os.path.join(d, f))
    outs += ["docs/phase4_report.md"]
    print("\nsha256 of outputs:")
    for f in outs:
        print(hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest(), f)


if __name__ == "__main__":
    main()
