"""Item 4a/4b helper: which commits' firmware trees have the hash a session recorded? (slow: hashes the firmware tree of every commit)
Writes data/derived/firmware_hash_commits.csv (board, phase, hash, n_matching_commits, oldest, newest, in_git). A hash with no match is an
uncommitted working tree at run time. Hash recipe = pc/shared/telemetry._firmware_build_hash (analysis/audit_data.fw_hash_commit)."""
import os
import subprocess
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import audit_data as A  # noqa: E402


def main():
    import audit
    pts = pd.concat([audit.audit_series(ph, b, c) for ph in (2, 3) for b in ("uno", "esp8266", "esp32")
                     for c in ("h_all", "bell_ghz", "qft", "grover")], ignore_index=True)
    want = pts[pts.ok_rows > 0][["phase", "board", "fw_hashes"]].drop_duplicates()
    revs = subprocess.run(["git", "rev-list", "--topo-order", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    rows = []
    for (ph, b), g in want.groupby(["phase", "board"]):
        hs = set(g.fw_hashes)
        found = {h: [] for h in hs}
        for c in revs:                       # newest first
            h = A.fw_hash_commit(ROOT, c, b, ph)
            if h in found:
                found[h].append(c[:7])
        for h in sorted(hs):
            m = found[h]
            rows.append(dict(board=b, phase=ph, hash=h, n_matching_commits=len(m), newest=m[0] if m else "", oldest=m[-1] if m else "",
                             in_git=bool(m)))
    out = os.path.join(ROOT, "data", "derived", "firmware_hash_commits.csv")
    pd.DataFrame(rows).sort_values(["phase", "board", "hash"]).to_csv(out, index=False)
    print(open(out).read())


if __name__ == "__main__":
    main()
