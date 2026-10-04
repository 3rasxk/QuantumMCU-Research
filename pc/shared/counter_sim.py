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
        self.high = False        # input level; True between a rising edge and its falling edge
        self.rise_t_us = 0
        self.clock_ppm_error = 0.0   # simulated counter oscillator error
        self.clock_tol_ppm = 50.0

    # --- PC -> counter ---
    def handle(self, frame):
        ftype, f = cp.decode(frame)
        out = []
        if ftype == cp.T_ARM:
            self.session, _board, _circ, _n, self.reps, self.min_width_ns, self.max_width_s = f
            self.armed, self.seq, self.ring, self.widths = True, 0, [], []
            self.mask = self.dropped = self.pcnt = self.t_us = 0
            self.high = False
            out.append(cp.encode(cp.T_ARM_ACK, self.session, 1))
        elif ftype == cp.T_ACK:
            self.ring = [fr for fr in self.ring if cp.decode(fr)[1][0] > f[1]]
        elif ftype == cp.T_REPLAY:
            # the PC saw a sequence jump (code 6): record it and resend what is still in the ring
            out.append(self._flag(cp.A_SEQ_GAP, f[1]))
            out += [fr for fr in self.ring if cp.decode(fr)[1][0] >= f[1]]
        elif ftype == cp.T_SELFTEST:
            out += self.selftest(f[0])
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
        self.high = False
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

    def rising_edge(self):
        """Line goes high without (yet) a falling edge."""
        self.high = True
        self.rise_t_us = self.t_us

    def tick(self, now_us):
        """Watchdog: line still high longer than max_width_s -> code 4."""
        if self.armed and self.high and self.max_width_s and now_us - self.rise_t_us > self.max_width_s * 1_000_000:
            self.high = False
            return [self._flag(cp.A_STUCK_HIGH, len(self.widths), 1)]
        return []

    SELFTEST_EXPECTED_NS = {1: 1_000_000, 2: 1_000_000_000}

    def selftest(self, pattern):
        """Self-loopback: the same oscillator generates and measures, so only a
        modelled `clock_ppm_error` (e.g. a fault injected for the test) can show up."""
        exp = self.SELFTEST_EXPECTED_NS.get(pattern, 1_000_000)
        meas = int(round(exp * (1 + self.clock_ppm_error * 1e-6)))
        out = [cp.encode(cp.T_SELFTEST_RESULT, pattern, exp, meas)]
        if abs(meas - exp) > exp * self.clock_tol_ppm * 1e-6:
            out.append(self._flag(cp.A_CLOCK_FAULT, 0, abs(meas - exp)))
        return out

    def _end(self):
        out = []
        if self.high:
            out.append(self._flag(cp.A_STUCK_HIGH, len(self.widths), 0))
            self.high = False
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


class SeqTracker:
    """PC-side check: detects a jump in PULSE sequence numbers and builds the REPLAY
    request (design code 6). Wraps at 16 bits like the wire field."""

    def __init__(self, session):
        self.session = session
        self.expected = 0
        self.gaps = 0

    def feed(self, frame):
        ftype, f = cp.decode(frame)
        if ftype != cp.T_PULSE:
            return []
        seq = f[0]
        if seq != self.expected & 0xFFFF:
            self.gaps += 1
            req = cp.encode(cp.T_REPLAY, self.session, self.expected & 0xFFFF)
            self.expected = (seq + 1)
            return [req]
        self.expected += 1
        return []
