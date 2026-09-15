// main.cpp — ESP32 DevKit V1 (32-bit, 240MHz, มี FPU ฮาร์ดแวร์)
// Phase 2: Edge Benchmark — วัด Memory Wall และ Execution Time
//
// นโยบายหน่วยความจำ: malloc ได้ เหมือน ESP8266 แต่ ESP32 มี heap แบบแบ่งเป็นหลาย
// region (capability-based) จึงวัดทั้ง free heap รวม (esp_get_free_heap_size) และ
// largest free block ต่อเนื่อง (heap_caps_get_largest_free_block) เพราะ malloc()
// ก้อนใหญ่ต้องการพื้นที่ "ต่อเนื่อง" — บางครั้ง free heap รวมพอ แต่ fragment จนจอง
// ก้อนใหญ่ไม่ได้ ตัวเลขสองตัวนี้จะเผยให้เห็นกรณีนั้น
//
// ข้อควรระวังที่สำคัญที่สุดสำหรับบอร์ดนี้: literal float ทุกตัวต้องมี suffix f
// (0.5f ไม่ใช่ 0.5) เพราะไม่งั้นจะกลายเป็น double โดยอัตโนมัติ ซึ่ง ESP32 FPU ทำงาน
// กับ double ไม่ได้ในฮาร์ดแวร์ ต้อง software-emulate ทำให้ช้าลงราว 10 เท่าแบบเงียบ ๆ
// (ตรวจสอบแล้วว่า firmware/common/*.hpp ใช้ f suffix ครบทุกตัวตั้งแต่ Phase 1)

#include <Arduino.h>
#include <WiFi.h>
#include <esp_heap_caps.h>
#include "../../common/circuits.hpp"

#ifndef N_QUBITS
#error "ต้องกำหนด N_QUBITS ผ่าน build_flags เช่น N_QUBITS=14"
#endif
#ifndef CIRCUIT_ID
#error "ต้องกำหนด CIRCUIT_ID ผ่าน build_flags (0=h_all, 1=bell_ghz, 2=qft)"
#endif

#define REPS 100
#define GPIO_TIMING_PIN 4  // สำรองไว้ต่อ Logic Analyzer ในอนาคต

static Cplx* g_state = nullptr;

static const char* circuit_name() {
    switch (CIRCUIT_ID) {
        case 0: return "h_all";
        case 1: return "bell_ghz";
        case 2: return "qft";
        default: return "unknown";
    }
}

static void run_circuit(qsize_t n_states) {
    switch (CIRCUIT_ID) {
        case 0: circuit_h_all(g_state, n_states, N_QUBITS); break;
        case 1: circuit_bell_ghz(g_state, n_states, N_QUBITS); break;
        case 2: circuit_qft(g_state, n_states, N_QUBITS); break;
    }
}

void setup() {
    WiFi.mode(WIFI_OFF);  // ปิด WiFi เพื่อความสอดคล้องกับบอร์ดอื่น ไม่ให้ stack แย่ง heap

    Serial.begin(115200);
    delay(200);

    pinMode(GPIO_TIMING_PIN, OUTPUT);
    digitalWrite(GPIO_TIMING_PIN, LOW);

    qsize_t n_states = (qsize_t)1 << N_QUBITS;
    g_state = (Cplx*)malloc((size_t)n_states * sizeof(Cplx));

    Serial.println(F("board,circuit,n,rep,exec_time_us,free_heap_before,free_heap_after,largest_block"));

    if (g_state == nullptr) {
        // ตรวจ OOM ได้ตรง ๆ เหมือน ESP8266 — malloc คืน NULL ไม่ hang
        Serial.println(F("MALLOC_FAILED"));
        Serial.println(F("DONE"));
        return;
    }

    for (int rep = 0; rep < REPS; rep++) {
        yield();

        uint32_t heap_before = esp_get_free_heap_size();

        digitalWrite(GPIO_TIMING_PIN, HIGH);
        unsigned long t0 = micros();
        run_circuit(n_states);
        unsigned long t1 = micros();
        digitalWrite(GPIO_TIMING_PIN, LOW);

        uint32_t heap_after = esp_get_free_heap_size();
        uint32_t largest_block = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
        unsigned long exec_us = t1 - t0;

        Serial.print("esp32,");
        Serial.print(circuit_name());
        Serial.print(',');
        Serial.print(N_QUBITS);
        Serial.print(',');
        Serial.print(rep);
        Serial.print(',');
        Serial.print(exec_us);
        Serial.print(',');
        Serial.print(heap_before);
        Serial.print(',');
        Serial.print(heap_after);
        Serial.print(',');
        Serial.println(largest_block);
    }

    free(g_state);
    Serial.println(F("DONE"));
}

void loop() {
    yield();
}
