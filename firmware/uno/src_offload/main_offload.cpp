// main_offload.cpp — Arduino Uno R3, Phase 3: Offload Benchmark
// วัด End-to-End Latency ของการขอให้ PC (รัน Qiskit) จำลองวงจรแทน
//
// ขั้นตอนสำคัญ: ระหว่างแลกเปลี่ยนเฟรมไบนารีกับ PC (30 รอบ) ห้ามพิมพ์ข้อความใด ๆ
// ออก Serial เด็ดขาด เพราะจะปนกับ byte ของโปรโตคอลทำให้ PC sync เฟรมผิด — เก็บผล
// ไว้ใน RAM ก่อน แล้วค่อยพิมพ์สรุปเป็น CSV ทีเดียวหลังแลกเปลี่ยนครบทุกรอบ
//
// ข้อควรระวัง: Uno มี Serial RX buffer แค่ 64 bytes เฟรม response แค่ 6 bytes
// จึงไม่มีความเสี่ยง overflow

#include <Arduino.h>
#include "../../common/protocol.hpp"

#ifndef N_QUBITS
#error "ต้องกำหนด N_QUBITS ผ่าน build_flags"
#endif
#ifndef CIRCUIT_ID
#error "ต้องกำหนด CIRCUIT_ID ผ่าน build_flags (0=h_all,1=bell_ghz,2=qft,3=grover,4=qpe,5=steane_encode)"
#endif
#ifndef BAUD_RATE
#error "ต้องกำหนด BAUD_RATE ผ่าน build_flags"
#endif

// REPS and RESPONSE_TIMEOUT_MS are set per point by pc/phase3_offload/sweep.py (PLATFORMIO_BUILD_FLAGS): fewer reps when
// 100 would pass the 2 h per-point cap, and a response timeout longer than the PC's simulation time. Defaults for manual builds.
#ifndef REPS
#define REPS 100
#endif
#define GPIO_TIMING_PIN 7  // same pin as Phase 2: HIGH for exactly one request/response round trip (ESP32 counter, --ref counter)
#ifndef RESPONSE_TIMEOUT_MS
#define RESPONSE_TIMEOUT_MS 5000UL
#endif

static unsigned long g_latency_us[REPS];
static uint8_t g_crc_error[REPS];       // 1 = timeout หรือ CRC ของ response ผิด
static uint8_t g_timed_out[REPS];       // 1 = timeout (ไม่ได้รับ response เลย)

static const char* circuit_name() {
    switch (CIRCUIT_ID) {
        case 0: return "h_all";
        case 1: return "bell_ghz";
        case 2: return "qft";
        case 3: return "grover";
        case 4: return "qpe";
        case 5: return "steane_encode";
        default: return "unknown";
    }
}

void setup() {
    pinMode(GPIO_TIMING_PIN, OUTPUT);
    digitalWrite(GPIO_TIMING_PIN, LOW);
    Serial.begin(BAUD_RATE);
    delay(200);

    for (int rep = 0; rep < REPS; rep++) {
        uint8_t req[FRAME_REQ_LEN];
        req[0] = FRAME_REQ_START;
        req[1] = (uint8_t)N_QUBITS;
        req[2] = (uint8_t)CIRCUIT_ID;
        req[3] = crc8(req, 3);

        while (Serial.available()) Serial.read();  // เคลียร์ byte ค้างจาก rep ก่อนหน้า

        digitalWrite(GPIO_TIMING_PIN, HIGH);
        unsigned long t0 = micros();
        Serial.write(req, FRAME_REQ_LEN);
        Serial.flush();  // รอส่งออกจริงหมดก่อนเริ่มนับเวลารอ response

        uint8_t resp[FRAME_RESP_LEN];
        uint8_t got = 0;
        unsigned long deadline = millis() + RESPONSE_TIMEOUT_MS;
        bool timed_out = false;
        while (got < FRAME_RESP_LEN) {
            if (millis() > deadline) { timed_out = true; break; }
            if (Serial.available()) {
                resp[got++] = Serial.read();
            }
        }
        unsigned long t1 = micros();
        digitalWrite(GPIO_TIMING_PIN, LOW);

        g_latency_us[rep] = t1 - t0;
        g_timed_out[rep] = timed_out ? 1 : 0;

        uint8_t crc_err = 1;
        if (!timed_out && resp[0] == FRAME_RESP_START) {
            if (crc8(resp, FRAME_RESP_LEN - 1) == resp[FRAME_RESP_LEN - 1]) crc_err = 0;
        }
        g_crc_error[rep] = crc_err;

        delay(20);  // เว้นช่วงกัน PC ยังประมวลผลค้าง (fresh-simulation ทุกครั้งอาจช้า)
    }

    Serial.println(F("board,circuit,n,baud_rate,rep,e2e_latency_us,crc_error,timed_out"));
    for (int rep = 0; rep < REPS; rep++) {
        Serial.print("uno,");
        Serial.print(circuit_name());
        Serial.print(',');
        Serial.print(N_QUBITS);
        Serial.print(',');
        Serial.print(BAUD_RATE);
        Serial.print(',');
        Serial.print(rep);
        Serial.print(',');
        Serial.print(g_latency_us[rep]);
        Serial.print(',');
        Serial.print(g_crc_error[rep]);
        Serial.print(',');
        Serial.println(g_timed_out[rep]);
    }
    Serial.println(F("DONE"));
}

void loop() {}
