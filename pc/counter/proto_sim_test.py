#!/usr/bin/env python3
# proto_sim_test.py -- tests for pc/counter/proto.py (protocol v2) and sim.py. No hardware.
#   .venv/bin/python pc/counter/proto_sim_test.py
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from counter import proto as cp  # noqa: E402
from counter.sim import CounterSim, SeqTracker  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def arm(sim, reps=5, min_w=500, max_w=130, start=0, version=None):
    f = cp.encode(cp.T_ARM, cp.PROTO_VERSION if version is None else version, 7, cp.BOARD_IDS["esp32"], 3, 8,
                  reps, min_w, max_w, start)
    return sim.handle(f)


def codes(frames):
    return [cp.decode(f)[1][1] for f in frames if cp.decode(f)[0] == cp.T_ANOMALY]


def end(sim):
    return sim.handle(cp.encode(cp.T_END, 7))


def main():
    check("protocol version is 2", cp.PROTO_VERSION == 2)
    f = cp.encode_arm(7, "esp32", 3, 8, 100, 500, 90_000, 5)
    check("ARM round-trips, max_width_s is u32 (90 000 s = 25 h)", cp.decode(f) == (cp.T_ARM, (2, 7, 2, 3, 8, 100, 500, 90_000, 5)))
    check("ARM payload is 20 bytes", f[2] == 20)
    check("frame ends with crc8 over the preceding bytes", f[-1] == cp.crc8(f[:-1]))
    bad = bytearray(f); bad[5] ^= 1
    try:
        cp.decode(bytes(bad)); ok = False
    except cp.FrameError:
        ok = True
    check("corrupt frame rejected by CRC", ok)
    pulse = cp.encode(cp.T_PULSE, 65535, 2**40, 130 * 80_000_000, 130 * 10**9, 2, 3)
    check("PULSE carries ticks, ns and wrap count", cp.decode(pulse)[1] == (65535, 2**40, 130 * 80_000_000, 130 * 10**9, 2, 3))
    hb = cp.encode(cp.T_HEARTBEAT, 2, 123_456_789_012, 1, 5, 0, 2, 1000, 7)
    check("HEARTBEAT carries a 64-bit microsecond clock", cp.decode(hb)[1][1] == 123_456_789_012)
    for t, args in [(cp.T_REPORT, (1, 0, 100, 0, 1, 2, 3, 100, 0)), (cp.T_ANOMALY, (3, 5, 9)), (cp.T_REFVAL, (1, 2, 3)),
                    (cp.T_ACK, (1, 2)), (cp.T_SELFTEST_RESULT, (1, 2, 3)), (cp.T_ARM_ACK, (1, 1, 2)), (cp.T_STATUS, ()),
                    (cp.T_REPLAY, (1, 2)), (cp.T_END, (4,)), (cp.T_SELFTEST, (0,))]:
        check(f"type {t:#x} round-trips", cp.decode(cp.encode(t, *args)) == (t, tuple(args)))

    d = cp.Decoder()
    stream = b"\x00\x01" + f[:5] + f + pulse
    out = d.feed(stream[:7]) + d.feed(stream[7:])
    check("decoder resyncs past noise and a truncated frame", [t for t, _ in out][-2:] == [cp.T_ARM, cp.T_PULSE])
    check("decoder drops a bad-CRC frame and still yields the next", [t for t, _ in cp.Decoder().feed(bytes(bad) + pulse)] == [cp.T_PULSE])
    check("decoder counts bad frames", (lambda dd: (dd.feed(bytes(bad)), dd.bad_frames)[1] >= 1)(cp.Decoder()))

    mod = 1 << 32
    check("unwrap: short pulse", cp.unwrap_width_ticks(100, 110, 10) == (10, 0))
    w = int(130 * 80e6)
    rise = random.Random(1).randrange(mod)
    t, k = cp.unwrap_width_ticks(rise, (rise + w) % mod, w + 40)
    check("unwrap: 130 s pulse spanning 2 wraps recovered exactly", (t, k) == (w, 2))
    w1h = int(3600 * 80e6)
    t, k = cp.unwrap_width_ticks(5, (5 + w1h) % mod, w1h - 200)
    check("unwrap: 1 h pulse (67 wraps), coarse clock 200 ticks low", (t, k) == (w1h, w1h >> 32))
    w1d = int(86400 * 80e6)
    t, k = cp.unwrap_width_ticks(99, (99 + w1d) % mod, w1d + 3000)
    check("unwrap: 1 day pulse (1 609 wraps)", (t, k) == (w1d, w1d >> 32))

    # ARM / ACK
    sim = CounterSim()
    a = arm(sim)
    check("ARM accepted, ACK status ok, counter version reported", cp.decode(a[0]) == (cp.T_ARM_ACK, (7, cp.ACK_OK, 2)))
    check("second ARM while armed is refused (busy)", cp.decode(arm(sim)[0])[1][1] == cp.ACK_BUSY)
    check("ARM with a different protocol version is refused", cp.decode(arm(CounterSim(), version=1)[0])[1][1] == cp.ACK_BAD_VERSION)

    for _ in range(5):
        sim.pulse(90_000)
    out = end(sim)
    rep = cp.decode(out[-1])
    check("clean point: no anomaly, report says 5 pulses", codes(out) == [] and rep[1][2] == 5 and rep[1][1] == 0)
    check("after END the counter can be armed again", cp.decode(arm(sim)[0])[1][1] == cp.ACK_OK)

    sim = CounterSim(); arm(sim)
    for _ in range(3):
        sim.pulse(90_000)
    check("missing pulses -> code 1", codes(end(sim)) == [cp.A_MISSING])

    sim = CounterSim(); arm(sim)
    for _ in range(6):
        sim.pulse(90_000)
    check("extra pulse -> code 2", cp.A_EXTRA in codes(end(sim)))

    sim = CounterSim(); arm(sim)
    fr = sim.pulse(100)
    check("glitch (width < min) raises code 3 at once and is still recorded",
          cp.A_GLITCH in codes(fr) and cp.decode(fr[0])[1][5] == 1 and len(sim.ring) == 1)

    sim = CounterSim(); arm(sim)
    check("never started -> code 7 at END", cp.A_NEVER_STARTED in codes(end(sim)))

    # start timeout
    sim = CounterSim(); arm(sim, start=30)
    check("no start timeout before 30 s", sim.tick(10 * 1_000_000) == [])
    fr = sim.tick(31 * 1_000_000)
    check("start timeout raises code 7 once", codes(fr) == [cp.A_NEVER_STARTED] and sim.tick(40 * 1_000_000) == [])
    sim = CounterSim(); arm(sim, start=30); sim.pulse(90_000)
    check("a pulse before the timeout cancels it", sim.tick(31 * 1_000_000) == [])

    sim = CounterSim(); arm(sim, reps=1); sim.pulse(90_000); sim.pcnt += 1
    check("ISR count != PCNT count -> code 5", cp.A_COUNT_MISMATCH in codes(end(sim)))

    sim = CounterSim(ring_size=2); arm(sim, reps=3)
    out = sum((sim.pulse(90_000) for _ in range(3)), [])
    check("ring overflow -> code 9 and dropped counter", cp.A_RING_OVERFLOW in codes(out) and sim.dropped == 1)

    sim = CounterSim(); arm(sim, reps=4)
    for _ in range(4):
        sim.pulse(90_000)
    rp = sim.handle(cp.encode(cp.T_REPLAY, 7, 2))
    check("REPLAY resends from seq 2", [cp.decode(x)[1][0] for x in rp if cp.decode(x)[0] == cp.T_PULSE] == [2, 3])
    sim.handle(cp.encode(cp.T_ACK, 7, 2))
    check("ACK frees the ring up to seq 2", [cp.decode(x)[1][0] for x in sim.ring] == [3])

    # heartbeat clock
    sim = CounterSim(); sim.advance(5_000_000)
    h1 = cp.decode(sim.heartbeat())[1][1]
    sim.advance(1_500)
    h2 = cp.decode(sim.heartbeat())[1][1]
    check("heartbeat clock has sub-second resolution", h2 - h1 == 1_500)
    sim.clock_ppm_error = 100.0
    check("a simulated 100 ppm clock error shows in the heartbeat clock",
          abs(cp.decode(sim.heartbeat())[1][1] / sim.t_us - 1.0001) < 1e-6)

    # code 4
    sim = CounterSim(); arm(sim, reps=2)
    sim.pulse(90_000); sim.pulse(90_000); sim.rising_edge()
    check("line still high at END -> code 4", cp.A_STUCK_HIGH in codes(end(sim)))
    sim = CounterSim(); arm(sim, reps=2)
    sim.pulse(90_000); sim.rising_edge()
    check("not stuck before max_width", sim.tick(sim.rise_t_us + 100 * 1_000_000) == [])
    fr = sim.tick(sim.rise_t_us + 131 * 1_000_000)
    check("high longer than max_width_s (130 s) -> code 4 from the watchdog", codes(fr) == [cp.A_STUCK_HIGH])
    sim = CounterSim(); arm(sim, reps=1); sim.rising_edge(); sim.pulse(90_000)
    check("a falling edge clears the level: no code 4", cp.A_STUCK_HIGH not in codes(end(sim)))
    sim = CounterSim(); arm(sim, reps=1, max_w=90_000); sim.rising_edge()
    check("max_width_s above 18 h (u32) is honoured", sim.tick(sim.rise_t_us + 89_000 * 1_000_000) == []
          and codes(sim.tick(sim.rise_t_us + 90_001 * 1_000_000)) == [cp.A_STUCK_HIGH])

    # code 6
    sim = CounterSim(); arm(sim, reps=4)
    frames = [sim.pulse(90_000)[0] for _ in range(4)]
    trk = SeqTracker(7)
    reqs = []
    for fr in (frames[0], frames[1], frames[3]):   # seq 2 lost on the link
        reqs += trk.feed(fr)
    check("PC detects the jump and asks for a replay from seq 2",
          len(reqs) == 1 and cp.decode(reqs[0]) == (cp.T_REPLAY, (7, 2)) and trk.gaps == 1)
    out = sim.handle(reqs[0])
    check("counter raises code 6 and resends seq 2 and 3",
          cp.A_SEQ_GAP in codes(out) and [cp.decode(x)[1][0] for x in out if cp.decode(x)[0] == cp.T_PULSE] == [2, 3])
    clean = SeqTracker(7)
    check("clean stream: no gap", not any(clean.feed(x) for x in frames))
    t = SeqTracker(7); t.expected = 65535
    check("sequence wraps at 16 bits without a false gap",
          t.feed(cp.encode(cp.T_PULSE, 65535, 0, 80, 1000, 0, 0)) == [] and t.feed(cp.encode(cp.T_PULSE, 0, 0, 80, 1000, 0, 0)) == [])

    # code 8
    sim = CounterSim(); arm(sim)
    out = sim.handle(cp.encode(cp.T_SELFTEST, 2))
    check("self-test with a good clock: result frame, no code 8", cp.decode(out[0])[1] == (2, 10**9, 10**9) and codes(out) == [])
    sim.clock_ppm_error = 20.0
    check("20 ppm is inside the 50 ppm tolerance", cp.A_CLOCK_FAULT not in codes(sim.handle(cp.encode(cp.T_SELFTEST, 2))))
    sim.clock_ppm_error = 200.0
    out = sim.handle(cp.encode(cp.T_SELFTEST, 2))
    check("200 ppm error -> code 8 with measured != expected",
          cp.A_CLOCK_FAULT in codes(out) and cp.decode(out[0])[1][2] == 10**9 + 200_000)

    n_fail = R.count(False)
    print(f"\n{len(R)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
