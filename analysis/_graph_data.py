# _graph_data.py -- shared read-only loaders and small helpers for the Phase 2 / Phase 3 PNG charts
# (phase2_uno_run_plots.py, phase2_cross_board_plots.py, phase3_run_plots.py, phase3_crossover_plot.py).
# Reads data/raw/ only; never writes. One place for: the rows of a (board, circuit, phase) point set, the git
# commit(s) the data were collected under (from each session's env JSON), the physical-counter check, and the
# status classification used by every outcome marker, so the charts agree with each other.

import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import paths as sp  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import resume as rs  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared.telemetry import is_warmup  # noqa: E402

BOARD_LINESTYLE = ps.BOARD_LINESTYLE      # second encoding next to BOARD_MARKER (grayscale); defined in plot_style
BOARD_SRAM_BYTES = {"uno": 2048, "esp8266": 81920, "esp32": 327680}
MIN_PAIRS = 10                                                    # fewer counter pairs: no median/IQR drawn


def read_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def need(rows, cols, what):
    """Refuse a file that lacks a column the chart reads (never plot around it)."""
    if rows:
        missing = [c for c in cols if c not in rows[0]]
        if missing:
            raise ValueError(f"{what}: missing column(s) {missing}")
    return rows


def f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def stats(values):
    """(median, q1, q3) with q1/q3 None for a single value (no error bar for a single-value point)."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return None
    med = float(np.median(v))
    if len(v) < 2:
        return med, None, None
    return med, float(np.percentile(v, 25)), float(np.percentile(v, 75))


def values_by_n(raw, col, skip_warmup=True):
    out = {}
    for r in raw:
        if skip_warmup and is_warmup(int(r["rep"])):
            continue
        v = f(r.get(col))
        if v is not None:
            out.setdefault(int(r["n"]), []).append(v)
    return out


def reps_text(counts):
    counts = list(counts)
    if not counts:
        return "no reps"
    lo, hi = min(counts), max(counts)
    return f"n = {lo} repetitions per point" if lo == hi else f"n = {lo}-{hi} repetitions per point (varies)"


# --------------------------------------------------------------------------- point sets

class PointSet:
    """Everything one (board, circuit, phase, bucket) directory holds that a chart reads."""

    def __init__(self, board, circuit, phase=2, ref=False):
        self.board, self.circuit, self.phase, self.ref = board, circuit, phase, ref
        self.dir = sp.raw_dir(board, circuit, phase=phase, ref=ref)
        self.raw = read_rows(sp.raw_csv_path(board, circuit, phase=phase, ref=ref))
        self.points = read_rows(sp.points_csv_path(board, circuit, phase=phase, ref=ref))
        if phase == 2:
            self.wall = read_rows(sp.memory_wall_csv_path(board, circuit, phase=2, ref=ref))
            self.log = []
        else:
            self.wall = []
            self.log = read_rows(sp.session_log_csv_path(board, circuit, phase=3, ref=ref))
        self.sessions = read_rows(sp.sessions_csv_path(board, circuit, phase=phase, ref=ref))
        self.env_dir = sp.env_dir(board, circuit, phase=phase, ref=ref)
        what = f"phase {phase} {board}/{circuit}"
        need(self.raw, ["n", "rep", "exec_time_us" if phase == 2 else "e2e_latency_us"], f"{what} raw.csv")
        need(self.points, ["n", "status"], f"{what} points.csv")
        need(self.wall, ["n", "status"], f"{what} memory_wall.csv")
        need(self.log, ["n", "baud_rate", "status"], f"{what} session_log.csv")

    @property
    def time_col(self):
        return "exec_time_us" if self.phase == 2 else "e2e_latency_us"

    def reps_by_n(self):
        out = {}
        for r in self.raw:
            out[int(r["n"])] = out.get(int(r["n"]), 0) + 1
        return out

    def commits(self):
        """Unique git commits of this directory's sessions in the order the sessions were recorded
        (env JSONs; falls back to sessions.csv)."""
        found = {}
        if Path(self.env_dir).exists():
            for p in sorted(Path(self.env_dir).glob("*.json")):
                if p.name.endswith(".ref.json"):
                    continue
                try:
                    j = json.loads(p.read_text())
                except (OSError, ValueError):
                    continue
                if j.get("git_commit"):
                    found.setdefault(j["git_commit"][:7], j.get("recorded_utc", ""))
        if not found:
            for r in self.sessions:
                if r.get("git_commit"):
                    found.setdefault(r["git_commit"][:7], r.get("start_utc", ""))
        return [c for c, _t in sorted(found.items(), key=lambda kv: kv[1])]

    def commit_note(self):
        return commit_phrase(self.commits())

    def physical_counter(self):
        """(True, '') only if every session sidecar names a real transport and a counter firmware hash.
        The counter simulator is only reachable from tests (port 'SIM'), never in a collected session."""
        sidecars = sorted(Path(self.env_dir).glob("*.ref.json")) if Path(self.env_dir).exists() else []
        if not sidecars:
            return False, "no counter sidecar (env/*.ref.json)"
        for s in sidecars:
            try:
                j = json.loads(s.read_text())
            except (OSError, ValueError):
                return False, "unreadable counter sidecar"
            port = str(j.get("counter_port", ""))
            if not port or port.upper().startswith("SIM"):
                return False, f"counter_port {port!r}"
            if not j.get("counter_fw_sha256"):
                return False, "empty counter firmware hash"
        return True, ""


def commit_phrase(commits):
    """'commit abc1234', 'commits a, b (mixed)', or 'N commits (mixed), first..last' when there are many."""
    if not commits:
        return "commit unknown"
    if len(commits) == 1:
        return f"commit {commits[0]}"
    if len(commits) == 2:
        return f"commits {commits[0]}, {commits[1]} (mixed)"
    return f"{len(commits)} commits (mixed), {commits[0]} .. {commits[-1]}"


def footnote(fig, text, width=135):
    """ps.add_footnote with the text wrapped so a long note cannot widen the saved figure."""
    import textwrap
    from shared import plot_style as ps
    ps.add_footnote(fig, "\n".join(textwrap.wrap(text, width)))


def known_circuits(board, phase=2, ref=False):
    base = REPO_ROOT / "data" / "raw" / f"phase{phase}" / board
    if not base.exists():
        return []
    bucket = "with_ref" if ref else "no_ref"
    return [c for c in tm_circuit_order() if (base / c / bucket / "raw.csv").exists()]


def tm_circuit_order():
    from shared import plot_style as ps
    return list(ps.CIRCUIT_ORDER)


# --------------------------------------------------------------------------- outcome classification

OK, OK_CAPPED, WALL, FAILED, WATCHDOG, HANG, TIME_LIMITED = (
    "ok", "ok_capped", "wall", "failed", "watchdog", "hang", "time_limited")


def classify_wall_row(status):
    """Category of a memory_wall.csv terminal row. Only recorded positive evidence (build_overflow /
    malloc_failed) is a WALL; resets and hangs are never a wall."""
    if status == "ok":
        return OK
    if rs.is_wall_status(status):
        return WALL
    if status.startswith("watchdog_suspected"):
        return WATCHDOG
    if status.startswith("runtime_hang_or_reset"):
        return HANG
    if status.startswith("skipped_compute_infeasible"):
        return TIME_LIMITED
    if status.startswith("skipped_"):
        return None            # resume / known-wall / sim-cost skips are not outcomes of this chart
    return FAILED              # build_or_upload_fail, build_timeout, ...


def outcomes_phase2(ps_):
    """{n: dict(cat, status, reps, row)} from the terminal rows of memory_wall.csv and the reps in raw.csv.
    cat OK_CAPPED = recorded ok but stopped by the per-point time cap before 100 reps."""
    reps = ps_.reps_by_n()
    out = {}
    for r in ps_.wall:
        n = int(r["n"])
        cat = classify_wall_row(r["status"])
        if cat is None:
            continue
        if cat == OK and 0 < reps.get(n, 0) < tm.REPS:
            cat = OK_CAPPED
        out[n] = dict(cat=cat, status=r["status"], reps=reps.get(n, 0), row=r)
    return out


def failed_attempts(ps_):
    """{n: [failure_type, ...]} of attempts in points.csv that failed for a reason that is NOT the wall itself
    (build/malloc failures at a recorded wall are the wall; resets and upload failures stay visible)."""
    walls = {int(r["n"]) for r in ps_.wall if rs.is_wall_status(r["status"])}
    out = {}
    for r in ps_.points:
        if r.get("status") != "failed":
            continue
        n = int(r["n"])
        ft = r.get("failure_type", "")
        if n in walls and ft in ("build", "malloc"):
            continue
        out.setdefault(n, []).append(ft or "failed")
    return out
