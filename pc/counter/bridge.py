#!/usr/bin/env python3
# bridge.py -- minimal PC-side server for the counter's WiFi link (basic data-path test, no sweep needed).
# Listens on a TCP port for the counter (it connects to this PC over WiFi), decodes protocol-v2 frames,
# prints what arrives, and serves the latest state as JSON on http://localhost:HTTP_PORT/status so the
# project (or a browser) can read it. Read-only toward the counter: it only sends a STATUS request.
#   .venv/bin/python pc/counter/bridge.py --tcp-port 5055 --http-port 8080
import argparse
import json
import sys
import threading
import time
import statistics
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import proto as cp  # noqa: E402
from counter.client import CounterClient, TcpServerTransport  # noqa: E402


HTML = Path(__file__).with_name("dashboard.html")
KEEP_WIDTHS = 200


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.d = {"connected": False, "peer": None, "heartbeats": 0, "last_heartbeat": None, "frames": 0,
                  "bad_frames": 0, "pulses": 0, "anomalies": [], "started_utc": time.time(),
                  "widths_us": []}

    def snapshot(self):
        with self.lock:
            return dict(self.d)


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


def run(tcp_port, http_port, seconds=None, out=print):
    state = State()
    tr = TcpServerTransport(tcp_port)
    client = CounterClient(tr)
    httpd = ThreadingHTTPServer(("127.0.0.1", http_port), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    out(f"listening for the counter on TCP :{tcp_port}; dashboard at http://localhost:{http_port}/ (JSON at /state)")
    t0 = time.monotonic()
    last_poll = 0
    try:
        while seconds is None or time.monotonic() - t0 < seconds:
            for ftype, f in client.drain():
                with state.lock:
                    state.d["frames"] += 1
                    if ftype == cp.T_HEARTBEAT:
                        state.d["heartbeats"] += 1
                        state.d["last_heartbeat"] = {"proto": f[0], "counter_us": f[1], "state": f[2], "ring_depth": f[3],
                                                     "dropped": f[4], "link_up": f[5], "free_heap": f[6], "last_seq": f[7],
                                                     "pc_time_utc": time.time()}
                        out(f"heartbeat #{state.d['heartbeats']}: counter clock {f[1] / 1e6:.3f} s, state {f[2]}, heap {f[6]}")
                    elif ftype == cp.T_PULSE:
                        state.d["pulses"] += 1
                        state.d["widths_us"] = (state.d["widths_us"] + [f[3] / 1000.0])[-KEEP_WIDTHS:]
                    elif ftype == cp.T_ANOMALY:
                        state.d["anomalies"].append({"seq": f[0], "code": f[1]})
            with state.lock:
                state.d["connected"] = tr.connected
                state.d["peer"] = None if tr.peer is None else f"{tr.peer[0]}:{tr.peer[1]}"
                state.d["bad_frames"] = client.bad_frames
            if tr.connected and time.monotonic() - last_poll > 5:   # ask for a status frame now and then
                last_poll = time.monotonic()
                try:
                    client.send(cp.encode(cp.T_STATUS))
                except OSError:
                    pass
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown(); client.close()
    return state.snapshot()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tcp-port", type=int, default=5055)
    ap.add_argument("--http-port", type=int, default=8080)
    ap.add_argument("--seconds", type=float, default=None, help="stop after this long (default: until Ctrl+C)")
    a = ap.parse_args()
    snap = run(a.tcp_port, a.http_port, a.seconds)
    print(json.dumps({k: snap[k] for k in ("connected", "heartbeats", "frames", "bad_frames", "pulses")}))
