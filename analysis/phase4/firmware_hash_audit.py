"""Item 4a: firmware hash behind every grover point (Phase 2 and Phase 3), with its timing class. Writes data/derived/grover_hashes.csv."""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import audit  # noqa: E402


def main():
    cls = pd.read_csv(os.path.join(HERE, "firmware_hash_classes.csv"))[["board", "phase", "hash", "timing_class"]]
    sc_path = os.path.join(ROOT, "data", "derived", "firmware_hash_commits.csv")
    sc = pd.read_csv(sc_path) if os.path.exists(sc_path) else pd.DataFrame(columns=["board", "phase", "hash", "in_git", "newest", "oldest"])
    rows = []
    for ph in (2, 3):
        for b in ("uno", "esp8266", "esp32"):
            d = audit.audit_selected(ph, b, "grover")
            for r in d[d.ok_rows > 0].itertuples():
                rows.append(dict(phase=ph, board=b, n=int(r.n), reps=int(r.reps), hash=r.fw_hashes, commit_recorded=r.commits))
    df = pd.DataFrame(rows).merge(cls, left_on=["board", "phase", "hash"], right_on=["board", "phase", "hash"], how="left")
    df = df.merge(sc[["board", "phase", "hash", "in_git", "newest", "oldest"]], on=["board", "phase", "hash"], how="left")
    assert df.timing_class.notna().all(), df[df.timing_class.isna()]
    df["timing_relevant_difference_from_reference"] = df.timing_class != "A"
    df = df.sort_values(["phase", "board", "n"]).reset_index(drop=True)
    df.to_csv(os.path.join(ROOT, "data", "derived", "grover_hashes.csv"), index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    print(main().to_string())
