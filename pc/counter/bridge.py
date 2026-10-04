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
from counter import live  # noqa: E402


def run(tcp_port, http_port, seconds=None, out=print):
    state = live.LiveState()
    tr = TcpServerTransport(tcp_port)
    client = CounterClient(tr, on_frame=state.on_frame)
    state.attach(client, tr)
    httpd = live.serve(state, http_port)
    if httpd is None:
        out(f"warning: HTTP port {http_port} is busy, dashboard not started")
    out(f"listening for the counter on TCP :{tcp_port}; dashboard at http://localhost:{http_port}/ (JSON at /state)")
    t0 = time.monotonic()
    last_poll = 0
    last_hb = 0
    try:
        while seconds is None or time.monotonic() - t0 < seconds:
            client.drain()                      # frames are already counted by the live hook; just empty the queue
            hb = state.d["heartbeats"]
            if hb != last_hb:
                last_hb = hb
                h = state.d["last_heartbeat"]
                out(f"heartbeat #{hb}: counter clock {h['counter_us'] / 1e6:.3f} s, state {h['state']}, heap {h['free_heap']}")
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
        if httpd is not None:
            httpd.shutdown()
        client.close()
    return state.snapshot()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tcp-port", type=int, default=5055)
    ap.add_argument("--http-port", type=int, default=8080)
    ap.add_argument("--seconds", type=float, default=None, help="stop after this long (default: until Ctrl+C)")
    a = ap.parse_args()
    snap = run(a.tcp_port, a.http_port, a.seconds)
    print(json.dumps({k: snap[k] for k in ("connected", "heartbeats", "frames", "bad_frames", "pulses")}))
