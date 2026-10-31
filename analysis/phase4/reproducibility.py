"""Reproducibility table: every in-scope point measured in more than one session (analysis/common/sessions.py `replicates`), medians per session and the
maximum relative difference between sessions. Phase 2: median of exec_time_us over the independent repetitions (analysis/common/weak.py). Phase 3: the median
round trip e2e, and its two logged-or-derived parts pc_sim (PC simulation) and residual (board + link), per session (analysis/phase4/offload_band.py).
Writes data/derived/reproducibility.csv (one row per phase, board, circuit, n, quantity)."""
import itertools
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import p4common as C  # noqa: E402
from common import sessions as SES  # noqa: E402
from common import weak as W  # noqa: E402
import offload_band as OB  # noqa: E402

OUT = os.path.join(C.ROOT, "data", "derived", "reproducibility.csv")


def _row(phase, board, circuit, n, quantity, vals):
    """vals: {session: median}; max relative difference = max |a-b| / min(|a|,|b|) over pairs (against the smaller value)"""
    items = sorted(vals.items())
    rel = max((abs(a - b) / max(min(abs(a), abs(b)), 1e-12) for (_, a), (_, b) in itertools.combinations(items, 2)), default=0.0)
    ab = max((abs(a - b) for (_, a), (_, b) in itertools.combinations(items, 2)), default=0.0)
    return dict(phase=phase, board=board, circuit=circuit, n=n, quantity=quantity, n_sessions=len(items), sessions=";".join("orig" if s == SES.ORIGINAL else s.replace(SES.ORIGINAL + "_", "") for s, _ in items),
                medians_us=";".join(f"{v:.3f}" for _, v in items), max_rel_diff=rel, max_abs_diff_us=ab)


def build():
    rows = []
    for b in C.BOARDS:
        for c in C.CIRCUITS:
            rep = SES.replicates(2, b, c)
            for n, buckets in rep.items():
                vals = {}
                for s in buckets:
                    raw = pd.read_csv(os.path.join(SES.bucket_dir(2, b, c, s), "raw.csv"))
                    x = raw[raw.n == n].exec_time_us.to_numpy(float)
                    vals[s] = float(np.median(x[:W.effective_reps(x)]))
                rows.append(_row(2, b, c, n, "exec_time_us", vals))
    allp = OB.p3_all_sessions()
    for (b, c, n), g in allp.groupby(["board", "circuit", "n"]):
        if g.session.nunique() < 2:
            continue
        for q, col in (("e2e_us", "e2e_us"), ("pc_sim_us", "pc_sim_us"), ("residual_us", "residual_us")):
            rows.append(_row(3, b, c, int(n), q, dict(zip(g.session, g[col]))))
    df = pd.DataFrame(rows).sort_values(["phase", "board", "circuit", "n", "quantity"]).reset_index(drop=True)
    df.to_csv(OUT, index=False)
    return df


if __name__ == "__main__":
    d = build()
    print(d.groupby(["phase", "quantity"]).max_rel_diff.agg(["count", "median", "max"]).to_string())
