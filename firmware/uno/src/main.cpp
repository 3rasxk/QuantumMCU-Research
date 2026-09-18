// main.cpp — Arduino Uno R3 (ATmega328P, 8-bit, 16MHz, ไม่มี FPU)
// Phase 2: Edge Benchmark — วัด Memory Wall และ Execution Time
//
// นโยบายหน่วยความจำ: static array เท่านั้น (ห้าม malloc) เพราะ Uno มี SRAM แค่ 2KB
// การจองแบบ dynamic เสี่ยง heap fragmentation สูงมากในพื้นที่ที่เล็กขนาดนี้
// ขนาด array กำหนดตอนคอมไพล์ผ่าน -D N_QUBITS=<n> (ดู platformio.ini) เพื่อให้หา
// Memory Wall ได้ด้วยการไล่คอมไพล์ค่า n ต่างกันทีละ build แทนการ resize runtime
//
// ผลที่คาดว่าจะพบ: เมื่อ n โตขึ้นจน .bss (static array) ชนกับ stack, avr-gcc
// อาจ link ผ่านแต่รันจริงแล้ว "hang" หรือ reset เพราะ stack ทับข้อมูล state —
// นี่คือความแตกต่างสำคัญจาก ESP ที่ใช้ malloc: Uno ล้มเหลวได้ทั้งตอน link-time
// (แน่นอน, จับได้ก่อน deploy) และ runtime (stack/bss ชนกัน, จับได้เฉพาะตอนรันจริง)
// ต้องบันทึกพฤติกรรมความล้มเหลวทั้งสองแบบแยกกันในผลการทดลอง

#include <Arduino.h>
#include "../../common/circuits.hpp"

#ifndef N_QUBITS
#error "ต้องกำหนด N_QUBITS ผ่าน build_flags เช่น N_QUBITS=6"
#endif
#ifndef CIRCUIT_ID
#error "ต้องกำหนด CIRCUIT_ID ผ่าน build_flags (0=h_all,1=bell_ghz,2=qft,3=grover,4=qpe,5=steane_encode)"
#endif

#define STATE_COUNT ((qsize_t)1 << N_QUBITS)
#define REPS 100
#define GPIO_TIMING_PIN 7  // สำรองไว้ต่อ Logic Analyzer ในอนาคต (toggle รอบการรันวงจร)

// จอง static array ขนาดคงที่ตอนคอมไพล์ — จุดที่ Uno ต่างจาก ESP8266/ESP32
static Cplx g_state[STATE_COUNT];

// ---------------------------------------------------------------------------
// freeMemory(): วัดช่องว่างระหว่าง heap กับ stack (stack-heap gap) แบบมาตรฐาน
// สำหรับ AVR — ใช้ตรวจว่าการจอง static array ไปกินพื้นที่จนใกล้ stack แค่ไหน
// อ้างอิงเทคนิคมาตรฐานที่ใช้กันทั่วไปในชุมชน Arduino
// ---------------------------------------------------------------------------
extern unsigned int __heap_start;
extern void* __brkval;

int freeMemory() {
    int free_bytes;
    if ((int)__brkval == 0) {
        free_bytes = ((int)&free_bytes) - ((int)&__heap_start);
    } else {
        free_bytes = ((int)&free_bytes) - ((int)__brkval);
    }
    return free_bytes;
}

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

static void run_circuit() {
    switch (CIRCUIT_ID) {
        case 0: circuit_h_all(g_state, STATE_COUNT, N_QUBITS); break;
        case 1: circuit_bell_ghz(g_state, STATE_COUNT, N_QUBITS); break;
        case 2: circuit_qft(g_state, STATE_COUNT, N_QUBITS); break;
        case 3: circuit_grover(g_state, STATE_COUNT, N_QUBITS); break;
        case 4: circuit_qpe(g_state, STATE_COUNT, N_QUBITS); break;
        case 5: circuit_steane_encode(g_state, STATE_COUNT, N_QUBITS); break;
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) { ; }

    pinMode(GPIO_TIMING_PIN, OUTPUT);
    digitalWrite(GPIO_TIMING_PIN, LOW);

    delay(200);  // เผื่อเวลาให้ host เปิด serial monitor ทัน
    Serial.println(F("board,circuit,n,rep,exec_time_us,free_heap_before,free_heap_after"));

    for (int rep = 0; rep < REPS; rep++) {
        int heap_before = freeMemory();

        digitalWrite(GPIO_TIMING_PIN, HIGH);   // ขอบขาขึ้น = เริ่มวงจร (สำหรับ Logic Analyzer)
        unsigned long t0 = micros();
        run_circuit();
        unsigned long t1 = micros();
        digitalWrite(GPIO_TIMING_PIN, LOW);    // ขอบขาลง = จบวงจร

        int heap_after = freeMemory();
        unsigned long exec_us = t1 - t0;

        Serial.print("uno,");
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
    Serial.println(F("DONE"));
}

void loop() {
    // ไม่ทำอะไรต่อ — จบชุดทดลองใน setup() แล้ว host อ่านผ่าน serial จนเจอ "DONE"
}
