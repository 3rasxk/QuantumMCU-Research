# ref_schema.py -- file schemas of the reference (counter) data, each with its OWN schema
# version constant. raw.csv / points.csv / sessions.csv are NOT touched (pc/shared/telemetry.py
# SCHEMA_VERSION stays 2). Writers refuse to append to a file whose header or schema_version
# differs from the constants here (same guard idea as telemetry.py).
#
# Files, all under data/raw/phase<N>/<board>/<circuit>/with_ref/ref/:
#   ref_pulses.csv          one row per pulse the counter reported
#   ref_points.csv          one row per point: counter report, status, anomalies
#   ref_compare.csv         one row per rep: micros() vs counter width
#   ref_compare_points.csv  one row per point: summary of the comparison
#   ref_issues.log          free-text reference problems (never read back for decisions)
#   env/<session>.ref.json  sidecar: counter fw hash, port, pin map, divider, calibration (REF_ENV)

import csv
from pathlib import Path

REF_PULSES_SCHEMA_VERSION = 1
REF_POINTS_SCHEMA_VERSION = 1
REF_COMPARE_SCHEMA_VERSION = 1
REF_COMPARE_POINTS_SCHEMA_VERSION = 1
REF_ENV_SCHEMA_VERSION = 1

PULSES_COLUMNS = ["schema_version", "session_id", "counter_session", "board", "circuit", "n", "seq",
                  "rise_us", "width_ticks", "width_us", "wraps", "flags", "anomaly_code"]
POINTS_COLUMNS = ["schema_version", "session_id", "board", "circuit", "n", "reps_expected", "pulses_received",
                  "pulses_used", "ref_status", "anomaly_mask", "anomaly_codes", "min_ns", "median_ns", "max_ns",
                  "report_pulses", "pcnt_count", "overruns", "counter_proto", "timestamp_utc"]
COMPARE_COLUMNS = ["schema_version", "session_id", "board", "circuit", "n", "rep", "micros_us", "counter_us",
                   "diff_us", "diff_pct"]
COMPARE_POINTS_COLUMNS = ["schema_version", "session_id", "board", "circuit", "n", "n_pairs", "median_diff_us",
                          "mean_diff_us", "std_diff_us", "iqr_diff_us", "max_abs_diff_us", "median_diff_pct",
                          "ref_status", "flagged", "micros_quantization_us", "notes"]

# micros() tick per board (4 us on the Uno: timer0 prescale 64 at 16 MHz; 1 us on the ESP boards)
MICROS_QUANTIZATION_US = {"uno": 4.0, "esp8266": 1.0, "esp32": 1.0}

FILE_SPECS = {
    "ref_pulses.csv": (PULSES_COLUMNS, REF_PULSES_SCHEMA_VERSION),
    "ref_points.csv": (POINTS_COLUMNS, REF_POINTS_SCHEMA_VERSION),
    "ref_compare.csv": (COMPARE_COLUMNS, REF_COMPARE_SCHEMA_VERSION),
    "ref_compare_points.csv": (COMPARE_POINTS_COLUMNS, REF_COMPARE_POINTS_SCHEMA_VERSION),
}


class RefSchemaError(RuntimeError):
    pass


def append_rows(path, rows):
    """Append dict rows to one of the reference files named in FILE_SPECS. Creates the file with
    its header; refuses (raises) if an existing file has a different header or schema_version."""
    path = Path(path)
    if path.name not in FILE_SPECS:
        raise RefSchemaError(f"{path.name} is not a known reference file")
    columns, version = FILE_SPECS[path.name]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header != columns:
                raise RefSchemaError(f"{path}: header {header} != expected {columns}; refusing to append")
            for row in reader:
                if row and row[0] != str(version):
                    raise RefSchemaError(f"{path}: contains schema_version {row[0]}, this code writes {version}; refusing to append")
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(columns)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        for r in rows:
            r = dict(r)
            r["schema_version"] = version
            w.writerow({c: r.get(c, "") for c in columns})
            f.flush()


def read_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
