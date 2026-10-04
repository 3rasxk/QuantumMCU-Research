# proto.py -- frame codec for the ESP32 pulse counter, PROTOCOL VERSION 2
# (docs/design/counter_design.md section 5). Pure Python, no hardware. Conventions follow
# firmware/common/protocol.hpp: fixed layouts, big-endian, CRC-8/SMBUS (poly 0x07, init 0x00)
# over every preceding byte, reused from pc/phase3_offload/protocol.py so the two never diverge.
#
# Frame: [marker][type][len][payload (len bytes)][crc8]
#   marker 0xC7 = PC -> counter, 0xD7 = counter -> PC.
#
# v2 (2026-10-04) vs the S0 draft (v1): ARM carries a protocol version, max_width_s widened
# u16 -> u32 (reps of 22.8 h exist in the plan), start_timeout_s added, ARM_ACK carries a status
# and the counter's version, PULSE carries width ticks and the 32-bit wrap count, HEARTBEAT carries
# a 64-bit microsecond counter clock (v1 had whole seconds: useless for ppm calibration).

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from phase3_offload.protocol import crc8  # noqa: E402

PROTO_VERSION = 2

M_TO_COUNTER = 0xC7
M_TO_PC = 0xD7

# PC -> counter
T_ARM, T_END, T_ACK, T_REPLAY, T_REFVAL, T_SELFTEST, T_STATUS = 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6
# counter -> PC
T_PULSE, T_ANOMALY, T_REPORT, T_HEARTBEAT, T_ARM_ACK, T_SELFTEST_RESULT = 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5

BOARD_IDS = {"uno": 0, "esp8266": 1, "esp32": 2}

# ARM_ACK status byte
ACK_OK, ACK_BUSY, ACK_BAD_VERSION, ACK_MALFORMED = 1, 0, 2, 3

# anomaly codes (design section 4)
A_MISSING, A_EXTRA, A_GLITCH, A_STUCK_HIGH, A_COUNT_MISMATCH, A_SEQ_GAP, A_NEVER_STARTED, \
    A_CLOCK_FAULT, A_RING_OVERFLOW = range(1, 10)
ANOMALY_NAMES = {1: "missing pulse", 2: "extra pulse", 3: "glitch", 4: "still high at end",
                 5: "count mismatch", 6: "sequence gap", 7: "never started / start timeout",
                 8: "clock fault", 9: "ring overflow"}

# payload layouts (big-endian)
_FMT = {
    T_ARM: ">BIBBBHIIH",      # proto, session, board, circuit, n, reps, min_width_ns, max_width_s(u32), start_timeout_s
    T_END: ">I",
    T_ACK: ">IH",
    T_REPLAY: ">IH",
    T_REFVAL: ">IHI",         # session, seq, micros_exec_us
    T_SELFTEST: ">B",
    T_STATUS: ">",
    T_PULSE: ">HQQQHB",       # seq, rise_us, width_ticks, width_ns, wraps, flags
    T_ANOMALY: ">HBI",        # seq, code, detail
    T_REPORT: ">IBHHQQQHH",   # session, status, pulses, anomaly_mask, min, max, sum width_ns, pcnt, overruns
    T_HEARTBEAT: ">BQBHHBIH",  # proto, counter_us, state, ring_depth, dropped, ws_clients, free_heap, last_seq
    T_ARM_ACK: ">IBB",        # session, status, counter proto version
    T_SELFTEST_RESULT: ">BQQ",  # group, expected_ns, measured_ns
}
_TO_COUNTER = {T_ARM, T_END, T_ACK, T_REPLAY, T_REFVAL, T_SELFTEST, T_STATUS}

PULSE_FIELDS = ("seq", "rise_us", "width_ticks", "width_ns", "wraps", "flags")


class FrameError(ValueError):
    pass


def encode(ftype, *fields):
    fmt = _FMT[ftype]
    payload = struct.pack(fmt, *fields)
    marker = M_TO_COUNTER if ftype in _TO_COUNTER else M_TO_PC
    body = bytes([marker, ftype, len(payload)]) + payload
    return body + bytes([crc8(body)])


def encode_arm(session, board, circuit, n, reps, min_width_ns=500, max_width_s=130, start_timeout_s=0):
    return encode(T_ARM, PROTO_VERSION, session, BOARD_IDS.get(board, board), circuit, n, reps,
                  min_width_ns, max_width_s, start_timeout_s)


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
    64-bit coarse clock only has to be right to within half a wrap. -> (ticks, wraps)"""
    mod = 1 << 32
    fine = (fall32 - rise32) % mod
    k = max(round((coarse_width_ticks - fine) / mod), 0)
    return fine + k * mod, k
