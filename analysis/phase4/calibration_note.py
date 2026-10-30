"""values quoted from data/calibration/counter_20261004.json (read-only), so the report does not carry them as literals"""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_c = json.load(open(os.path.join(ROOT, "data", "calibration", "counter_20261004.json")))
PPM = _c["ppm"]
PPM_ERR = _c["ppm_stderr"]
DATE = _c["timestamp_utc"][:10]
