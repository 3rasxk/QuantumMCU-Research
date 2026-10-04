#!/usr/bin/env python3
# counter_fw_parity_test.py -- hardware-free byte-for-byte check that the frame code in
# firmware/counter_esp32/src/main.cpp (UNFLASHED DRAFT) produces exactly the frames
# pc/shared/counter_proto.py encodes. The firmware's own helper source is extracted
# verbatim, compiled on the PC with g++ (no board involved) and run.
#   .venv/bin/python pc/shared/counter_fw_parity_test.py
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pc"))
from counter import proto as cp  # noqa: E402

CASES = [
    ("ARM_ACK", "begin(f,T_ARM_ACK); put32(f,0x01020304); put8(f,1); put8(f,2);", (cp.T_ARM_ACK, 0x01020304, 1, 2)),
    ("ANOMALY", "begin(f,T_ANOMALY); put16(f,513); put8(f,3); put32(f,0xDEADBEEF);", (cp.T_ANOMALY, 513, 3, 0xDEADBEEF)),
    ("PULSE", "begin(f,T_PULSE); put16(f,65535); put64(f,1ULL<<40); put64(f,10400000000ULL); put64(f,130000000000ULL); put16(f,2); put8(f,3);",
     (cp.T_PULSE, 65535, 1 << 40, 10400000000, 130000000000, 2, 3)),
    ("REPORT", "begin(f,T_REPORT); put32(f,7); put8(f,1); put16(f,100); put16(f,8); put64(f,1); put64(f,2); put64(f,3); put16(f,100); put16(f,0);",
     (cp.T_REPORT, 7, 1, 100, 8, 1, 2, 3, 100, 0)),
    ("HEARTBEAT", "begin(f,T_HEARTBEAT); put8(f,2); put64(f,123456789012ULL); put8(f,1); put16(f,5); put16(f,0); put8(f,2); put32(f,1000); put16(f,7);",
     (cp.T_HEARTBEAT, 2, 123456789012, 1, 5, 0, 2, 1000, 7)),
    ("SELFTEST_RESULT", "begin(f,T_SELFTEST_RESULT); put8(f,2); put64(f,10); put64(f,11);", (cp.T_SELFTEST_RESULT, 2, 10, 11)),
]


def check_arm_parse(src):
    """Run the firmware's own ARM field-offset statements and rd16/rd32 helpers on a Python-encoded ARM payload."""
    import re
    rd = re.search(r"static uint16_t rd16.*?\n.*?rd32[^\n]*\n", src, re.S).group(0)
    m = re.search(r"session = sess; (reps = rd16\(p \+ 8\); min_width_ns = rd32\(p \+ 10\); max_width_s = rd32\(p \+ 14\);)\s*\n\s*(start_timeout_s = rd16\(p \+ 18\);)", src)
    sess = re.search(r"uint32_t sess = (n >= 5 \? rd32\(p \+ 1\) : 0);", src)
    ver = re.search(r"else if \(p\[0\] != PROTO_VERSION\)", src)
    if not (rd and m and sess and ver):
        return False, "could not locate the firmware ARM parsing statements"
    arm = cp.encode_arm(0xA1B2C3D4, "esp32", 3, 9, 100, 777, 90_000, 33)
    payload = arm[3:-1]
    prog = ("#include <stdio.h>\n#include <stdint.h>\n" + rd + "int main(){ uint8_t p[] = {" + ",".join(str(b) for b in payload) + "}; uint8_t n=sizeof(p);\n"
            "uint32_t " + sess.group(1).replace("n >= 5 ?", "n >= 5 ?") .join(["sess = ", ";"]) + "\n"
            "uint16_t reps; uint32_t min_width_ns, max_width_s; uint16_t start_timeout_s;\n" + m.group(1) + m.group(2) +
            '\nprintf("%u %u %u %u %u %u\\n", (unsigned)p[0], (unsigned)sess, (unsigned)reps, (unsigned)min_width_ns, (unsigned)max_width_s, (unsigned)start_timeout_s); return 0; }\n')
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a.cpp").write_text(prog)
        subprocess.run(["g++", "-std=c++11", "-o", str(Path(tmp) / "a"), str(Path(tmp) / "a.cpp")], check=True)
        out = subprocess.run([str(Path(tmp) / "a")], capture_output=True, text=True, check=True).stdout.split()
    want = ["2", str(0xA1B2C3D4), "100", "777", "90000", "33"]
    return out == want, f"firmware read {out}, python encoded {want}"


def main():
    src = (ROOT / "firmware" / "counter_esp32" / "src" / "main.cpp").read_text()
    a = src.index("enum : uint8_t { M_TO_COUNTER")
    b = src.index("static void send(Frame& f)")
    prog = ('#include <stdio.h>\n#include <stdint.h>\n#include "protocol.hpp"\n' + src[a:b] +
            'static void send(Frame& f){ for(int i=0;i<f.n;i++) printf("%02x",f.b[i]); printf("\\n"); }\n'
            "int main(){ Frame f;\n" + "".join(f" {c} finish(f); send(f);\n" for _, c, _ in CASES) + " return 0; }\n")
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp) / "t.cpp"
        cpp.write_text(prog)
        exe = Path(tmp) / "t"
        subprocess.run(["g++", "-std=c++11", "-I", str(ROOT / "firmware" / "common"), "-o", str(exe), str(cpp)], check=True)
        out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split()
    results = []
    for (name, _, args), got in zip(CASES, out):
        want = cp.encode(*args).hex()
        ok = got == want
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] firmware frame == counter_proto frame: {name} ({len(got) // 2} bytes)")
    ok = len(out) == len(CASES)
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] every case produced a frame")
    ok, detail = check_arm_parse(src)
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] firmware ARM v2 field offsets read what encode_arm wrote  {detail}")
    print(f"\n{len(results)} checks, {results.count(False)} failed")
    sys.exit(1 if results.count(False) else 0)


if __name__ == "__main__":
    main()
