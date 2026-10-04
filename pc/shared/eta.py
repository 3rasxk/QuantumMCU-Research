# eta.py -- run-time estimates and ETA display for pc/run.py (2026-10-03).
#
# Pure estimation and formatting. No hardware access, no collection logic: the
# sweep scripts are untouched. Used by
#   * pc/run.py preflight (also --dry-run): per-n table before a run,
#   * pc/run.py --plan: the same table for every board x circuit x phase,
#   * pc/run.py during a real run: PointWatcher reads the terminal-record CSV
#     the sweep script already writes and prints an updated ETA after each point.
#
# Sources, labelled per row:
#   MEASURED  values measured in the NEW run: the per-point telemetry (points.csv) the sweep
#             scripts write for this board and phase (device_exec_s per (circuit, n);
#             compile/upload medians pooled per board and phase), used as soon as
#             at least one ok point exists.
#   ESTIMATE  everything else: pc/shared/timing_model.py (gate-count model with a prior
#             fit, COMPILE_S/UPLOAD_S/DEVICE_OVERHEAD_S tables with stated bases) and the
#             Phase 3 PC-sim model. No retired measurement is used anywhere.
# The wall-point hang column is the 90 s budget (timing_model.FLOOR_S), a
# conservative upper bound, not a measurement.

import csv
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from shared import experiment_plan as plan
from shared import paths as sp
from shared import timing_model as tm

BANGKOK = ZoneInfo("Asia/Bangkok")
HANG_BUDGET_S = float(tm.FLOOR_S)  # 90 s


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_measured(board, phase):
    """Medians from the NEW run for one (board, phase): scans every circuit's points.csv
    (both reference buckets), status == ok rows only. Empty dict when nothing is collected."""
    rows = []
    for circuit in plan.EXPERIMENT_CIRCUITS:
        for bucket in (False, True):
            p = sp.points_csv_path(board, circuit, phase, bucket)
            if p.exists():
                with open(p, newline="", encoding="utf-8") as f:
                    rows += [r for r in csv.DictReader(f) if r.get("status") == "ok"]
    if not rows:
        return {}
    dev = {}
    small = []
    for r in rows:
        d = _f(r.get("device_exec_s"))
        try:
            n = int(r["n"])
        except (KeyError, ValueError):
            continue
        if d is None:
            continue
        dev.setdefault(r["circuit"], {}).setdefault(n, []).append(d)
        if tm.expected_point_time_s(board, r["circuit"], n) < 0.05:
            small.append(d)
    return {
        "n_ok_points": len(rows),
        "compile_s": _med([_f(r.get("build_compile_s")) for r in rows]),
        "upload_s": _med([_f(r.get("upload_s")) for r in rows]),
        "device_overhead_s": _med(small),
        "device_s": {c: {n: _med(v) for n, v in by.items()} for c, by in dev.items()},
    }


@dataclass
class PointEst:
    board: str
    circuit: str
    phase: int
    n: int
    device_s: float
    compile_s: float
    upload_s: float
    hang_s: float
    label: str  # MEASURED | ESTIMATE
    wall: bool = False
    time_limited: bool = False
    per_rep_s: float = 0.0
    wdt_risk: bool = False

    @property
    def overhead_s(self):
        return self.compile_s + self.upload_s + self.hang_s

    @property
    def total_s(self):
        return self.device_s + self.overhead_s


def estimate_point(board, circuit, n, phase, measured=None):
    """One point's estimate. Phase 2: device = model exec x 100 reps + fixed boot/serial
    overhead; a predicted wall point has no device time but costs compile + upload + the
    90 s hang budget. Phase 3: device = PC-side Aer simulation x 100 requests.
    `measured` = load_measured(board, phase); a (circuit, n) with a measured device time
    uses it and is labelled MEASURED, compile/upload use the measured medians when present."""
    measured = measured if measured is not None else load_measured(board, phase)
    wall = plan.is_wall_point(board, circuit, n, phase)
    have = bool(measured)
    compile_s = measured["compile_s"] if have and measured.get("compile_s") is not None \
        else tm.COMPILE_S_ESTIMATE[board]
    upload_s = measured["upload_s"] if have and measured.get("upload_s") is not None \
        else tm.UPLOAD_S_ESTIMATE[board]
    meas_dev = measured.get("device_s", {}).get(circuit, {}).get(n) if have else None

    label = "ESTIMATE"
    if wall:
        device_s = 0.0
        if have and measured.get("compile_s") is not None and measured.get("upload_s") is not None:
            label = "MEASURED"  # compile/upload measured in this run; hang is the 90 s budget
    elif meas_dev is not None:
        device_s, label = float(meas_dev), "MEASURED"
    elif phase == 3:
        device_s = tm.pc_sim_time_s(circuit, n) * tm.REPS
    else:
        overhead = measured["device_overhead_s"] if have and measured.get("device_overhead_s") \
            else tm.DEVICE_OVERHEAD_S_ESTIMATE[board]
        device_s = tm.expected_point_time_s(board, circuit, n) + overhead

    per_rep = 0.0
    wdt = False
    if phase == 2 and not wall:
        per_rep = tm.expected_exec_time_us(board, circuit, n) / 1e6
        thr = tm.WDT_PER_REP_THRESHOLD_S.get(board)
        wdt = thr is not None and per_rep > thr
    return PointEst(board, circuit, phase, n, device_s, compile_s, upload_s,
                    HANG_BUDGET_S if wall else 0.0, label, wall,
                    time_limited=device_s > plan.TIME_FLAG_S, per_rep_s=per_rep, wdt_risk=wdt)


def plan_points(board, circuit, phase, n_start=None, n_max=None, completed=(), measured=None):
    """Points a run will attempt, in order, minus `completed` n (already in the
    terminal-record file, so resume skips them). The sweep stops at the first
    wall, so the list ends at the predicted wall n."""
    out = []
    measured = measured if measured is not None else load_measured(board, phase)
    for n in plan.plan_n_values(board, circuit, phase):
        if n_start is not None and n < n_start:
            continue
        if n_max is not None and n > n_max:
            continue
        if n in completed:
            continue
        out.append(estimate_point(board, circuit, n, phase, measured))
    return out


# --------------------------- clock arithmetic ---------------------------

def now_bangkok():
    return datetime.now(BANGKOK)


def finish_clock(start, seconds):
    """start (aware datetime) + seconds, in Asia/Bangkok."""
    return start.astimezone(BANGKOK) + timedelta(seconds=seconds)


def format_clock(finish, start):
    """HH:MM, with the date added when the finish is on a later calendar day
    (Asia/Bangkok) than `start`."""
    finish = finish.astimezone(BANGKOK)
    if finish.date() != start.astimezone(BANGKOK).date():
        return finish.strftime("%a %d %b %H:%M")
    return finish.strftime("%H:%M")


def table_rows(points, start):
    """Per-n rows with cumulative seconds and finish clock."""
    rows, cum = [], 0.0
    for p in points:
        cum += p.total_s
        rows.append({"p": p, "cum_s": cum, "finish": format_clock(finish_clock(start, cum), start)})
    return rows


def totals(points):
    all_s = sum(p.total_s for p in points)
    limited = sum(p.total_s for p in points if p.time_limited)
    return {"points": len(points), "total_s": all_s, "limited_s": limited,
            "excl_limited_s": all_s - limited,
            "n_limited": sum(1 for p in points if p.time_limited)}


# --------------------------- formatting ---------------------------

DURATION_TIERS_S = ((72 * 3600, ">72h"), (24 * 3600, ">24h"), (6 * 3600, ">6h"))


def duration_tier(device_s):
    for limit, tag in DURATION_TIERS_S:
        if device_s > limit:
            return tag
    return ""


def _d(s):
    return tm.human_duration(s)


def format_table(board, circuit, phase, points, start, title_extra=""):
    lines = []
    wall = plan.wall_n(board)
    ev = plan.wall_evidence(board)
    head = (f"--- run-time estimate: board={board} circuit={circuit} phase={phase} "
            f"({tm.REPS} reps){title_extra} ---")
    lines.append(head)
    if phase == 2:
        lines.append(f"predicted wall: n={wall} ({ev}) -- UNVERIFIED until the run reaches it; "
                     f"a wall point costs compile + upload + {HANG_BUDGET_S:.0f}s hang budget")
    else:
        lines.append("Phase 3: device time = PC-side Aer simulation of 100 requests; "
                     "no board memory wall (state lives on the PC)")
    lines.append(f"start {start.astimezone(BANGKOK).strftime('%a %d %b %H:%M')} (Asia/Bangkok)")
    lines.append(f"{'n':>3s} {'per-rep':>9s} {'device':>9s} {'compile':>9s} {'upload':>9s} {'hang':>7s} "
                 f"{'total':>9s} {'cumul':>9s} {'finish':>14s}  {'src':8s} note")
    for r in table_rows(points, start):
        p = r["p"]
        note = []
        if p.wall:
            note.append("WALL (predicted)")
        if p.time_limited:
            note.append(f"TIME-LIMITED (device > {_d(plan.TIME_FLAG_S)})")
        tier = duration_tier(p.device_s)
        if tier:
            note.append(tier)
        if p.wdt_risk:
            note.append(f"WATCHDOG RISK (per rep > {tm.WDT_PER_REP_THRESHOLD_S[p.board]:.1f}s, UNVERIFIED threshold)")
        lines.append(f"{p.n:3d} {(_d(p.per_rep_s) if p.per_rep_s else '-'):>9s} {_d(p.device_s):>9s} {_d(p.compile_s):>9s} {_d(p.upload_s):>9s} "
                     f"{_d(p.hang_s) if p.hang_s else '-':>7s} {_d(p.total_s):>9s} "
                     f"{_d(r['cum_s']):>9s} {r['finish']:>14s}  {p.label:8s} {'; '.join(note)}")
    t = totals(points)
    if points:
        end = format_clock(finish_clock(start, t["total_s"]), start)
        lines.append(f"total {_d(t['total_s'])} over {t['points']} point(s); whole run finishes ~{end}")
        if t["n_limited"]:
            lines.append(f"  of which {t['n_limited']} TIME-LIMITED point(s) = {_d(t['limited_s'])} "
                         f"(excluding them: {_d(t['excl_limited_s'])}); no ceiling is set -- owner decision")
    else:
        lines.append("nothing to run (every planned point is already recorded)")
    lines.append("src: MEASURED = measured in the new run (points.csv, this board+phase); "
                 "ESTIMATE = timing_model.py model (hang column is the 90 s budget, not a measurement)")
    return "\n".join(lines)


def print_run_table(board, circuit, phase, n_start=None, n_max=None, completed=(),
                    start=None, out=print):
    start = start or now_bangkok()
    points = plan_points(board, circuit, phase, n_start, n_max, completed)
    out(format_table(board, circuit, phase, points, start))
    return points


def plan_report(boards=None, circuits=None, phases=None, start=None, brief=False, out=print):
    """--plan: every board x circuit x phase of the new scope. Returns a dict of totals."""
    start = start or now_bangkok()
    rows = [(b, c, p) for (b, c, p) in plan.all_rows()
            if (boards is None or b in boards) and (circuits is None or c in circuits)
            and (phases is None or p in phases)]
    summary = []
    for b, c, p in rows:
        pts = plan_points(b, c, p)
        summary.append((b, c, p, pts, totals(pts)))
        if not brief:
            out(format_table(b, c, p, pts, start))
            out("")
    out("=== plan summary (every point from the minimum n to the predicted wall) ===")
    out(f"{'ph':>2s} {'board':8s} {'circuit':9s} {'pts':>3s} {'wall n':>6s} {'evidence':14s} "
        f"{'total':>9s} {'time-limited':>14s} {'excl. limited':>13s}")
    per_board = {}
    grand = {"total_s": 0.0, "limited_s": 0.0, "excl_s": 0.0, "points": 0, "n_limited": 0}
    for b, c, p, pts, t in summary:
        wall = f"{plan.wall_n(b)}" if p == 2 else "n/a"
        ev = plan.wall_evidence(b) if p == 2 else "(offload)"
        lim = f"{t['n_limited']} pt / {_d(t['limited_s'])}" if t["n_limited"] else "-"
        out(f"{p:2d} {b:8s} {c:9s} {t['points']:3d} {wall:>6s} {ev:14s} "
            f"{_d(t['total_s']):>9s} {lim:>14s} {_d(t['excl_limited_s']):>13s}")
        pb = per_board.setdefault(b, {"total_s": 0.0, "excl_s": 0.0, "limited_s": 0.0,
                                      "points": 0, "n_limited": 0})
        for d in (pb, grand):
            d["total_s"] += t["total_s"]
            d["limited_s"] += t["limited_s"]
            d["excl_s"] += t["excl_limited_s"]
            d["points"] += t["points"]
            d["n_limited"] += t["n_limited"]
    out("")
    out("points above 6 h / 24 h / 72 h device time, and watchdog-risk points (per rep above the board's WDT threshold):")
    for b in plan.BOARDS:
        for ph in (2, 3):
            pts = [p for (bb, c, pp, ps_, t) in summary if bb == b and pp == ph for p in ps_]
            n6 = sum(1 for p in pts if p.device_s > 6 * 3600)
            n24 = sum(1 for p in pts if p.device_s > 24 * 3600)
            n72 = sum(1 for p in pts if p.device_s > 72 * 3600)
            nw = sum(1 for p in pts if p.wdt_risk)
            out(f"  {b:8s} phase {ph}: >6h {n6}, >24h {n24}, >72h {n72}, watchdog-risk {nw}")
    out("")
    out("grover, time to complete up to the predicted wall (sum of all its points):")
    for b in plan.BOARDS:
        for ph in (2, 3):
            for bb, c, pp, ps_, t in summary:
                if bb == b and pp == ph and c == "grover":
                    last = ps_[-1].n if ps_ else 0
                    out(f"  {b:8s} phase {ph}: n=2..{last}: {_d(t['total_s'])}")
    out("")
    out("per-board totals (all points | excluding TIME-LIMITED points):")
    for b, d in per_board.items():
        out(f"  {b:8s} {d['points']:4d} pts  {_d(d['total_s']):>10s} | {_d(d['excl_s']):>10s}")
    out(f"GRAND TOTAL {grand['points']} points: {_d(grand['total_s'])} all | "
        f"{_d(grand['excl_s'])} excluding {grand['n_limited']} TIME-LIMITED point(s) "
        f"(device > {_d(plan.TIME_FLAG_S)}, flag only; no ceiling set -- owner decision)")
    out("estimates are sequential single-operator wall time; the finish clock of a whole "
        "plan = start + total")
    return {"per_board": per_board, "grand": grand, "rows": summary}


# --------------------------- live ETA ---------------------------

class LiveEta:
    """Updates the ETA for the remaining points from times measured in THIS run.

    Each point's estimate is split into an overhead part (compile + upload +
    hang) and a device part. Overhead scale is fitted on points whose device part
    is small (< 5 % of the estimate); device scale on the rest, after removing the
    scaled overhead. With no measured point of a kind the scale is 1.0 (the
    static estimate stands)."""

    def __init__(self, points):
        self.points = list(points)
        self.actual = {}  # n -> measured seconds

    def record(self, n, actual_s):
        self.actual[n] = float(actual_s)

    def remaining(self):
        return [p for p in self.points if p.n not in self.actual]

    def scales(self):
        done = [p for p in self.points if p.n in self.actual]
        small = [p for p in done if p.device_s < 0.05 * p.total_s]
        big = [p for p in done if p.device_s >= 0.05 * p.total_s]
        s_o = 1.0
        if small and sum(p.overhead_s for p in small) > 0:
            s_o = sum(self.actual[p.n] for p in small) / sum(p.total_s for p in small)
        s_d = 1.0
        if big and sum(p.device_s for p in big) > 0:
            resid = sum(self.actual[p.n] - s_o * p.overhead_s for p in big)
            s_d = max(resid, 0.0) / sum(p.device_s for p in big)
        return s_o, s_d

    def remaining_seconds(self):
        s_o, s_d = self.scales()
        return sum(s_o * p.overhead_s + s_d * p.device_s for p in self.remaining())

    def line(self, n, status, now=None):
        now = now or now_bangkok()
        rem = self.remaining()
        secs = self.remaining_seconds()
        if not rem:
            return (f"[ETA] n={n} {status} in {_d(self.actual[n])} | all planned points done "
                    f"({now.astimezone(BANGKOK).strftime('%H:%M')})")
        fin = format_clock(finish_clock(now, secs), now)
        s_o, s_d = self.scales()
        return (f"[ETA] n={n} {status} in {_d(self.actual[n])} | {len(rem)} point(s) left "
                f"(next n={rem[0].n}) ~{_d(secs)} | finish ~{fin} Asia/Bangkok "
                f"(scale overhead x{s_o:.2f}, device x{s_d:.2f} vs estimate)")


class PointWatcher:
    """Polls the terminal-record CSV (memory_wall.csv / session_log.csv) that the
    delegated sweep script already appends to, and turns each new row into one
    LiveEta line. Read-only; never touches the sweep. poll() is synchronous
    (tests call it directly); start() runs it in a daemon thread."""

    def __init__(self, csv_path, points, run_start, out=print, now_fn=now_bangkok,
                 skip_existing=False):
        self.csv_path = Path(csv_path)
        self.eta = LiveEta(points)
        self.seen = 0
        self.last_t = run_start  # aware datetime of previous completion (or run start)
        self.out = out
        self.now_fn = now_fn
        self._stop = False
        self._thread = None
        if skip_existing:
            self.seen = len(self._rows())  # rows from earlier runs (resume) are not this run's points

    def _rows(self):
        if not self.csv_path.exists():
            return []
        try:
            with open(self.csv_path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except OSError:
            return []

    def poll(self):
        rows = self._rows()
        lines = []
        for r in rows[self.seen:]:
            try:
                n = int(r["n"])
                t = datetime.fromisoformat(r["timestamp_utc"])
            except (KeyError, ValueError):
                self.seen += 1
                continue
            self.eta.record(n, max((t - self.last_t).total_seconds(), 0.0))
            self.last_t = t
            self.seen += 1
            line = self.eta.line(n, r.get("status", "?"), self.now_fn())
            lines.append(line)
            self.out(line)
        return lines

    def start(self, interval_s=5.0):
        import threading
        import time

        def loop():
            while not self._stop:
                self.poll()
                time.sleep(interval_s)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=10)
        self.poll()
