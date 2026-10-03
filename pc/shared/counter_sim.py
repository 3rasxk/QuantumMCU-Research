# counter_sim.py -- software model of the ESP32 counter's state machine (design
# sections 4-5). Lets the PC side (client, cross-check) be built and tested with
# no hardware. Feed it widths in ns; it emits the same frames the firmware would.

from shared import counter_proto as cp


class CounterSim:
    def __init__(self, ring_size=4096):
        self.ring_size = ring_size
        self.armed = False
        self.session = 0
        self.reps = 0
        self.min_width_ns = 500
        self.max_width_s = 0
        self.seq = 0
        self.ring = []          # unacked PULSE frames
        self.widths = []
        self.mask = 0
        self.dropped = 0
        self.t_us = 0
        self.pcnt = 0

    # --- PC -> counter ---
    def handle(self, frame):
        ftype, f = cp.decode(frame)
        out = []
        if ftype == cp.T_ARM:
            self.session, _board, _circ, _n, self.reps, self.min_width_ns, self.max_width_s = f
            self.armed, self.seq, self.ring, self.widths = True, 0, [], []
            self.mask = self.dropped = self.pcnt = self.t_us = 0
            out.append(cp.encode(cp.T_ARM_ACK, self.session, 1))
        elif ftype == cp.T_ACK:
            self.ring = [fr for fr in self.ring if cp.decode(fr)[1][0] > f[1]]
        elif ftype == cp.T_REPLAY:
            out += [fr for fr in self.ring if cp.decode(fr)[1][0] >= f[1]]
        elif ftype == cp.T_END:
            out += self._end()
        return out

    def _flag(self, code, seq, detail=0):
        self.mask |= 1 << code
        return cp.encode(cp.T_ANOMALY, seq, code, detail)

    # --- signal side ---
    def pulse(self, width_ns, gap_us=100, high_at_end=False):
        """One pulse seen on the input. Returns frames for the PC."""
        if not self.armed:
            return []
        out = []
        seq = self.seq
        self.seq += 1
        self.pcnt += 1
        self.t_us += gap_us
        flags = 0
        if width_ns < self.min_width_ns:
            flags |= 1
            out.append(self._flag(cp.A_GLITCH, seq, width_ns))
        frame = cp.encode(cp.T_PULSE, seq & 0xFFFF, self.t_us, width_ns, flags)
        if len(self.ring) >= self.ring_size:
            self.dropped += 1
            out.append(self._flag(cp.A_RING_OVERFLOW, seq))
        else:
            self.ring.append(frame)
        self.widths.append(width_ns)
        self.t_us += width_ns // 1000
        return [frame] + out

    def _end(self):
        out = []
        n = len(self.widths)
        if n == 0:
            out.append(self._flag(cp.A_NEVER_STARTED, 0))
        elif n < self.reps:
            out.append(self._flag(cp.A_MISSING, n, self.reps - n))
        elif n > self.reps:
            out.append(self._flag(cp.A_EXTRA, n, n - self.reps))
        if self.pcnt != n:
            out.append(self._flag(cp.A_COUNT_MISMATCH, n, self.pcnt))
        self.armed = False
        w = self.widths or [0]
        out.append(cp.encode(cp.T_REPORT, self.session, 0 if not self.mask else 1, n,
                             self.mask, min(w), max(w), sum(w), self.pcnt, self.dropped))
        return out

    def heartbeat(self, uptime_s=1):
        return cp.encode(cp.T_HEARTBEAT, uptime_s, 1 if self.armed else 0, len(self.ring),
                         self.dropped, 0, 200000, (self.seq - 1) & 0xFFFF)
