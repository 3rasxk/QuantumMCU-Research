# test_ledger.py -- import this FIRST in any test that can reach pc/shared/run_history.py (directly or through pc/run.py).
# It points the run-history ledger at a throw-away file, so no test can append to the real data/run_history.jsonl.
import os
import tempfile

if not os.environ.get("QLAB_RUN_HISTORY"):
    os.environ["QLAB_RUN_HISTORY"] = os.path.join(tempfile.mkdtemp(prefix="qlab_ledger_"), "run_history.jsonl")
