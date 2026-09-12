// protocol.hpp — Phase 3: โปรโตคอลเฟรมสำหรับ Offload Benchmark
// ใช้ร่วมกันทั้ง 3 บอร์ด ต้องตรงกับ pc/phase3_offload/protocol.py ทุกประการ
// (CRC8 polynomial, ตำแหน่ง byte, ขนาดเฟรม)
//
// Request (MCU -> PC), 4 bytes:
//   [0]=0xAA (start marker)  [1]=n_qubits  [2]=circuit_type  [3]=CRC8(byte 0..2)
// Response (PC -> MCU), 6 bytes:
//   [0]=0x55 (start marker)  [1..4]=outcome (uint32 big-endian)  [5]=CRC8(byte 0..4)
//
// เหตุผลที่เฟรมเล็กมาก (4/6 bytes): Uno มี Serial RX buffer แค่ 64 bytes ต้องกันไม่ให้
// เฟรมใหญ่จนเสี่ยง buffer overflow ถ้ามีดีเลย์ระหว่างอ่าน

#pragma once
#include <stdint.h>

#define FRAME_REQ_START  0xAA
#define FRAME_RESP_START 0x55
#define FRAME_REQ_LEN  4
#define FRAME_RESP_LEN 6

// CRC-8 แบบ bit-by-bit, polynomial 0x07 (CRC-8/SMBUS), init=0x00
// ต้องตรงกับ pc/phase3_offload/protocol.py::crc8() เป๊ะ ๆ
static inline uint8_t crc8(const uint8_t* data, uint8_t len) {
    uint8_t crc = 0x00;
    for (uint8_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t b = 0; b < 8; b++) {
            if (crc & 0x80) {
                crc = (uint8_t)((crc << 1) ^ 0x07);
            } else {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc;
}
