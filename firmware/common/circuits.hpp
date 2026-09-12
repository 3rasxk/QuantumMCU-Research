// circuits.hpp
// นิยามวงจรทดสอบทั้ง 3 แบบ สร้างจากเกทพื้นฐานใน qsim.hpp เท่านั้น
// (H, CNOT, CPhase) เพื่อให้ผลลัพธ์ตรงกับที่สร้างขึ้นฝั่ง Qiskit แบบ gate-by-gate
//
// ไม่ใช้ M_PI จาก math.h เพราะไม่ได้ประกาศเสมอไปในบาง toolchain (เช่น avr-gcc
// ที่ build ด้วย -std=c++11 strict) จึงประกาศค่าคงที่เองให้ชัดเจน

#pragma once
#include "qsim.hpp"

#ifndef QSIM_PI
#define QSIM_PI 3.14159265358979323846f
#endif

// ---------------------------------------------------------------------------
// circuit_h_all: ใช้ Hadamard กับทุกคิวบิต -> superposition สม่ำเสมอ (uniform)
// วงจรนี้ทดสอบว่าเกท H ทำงานถูกต้องแบบขนานหลายคิวบิต ไม่มี entanglement
// ---------------------------------------------------------------------------
static inline void circuit_h_all(Cplx* state, qsize_t n_states, int n) {
    qsim_init0(state, n_states);
    for (int q = 0; q < n; q++) {
        qsim_h(state, n_states, q);
    }
}

// ---------------------------------------------------------------------------
// circuit_bell_ghz: n=2 คือ Bell state แท้ ๆ (H(0), CNOT(0,1))
// n>2 ขยายเป็น GHZ state ด้วยสายโซ่ CNOT(0,1),(1,2),...,(n-2,n-1)
// ผลลัพธ์คือ (|00...0> + |11...1>) / sqrt(2) — ทดสอบ entanglement ข้ามคิวบิต
// (ตั้งชื่อ bell_ghz เพื่อสื่อว่าเป็นการขยาย Bell state ไปหลายคิวบิต)
// ---------------------------------------------------------------------------
static inline void circuit_bell_ghz(Cplx* state, qsize_t n_states, int n) {
    qsim_init0(state, n_states);
    qsim_h(state, n_states, 0);
    for (int q = 1; q < n; q++) {
        qsim_cnot(state, n_states, q - 1, q);
    }
}

// ---------------------------------------------------------------------------
// circuit_qft: Quantum Fourier Transform แบบไม่มี SWAP ท้ายวงจร (do_swaps=False)
// เหตุผลที่ตัด SWAP ออก: โจทย์กำหนดเกทที่ใช้ได้แค่ H, CNOT, CPhase เท่านั้น
// ฝั่ง Qiskit ต้องสร้างด้วย QFT(n, do_swaps=False) ให้ตรงกันเพื่อเทียบผลได้
// ลำดับตรงตาม Qiskit reference implementation:
//   for j in range(n): H(j); for k in range(j+1,n): CPhase(pi/2^(k-j), control=k, target=j)
// ---------------------------------------------------------------------------
static inline void circuit_qft(Cplx* state, qsize_t n_states, int n) {
    qsim_init0(state, n_states);
    for (int j = 0; j < n; j++) {
        qsim_h(state, n_states, j);
        for (int k = j + 1; k < n; k++) {
            float theta = QSIM_PI / (float)((qsize_t)1 << (k - j));
            qsim_cphase(state, n_states, k, j, theta);
        }
    }
}
