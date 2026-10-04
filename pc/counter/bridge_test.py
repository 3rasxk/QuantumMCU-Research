#!/usr/bin/env python3
# bridge_test.py -- bridge.py end to end on loopback: a fake counter connects over TCP, the bridge decodes its frames
# and serves /status JSON on localhost. No hardware.
import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import bridge  # noqa: E402
from counter import proto as cp  # noqa: E402
from counter.sim import CounterSim  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_ctl():
    import subprocess
    import tempfile
    from counter import bridge_ctl as bc
    tmp = Path(tempfile.mkdtemp())
    pf = tmp / "pid"
    fake = tmp / "bridge.py"
    fake.write_text("import time\nwhile True: time.sleep(0.2)\n")
    pid = bc.start(free_port(), 0, pidfile=pf, script=fake)
    check("bridge_ctl.start writes the pid file and the process runs", pf.read_text().strip() == str(pid) and bc._alive(pid))
    check("bridge_ctl.stop stops it and removes the pid file", bc.stop(pf) and not pf.exists())
    import os
    time.sleep(0.5)
    try:
        os.waitpid(pid, os.WNOHANG)            # reap: in this test we are the parent (run.py is not, in real use)
    except ChildProcessError:
        pass
    check("stopped process is gone", not bc._alive(pid))
    other = subprocess.Popen(["sleep", "30"])
    pf.write_text(str(other.pid))
    check("stop never kills a process that is not a bridge", bc.stop(pf) is False and other.poll() is None)
    other.kill()


def main():
    test_ctl()
    tp, hp = free_port(), free_port()
    result = {}
    th = threading.Thread(target=lambda: result.update(bridge.run(tp, hp, seconds=4, out=lambda *_: None)), daemon=True)
    th.start()
    time.sleep(0.5)
    sim = CounterSim()
    c = socket.create_connection(("127.0.0.1", tp), timeout=2)
    for i in range(3):
        sim.advance(1_000_000)
        c.sendall(sim.heartbeat()); time.sleep(0.2)
    c.sendall(cp.encode(cp.T_ANOMALY, 1, 3, 0)); c.sendall(b"\x00\x11garbage")
    time.sleep(0.8)
    body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{hp}/status", timeout=2).read())
    check("/status on localhost shows the counter connected", body["connected"] is True and body["peer"].startswith("127.0.0.1"))
    check("3 heartbeats decoded with the counter's microsecond clock", body["heartbeats"] == 3 and body["last_heartbeat"]["counter_us"] == 3_000_000)
    check("anomaly frame recorded", body["anomalies"] == [{"seq": 1, "code": 3}])
    check("unknown/garbage bytes do not break the stream", body["frames"] >= 4)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{hp}/other", timeout=2); ok = False
    except Exception:
        ok = True
    check("unknown URL -> 404", ok)
    html = urllib.request.urlopen(f"http://127.0.0.1:{hp}/", timeout=2).read().decode()
    check("GET / serves the dashboard page (read-only: no control endpoints)", "<canvas" in html and "Counter live" in html and "POST" not in html)
    st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{hp}/state", timeout=2).read())
    check("/state carries only real data: empty pulse list, no demo field, page has no DEMO text", st["widths_us"] == [] and "demo" not in st and "DEMO" not in html)
    c.close()
    th.join(timeout=8)
    check("bridge.run returns a final snapshot", result.get("heartbeats") == 3)
    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
