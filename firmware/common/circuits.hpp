// circuits.hpp
// นิยามวงจรทดสอบทั้ง 6 แบบ (h_all, bell_ghz, qft, grover, qpe, steane_encode)
// สร้างจากเกทพื้นฐานใน qsim.hpp เท่านั้น (H, CNOT, CPhase) เพื่อให้ผลลัพธ์ตรงกับที่
// สร้างขึ้นฝั่ง Qiskit แบบ gate-by-gate
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
// qft_apply_forward / qft_apply_inverse: เนื้อวงจร QFT (ไม่รวม qsim_init0) แยกออกมา
// จาก circuit_qft เพื่อให้ circuit_qpe เรียกซ้ำได้บนแค่ "ส่วนหนึ่ง" ของคิวบิตทั้งหมด
// (counting register) โดยไม่ต้อง reset ทั้ง state — สอดคล้องกับข้อกำหนดที่ว่า inverse
// QFT ต้องนำ QFT เดิมมาใช้ซ้ำ ไม่ใช่เขียนใหม่แยกต่างหาก
//
// qft_apply_inverse คือ exact inverse ของ qft_apply_forward: กลับลำดับเกททั้งหมด
// (H เป็นเกทของตัวเอง H†=H ไม่ต้องกลับเฟส, CPhase(theta)† = CPhase(-theta))
// พิสูจน์ด้วยมือสำหรับ num_qubits=3 แล้วตรงกับ reverse ของลำดับ forward ทุกตัว:
//   forward  = H0,CP(1,0),CP(2,0), H1,CP(2,1), H2
//   reverse  = H2,CP(2,1), H1,CP(2,0),CP(1,0), H0   <- ตรงกับ loop ด้านล่างเป๊ะ
// ---------------------------------------------------------------------------
static inline void qft_apply_forward(Cplx* state, qsize_t n_states, int num_qubits) {
    for (int j = 0; j < num_qubits; j++) {
        qsim_h(state, n_states, j);
        for (int k = j + 1; k < num_qubits; k++) {
            float theta = QSIM_PI / (float)((qsize_t)1 << (k - j));
            qsim_cphase(state, n_states, k, j, theta);
        }
    }
}

static inline void qft_apply_inverse(Cplx* state, qsize_t n_states, int num_qubits) {
    for (int j = num_qubits - 1; j >= 0; j--) {
        for (int k = num_qubits - 1; k >= j + 1; k--) {
            float theta = QSIM_PI / (float)((qsize_t)1 << (k - j));
            qsim_cphase(state, n_states, k, j, -theta);
        }
        qsim_h(state, n_states, j);
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
    qft_apply_forward(state, n_states, n);
}

// ---------------------------------------------------------------------------
// mc_phase_apply / mc_x_apply: multi-controlled-phase / multi-controlled-X แบบไม่ใช้
// ancilla เลย ("ancilla-free"), สร้างจาก H, CNOT, CPhase เพียงสามตัวเท่านั้น
//
// ข้อจำกัดที่ตั้งใจ (fixed by construction, ไม่ใช่ทางเลือกโดยพลการ): controls เป็น
// คิวบิต [0 .. k-1] เสมอ (ต่อเนื่องจาก 0) — พอดีกับวิธีที่ circuit_grover เรียกใช้
// (controls = ทุกคิวบิตยกเว้นตัวสุดท้าย, target = คิวบิตตัวสุดท้าย) จึงไม่ต้องส่ง
// array รายชื่อ control จริง ๆ ประหยัด stack บน AVR
//
// ที่มา (สรุปเป็นเอกสารประกอบ ตรวจด้วยตัวเลขจริงก่อนใช้งาน — ดู
// verify_mcz.py / verify_grover.py ในรอบพัฒนา): สูตรมาตรฐานสำหรับ doubly-controlled-U
// จาก V ที่ V^2=U (Nielsen & Chuang, งานสร้าง Toffoli จาก controlled-V):
//   CCU(a,b;c) = CV(b,c) · CNOT(a,b) · CV†(b,c) · CNOT(a,b) · CV(a,c)
// ขยายเป็น k controls แบบเวียนเกิด โดยแทนที่ "CNOT(a,b)" (สำหรับ 2 control) ด้วย
// C^{k-1}(X) (สำหรับ k control) ซึ่งสร้างจาก C^{k-1}(P(pi)) ประกบด้วย H สองข้าง
// (เอกลักษณ์ X = H·Z·H): เวียนเกิดจนเหลือ 1 control ก็ใช้ qsim_cphase/qsim_cnot ตรง ๆ
//
// จำนวนเกท G(k) โตแบบ O(3^k) (verified: G(1)=1, G(2)=5, G(3)=21, ..., G(11)=157461)
// แพงมากเมื่อ k โต แต่เป็นราคาที่ต้องจ่ายเพื่อความถูกต้องแบบ exact โดยไม่มี ancilla —
// เอกสารใน Part 5 ของรายงานอธิบายผลกระทบต่อเวลาเบนช์มาร์กของ circuit_grover
// ---------------------------------------------------------------------------
static void mc_x_apply(Cplx* state, qsize_t n_states, int k, int target);

static void mc_phase_apply(Cplx* state, qsize_t n_states, int k, int target, float theta) {
    if (k == 0) {
        // 0 control = เกทเฟสธรรมดาบนคิวบิตเดียว (ผ่าน cphase(q,q,theta) เพราะ
        // control==target ทำให้เงื่อนไข "ทั้งคู่เป็น 1" ลดรูปเหลือแค่ qubit นั้นเป็น 1)
        qsim_cphase(state, n_states, target, target, theta);
        return;
    }
    if (k == 1) {
        qsim_cphase(state, n_states, 0, target, theta);
        return;
    }
    int c_last = k - 1;  // คิวบิตควบคุมตัวสุดท้าย (index k-1)
    qsim_cphase(state, n_states, c_last, target, theta / 2.0f);
    mc_x_apply(state, n_states, k - 1, c_last);
    qsim_cphase(state, n_states, c_last, target, -theta / 2.0f);
    mc_x_apply(state, n_states, k - 1, c_last);
    mc_phase_apply(state, n_states, k - 1, target, theta / 2.0f);
}

static void mc_x_apply(Cplx* state, qsize_t n_states, int k, int target) {
    if (k == 1) {
        qsim_cnot(state, n_states, 0, target);
        return;
    }
    qsim_h(state, n_states, target);
    mc_phase_apply(state, n_states, k, target, QSIM_PI);
    qsim_h(state, n_states, target);
}

// ---------------------------------------------------------------------------
// circuit_grover: ค้นหา |11...1> (สถานะเป้าหมายเดียว, คงที่) ด้วย Grover's algorithm
//
// Oracle: พลิกเฟสของ |11...1> เท่านั้น = multi-controlled-Z ที่มี n-1 control
// (คิวบิต 0..n-2) และ target คือคิวบิตตัวสุดท้าย (n-1) -> mc_phase_apply(k=n-1,theta=pi)
//
// Diffusion = H^n · (2|0...0><0...0| - I) · H^n
// (2|0><0|-I) ทำจาก MCZ ตัวเดียวกัน (ที่พลิกเฟส |1...1>) ประกบด้วย X บนทุกคิวบิต:
//   X^n · MCZ_all1 · X^n  เพราะ X^n สลับป้าย |0...0> <-> |1...1>
// X ที่ใช้ไม่ใช่เกทดิบจาก qsim.hpp (ไม่มี X ในรายการเกทที่กำหนด) แต่สร้างจาก
// H·Z·H (Z ผ่าน qsim_cphase(q,q,pi) เหมือนด้านบน) — เอกลักษณ์มาตรฐาน X=HZH
//
// จำนวนรอบวนซ้ำ: floor(pi/4 * sqrt(2^n)) ตามสูตรมาตรฐานของ Grover
// ต้องการ n >= 2 (มิฉะนั้นไม่มี control เหลือให้ mc_phase_apply)
// ---------------------------------------------------------------------------
static inline void circuit_grover(Cplx* state, qsize_t n_states, int n) {
    qsim_init0(state, n_states);
    for (int q = 0; q < n; q++) {
        qsim_h(state, n_states, q);
    }

    float sqrt_n_states = sqrtf((float)n_states);
    int iterations = (int)((QSIM_PI / 4.0f) * sqrt_n_states);
    if (iterations < 1) iterations = 1;

    for (int it = 0; it < iterations; it++) {
        // Oracle: พลิกเฟส |1...1>
        mc_phase_apply(state, n_states, n - 1, n - 1, QSIM_PI);

        // Diffusion
        for (int q = 0; q < n; q++) qsim_h(state, n_states, q);
        for (int q = 0; q < n; q++) {
            qsim_h(state, n_states, q);
            qsim_cphase(state, n_states, q, q, QSIM_PI);
            qsim_h(state, n_states, q);
        }
        mc_phase_apply(state, n_states, n - 1, n - 1, QSIM_PI);
        for (int q = 0; q < n; q++) {
            qsim_h(state, n_states, q);
            qsim_cphase(state, n_states, q, q, QSIM_PI);
            qsim_h(state, n_states, q);
        }
        for (int q = 0; q < n; q++) qsim_h(state, n_states, q);
    }
}

// ---------------------------------------------------------------------------
// circuit_qpe: Quantum Phase Estimation ของ U = S gate = P(pi/2) หนึ่งตัว
// (ไม่ใช่ modular exponentiation แบบ Shor's — งานนี้ทดสอบแค่โครงสร้าง QPE ล้วน ๆ
// กับ U ที่ทฤษฎีรู้ค่าแน่นอน ไม่ใช่การจำลองอัลกอริทึม Shor)
//
// eigenstate = |1> (ค่าเจาะจง, eigenvalue ของ P(pi/2) บน |1> คือ e^{i*pi/2} = i
// ดังนั้น phi ที่แท้จริง = 1/4 พอดี ซึ่งเขียนเป็นเลขฐานสองได้ไม่รู้จบด้วยจำนวนบิตเท่าไหร่
// ก็ได้ (0.01000...) -> QPE ในอุดมคติต้องให้พีคเดียวคมชัด (prob ~1.0) ไม่มี spectral
// leakage ไม่ว่า counting register จะกว้างแค่ไหน — ใช้เป็น ground truth ของ Phase 1)
//
// การจัดคิวบิต: n คิวบิตทั้งหมด แบ่งเป็น counting register = คิวบิต [0, n-2] (t=n-1 ตัว)
// และ eigenstate qubit = คิวบิตตัวสุดท้าย (n-1) ต้องการ n >= 3 (อย่างน้อย 2 counting
// qubit + 1 eigenstate qubit)
//
// ลำดับวงจร:
//   1. เตรียม eigenstate |1> ด้วย X = H·Z·H (ไม่มี X ดิบให้ใช้ตรง ๆ)
//   2. H บน counting register ทั้งหมด
//   3. คิวบิต i ควบคุม U^(2^i) บน eigenstate qubit = qsim_cphase(i, eigen, theta*2^i)
//      (P(theta)^m = P(m*theta) เพราะเป็นเกทเฟสทแยงมุม คูณมุมกันตรง ๆ ไม่ต้องทำ U ซ้ำ)
//   4. inverse QFT บน counting register (เรียก qft_apply_inverse ซ้ำ ไม่เขียนใหม่)
//
// หมายเหตุการอ่านผล (สำหรับสคริปต์วิเคราะห์ ไม่ใช่ส่วนของวงจร): เพราะ QFT ในไฟล์นี้
// ตัด SWAP ท้ายวงจรออก (ดู circuit_qft) บิตของผลลัพธ์จึงกลับด้าน (bit-reversed) เทียบ
// กับข้อตกลง qubit0=LSB ปกติ — ค่าประมาณ phi ต้องอ่านบิตของ counting register แบบ
// กลับด้านจึงจะตรงกับค่าจริง (ตรวจสอบเชิงตัวเลขแล้วก่อนเขียนโค้ดนี้)
// ---------------------------------------------------------------------------
static inline void circuit_qpe(Cplx* state, qsize_t n_states, int n) {
    qsim_init0(state, n_states);

    int t = n - 1;       // จำนวนคิวบิตใน counting register
    int eigen = n - 1;   // คิวบิต eigenstate

    // X บน eigenstate qubit ผ่าน H-Z-H (X = H·Z·H, Z ผ่าน cphase(q,q,pi))
    qsim_h(state, n_states, eigen);
    qsim_cphase(state, n_states, eigen, eigen, QSIM_PI);
    qsim_h(state, n_states, eigen);

    const float U_THETA = QSIM_PI / 2.0f;  // U = S gate = P(pi/2), phi แท้จริง = 1/4

    for (int q = 0; q < t; q++) {
        qsim_h(state, n_states, q);
    }
    for (int q = 0; q < t; q++) {
        float theta_q = U_THETA * (float)((qsize_t)1 << q);
        theta_q = fmodf(theta_q, 2.0f * QSIM_PI);  // ลด range ก่อนเข้า cosf/sinf กัน error สะสมที่ n สูง
        qsim_cphase(state, n_states, q, eigen, theta_q);
    }
    qft_apply_inverse(state, n_states, t);
}

// ---------------------------------------------------------------------------
// circuit_steane_encode: เข้ารหัส |0>_L ของ Steane [[7,1,3]] code ด้วย H และ CNOT
// เท่านั้น คงที่ที่ n=7 เสมอ (ไม่ scale ตาม n — ดู pc/phase1_validate, สคริปต์ sweep
// ทุกตัวต้อง treat วงจรนี้เป็นกรณีพิเศษ ห้ามเรียกที่ n อื่น)
//
// ขอบเขตที่ตั้งใจ (ต้องระบุในรายงานตรง ๆ ไม่ให้ชื่อวงจรสื่อเกินจริง): นี่คือการวัด
// วงจร "เข้ารหัส" เท่านั้น ไม่ใช่การสาธิตการแก้ไขข้อผิดพลาดจริง — ไม่มี syndrome
// measurement และไม่มีขั้นตอนแก้ไข เพราะตัวจำลองนี้ไม่มีความสามารถวัดกลางวงจร
// (mid-circuit measurement) เลย
//
// ที่มาวงจร: [[7,1,3]] Steane code มาจาก classical Hamming(7,4) code, X-stabilizer
// 3 ตัว (พร้อม Z-stabilizer ที่ support ชุดเดียวกัน เพราะโค้ดนี้ self-dual):
//   S1 = X บนคิวบิต {0,2,4,6}   S2 = X บนคิวบิต {1,2,5,6}   S3 = X บนคิวบิต {3,4,5,6}
// วงจรเตรียม |0>_L โดย H บนคิวบิต pivot ของแต่ละ generator (0,1,3 ตามลำดับ) แล้ว
// CNOT จาก pivot ไปยังคิวบิตที่เหลือใน generator เดียวกัน — มาตรฐานสำหรับเตรียม
// CSS stabilizer state จาก generator matrix ที่มี pivot column สะอาด (แต่ละ pivot
// column มี 1 อยู่แถวเดียว) ตรวจสอบเชิงตัวเลขแล้วว่า state ที่ได้เป็น +1-eigenstate
// ของ stabilizer ทั้ง 6 ตัว (S1,S2,S3 ทั้งแบบ X และ Z) และของ logical Z_L=Z^{⊗7}
// ก่อนเขียนโค้ดนี้ (ดู verify_steane.py ในรอบพัฒนา)
// ---------------------------------------------------------------------------
static inline void circuit_steane_encode(Cplx* state, qsize_t n_states, int n) {
    (void)n;  // ตั้งใจไม่ใช้: วงจรนี้คงที่ที่ 7 คิวบิตเสมอ ไม่ scale ตาม n
    qsim_init0(state, n_states);

    qsim_h(state, n_states, 0);
    qsim_cnot(state, n_states, 0, 2);
    qsim_cnot(state, n_states, 0, 4);
    qsim_cnot(state, n_states, 0, 6);

    qsim_h(state, n_states, 1);
    qsim_cnot(state, n_states, 1, 2);
    qsim_cnot(state, n_states, 1, 5);
    qsim_cnot(state, n_states, 1, 6);

    qsim_h(state, n_states, 3);
    qsim_cnot(state, n_states, 3, 4);
    qsim_cnot(state, n_states, 3, 5);
    qsim_cnot(state, n_states, 3, 6);
}
