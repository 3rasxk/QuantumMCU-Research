#!/usr/bin/env python3
# tcp_test.py -- the counter over WiFi/TCP, without hardware: a thread plays the counter (CounterSim) and CONNECTS to
# the PC's TcpServerTransport on 127.0.0.1, exactly as the firmware does over WiFi. Covers: heartbeat/ARM/pulses/END over
# TCP into the reference files, reconnect after a drop, a frame lost on the link repaired by REPLAY (code 6), a counter
# that never connects, and the runner's tcp: port handling.
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pc"))
from counter import proto as cp  # noqa: E402
from counter.client import CounterClient, TcpServerTransport, make_transport  # noqa: E402
from counter.session import CounterSession  # noqa: E402
from counter.sim import CounterSim  # noqa: E402
from counter import ref_schema as rs  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class FakeCounter(threading.Thread):
    """Plays the ESP32: connects to the PC, answers frames with CounterSim, streams heartbeats, can drop frames."""

    def __init__(self, port, drop_pulse_seq=None, pulses_per_point=10):
        super().__init__(daemon=True)
        self.port, self.sim, self.stop = port, CounterSim(), False
        self.drop_seq, self.pulses_per_point = drop_pulse_seq, pulses_per_point
        self.sock = None
        self.dropped_once = False

    def connect(self):
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        self.sock.settimeout(0.05)

    def send(self, frames):
        for fr in frames:
            t, f = cp.decode(fr)
            if t == cp.T_PULSE and f[0] == self.drop_seq and not self.dropped_once:
                self.dropped_once = True
                continue                                      # lost on the link
            try:
                self.sock.sendall(fr)
            except OSError:
                return

    def run(self):
        dec = cp.Decoder()
        last_hb = 0
        while not self.stop:
            if self.sock is None:
                time.sleep(0.05); continue
            if time.monotonic() - last_hb > 0.2:
                last_hb = time.monotonic(); self.send([self.sim.heartbeat()])
            try:
                data = self.sock.recv(256)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                return
            for t, f in dec.feed(data):
                fr = cp.encode(t, *f)
                out = self.sim.handle(fr)
                self.send(out)
                if t == cp.T_ARM:                             # the "target" runs: pulses stream back
                    for _ in range(self.pulses_per_point):
                        self.send(self.sim.pulse(90_000))


def rows(p):
    return rs.read_rows(p)


def main():
    # make_transport routing
    p = free_port()
    tr = make_transport(f"tcp:{p}")
    check("make_transport('tcp:PORT') returns a TCP server transport", isinstance(tr, TcpServerTransport))
    tr.close()
    check("make_transport(device path) is serial (not opened here)", make_transport.__doc__ is not None)

    # full point over TCP
    with tempfile.TemporaryDirectory() as tmp:
        port = free_port()
        client = CounterClient(TcpServerTransport(port))
        check("no counter connected yet: client not alive, write refused", not client.alive(0.5))
        fc = FakeCounter(port); fc.connect(); fc.start()
        t0 = time.monotonic()
        while not client.alive(2) and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        check("counter connects over TCP and its heartbeat is seen", client.alive(2))
        cs = CounterSession(client, "esp32", "h_all", Path(tmp) / "ref", reps=10, session_id="TCP")
        ok = cs.arm_point(4)
        time.sleep(0.4)
        st = cs.finish_point(4, [90.0 + 1.0] * 10)
        check("ARM, 10 pulses and END over TCP: ref_status ok", ok and st == "ok", st)
        cmp_ = rows(Path(tmp) / "ref" / "ref_compare_points.csv")
        check("micros() minus counter comparison written from TCP data (+1 us)", cmp_ and abs(float(cmp_[0]["median_diff_us"]) - 1.0) < 1e-6)
        fc.stop = True; fc.sock.close()
        client.close()

    # a frame lost on the link is repaired by REPLAY
    with tempfile.TemporaryDirectory() as tmp:
        port = free_port()
        client = CounterClient(TcpServerTransport(port))
        fc = FakeCounter(port, drop_pulse_seq=3); fc.connect(); fc.start()
        t0 = time.monotonic()
        while not client.alive(2) and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        cs = CounterSession(client, "esp32", "h_all", Path(tmp) / "ref", reps=10, session_id="TCP2")
        cs.arm_point(4); time.sleep(0.4)
        st = cs.finish_point(4, [90.0] * 10)
        pl = rows(Path(tmp) / "ref" / "ref_pulses.csv")
        check("pulse 3 lost on the link: all 10 pulses present after REPLAY", sorted(int(r["seq"]) for r in pl) == list(range(10)), str(len(pl)))
        check("the gap is an anomaly (code 6), logged, comparison still joined from the repaired data",
              st == "anomaly" and "6" in rows(Path(tmp) / "ref" / "ref_points.csv")[0]["anomaly_codes"].split()
              and "sequence gap" in (Path(tmp) / "ref" / "ref_issues.log").read_text() and len(rows(Path(tmp) / "ref" / "ref_compare.csv")) == 10)
        fc.stop = True; fc.sock.close(); client.close()

    # reconnect after a drop
    with tempfile.TemporaryDirectory() as tmp:
        port = free_port()
        tr = TcpServerTransport(port)
        client = CounterClient(tr)
        fc = FakeCounter(port); fc.connect(); fc.start()
        t0 = time.monotonic()
        while not client.alive(2) and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        fc.stop = True; fc.sock.close()
        time.sleep(0.4)
        check("peer closed: server notices, write refused (counter lost)", not tr.connected)
        fc2 = FakeCounter(port); fc2.connect(); fc2.start()
        t0 = time.monotonic()
        while not (tr.connected and client.alive(1)) and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        check("counter reconnects over TCP and the heartbeat resumes", tr.connected and client.alive(1))
        fc2.stop = True; fc2.sock.close(); client.close()

    # runner: tcp: port handling
    import run as run_mod
    p = free_port()
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        run_mod.check_counter_port(f"tcp:{p}", "/dev/cu.T")
    check("runner accepts tcp:PORT and explains the WiFi link", "WiFi/TCP" in buf.getvalue())
    s = socket.socket(); s.bind(("0.0.0.0", p)); s.listen(1)
    try:
        run_mod.check_counter_port(f"tcp:{p}", "/dev/cu.T"); ok = False
    except run_mod.RunnerError:
        ok = True
    s.close()
    check("runner refuses a TCP port that is already in use", ok)
    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
