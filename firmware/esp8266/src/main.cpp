// main.cpp — NodeMCU ESP8266 (32-bit, 80MHz, ไม่มี FPU)
// Phase 2: Edge Benchmark — วัด Memory Wall และ Execution Time
//
// นโยบายหน่วยความจำ: malloc ได้ (ต่างจาก Uno) จองด้วย malloc() ตอน runtime
// ขนาดตาม N_QUBITS (compile-time define เหมือน Uno เพื่อให้ sweep เดียวกันเทียบกันได้)
// ข้อดีของ malloc คือ "ตรวจับ OOM ได้ตรง ๆ" — malloc() คืนค่า NULL เมื่อหน่วยความจำ
// ไม่พอ ไม่ต้องเดาแบบ Uno ที่ static array เกินขนาดแล้วอาจ hang แทน
//
// ข้อควรระวังเฉพาะบอร์ดนี้ (ตามที่ระบุไว้ในโจทย์วิจัย):
//   - ปิด WiFi (WiFi.forceSleepBegin) เพื่อไม่ให้ WiFi stack แย่งใช้ heap และไม่ให้
//     สัญญาณรบกวนจับเวลาไม่นิ่ง
//   - ปิด software watchdog เฉพาะช่วงที่จับเวลารันวงจร (ป้องกัน WDT reset ตอน n สูง
//     ที่วงจรใช้เวลานาน) แล้วเปิดกลับทันทีหลังรันเสร็จ พร้อม yield() ระหว่าง trial

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include "../../common/circuits.hpp"

#ifndef N_QUBITS
#error "ต้องกำหนด N_QUBITS ผ่าน build_flags เช่น N_QUBITS=10"
#endif
#ifndef CIRCUIT_ID
#error "ต้องกำหนด CIRCUIT_ID ผ่าน build_flags (0=h_all,1=bell_ghz,2=qft,3=grover,4=qpe,5=steane_encode)"
#endif

#define REPS 100
#define GPIO_TIMING_PIN 5  // D1 บน NodeMCU — สำรองไว้ต่อ Logic Analyzer ในอนาคต

static Cplx* g_state = nullptr;

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

static void run_circuit(qsize_t n_states) {
    switch (CIRCUIT_ID) {
        case 0: circuit_h_all(g_state, n_states, N_QUBITS); break;
        case 1: circuit_bell_ghz(g_state, n_states, N_QUBITS); break;
        case 2: circuit_qft(g_state, n_states, N_QUBITS); break;
        case 3: circuit_grover(g_state, n_states, N_QUBITS); break;
        case 4: circuit_qpe(g_state, n_states, N_QUBITS); break;
        case 5: circuit_steane_encode(g_state, n_states, N_QUBITS); break;
    }
}

void setup() {
    // ปิด WiFi ก่อนอื่น เพื่อไม่ให้ WiFi stack จองหน่วยความจำหรือรบกวนการจับเวลา
    WiFi.mode(WIFI_OFF);
    WiFi.forceSleepBegin();
    delay(1);

    Serial.begin(115200);
    delay(200);

    pinMode(GPIO_TIMING_PIN, OUTPUT);
    digitalWrite(GPIO_TIMING_PIN, LOW);

    qsize_t n_states = (qsize_t)1 << N_QUBITS;
    g_state = (Cplx*)malloc((size_t)n_states * sizeof(Cplx));

    Serial.println(F("board,circuit,n,rep,exec_time_us,free_heap_before,free_heap_after"));

    if (g_state == nullptr) {
        // ตรวจ OOM ได้ตรง ๆ จาก malloc คืนค่า NULL — ต่างจาก Uno ที่ไม่มีสัญญาณเตือน
        Serial.println(F("MALLOC_FAILED"));
        Serial.println(F("DONE"));
        return;
    }

    for (int rep = 0; rep < REPS; rep++) {
        yield();  // ป้อน watchdog ก่อนเริ่ม trial ใหม่

        uint32_t heap_before = ESP.getFreeHeap();

        digitalWrite(GPIO_TIMING_PIN, HIGH);
        ESP.wdtDisable();  // วงจรมี upper bound แน่นอน (for-loop ธรรมดา) จึงปิดชั่วคราวได้ปลอดภัย
        unsigned long t0 = micros();
        run_circuit(n_states);
        unsigned long t1 = micros();
        ESP.wdtEnable(0);
        digitalWrite(GPIO_TIMING_PIN, LOW);

        uint32_t heap_after = ESP.getFreeHeap();
        unsigned long exec_us = t1 - t0;

        Serial.print("esp8266,");
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
        Serial.println(heap_after);
    }

    free(g_state);
    Serial.println(F("DONE"));
}

void loop() {
    yield();
}
