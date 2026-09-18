// main.cpp — Phase 1 PC test runner
// รันวงจรที่กำหนดด้วยตัวจำลอง (simulator) ตัวเดียวกับที่จะพอร์ตลง MCU ใน Phase 2
// แล้วพิมพ์ state vector (แอมพลิจูดเชิงซ้อนทุกตัว) ออกทาง stdout เป็น CSV
// ให้ analysis/phase1_compare.py อ่านไปเทียบกับผลจาก Qiskit Aer
//
// การใช้งาน: ./phase1_validate <circuit> <n>
//   circuit = h_all | bell_ghz | qft | grover | qpe | steane_encode
//   n       = จำนวนคิวบิต (2..12 ตามที่ระเบียบวิธีวิจัยกำหนด)
//             grover ต้องการ n >= 2, qpe ต้องการ n >= 3
//             steane_encode คงที่ที่ n = 7 เท่านั้น (ค่าอื่นถือเป็น error)

#include "../../firmware/common/circuits.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <h_all|bell_ghz|qft|grover|qpe|steane_encode> <n>\n", argv[0]);
        return 1;
    }
    const char* circuit = argv[1];
    int n = atoi(argv[2]);
    if (n < 1 || n > 20) {
        fprintf(stderr, "error: n out of range (1..20), got %d\n", n);
        return 1;
    }
    if (strcmp(circuit, "grover") == 0 && n < 2) {
        fprintf(stderr, "error: grover requires n >= 2 (got %d)\n", n);
        return 1;
    }
    if (strcmp(circuit, "qpe") == 0 && n < 3) {
        fprintf(stderr, "error: qpe requires n >= 3 (got %d)\n", n);
        return 1;
    }
    if (strcmp(circuit, "steane_encode") == 0 && n != 7) {
        fprintf(stderr, "error: steane_encode is fixed at n = 7 (got %d)\n", n);
        return 1;
    }

    qsize_t n_states = (qsize_t)1 << n;
    std::vector<Cplx> state(n_states);

    if (strcmp(circuit, "h_all") == 0) {
        circuit_h_all(state.data(), n_states, n);
    } else if (strcmp(circuit, "bell_ghz") == 0) {
        circuit_bell_ghz(state.data(), n_states, n);
    } else if (strcmp(circuit, "qft") == 0) {
        circuit_qft(state.data(), n_states, n);
    } else if (strcmp(circuit, "grover") == 0) {
        circuit_grover(state.data(), n_states, n);
    } else if (strcmp(circuit, "qpe") == 0) {
        circuit_qpe(state.data(), n_states, n);
    } else if (strcmp(circuit, "steane_encode") == 0) {
        circuit_steane_encode(state.data(), n_states, n);
    } else {
        fprintf(stderr, "error: unknown circuit '%s'\n", circuit);
        return 1;
    }

    // header บอกจำนวนคิวบิต แล้วตามด้วย CSV: index,re,im
    // index ใช้ข้อตกลง qubit 0 = LSB เหมือน Qiskit
    printf("n=%d\n", n);
    printf("index,re,im\n");
    for (qsize_t i = 0; i < n_states; i++) {
        printf("%u,%.9g,%.9g\n", (unsigned)i, (double)state[i].re, (double)state[i].im);
    }
    return 0;
}
