# client.py -- serial client for the ESP32 counter (protocol v2). A background thread drains the
# port continuously and decodes frames into a queue, because the sweep blocks on the TARGET port
# for minutes or hours while the counter keeps streaming (pulses and 1 Hz heartbeats). The counter
# port is opened by exactly one CounterClient and is never shared with the target port.
#
# Transports: SerialTransport (pyserial, real counter) and SimTransport (wraps counter.sim.CounterSim,
# for tests and dry flows, no hardware).

import queue
import socket
import threading
import time

from counter import proto as cp


class SerialTransport:
    def __init__(self, port, baud=115200):
        import serial
        self.port = port
        self.ser = serial.Serial(port, baud, timeout=0.1)

    def write(self, data):
        self.ser.write(data)

    def read(self, n=512):
        return self.ser.read(n)

    def close(self):
        try:
            self.ser.close()
        except Exception:  # noqa: BLE001
            pass


class TcpServerTransport:
    """The counter connects TO the PC (WiFi): this side listens on `port` and serves the most recent connection.
    Same byte stream as the USB serial link (protocol v2 frames). A dropped connection is not an error: read()
    returns nothing until the counter reconnects; write() raises OSError while nobody is connected, which the
    session treats like any other counter problem (logged, micros() data untouched).
    Local network only: bind address defaults to all interfaces because the counter is a separate device; use
    a trusted WiFi (docs/design/counter_design.md, security)."""

    def __init__(self, port, host="0.0.0.0"):
        self.port = f"tcp:{port}"
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((host, int(port)))
        self.srv.listen(1)
        self.srv.settimeout(0.2)
        self.conn = None
        self.peer = None
        self._lock = threading.Lock()
        self._stop = False
        self._th = threading.Thread(target=self._accept_loop, daemon=True)
        self._th.start()

    def _accept_loop(self):
        while not self._stop:
            try:
                c, addr = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            c.settimeout(0.05)
            c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                old, self.conn, self.peer = self.conn, c, addr
            if old is not None:
                try:
                    old.close()
                except OSError:
                    pass

    @property
    def connected(self):
        return self.conn is not None

    def write(self, data):
        with self._lock:
            c = self.conn
        if c is None:
            raise OSError("counter not connected (waiting for it on the TCP port)")
        try:
            c.sendall(data)
        except OSError:
            self._drop(c)
            raise

    def _drop(self, c):
        with self._lock:
            if self.conn is c:
                self.conn = None
        try:
            c.close()
        except OSError:
            pass

    def read(self, n=512):
        with self._lock:
            c = self.conn
        if c is None:
            time.sleep(0.05)
            return b""
        try:
            data = c.recv(n)
        except socket.timeout:
            return b""
        except OSError:
            self._drop(c)
            return b""
        if data == b"":          # peer closed
            self._drop(c)
        return data

    def close(self):
        self._stop = True
        for c in (self.conn, self.srv):
            try:
                if c is not None:
                    c.close()
            except OSError:
                pass


def make_transport(port_spec, baud=115200):
    """'tcp:5055' -> listen for the counter over WiFi; anything else -> USB serial device path."""
    if str(port_spec).startswith("tcp:"):
        return TcpServerTransport(int(str(port_spec)[4:]))
    return SerialTransport(port_spec, baud)


class SimTransport:
    """In-memory counter. `sim` is a counter.sim.CounterSim; frames written by the client are handled
    by it and its replies are queued for read(). Tests drive the signal side via sim.pulse()/... and
    call push() with the frames those return (pulses reach the PC as the firmware would stream them)."""

    def __init__(self, sim, port="SIM"):
        self.sim = sim
        self.port = port
        self._q = queue.Queue()
        self.closed = False
        self.fail_after_writes = None   # tests: simulate a disconnect
        self.writes = 0

    def write(self, data):
        self.writes += 1
        if self.fail_after_writes is not None and self.writes > self.fail_after_writes:
            raise OSError("simulated counter disconnect")
        for fr in self.sim.handle(bytes(data)):
            self._q.put(fr)

    def push(self, frames):
        for fr in frames:
            self._q.put(fr)

    def read(self, n=512):
        out = b""
        try:
            out += self._q.get(timeout=0.02)
            while True:
                out += self._q.get_nowait()
        except queue.Empty:
            pass
        return out

    def close(self):
        self.closed = True


class CounterClient:
    def __init__(self, transport, on_frame=None):
        self.t = transport
        self.on_frame = on_frame     # optional live-view hook, called in the reader thread for every frame
        self.decoder = cp.Decoder()
        self.frames = queue.Queue()
        self.last_heartbeat = None      # (monotonic time, fields)
        self.error = None
        self._stop = False
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self):
        while not self._stop:
            try:
                data = self.t.read(512)
            except Exception as e:  # noqa: BLE001
                self.error = e
                return
            if data:
                for ftype, fields in self.decoder.feed(data):
                    if ftype == cp.T_HEARTBEAT:
                        self.last_heartbeat = (time.monotonic(), fields)
                    if self.on_frame is not None:
                        try:
                            self.on_frame(ftype, fields)
                        except Exception:  # noqa: BLE001 -- the live view must never break the link
                            pass
                    self.frames.put((ftype, fields))
            else:
                time.sleep(0.005)

    @property
    def bad_frames(self):
        return self.decoder.bad_frames

    def send(self, frame):
        self.t.write(frame)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.frames.get_nowait())
            except queue.Empty:
                return out

    def wait_for(self, ftype, timeout_s, collect=None):
        """Block until a frame of `ftype` arrives; every other frame seen meanwhile is appended to `collect`."""
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            try:
                t, f = self.frames.get(timeout=0.05)
            except queue.Empty:
                if self.error:
                    return None
                continue
            if t == ftype:
                return t, f
            if collect is not None:
                collect.append((t, f))
        return None

    def heartbeat_age_s(self):
        return None if self.last_heartbeat is None else time.monotonic() - self.last_heartbeat[0]

    def alive(self, max_age_s=5.0):
        age = self.heartbeat_age_s()
        return self.error is None and age is not None and age <= max_age_s

    def close(self):
        self._stop = True
        self._th.join(timeout=2)
        self.t.close()
