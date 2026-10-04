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
from shared import counter_proto as cp  # noqa: E402

CASES = [
    ("ARM_ACK", "begin(f,T_ARM_ACK); put32(f,0x01020304); put8(f,1);", (cp.T_ARM_ACK, 0x01020304, 1)),
    ("ANOMALY", "begin(f,T_ANOMALY); put16(f,513); put8(f,3); put32(f,0xDEADBEEF);", (cp.T_ANOMALY, 513, 3, 0xDEADBEEF)),
    ("PULSE", "begin(f,T_PULSE); put16(f,65535); put64(f,1ULL<<40); put64(f,130000000000ULL); put8(f,3);",
     (cp.T_PULSE, 65535, 1 << 40, 130000000000, 3)),
    ("REPORT", "begin(f,T_REPORT); put32(f,7); put8(f,1); put16(f,100); put16(f,8); put64(f,1); put64(f,2); put64(f,3); put16(f,100); put16(f,0);",
     (cp.T_REPORT, 7, 1, 100, 8, 1, 2, 3, 100, 0)),
    ("HEARTBEAT", "begin(f,T_HEARTBEAT); put32(f,9); put8(f,1); put16(f,5); put16(f,0); put8(f,2); put32(f,1000); put16(f,7);",
     (cp.T_HEARTBEAT, 9, 1, 5, 0, 2, 1000, 7)),
    ("SELFTEST_RESULT", "begin(f,T_SELFTEST_RESULT); put8(f,2); put64(f,10); put64(f,11);", (cp.T_SELFTEST_RESULT, 2, 10, 11)),
]


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
    print(f"\n{len(results)} checks, {results.count(False)} failed")
    sys.exit(1 if results.count(False) else 0)


if __name__ == "__main__":
    main()
