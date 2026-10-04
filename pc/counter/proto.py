# counter_proto.py -- frame codec for the ESP32 pulse counter (docs/counter_design.md
# section 5). Pure Python, no hardware. Conventions follow firmware/common/protocol.hpp:
# fixed layouts, big-endian, CRC-8/SMBUS (poly 0x07, init 0x00) over every preceding
# byte, reused from pc/phase3_offload/protocol.py so the two never diverge.
#
# Frame: [marker][type][len][payload (len bytes)][crc8]
#   marker 0xC7 = PC -> counter, 0xD7 = counter -> PC.

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from phase3_offload.protocol import crc8  # noqa: E402

M_TO_COUNTER = 0xC7
M_TO_PC = 0xD7

# PC -> counter
T_ARM, T_END, T_ACK, T_REPLAY, T_REFVAL, T_SELFTEST, T_STATUS = 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6
# counter -> PC
T_PULSE, T_ANOMALY, T_REPORT, T_HEARTBEAT, T_ARM_ACK, T_SELFTEST_RESULT = 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5

BOARD_IDS = {"uno": 0, "esp8266": 1, "esp32": 2}

# anomaly codes (design section 4)
A_MISSING, A_EXTRA, A_GLITCH, A_STUCK_HIGH, A_COUNT_MISMATCH, A_SEQ_GAP, A_NEVER_STARTED, \
    A_CLOCK_FAULT, A_RING_OVERFLOW = range(1, 10)

# payload layouts (big-endian)
_FMT = {
    T_ARM: ">IBBBHIH",        # session, board, circuit, n, reps, min_width_ns, max_width_s
    T_END: ">I",
    T_ACK: ">IH",
    T_REPLAY: ">IH",
    T_REFVAL: ">IHI",         # session, seq, micros_exec_us
    T_SELFTEST: ">B",
    T_STATUS: ">",
    T_PULSE: ">HQQB",         # seq, rise_us, width_ns, flags
    T_ANOMALY: ">HBI",        # seq, code, detail
    T_REPORT: ">IBHHQQQHH",   # session, status, pulses, anomaly_mask, min, max, sum width_ns, pcnt, overruns
    T_HEARTBEAT: ">IBHHBIH",  # uptime_s, state, ring_depth, dropped, ws_clients, free_heap, last_seq
    T_ARM_ACK: ">IB",         # session, accepted
    T_SELFTEST_RESULT: ">BQQ",  # pattern, expected_ns, measured_ns
}
_TO_COUNTER = {T_ARM, T_END, T_ACK, T_REPLAY, T_REFVAL, T_SELFTEST, T_STATUS}


class FrameError(ValueError):
    pass


def encode(ftype, *fields):
    fmt = _FMT[ftype]
    payload = struct.pack(fmt, *fields)
    marker = M_TO_COUNTER if ftype in _TO_COUNTER else M_TO_PC
    body = bytes([marker, ftype, len(payload)]) + payload
    return body + bytes([crc8(body)])


def decode(frame):
    """-> (type, fields tuple). Raises FrameError on any structural problem."""
    if len(frame) < 4:
        raise FrameError("short frame")
    marker, ftype, n = frame[0], frame[1], frame[2]
    if marker not in (M_TO_COUNTER, M_TO_PC):
        raise FrameError(f"bad marker {marker:#x}")
    if ftype not in _FMT:
        raise FrameError(f"unknown type {ftype:#x}")
    if len(frame) != 4 + n:
        raise FrameError("length mismatch")
    if crc8(frame[:-1]) != frame[-1]:
        raise FrameError("crc mismatch")
    if struct.calcsize(_FMT[ftype]) != n:
        raise FrameError("payload size does not match type")
    return ftype, struct.unpack(_FMT[ftype], frame[3:3 + n])


class Decoder:
    """Byte-stream decoder: resynchronises on the next marker after a bad frame
    (never raises), counts what it dropped."""

    def __init__(self):
        self.buf = bytearray()
        self.bad_frames = 0

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            while self.buf and self.buf[0] not in (M_TO_COUNTER, M_TO_PC):
                self.buf.pop(0)
            if len(self.buf) < 3:
                break
            total = 4 + self.buf[2]
            if len(self.buf) < total:
                break
            frame = bytes(self.buf[:total])
            try:
                out.append(decode(frame))
                del self.buf[:total]
            except FrameError:
                self.bad_frames += 1
                self.buf.pop(0)  # resync one byte later
        return out


def unwrap_width_ticks(rise32, fall32, coarse_width_ticks):
    """Coarse+fine width (design section 3): the 32-bit capture timer wraps; the
    64-bit coarse clock only has to be right to within half a wrap."""
    mod = 1 << 32
    fine = (fall32 - rise32) % mod
    k = round((coarse_width_ticks - fine) / mod)
    return fine + max(k, 0) * mod
