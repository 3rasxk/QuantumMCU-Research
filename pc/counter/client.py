# client.py -- serial client for the ESP32 counter (protocol v2). A background thread drains the
# port continuously and decodes frames into a queue, because the sweep blocks on the TARGET port
# for minutes or hours while the counter keeps streaming (pulses and 1 Hz heartbeats). The counter
# port is opened by exactly one CounterClient and is never shared with the target port.
#
# Transports: SerialTransport (pyserial, real counter) and SimTransport (wraps counter.sim.CounterSim,
# for tests and dry flows, no hardware).

import queue
import threading
import time

from counter import proto as cp


class SerialTransport:
    def __init__(self, port, baud=921600):
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
    def __init__(self, transport):
        self.t = transport
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
