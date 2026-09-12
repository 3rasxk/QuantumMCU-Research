// qsim.hpp
// แกนกลาง Quantum Circuit Simulator แบบพกพา (portable core)
//
// ออกแบบให้ทำงานบน "บัฟเฟอร์ดิบ" (Cplx*) เท่านั้น ไม่ผูกกับวิธีจองหน่วยความจำ
// เหตุผล: Phase 2 ต้องพอร์ตโค้ดตัวเดียวกันนี้ไปรันบน 3 บอร์ดที่มีนโยบายจองหน่วยความจำ
// ต่างกัน (Uno = static array เท่านั้น, ESP8266/ESP32 = malloc ได้) โดยไม่ต้องแก้ไฟล์นี้เลย
//
// ห้ามใช้ std::complex เพราะ AVR-GCC (avr-g++) ไม่รองรับ libstdc++ เต็มรูปแบบ
// และ std::complex<float> มี overhead จาก template/exception ที่ไม่เหมาะกับ 8-bit MCU
//
// ข้อตกลงลำดับบิต (bit-ordering convention) — สำคัญมาก:
//   qubit 0 = บิตนัยสำคัญน้อยที่สุด (LSB) ของ index สถานะ
//   ตรงกับข้อตกลงของ Qiskit (little-endian qubit ordering)
//   ถ้า Infidelity สูงผิดปกติเฉพาะวงจรที่ไม่สมมาตร (เช่น QFT) ให้สงสัยจุดนี้ก่อน

#pragma once

#ifdef ARDUINO
  #include <Arduino.h>  // ให้ใช้ sqrtf/cosf/sinf จาก avr-libm ผ่าน Arduino core
#else
  #include <math.h>
  #include <stdint.h>
#endif

// จำนวนแอมพลิจูดเชิงซ้อนของ n คิวบิต คือ 2^n
// ใช้ uint32_t เพราะ n สูงสุดที่ทดสอบคือ 12 -> 2^12 = 4096 ยังพอดีกับ uint16_t
// แต่เผื่อการขยายในอนาคตจึงใช้ uint32_t เป็นมาตรฐานเดียวกันทุกบอร์ด
typedef uint32_t qsize_t;

struct Cplx {
    float re;
    float im;
};

// ผลคูณเชิงซ้อน: (a.re + i a.im) * (b.re + i b.im)
static inline Cplx cplx_mul(Cplx a, Cplx b) {
    Cplx r;
    r.re = a.re * b.re - a.im * b.im;
    r.im = a.re * b.im + a.im * b.re;
    return r;
}

// ---------------------------------------------------------------------------
// qsim_init0: ตั้งค่าสถานะเริ่มต้นเป็น |00...0> คือแอมพลิจูด index 0 = 1+0i
// ที่เหลือ = 0
// ---------------------------------------------------------------------------
static inline void qsim_init0(Cplx* state, qsize_t n_states) {
    state[0].re = 1.0f;
    state[0].im = 0.0f;
    for (qsize_t i = 1; i < n_states; i++) {
        state[i].re = 0.0f;
        state[i].im = 0.0f;
    }
}

// ---------------------------------------------------------------------------
// qsim_h: ใช้เกท Hadamard กับ qubit เป้าหมาย (target)
// H = 1/sqrt(2) * [[1, 1], [1, -1]]
// วนดูทุก index i ที่บิต target เป็น 0 แล้วจับคู่กับ j = i ที่บิต target เป็น 1
// เพื่อไม่ให้คำนวณคู่เดิมซ้ำสองรอบ
// ---------------------------------------------------------------------------
static inline void qsim_h(Cplx* state, qsize_t n_states, int target) {
    const float INV_SQRT2 = 0.70710678118654752f;
    qsize_t mask = (qsize_t)1 << target;
    for (qsize_t i = 0; i < n_states; i++) {
        if ((i & mask) == 0) {
            qsize_t j = i | mask;
            Cplx a = state[i];
            Cplx b = state[j];
            state[i].re = (a.re + b.re) * INV_SQRT2;
            state[i].im = (a.im + b.im) * INV_SQRT2;
            state[j].re = (a.re - b.re) * INV_SQRT2;
            state[j].im = (a.im - b.im) * INV_SQRT2;
        }
    }
}

// ---------------------------------------------------------------------------
// qsim_cnot: เกท Controlled-NOT
// สลับแอมพลิจูดของ |...1(control)...0(target)...> กับ |...1(control)...1(target)...>
// เมื่อ control = 1 เท่านั้น ถ้า control = 0 ไม่มีผลใด ๆ
// ---------------------------------------------------------------------------
static inline void qsim_cnot(Cplx* state, qsize_t n_states, int control, int target) {
    qsize_t cmask = (qsize_t)1 << control;
    qsize_t tmask = (qsize_t)1 << target;
    for (qsize_t i = 0; i < n_states; i++) {
        if ((i & cmask) && !(i & tmask)) {
            qsize_t j = i | tmask;
            Cplx tmp = state[i];
            state[i] = state[j];
            state[j] = tmp;
        }
    }
}

// ---------------------------------------------------------------------------
// qsim_cphase: เกท Controlled-Phase ใส่เฟส e^{i*theta} เมื่อทั้ง control และ
// target เป็น 1 พร้อมกัน (สมมาตรระหว่าง control/target เพราะเกทนี้ diagonal)
// ใช้สร้าง QFT: theta = pi / 2^(k-j)
// ---------------------------------------------------------------------------
static inline void qsim_cphase(Cplx* state, qsize_t n_states, int control, int target, float theta) {
    qsize_t cmask = (qsize_t)1 << control;
    qsize_t tmask = (qsize_t)1 << target;
    Cplx phase;
    phase.re = cosf(theta);
    phase.im = sinf(theta);
    for (qsize_t i = 0; i < n_states; i++) {
        if ((i & cmask) && (i & tmask)) {
            state[i] = cplx_mul(state[i], phase);
        }
    }
}
