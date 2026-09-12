#!/usr/bin/env python3
# protocol.py — Phase 3: โปรโตคอลเฟรม ต้องตรงกับ firmware/common/protocol.hpp เป๊ะ ๆ
#
# Request (MCU -> PC), 4 bytes:  [0xAA][n_qubits][circuit_type][CRC8]
# Response (PC -> MCU), 6 bytes: [0x55][outcome:4 bytes big-endian][CRC8]

FRAME_REQ_START = 0xAA
FRAME_RESP_START = 0x55
FRAME_REQ_LEN = 4
FRAME_RESP_LEN = 6


def crc8(data: bytes) -> int:
    """CRC-8 แบบ bit-by-bit, polynomial 0x07 (CRC-8/SMBUS), init=0x00 — ต้องตรงกับ
    firmware/common/protocol.hpp::crc8() เป๊ะ ๆ"""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def pack_response(outcome: int) -> bytes:
    body = bytes([FRAME_RESP_START]) + outcome.to_bytes(4, "big")
    return body + bytes([crc8(body)])


def parse_request(frame: bytes):
    """คืนค่า (n_qubits, circuit_type) ถ้าเฟรมถูกต้อง, None ถ้า CRC ไม่ตรง"""
    if len(frame) != FRAME_REQ_LEN or frame[0] != FRAME_REQ_START:
        return None
    if crc8(frame[:3]) != frame[3]:
        return None
    return frame[1], frame[2]
