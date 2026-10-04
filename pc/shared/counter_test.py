#!/usr/bin/env python3
# counter_test.py -- tests for pc/shared/counter_proto.py and counter_sim.py (no hardware).
#   .venv/bin/python pc/shared/counter_test.py
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import counter_proto as cp  # noqa: E402
from shared.counter_sim import CounterSim, SeqTracker  # noqa: E402

R = []


def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")


def arm(sim, reps=5, min_w=500):
    return sim.handle(cp.encode(cp.T_ARM, 7, cp.BOARD_IDS["esp32"], 3, 8, reps, min_w, 130))


def codes(frames):
    return [cp.decode(f)[1][1] for f in frames if cp.decode(f)[0] == cp.T_ANOMALY]


def main():
    f = cp.encode(cp.T_ARM, 7, 2, 3, 8, 100, 500, 130)
    check("ARM round-trips", cp.decode(f) == (cp.T_ARM, (7, 2, 3, 8, 100, 500, 130)))
    check("frame ends with crc8 over the preceding bytes", f[-1] == cp.crc8(f[:-1]))
    bad = bytearray(f); bad[5] ^= 1
    try:
        cp.decode(bytes(bad)); ok = False
    except cp.FrameError:
        ok = True
    check("corrupt frame rejected by CRC", ok)
    pulse = cp.encode(cp.T_PULSE, 65535, 2**40, 130 * 10**9, 3)
    check("PULSE carries a 130 s width as u64 ns", cp.decode(pulse)[1] == (65535, 2**40, 130 * 10**9, 3))
    for t, args in [(cp.T_REPORT, (1, 0, 100, 0, 1, 2, 3, 100, 0)), (cp.T_HEARTBEAT, (9, 1, 5, 0, 2, 1000, 7)),
                    (cp.T_ANOMALY, (3, 5, 9)), (cp.T_REFVAL, (1, 2, 3)), (cp.T_ACK, (1, 2)),
                    (cp.T_SELFTEST_RESULT, (1, 2, 3)), (cp.T_ARM_ACK, (1, 1)), (cp.T_STATUS, ())]:
        check(f"type {t:#x} round-trips", cp.decode(cp.encode(t, *args)) == (t, tuple(args)))

    d = cp.Decoder()
    stream = b"\x00\x01" + f[:5] + f + pulse
    out = d.feed(stream[:7]) + d.feed(stream[7:])
    check("decoder resyncs past noise and a truncated frame", [t for t, _ in out][-2:] == [cp.T_ARM, cp.T_PULSE],
          str([hex(t) for t, _ in out]))
    out2 = cp.Decoder().feed(bytes(bad) + pulse)
    check("decoder drops a bad-CRC frame and still yields the next", [t for t, _ in out2] == [cp.T_PULSE])

    fine = 10
    check("unwrap: short pulse", cp.unwrap_width_ticks(100, 100 + fine, fine) == fine)
    mod = 1 << 32
    w = int(130 * 80e6)  # 130 s at 80 MHz
    rise = random.Random(1).randrange(mod)
    fall = (rise + w) % mod
    check("unwrap: 130 s pulse spanning 2 wraps recovered exactly", cp.unwrap_width_ticks(rise, fall, w + 40) == w)

    sim = CounterSim()
    check("ARM accepted", cp.decode(arm(sim)[0]) == (cp.T_ARM_ACK, (7, 1)))
    for _ in range(5):
        sim.pulse(90_000)
    out = sim.handle(cp.encode(cp.T_END, 7))
    rep = cp.decode(out[-1])
    check("clean point: no anomaly, report says 5 pulses", codes(out) == [] and rep[1][2] == 5 and rep[1][1] == 0)

    sim = CounterSim(); arm(sim)
    for _ in range(3):
        sim.pulse(90_000)
    out = sim.handle(cp.encode(cp.T_END, 7))
    check("missing pulses -> code 1", codes(out) == [cp.A_MISSING])

    sim = CounterSim(); arm(sim)
    for _ in range(6):
        sim.pulse(90_000)
    check("extra pulse -> code 2", cp.A_EXTRA in codes(sim.handle(cp.encode(cp.T_END, 7))))

    sim = CounterSim(); arm(sim)
    fr = sim.pulse(100)
    check("glitch (width < min) raises code 3 at once and is still recorded",
          cp.A_GLITCH in codes(fr) and cp.decode(fr[0])[1][3] == 1 and len(sim.ring) == 1)

    sim = CounterSim(); arm(sim)
    check("never started -> code 7", cp.A_NEVER_STARTED in codes(sim.handle(cp.encode(cp.T_END, 7))))

    sim = CounterSim(); arm(sim); sim.pulse(90_000); sim.pcnt += 1
    check("ISR count != PCNT count -> code 5", cp.A_COUNT_MISMATCH in codes(sim.handle(cp.encode(cp.T_END, 7))))

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
    check("heartbeat decodes", cp.decode(sim.heartbeat())[0] == cp.T_HEARTBEAT)

    # code 4: still high at end / stuck high
    sim = CounterSim(); arm(sim, reps=2)
    sim.pulse(90_000); sim.pulse(90_000); sim.rising_edge()
    out = sim.handle(cp.encode(cp.T_END, 7))
    check("line still high at END -> code 4", cp.A_STUCK_HIGH in codes(out))
    sim = CounterSim(); arm(sim, reps=2)
    sim.pulse(90_000); sim.rising_edge()
    check("not stuck before max_width", sim.tick(100 * 1_000_000) == [])
    fr = sim.tick(131 * 1_000_000)
    check("high longer than max_width_s (130 s) -> code 4 from the watchdog", codes(fr) == [cp.A_STUCK_HIGH])
    sim = CounterSim(); arm(sim, reps=1); sim.rising_edge(); sim.pulse(90_000)
    check("a falling edge clears the level: no code 4", cp.A_STUCK_HIGH not in codes(sim.handle(cp.encode(cp.T_END, 7))))

    # code 6: sequence gap seen by the PC, REPLAY, counter records the code
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
          t.feed(cp.encode(cp.T_PULSE, 65535, 0, 1000, 0)) == [] and t.feed(cp.encode(cp.T_PULSE, 0, 0, 1000, 0)) == [])

    # code 8: clock fault
    sim = CounterSim(); arm(sim)
    out = sim.handle(cp.encode(cp.T_SELFTEST, 2))
    check("self-test with a good clock: result frame, no code 8",
          cp.decode(out[0])[1] == (2, 10**9, 10**9) and codes(out) == [])
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
