# live.py -- read-only live view of the counter, shared by bridge.py (standalone) and the sweep scripts (during a
# real run). The sweep owns the counter's TCP port while it runs, so the dashboard must live INSIDE that process:
# CounterClient calls LiveState.on_frame for every decoded frame (reader thread, before the session consumes it),
# CounterSession reports what it is doing (point, status, comparison) via set_context/point_result, and
# serve() exposes http://localhost:PORT/ (dashboard.html) and /state (JSON). No endpoint can change anything.
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from counter import proto as cp

HTML = Path(__file__).with_name("dashboard.html")
KEEP_WIDTHS = 200
KEEP_POINTS = 12


class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.client = None
        self.transport = None
        self.d = {"heartbeats": 0, "last_heartbeat": None, "frames": 0, "pulses": 0, "anomalies": [],
                  "started_utc": time.time(), "widths_us": [], "context": {}, "points": []}

    def attach(self, client, transport):
        self.client, self.transport = client, transport

    def on_frame(self, ftype, f):
        with self.lock:
            self.d["frames"] += 1
            if ftype == cp.T_HEARTBEAT:
                self.d["heartbeats"] += 1
                self.d["last_heartbeat"] = {"proto": f[0], "counter_us": f[1], "state": f[2], "ring_depth": f[3],
                                            "dropped": f[4], "link_up": f[5], "free_heap": f[6], "last_seq": f[7],
                                            "pc_time_utc": time.time()}
            elif ftype == cp.T_PULSE:
                self.d["pulses"] += 1
                self.d["widths_us"] = (self.d["widths_us"] + [f[3] / 1000.0])[-KEEP_WIDTHS:]
                self.d["context"]["pulses_this_point"] = self.d["context"].get("pulses_this_point", 0) + 1
            elif ftype == cp.T_ANOMALY:
                self.d["anomalies"].append({"seq": f[0], "code": f[1]})
                self.d["anomalies"] = self.d["anomalies"][-50:]

    def set_context(self, **kw):
        with self.lock:
            if kw.get("reset_pulses"):
                kw.pop("reset_pulses")
                self.d["context"]["pulses_this_point"] = 0
                self.d["widths_us"] = []
            self.d["context"].update(kw)

    def point_result(self, row):
        with self.lock:
            self.d["points"] = (self.d["points"] + [row])[-KEEP_POINTS:]

    def snapshot(self):
        with self.lock:
            s = json.loads(json.dumps(self.d))
        tr, cl = self.transport, self.client
        s["connected"] = bool(getattr(tr, "connected", False)) if tr is not None else False
        peer = getattr(tr, "peer", None)
        s["peer"] = None if peer is None else f"{peer[0]}:{peer[1]}"
        s["bad_frames"] = cl.bad_frames if cl is not None else 0
        return s


def make_handler(state):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, ctype, body):
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", HTML.read_bytes())
            elif path in ("/state", "/status"):
                self._send(200, "application/json", json.dumps(state.snapshot()).encode())
            else:
                self.send_error(404)

        def log_message(self, *a):
            pass
    return H


def serve(state, port):
    """Start the read-only HTTP server in a daemon thread. Returns the server, or None if the port is busy
    (the run must never fail because of the dashboard)."""
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", int(port)), make_handler(state))
    except OSError:
        return None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
