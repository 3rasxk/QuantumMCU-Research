// main_offload.cpp — ESP32 DevKit V1, Phase 3: Offload Benchmark
// วัด End-to-End Latency ของการขอให้ PC (รัน Qiskit) จำลองวงจรแทน
// ระหว่างแลกเปลี่ยนเฟรมไบนารีกับ PC ห้ามพิมพ์ข้อความใด ๆ ออก Serial (ดูเหตุผลใน
// firmware/uno/src_offload/main_offload.cpp) เก็บผลใน RAM แล้วค่อยพิมพ์สรุปทีเดียว

#include <Arduino.h>
#include <WiFi.h>
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

#define REPS 100
#define RESPONSE_TIMEOUT_MS 5000UL

static unsigned long g_latency_us[REPS];
static uint8_t g_crc_error[REPS];
static long g_timed_out[REPS];

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
    WiFi.mode(WIFI_OFF);

    Serial.begin(BAUD_RATE);
    delay(200);

    for (int rep = 0; rep < REPS; rep++) {
        yield();

        uint8_t req[FRAME_REQ_LEN];
        req[0] = FRAME_REQ_START;
        req[1] = (uint8_t)N_QUBITS;
        req[2] = (uint8_t)CIRCUIT_ID;
        req[3] = crc8(req, 3);

        while (Serial.available()) Serial.read();

        unsigned long t0 = micros();
        Serial.write(req, FRAME_REQ_LEN);
        Serial.flush();

        uint8_t resp[FRAME_RESP_LEN];
        uint8_t got = 0;
        unsigned long deadline = millis() + RESPONSE_TIMEOUT_MS;
        bool timed_out = false;
        while (got < FRAME_RESP_LEN) {
            if (millis() > deadline) { timed_out = true; break; }
            if (Serial.available()) {
                resp[got++] = Serial.read();
            }
            yield();
        }
        unsigned long t1 = micros();

        g_latency_us[rep] = t1 - t0;
        g_timed_out[rep] = timed_out ? 1 : 0;

        uint8_t crc_err = 1;
        if (!timed_out && resp[0] == FRAME_RESP_START) {
            if (crc8(resp, FRAME_RESP_LEN - 1) == resp[FRAME_RESP_LEN - 1]) crc_err = 0;
        }
        g_crc_error[rep] = crc_err;

        delay(20);
    }

    Serial.println(F("board,circuit,n,baud_rate,rep,e2e_latency_us,crc_error,timed_out"));
    for (int rep = 0; rep < REPS; rep++) {
        Serial.print("esp32,");
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

void loop() { yield(); }
