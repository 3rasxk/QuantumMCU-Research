#!/usr/bin/env python3
# wifi_link_check.py -- hardware check of the counter's WiFi/TCP link with NO signal wiring: connect, soak, round-trip
# latency, server restart (counter must reconnect), counter reboot (via the USB port's reset line, optional).
#   .venv/bin/python pc/counter/wifi_link_check.py --tcp-port 5055 --soak-s 90 --reset-port /dev/cu.usbserial-110
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import proto as cp  # noqa: E402
from counter.client import CounterClient, TcpServerTransport  # noqa: E402


def wait_alive(cl, timeout):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        if cl.alive(2.5):
            return time.monotonic() - t
        time.sleep(0.05)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tcp-port", type=int, default=5055)
    ap.add_argument("--soak-s", type=float, default=90)
    ap.add_argument("--reset-port", default=None, help="USB port of the counter; its RTS line reboots the board")
    a = ap.parse_args()
    res = {}
    tr = TcpServerTransport(a.tcp_port)
    cl = CounterClient(tr)
    t = wait_alive(cl, 60)
    res["connect_s"] = t
    print(f"A. counter connected over WiFi after {t:.1f} s (peer {tr.peer})" if t is not None else "A. NO CONNECTION within 60 s")
    if t is None:
        sys.exit(1)

    # B soak: heartbeat arrival gaps and counter-clock continuity
    hb = []
    end = time.monotonic() + a.soak_s
    while time.monotonic() < end:
        for ftype, f in cl.drain():
            if ftype == cp.T_HEARTBEAT:
                hb.append((time.monotonic(), f[1]))
        time.sleep(0.05)
    gaps = [b[0] - a_[0] for a_, b in zip(hb, hb[1:])]
    clk = [(b[1] - a_[1]) / 1e6 for a_, b in zip(hb, hb[1:])]
    res["soak"] = {"heartbeats": len(hb), "max_pc_gap_s": max(gaps), "median_pc_gap_s": statistics.median(gaps),
                   "max_counter_gap_s": max(clk), "bad_frames": cl.bad_frames}
    print(f"B. soak {a.soak_s:.0f} s: {len(hb)} heartbeats, PC-side gap median {statistics.median(gaps):.2f} s max {max(gaps):.2f} s, "
          f"counter-clock step max {max(clk):.3f} s, bad frames {cl.bad_frames}")

    # C round trip: STATUS -> HEARTBEAT reply
    rtt = []
    for _ in range(40):
        cl.drain()
        t0 = time.monotonic()
        cl.send(cp.encode(cp.T_STATUS))
        if cl.wait_for(cp.T_HEARTBEAT, 2.0) is not None:
            rtt.append((time.monotonic() - t0) * 1000)
        time.sleep(0.05)
    if rtt:
        rtt.sort()
        print(f"C. STATUS round trip over WiFi: {len(rtt)}/40 answered, median {statistics.median(rtt):.1f} ms, p95 {rtt[int(len(rtt) * .95) - 1]:.1f} ms, max {rtt[-1]:.1f} ms")
    else:
        print("C. no STATUS answers")
    res["rtt_ms"] = rtt

    # D server restart
    print("D. closing the server for 6 s, then reopening...")
    cl.close()
    time.sleep(6)
    tr = TcpServerTransport(a.tcp_port)
    cl = CounterClient(tr)
    t = wait_alive(cl, 60)
    res["reconnect_after_server_restart_s"] = t
    print(f"D. counter reconnected {t:.1f} s after the server came back" if t is not None else "D. counter did NOT reconnect within 60 s")

    # E counter reboot: a real reboot is a heartbeat whose counter clock restarted (smaller than before)
    if a.reset_port:
        import serial
        cl.drain(); time.sleep(1.3)
        before = [f[1] for ty, f in cl.drain() if ty == cp.T_HEARTBEAT]
        before = before[-1] if before else 0
        s = serial.Serial(); s.port = a.reset_port; s.baudrate = 115200; s.dtr = False; s.rts = False; s.open()
        s.rts = True; time.sleep(0.15); s.rts = False
        s.close()
        t0 = time.monotonic()
        seen = None
        while time.monotonic() - t0 < 60 and seen is None:
            for ty, f in cl.drain():
                if ty == cp.T_HEARTBEAT and f[1] < before - 500_000:
                    seen = (time.monotonic() - t0, f[1] / 1e6)
                    break
            time.sleep(0.05)
        res["reconnect_after_reboot_s"] = seen[0] if seen else None
        print(f"E. counter rebooted and its link was back {seen[0]:.1f} s later (counter clock then {seen[1]:.1f} s)" if seen else "E. counter did NOT reconnect after reboot within 60 s")
    print(f"frames bad total: {cl.bad_frames}")
    cl.close()


if __name__ == "__main__":
    main()
