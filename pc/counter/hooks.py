# hooks.py -- the thin layer the three Phase 2 sweep scripts call. With `--ref none` (default) every hook is a
# no-op: no counter module code runs per point, no counter file is touched, the sweep's behaviour and its
# output files are byte-identical to a run without this feature (proved in pc/counter/hooks_test.py).
# With `--ref counter --counter-port PORT` the counter is REQUIRED: a missing or silent counter stops the
# run before the first point (official runs require it; policy in docs/design/system_design.md).
#
# Never shared: the counter port is opened here by one CounterClient and never by the target code.

import os
import sys
from pathlib import Path

REF_CHOICES = ("none", "counter")
_client = None
_sessions = []
_live = None
_httpd = None
_HEARTBEAT_WAIT_S = 6.0
_TCP_WAIT_S = 60.0   # over WiFi the counter may still be joining the network when the sweep starts


def add_args(ap):
    ap.add_argument("--ref", choices=REF_CHOICES, default="none",
                    help="timing reference: 'counter' = ESP32 pulse counter (official runs REQUIRE it; data goes to "
                         "the with_ref/ bucket), 'none' = micros() only (no_ref/ bucket, not for official runs)")
    ap.add_argument("--counter-port", default=None,
                    help="counter link, required with --ref counter, never auto-guessed: a USB serial device path, or 'tcp:5055' to listen on that TCP port for the counter over WiFi; never the same as --port")
    ap.add_argument("--dashboard-port", type=int, default=8080,
                    help="live read-only dashboard during a --ref counter run at http://localhost:PORT/ (0 = off; a busy port is skipped, never fatal)")
    ap.add_argument("--counter-cal", default=None,
                    help="calibration JSON from pc/counter/calibration.py; its ppm/uncertainty is copied into the "
                         "per-session reference sidecar (recommended for official runs)")


def ref_active(args):
    return getattr(args, "ref", "none") == "counter"


class SweepRef:
    """Per-circuit reference handle. `enabled` False = every method does nothing."""

    def __init__(self, session=None, micros_col=4):
        self.s = session
        self.micros_col = micros_col   # CSV column holding the target's own time: 4 = exec_time_us (Phase 2), 5 = e2e_latency_us (Phase 3)
        self.enabled = session is not None
        self.last = None

    def arm(self, n):
        if self.enabled:
            ok = self.s.arm_point(n)
            if not ok:
                print(f"[ref] counter not armed for n={n} (see ref_issues.log) -- this point runs WITHOUT a reference")
            return ok
        return None

    def target_failed(self, n):
        if self.enabled and self.s.armed_n == n:
            self.s.finish_point(n, None, target_ran=False)   # also records arm_failed points

    def finish(self, n, rows, done):
        """rows: raw trial lines of this attempt (Phase 2 'board,circuit,n,rep,exec_time_us,...', Phase 3
        'board,circuit,n,baud,rep,e2e_latency_us,...'); done: point completed."""
        if not self.enabled or self.s.armed_n != n:
            return None
        micros = None
        if done and rows:
            try:
                micros = [float(line.split(",")[self.micros_col]) for line in rows]
            except (IndexError, ValueError):
                micros = None
        capped = bool(done and rows and len(rows) < self.s.reps)  # time-capped point: fewer reps than armed for
        st = self.s.finish_point(n, micros, target_ran=bool(rows), reps_expected=len(rows) if capped else None)
        self.last = (st, getattr(self.s, "last_result", None))
        if os.environ.get("QLAB_COMPACT") != "1":   # compact runs fold this into the sweep's single per-point line
            print(f"[ref] n={n} reference status: {st}")
        return st

    def summary_text(self):
        """Compact 'ref=... pulses=k/100 micros-counter ...' for the last finished point ('' when the reference is off)."""
        last = getattr(self, "last", None)
        if not self.enabled or not last:
            return ""
        st, res = last
        parts = [f"ref={st}"]
        if res:
            if res.get("pulses_used") is not None:
                parts.append(f"pulses={res['pulses_used']}/{self.s.reps}")
            s = res.get("summary") or {}
            if res.get("status") == "joined":
                if str(res.get("notes", "")).startswith("partial"):
                    parts.append(f"partial join {s['n_pairs']}/{self.s.reps}")
                parts.append(f"micros-counter med {s['median_diff_us']:+.1f}us ({s['median_diff_pct']:+.2f}%) "
                             f"sd {s['std_diff_us']:.1f}us{' FLAGGED' if s['flagged'] else ''}")
            else:
                parts.append(f"compare {res.get('status')}")
        return "  ".join(parts)

    def stop_requested(self):
        return self.enabled and self.s.should_stop()


def from_args(args, board, circuit, session_id="", phase=2):
    """Build the SweepRef for one circuit. Exits (code 2) if --ref counter is requested but the counter is unusable."""
    global _client, _live, _httpd
    if not ref_active(args):
        return SweepRef()
    from counter.client import CounterClient, make_transport
    from counter.session import CounterSession
    from shared import paths as sp
    from shared import timing_model as tm
    if not args.counter_port:
        print("error: --ref counter requires --counter-port (never auto-guessed)", file=sys.stderr)
        sys.exit(2)
    if args.counter_port == args.port:
        print("error: --counter-port must differ from the target --port (the ports are never shared)", file=sys.stderr)
        sys.exit(2)
    if _client is None:
        try:
            from counter import live as live_mod
            _live = live_mod.LiveState()
            tr = make_transport(args.counter_port)
            _client = CounterClient(tr, on_frame=_live.on_frame)
            _live.attach(_client, tr)
            if getattr(args, "dashboard_port", 0):
                _httpd = live_mod.serve(_live, args.dashboard_port)
                print(f"[ref] live dashboard: http://localhost:{args.dashboard_port}/ (read-only)" if _httpd else
                      f"[ref] dashboard port {args.dashboard_port} busy: continuing without the live page")
        except Exception as e:  # noqa: BLE001
            print(f"error: cannot open counter port {args.counter_port}: {e}", file=sys.stderr)
            sys.exit(2)
        import time
        wait_s = _TCP_WAIT_S if str(args.counter_port).startswith("tcp:") else _HEARTBEAT_WAIT_S
        end = time.monotonic() + wait_s
        while time.monotonic() < end and not _client.alive():
            time.sleep(0.1)
        if not _client.alive():
            print(f"error: no counter heartbeat on {args.counter_port} within {wait_s:.0f} s -- "
                  "official runs require a working counter", file=sys.stderr)
            shutdown()
            sys.exit(2)
    sess = CounterSession(_client, board, circuit, sp.ref_dir(board, circuit, phase=phase), reps=tm.REPS,
                          session_id=session_id, live=_live, phase=phase)
    _sessions.append(sess)
    return SweepRef(sess, micros_col=5 if phase == 3 else 4)


def shutdown():
    """Disarm and close. Safe to call any number of times, from a `finally` or a Ctrl+C path."""
    global _client, _httpd
    for s in _sessions:
        try:
            s.abort()
        except Exception:  # noqa: BLE001
            pass
    _sessions.clear()
    if _httpd is not None:
        try:
            _httpd.shutdown()
        except Exception:  # noqa: BLE001
            pass
        _httpd = None
    if _client is not None:
        try:
            _client.close()
        except Exception:  # noqa: BLE001
            pass
        _client = None


PIN_MAP = {"IN_DUT": "GPIO34", "GND": "common with the target", "SELFTEST_OUT": "GPIO25", "SELFTEST_IN": "GPIO35"}
DIVIDERS = {"uno": {"r_top_ohm": 2200, "r_bottom_ohm": 3900, "series_ohm": 330, "note": "5 V Uno pin 7 -> 3.2 V"},
            "esp8266": {"series_ohm": 330, "pulldown_ohm": 10000, "note": "3.3 V direct"},
            "esp32": {"series_ohm": 330, "pulldown_ohm": 10000, "note": "3.3 V direct"}}


def write_sidecar(env_directory, session_id, args, board):
    """env/<session>.ref.json (REF_ENV_SCHEMA_VERSION): counter fw hash, port, pin map, divider, calibration."""
    if not ref_active(args):
        return None
    import hashlib
    import json
    from counter.session import write_env_sidecar
    root = Path(__file__).resolve().parent.parent.parent
    fw = root / "firmware" / "counter_esp32" / "src" / "main.cpp"
    sha = hashlib.sha256(fw.read_bytes()).hexdigest() if fw.exists() else ""
    cal = {}
    if getattr(args, "counter_cal", None) and Path(args.counter_cal).exists():
        cal = json.loads(Path(args.counter_cal).read_text())
    return write_env_sidecar(Path(env_directory) / f"{session_id}.ref.json", counter_port=args.counter_port,
                             counter_fw_sha256=sha, pin_map=PIN_MAP, divider=DIVIDERS.get(board, {}), calibration=cal)
