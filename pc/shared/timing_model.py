# timing_model.py — ประมาณเวลาที่แต่ละจุดข้อมูล (circuit, n) "ควรจะ" ใช้ แล้วแปลงเป็น
# timeout budget ต่อจุด (แหล่งความจริงเดียวของทั้ง Phase 2 และ Phase 3)
#
# ทำไมต้องมีไฟล์นี้: เดิมทุกสคริปต์ sweep ใช้ timeout ค่าคงที่ค่าเดียว (SERIAL_TIMEOUT_S
# = 70 วินาที) ซึ่งพอดีกับ h_all/bell_ghz/qft แต่ "สั้นเกินไปมาก" สำหรับ grover ที่ n สูง
# (ESP8266 grover n=12 ประเมินไว้ ~2004 วินาทีต่อจุด) ผลคือจุดข้อมูลของ grover ที่ n สูง
# จะถูกบันทึกเป็น runtime_hang_or_reset ทั้งที่บอร์ด "ไม่ได้ hang" — แค่ยังคำนวณไม่เสร็จ
# กลายเป็น timeout artifact ที่ถูกตีความผิดเป็น Memory Wall
#
# การแก้แบบ "ขึ้น timeout รวมให้สูงไปเลย" ใช้ไม่ได้ เพราะจะทำให้การ hang จริงของวงจร
# "ถูก ๆ" (เช่น h_all n=2) ต้องรอนานเท่ากัน — เสียเวลาหลายชั่วโมงไปกับความล้มเหลวที่
# ตรวจพบได้ในไม่กี่วินาที จึงต้องให้ timeout เป็นฟังก์ชันของต้นทุนวงจรที่คาดไว้แทน
#
# โครงสร้าง:
#   1. GATE_COUNTS — จำนวนเกทแยกตามชนิด (H / CNOT / CPhase) ของแต่ละวงจร
#      ต้องตรงกับ firmware/common/circuits.hpp เสมอ (มี self-test ท้ายไฟล์)
#   2. BOARD_GATE_COST — ค่าคงที่เวลาต่อเกทต่อ amplitude ของแต่ละบอร์ด fit จากข้อมูล
#      ที่ "วัดจริง" ในรอบ REPS=30 (กู้จาก git history: docs/report/chapter4_results_th.md
#      ที่ commit 7a7c728~1) — ไม่ใช่ค่าที่เดาเอา
#   3. timeout_budget_s() — expected × SAFETY_FACTOR หนีบด้วย FLOOR/CEILING
#
# ข้อจำกัดที่ต้องรู้: ค่าประมาณของ grover/qpe/steane_encode เป็นการ "ประมาณการ"
# (projected) จากสูตรจำนวนเกท ไม่ใช่ค่าที่วัดจากบอร์ดจริง เพราะยังไม่เคยรันวงจรทั้งสาม
# บนฮาร์ดแวร์เลย ส่วน h_all/bell_ghz/qft เป็นค่าที่ fit จากการวัดจริง หลังรอบ REPS=100
# เสร็จควรกลับมา re-fit ค่าคงที่ทั้งหมดจากข้อมูลจริงชุดใหม่

import math
from datetime import datetime, timedelta

REPS = 100  # ต้องตรงกับ #define REPS ใน firmware/*/src/main.cpp

# --- นโยบาย timeout (ค่าตัดสินใจเชิงระเบียบวิธี ไม่ใช่ค่าที่ได้จากข้อมูล) ---

# 2.5× เผื่อความแปรปรวน: IQR ที่วัดจริงในรอบ REPS=30 แคบมาก (< 0.3% ของ median ทุกจุด
# เพราะเป็น bare-metal ไม่มี OS คั่น) ตัวที่ต้องเผื่อจริง ๆ คือความคลาดเคลื่อนของ "ตัวแบบ"
# เอง (ดู validate_model() — residual สูงสุดอยู่ราว ±40%) บวกเวลา build/upload/boot
# ที่ไม่ได้อยู่ในสูตร ไม่ใช่ความแปรปรวนของตัวเลขเวลาเอง
SAFETY_FACTOR = 2.5

# พื้น: จุดข้อมูลที่ถูกที่สุด (h_all n=2 บน ESP32) ประเมินได้ ~0.2 มิลลิวินาที ซึ่งแปลว่า
# timeout จะเหลือเศษวินาที — สั้นกว่าเวลาที่บอร์ด reset ตัวเองหลัง upload แล้วเริ่ม
# setup() ใหม่ (~1-2 วินาที) เสียอีก จึงต้องมีพื้นที่ครอบเวลา boot + serial handshake
FLOOR_S = 90

# เพดาน: 4 ชั่วโมงต่อจุดข้อมูล — เลือกจาก 2 ข้อจำกัดที่ชนกัน
#
# (1) ความเสี่ยงของลิงก์ USB: เคยเจอจริงในรอบ REPS=30 ว่าพอร์ต USB-CDC ของ Uno ค้าง
#     เกิน 16 นาทีโดยที่ pyserial ไม่ timeout ตามที่ตั้งไว้ (ดู run_log.md) ยิ่งรอนาน
#     ต่อจุด โอกาสที่สายหลุด/พอร์ต re-enumerate กลางคันจนเสียการรอทั้งหมดยิ่งสูง
# (2) ต้องครอบ "จุดที่แพงที่สุดเท่าที่ยังทำได้จริง" ซึ่งคือ ESP32 grover n=10
#     (ประเมิน 6169 วินาที = 1.7 ชั่วโมง) — เพดาน 4 ชั่วโมงยังเหลือ headroom 2.3 เท่า
#
# จุดที่ "ประเมินแล้วเกินเพดาน" (เช่น ESP8266 grover n=10 = 1.3 วัน, grover n=12 = 95 วัน)
# ไม่ใช่เรื่องของ timeout อีกต่อไป แต่เป็นขีดจำกัดเชิงการคำนวณจริง ๆ ไม่มีค่า timeout
# ไหนช่วยได้ — สคริปต์จะข้ามจุดพวกนี้พร้อมบันทึกเหตุผลและตัวเลขประเมินไว้ในผลลัพธ์
# (ดู is_compute_infeasible) แทนที่จะนั่งรอ 4 ชั่วโมงเพื่อให้ได้ timeout เปล่า ๆ
#
# 2026-09-22 — Phase 2 ตัดสินใจใหม่ (ยืนยันจากเจ้าของโครงการ): เพดานนี้ "ไม่บังคับ
# ใช้กับ Phase 2 อีกต่อไป" — timeout_budget_s()/is_compute_infeasible()/
# budget_is_capped() ของ Phase 2 ไม่ใช้ค่านี้แล้ว (ดู comment ที่แต่ละฟังก์ชัน) จุดไหน
# ก็ตามจะถูกพยายามรันจริงเสมอ ไม่มีการ skip ล่วงหน้าอีกต่อไป เหตุผล: ผู้ควบคุมต้องการ
# ควบคุมเองว่าจะรอนานแค่ไหนต่อจุด (ดู uno_sweep.py's ETA/progress printing + Ctrl+C
# manual-stop, ที่มาแทนบทบาทเดิมของเพดานนี้ในฐานะกลไก "ป้องกันรอไม่มีที่สิ้นสุด")
# ตัวแปรนี้ (และค่าคงที่/ฟังก์ชันที่ยังอ้างถึงมันด้านล่าง) คงไว้เฉพาะสำหรับ Phase 3
# (PHASE3_CEILING_S แยกต่างหากอยู่แล้ว ไม่ถูกกระทบ) และเพื่อไม่ให้โค้ด/เทสต์เก่าที่ยัง
# import ชื่อนี้พัง — ไม่ใช่ค่าที่มีผลจริงต่อพฤติกรรม Phase 2 อีกต่อไป
CEILING_S = 14400

# retry: ดูเหตุผลใน retry_allowed()
RETRY_MAX_BUDGET_S = 600

# ---------------------------------------------------------------------------
# BUILD_TIMEOUT_S — เวลาสูงสุดที่ยอมรอ `pio run` (compile) และ `pio run -t upload`
# ต่อครั้ง ค่าเดิมคือ 120s (uno/esp8266) และ 150s (esp32/phase3) ซึ่ง "แคบเกินไป"
# เมื่อวัดจริง: preflight (docs/preflight_report.md, 66 builds) วัด compile ของ
# ESP8266 ได้ mean 47.3s / **peak 85s** — เหลือ margin แค่ 1.4 เท่าของเพดาน 120s
# และทุกจุดข้อมูลเปลี่ยน N_QUBITS จึง rebuild ใหม่ทั้งหมดทุกครั้ง (ไม่ใช่เฉพาะ build
# แรก) margin แคบขนาดนี้กับงานที่รันยาว 13.9 ชั่วโมงบนเครื่องที่มีงานอื่นแย่ง CPU
# (Spotlight, thermal throttle, การดาวน์โหลด toolchain ที่เกิดใน `pio run` เดียวกัน)
# เสี่ยงเกินไป
#
# 300s = ~3.5 เท่าของ peak ที่วัดได้จริง (85s) เลือกค่านี้เพราะ:
#   - timeout ไม่ใช่ "กำแพง" อีกต่อไป (ดู resume.is_wall_status) และ retry ได้
#     ดังนั้นค่าที่ใหญ่เกินจำเป็นมีต้นทุนแค่ "รอนานขึ้นในกรณีที่พังจริง" เท่านั้น
#     ไม่ได้ทำให้ข้อมูลผิด — ต่างจากค่าที่แคบเกินซึ่งทำให้ข้อมูลผิดได้ (บันทึกเป็นกำแพงปลอม)
#   - 3.5 เท่าครอบคลุมเครื่องที่ช้าลง 2-3 เท่าชั่วคราวได้สบาย ๆ
#   - ยังสั้นพอที่จะจับ "pio ค้างจริง" ได้ภายใน 5 นาที ไม่ใช่ค้างข้ามคืน
# ปรับได้ต่อการรันผ่าน --build-timeout ของแต่ละสคริปต์ sweep
BUILD_TIMEOUT_S = 300

# ---------------------------------------------------------------------------
# WDT_PER_REP_THRESHOLD_S — เกณฑ์ "เวลาต่อ 1 rep ที่ทำให้ watchdog reset เป็นไปได้"
# ต่อบอร์ด ถ้าเวลาที่ประเมินไว้ต่อ rep เกินค่านี้ การที่บอร์ดเงียบ/รีเซ็ตต้องถูกบันทึก
# เป็น watchdog_suspected ไม่ใช่ runtime_hang_or_reset และ "ห้าม" ตีความเป็น Memory Wall
# โดยอัตโนมัติ (ดู docs/preflight_report.md finding H1)
#
# *** สมมติฐานเรื่อง WDT — ยังไม่ได้ยืนยันกับฮาร์ดแวร์จริง (UNVERIFIED) ***
#   esp8266 = 6.0s : hardware WDT ของ ESP8266 รีเซ็ตที่ราว 8 วินาที และ
#                    ESP.wdtDisable() ในเฟิร์มแวร์ปิดได้แค่ "software" WDT เท่านั้น
#                    ไม่ได้ปิด hardware WDT — ตั้ง 6.0s ให้ต่ำกว่า 8s ไว้เป็น margin
#   esp32   = 5.0s : ค่า default ของ Task WDT ใน ESP-IDF คือ 5 วินาที (แม้ Arduino
#                    core มักไม่เปิดให้ loopTask ก็ตาม จึงเป็นการตั้งแบบระมัดระวังไว้ก่อน)
#   uno     = None : Arduino AVR core ไม่เปิด watchdog ให้โดยค่าเริ่มต้น จึงไม่มีเกณฑ์นี้
# ทั้งสามค่ามาจากความรู้ทั่วไปเรื่องแพลตฟอร์ม ไม่ได้มาจากการวัดในโปรเจกต์นี้ —
# ต้องยืนยันกับ datasheet/ซอร์สของ core ก่อนนำตัวเลขไปอ้างในรายงาน
WDT_PER_REP_THRESHOLD_S = {"uno": None, "esp8266": 6.0, "esp32": 5.0}


# ---------------------------------------------------------------------------
# 1. จำนวนเกทแยกชนิด — ต้องตรงกับ firmware/common/circuits.hpp
#    คืนค่า (n_h, n_cnot, n_cphase)
# ---------------------------------------------------------------------------

def _mc_phase_types(k, _memo={}):
    """จำนวนเกทของ mc_phase_apply(k) (k control = คิวบิต [0,k-1])

    เวียนเกิดตรงตาม circuits.hpp:
      k<=1 : CPhase 1 ตัว
      k>=2 : CPhase 2 ตัว (คู่ ±theta/2) + mc_x_apply(k-1) 2 ครั้ง + mc_phase_apply(k-1)
    และ mc_x_apply(m) = CNOT 1 ตัว ถ้า m==1, ไม่งั้น = H 2 ตัว + mc_phase_apply(m)
    """
    if k in _memo:
        return _memo[k]
    if k <= 1:
        return (0, 0, 1)
    if k - 1 == 1:
        mcx = (0, 1, 0)  # mc_x_apply(1) = CNOT ตรง ๆ
    else:
        h, c, p = _mc_phase_types(k - 1)
        mcx = (h + 2, c, p)  # H ประกบสองข้าง + mc_phase_apply(k-1)
    rest = _mc_phase_types(k - 1)
    out = (2 * mcx[0] + rest[0],
           2 * mcx[1] + rest[1],
           2 * mcx[2] + rest[2] + 2)
    _memo[k] = out
    return out


def grover_iterations(n):
    """floor(pi/4 * sqrt(2^n)) อย่างน้อย 1 — ตรงกับ circuit_grover"""
    return max(1, int((math.pi / 4) * math.sqrt(1 << n)))


def gate_counts(circuit, n):
    """คืน (n_h, n_cnot, n_cphase) ของวงจรที่ n ที่กำหนด"""
    if circuit == "h_all":
        return (n, 0, 0)
    if circuit == "bell_ghz":
        return (1, n - 1, 0)
    if circuit == "qft":
        return (n, 0, n * (n - 1) // 2)
    if circuit == "grover":
        it = grover_iterations(n)
        mh, mc, mp = _mc_phase_types(n - 1)
        # ต่อ 1 iteration: oracle (mc_phase) + diffusion (H ทุกคิวบิต, X ทุกคิวบิตผ่าน
        # H-Z-H, mc_phase, X ทุกคิวบิตอีกครั้ง, H ทุกคิวบิต)
        #   H     = 2*mh + (n + 2n + 2n + n) = 2*mh + 6n
        #   CNOT  = 2*mc
        #   CPhase= 2*mp + 2n   (Z ของ X-sandwich ทั้งสองชุด)
        return (n + it * (2 * mh + 6 * n),
                it * (2 * mc),
                it * (2 * mp + 2 * n))
    if circuit == "qpe":
        t = n - 1
        # eigenstate prep (H,Z,H) + H counting + controlled-U + inverse QFT
        return (2 + t + t, 0, 1 + t + t * (t - 1) // 2)
    if circuit == "steane_encode":
        return (3, 9, 0)  # คงที่ ไม่ขึ้นกับ n
    raise ValueError(f"unknown circuit {circuit!r}")


# ---------------------------------------------------------------------------
# 2. ค่าคงที่เวลาต่อเกทต่อ amplitude ของแต่ละบอร์ด
#    แบบจำลอง: exec_time_us = sum_type(count_type * k_type) * n_states
#
#    fit จากค่า median ที่วัดจริงในรอบ REPS=30 (h_all, bell_ghz, qft) ที่ n สูงสุดของ
#    แต่ละบอร์ด — เลือก n สูงสุดเพราะจุดที่ต้องใช้ตัวแบบนี้จริง ๆ คือ n สูง (ที่ timeout
#    สำคัญ) และที่ n ต่ำ overhead คงที่ของ micros()/ลูปจะครอบงำจนบิดค่า fit
#
#    ที่มาของตัวเลข: docs/report/chapter4_results_th.md ตารางที่ 4.3 / 4.5 / 4.7
#    (ไฟล์ถูกลบไปแล้ว อ่านจาก git history: `git show 7a7c728~1:docs/report/...`)
# ---------------------------------------------------------------------------

BOARD_GATE_COST = {
    # (k_h, k_cnot, k_cphase) หน่วย: ไมโครวินาที ต่อ 1 เกท ต่อ 1 amplitude
    # fit ที่ n = 7 (uno), 12 (esp8266), 13 (esp32) ตามลำดับ ด้วยสมการ 3 ตัวแปร:
    #   h_all    : exec = n * k_h * n_states
    #   bell_ghz : exec = (1 * k_h + (n-1) * k_cnot) * n_states
    #   qft      : exec = (n * k_h + n(n-1)/2 * k_cphase) * n_states
    "uno":     (29.36161, 4.93973, 13.06399),
    "esp8266": (2.73098, 0.15243, 1.10248),
    "esp32":   (0.07863, 0.10349, 0.04637),
}
# ข้อสังเกตที่ตัวเลขบอก: บน Uno (8-bit ไม่มี FPU) H แพงกว่า CNOT ~6 เท่า เพราะ H ทำ
# เลขทศนิยมจริง (คูณ/บวก) ส่วน CNOT แค่สลับ struct ไม่แตะ ALU ทศนิยมเลย — บน ESP32
# ที่มี FPU ความต่างนี้หายไป (k_cnot โผล่สูงกว่า k_h ด้วยซ้ำ ซึ่งมาจาก quantization
# ของ micros() ที่ค่าระดับหลักหน่วยไมโครวินาที ไม่ใช่ความจริงเชิงสถาปัตยกรรม)

# n สูงสุดที่วัดจริงว่ารันสำเร็จในรอบ REPS=30 (Memory Wall ที่วัดได้ ไม่ใช่ทฤษฎี)
MEASURED_WALL_N = {"uno": 7, "esp8266": 12, "esp32": 13}

# ---------------------------------------------------------------------------
# ต้นทุน reflash ต่อจุดข้อมูล — ทั้ง Phase 2 (uno/esp32/esp8266_sweep.py) และ Phase 3
# (pc/phase3_offload/sweep.py) เรียก build_and_upload() หนึ่งครั้งต่อ (circuit, n)
# [Phase 3 เพิ่ม baud เป็นมิติที่ 3] ก่อนเริ่มเก็บ 100 trial ของจุดนั้น เหตุผล: ทั้ง
# N_QUBITS และ CIRCUIT_ID ประกาศเป็น #define ผ่าน build_flags (ดู
# firmware/*/src{,_offload}/main{,_offload}.cpp) จึงเป็นค่าคงที่ตอน "คอมไพล์" ไม่ใช่
# ค่าที่อ่านตอนรันจริง — เฟิร์มแวร์ที่ build ไว้แล้วรันได้แค่ (circuit, n) เดียวตลอดไป
# เปลี่ยนต้องคอมไพล์ + อัปโหลดใหม่เท่านั้น ไม่มีทางอื่น
#
# ข้อสังเกตสำคัญที่เจอระหว่างตรวจสอบ (ไม่ใช่แค่ต้นทุนเวลา แต่เป็นข้อจำกัดเชิงสถาปัตยกรรม
# ที่ควรบันทึกแยกไว้): โปรโตคอล Phase 3 เอง "รองรับ" การเลือก n/circuit_type แบบ runtime
# อยู่แล้ว — เฟรม request 4 byte มี byte[1]=n_qubits, byte[2]=circuit_type ส่งมาพร้อม
# ทุกคำขอ (ดู firmware/common/protocol.hpp) และฝั่ง PC
# (pc/phase3_offload/sweep.py::simulate_and_sample) ก็สร้างวงจร Qiskit ใหม่ตาม
# n/circuit_id ที่ parse ได้จากเฟรมทุกครั้งอยู่แล้ว ไม่ผูกกับค่าคงที่ใด ๆ เลย — ฝั่ง PC
# "พร้อม" รับคำขอที่ n/circuit ต่างกันในทุกเฟรมได้จริง
# แต่เฟิร์มแวร์ฝั่ง MCU (main_offload.cpp) ใช้ N_QUBITS/CIRCUIT_ID (compile-time
# #define) เป็นค่าคงที่ตายตัวเขียนลง req[1]/req[2] "เดิมทุกรอบ" ตลอด 100 rep ของ
# setup() เดียว — ไม่มีกลไกใดให้ MCU เปลี่ยนค่านี้ระหว่างรัน (ไม่มีคำสั่ง serial ให้ตั้งค่า,
# ไม่มีปุ่ม, ไม่มี EEPROM config) สรุปคือ: โปรโตคอลออกแบบให้ "sweep หลายจุดข้อมูลได้ในการ
# เชื่อมต่อเดียว" แต่เฟิร์มแวร์ปัจจุบันใช้งานมันแค่ "ถามคำถามเดียวซ้ำ 100 ครั้ง" เท่านั้น —
# ถ้าจะลดต้นทุน reflash ของ Phase 3 ลงจริง ๆ ต้องแก้เฟิร์มแวร์ให้อ่านชุด (n, circuit)
# ที่จะทดสอบจาก PC ตอน boot ครั้งเดียว (เช่นผ่านเฟรมพิเศษ) แล้ววนสวีปเองในเครื่อง —
# เป็นงานแยกต่างหากจากที่ทำใน session นี้ ไม่ได้แก้ในรอบนี้
#
# ค่าต้นทุนด้านล่าง "ยังไม่ได้วัดจริง" (ต้อง build+upload จริงบนบอร์ดจึงจะวัดได้ ซึ่ง
# session นี้ไม่แตะฮาร์ดแวร์ตามที่ตกลงไว้) เป็นค่าประมาณเชิงเหตุผลจาก 2 ส่วน: (1) เวลา
# คอมไพล์ — N_QUBITS/CIRCUIT_ID เปลี่ยนทุกจุดบังคับ full rebuild ไม่ใช่แค่ relink,
# avr-gcc คอมไพล์โปรเจกต์เล็กเร็ว (~5-10s) แต่ xtensa-gcc (ESP8266/ESP32 บน Arduino
# framework) คอมไพล์ช้ากว่ามากแม้ user code เล็ก เพราะมี framework glue code ให้แปล
# (~15-30s ทั่วไปจากประสบการณ์ใช้งาน PlatformIO) (2) เวลาอัปโหลด — avrdude ที่ 115200
# baud กับไบนารีเล็ก (~2-5s) เทียบกับ esptool ที่ baud สูงกว่าแต่ไบนารีใหญ่กว่ามากเพราะ
# มี framework/bootloader/partition table (~5-10s) ตัวเลขเหล่านี้ "ต้องแทนที่ด้วยค่าที่
# วัดจริง" ก่อนเชื่อถือได้ — ห้ามใช้ตัดสินใจเรื่องเวลารันจริงจนกว่าจะมีการวัด
REFLASH_COST_S = {"uno": 20, "esp8266": 30, "esp32": 30}  # UNMEASURED — placeholder, see above


def session_total_s(board, points, phase=2):
    """ต้นทุนรวมของชุดจุดข้อมูล (circuit, n) หนึ่ง ๆ แยกเป็น (device_s, reflash_s,
    n_run, n_skipped) อย่างชัดเจน — ห้ามรวมกันเป็นตัวเลขเดียวเงียบ ๆ ก่อนรายงาน เพราะ
    reflash_s เป็นค่าประมาณที่ยังไม่วัดจริง (REFLASH_COST_S) ในขณะที่ device_s (เฉพาะ
    h_all/bell_ghz/qft) มาจากข้อมูลวัดจริง — ปนสองอย่างเข้าด้วยกันโดยไม่บอกสัดส่วนทำให้
    ตรวจสอบย้อนหลังไม่ได้ว่าตัวเลขสุดท้ายเชื่อถือได้แค่ไหน

    points = list ของ (circuit, n) ไม่ต้องกรอง infeasible มาก่อน — ฟังก์ชันนี้เช็คเองแล้ว
    ข้ามจุดที่ทำไม่ได้ (ไม่นับ reflash cost ให้จุดที่ถูกข้าม เพราะจริง ๆ แล้วไม่ได้ reflash)"""
    device = reflash = 0.0
    n_run = n_skipped = 0
    for circuit, n in points:
        infeasible = (phase3_is_infeasible(circuit, n) if phase == 3
                      else is_compute_infeasible(board, circuit, n))
        if infeasible:
            n_skipped += 1
            continue
        n_run += 1
        reflash += REFLASH_COST_S[board]
        device += (pc_sim_time_s(circuit, n) * REPS if phase == 3
                   else expected_point_time_s(board, circuit, n))
    return device, reflash, n_run, n_skipped


def point_wall_estimate_s(board, circuit, n, reps=REPS):
    """wall-clock ต่อจุดที่ควรคาดจริง = เวลารันบนบอร์ด + compile/upload (REFLASH_COST_S,
    ยังเป็นค่าประมาณ ไม่ได้วัด) — expected_point_time_s เดี่ยว ๆ ไม่รวม reflash จึงทำให้
    ETA ของจุดเล็ก ๆ (ที่บอร์ดรันเสร็จในเสี้ยววินาที) ต่ำกว่าความจริงหลายเท่า"""
    return expected_point_time_s(board, circuit, n, reps) + REFLASH_COST_S[board]


def expected_exec_time_us(board, circuit, n):
    """เวลารันวงจร 1 trial (ไมโครวินาที) ที่ตัวแบบทำนาย"""
    k_h, k_cnot, k_cphase = BOARD_GATE_COST[board]
    n_h, n_cnot, n_cphase = gate_counts(circuit, n)
    n_states = 1 << n
    return (n_h * k_h + n_cnot * k_cnot + n_cphase * k_cphase) * n_states


def expected_point_time_s(board, circuit, n, reps=REPS):
    """เวลาที่บอร์ดใช้รันครบทั้งจุดข้อมูล (reps trial) เป็นวินาที

    เฟิร์มแวร์รันครบทุก trial ก่อนแล้วค่อยพิมพ์ผลทั้งชุด (ไม่ได้ stream ทีละ trial)
    ฝั่ง host จึงต้องรอครบ reps × เวลาต่อ trial ก่อนจะได้เห็นอะไรเลย"""
    return expected_exec_time_us(board, circuit, n) * reps / 1e6


def timeout_budget_s(board, circuit, n, reps=REPS):
    """timeout/ETA-basis ที่ควรใช้กับจุดข้อมูลนี้ (วินาที, ปัดเป็นจำนวนเต็ม)

    2026-09-22: ไม่หนีบด้วย CEILING_S อีกต่อไปสำหรับ Phase 2 — เดิมค่านี้ทำหน้าที่สอง
    อย่างพร้อมกัน (1) ประมาณเวลาที่ "ควร" รอ และ (2) เป็นเพดานบังคับที่ทำให้จุดแพง ๆ
    ถูกข้ามล่วงหน้า ตอนนี้แยกออกจากกัน: ฟังก์ชันนี้ยังคืนค่าประมาณ (ใช้แสดง ETA/progress
    เท่านั้น ไม่ใช่ hard cutoff อีกต่อไป) ส่วนการหยุดจริงเป็นหน้าที่ของผู้ควบคุม (Ctrl+C,
    ดู read_serial_trials ในแต่ละ sweep script) หรือ hard-hang safety-net ภายในที่แยก
    ต่างหาก (STUCK_READ_ALARM_S ในแต่ละ sweep script เอง ไม่ใช่ค่านี้)"""
    raw = expected_point_time_s(board, circuit, n, reps) * SAFETY_FACTOR
    return int(max(raw, FLOOR_S))


def budget_is_capped(board, circuit, n, reps=REPS):
    """2026-09-22: Phase 2 ไม่มีเพดานให้ชนอีกต่อไป — คืน False เสมอ (เก็บฟังก์ชันไว้ให้
    โค้ด/เทสต์เดิมที่ยัง import อยู่ไม่พัง) ดู CEILING_S ด้านบนสำหรับเหตุผลเต็ม"""
    return False


def is_compute_infeasible(board, circuit, n, reps=REPS):
    """2026-09-22: Phase 2 ไม่ skip จุดไหนล่วงหน้าจากเวลาประมาณอีกต่อไป — คืน False
    เสมอ (เก็บฟังก์ชันไว้ให้โค้ด/เทสต์เดิมที่ยัง import อยู่ไม่พัง เช่น
    analysis/la_capture_plan.py) จุดที่แพงมากยังคงถูก "พยายามรันจริง" เสมอ ผู้ควบคุม
    เป็นคนตัดสินใจเองว่าจะรอนานแค่ไหนผ่าน ETA/progress display + Ctrl+C manual-stop
    แทนที่บทบาทเดิมของเพดานนี้ — ดู CEILING_S ด้านบนสำหรับเหตุผลเต็ม (ยืนยันจากเจ้าของ
    โครงการ 2026-09-22)"""
    return False


def human_duration(seconds):
    """ทำให้ตัวเลขวินาทีอ่านออกในบรรทัด log (95 วัน กับ 8208961 วินาที คนละความรู้สึก)"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}days"


def retry_allowed(budget_s):
    """retry จุดที่ล้มเหลวแบบ transient ได้หรือไม่ ตัดสินจาก timeout budget ของจุดนั้น

    เหตุผล: retry มีไว้กลบความล้มเหลวชั่วคราวของลิงก์ USB (สายหลุด, CDC re-enumerate)
    "ประโยชน์" ของมันคงที่ไม่ว่าจุดจะแพงแค่ไหน (กู้จุดข้อมูลได้ 1 จุด) แต่ "ต้นทุน"
    แปรผันตรงกับ budget — ที่ 70 วินาทีคุ้มชัดเจน แต่ที่ 3600 วินาทีคือการจ่ายเพิ่ม
    อีกชั่วโมงเพื่อทดสอบสมมติฐานที่รันซ้ำเฉพาะจุดนั้นทีหลังก็ได้ (ไฟล์ผลลัพธ์เป็น
    append-only จึงรันซ้ำเฉพาะจุดได้โดยไม่ต้องเริ่มบอร์ดใหม่ทั้งชุด)

    จุดที่ถูกข้าม retry ต้องบันทึกให้เห็นในข้อมูล (คอลัมน์ retry_policy) ไม่ใช่ปล่อยให้
    retry_count=0 ไปปนกับจุดที่ "สำเร็จตั้งแต่ครั้งแรก" ซึ่งคนละความหมายกันสิ้นเชิง"""
    return budget_s <= RETRY_MAX_BUDGET_S


def watchdog_suspected(board, circuit, n, threshold_s=None):
    """True ถ้าเวลาที่ "ประเมินไว้ต่อ 1 rep" ของจุดนี้เกินเกณฑ์ WDT ของบอร์ดนั้น —
    แปลว่าถ้าบอร์ดเงียบ/รีเซ็ต สาเหตุที่เป็นไปได้มากที่สุดคือ watchdog ไม่ใช่หน่วยความจำ
    จึงห้ามบันทึกเป็น Memory Wall โดยอัตโนมัติ (ดู WDT_PER_REP_THRESHOLD_S ประกอบ —
    เกณฑ์เป็นสมมติฐาน ยังไม่ยืนยันกับฮาร์ดแวร์จริง)

    หมายเหตุ: ใช้ "ค่าประเมิน" ไม่ใช่ค่าที่วัดได้ เพราะจุดที่ล้มเหลวไม่มีค่าที่วัดได้ให้ใช้
    เลยตามนิยาม — ค่าประเมินคือข้อมูลเดียวที่มีตอนต้องตัดสินใจ"""
    if threshold_s is None:
        threshold_s = WDT_PER_REP_THRESHOLD_S.get(board)
    if threshold_s is None:
        return False
    return expected_exec_time_us(board, circuit, n) / 1e6 > threshold_s


# ---------------------------------------------------------------------------
# 3. Phase 3 — คนละคอขวดกับ Phase 2 โดยสิ้นเชิง
#    Phase 2 ช้าเพราะ "บอร์ด" คำนวณ, Phase 3 ช้าเพราะ "PC" จำลองด้วย Qiskit Aer ใหม่
#    ทุกคำขอ (ตั้งใจไม่ cache — ดู pc/phase3_offload/sweep.py) ต้นทุนต่อคำขอจึงแปรผัน
#    ตามจำนวนเกทของวงจร ไม่ใช่ตามความเร็วบอร์ด
#
#    ค่าคงที่ fit จากเวลาที่วัดจริงในรอบ Phase 1 ของ session นี้ (เครื่องเดียวกับที่จะ
#    เป็น PC ฝั่ง offload): grover n=8 ใช้ 1.9 วินาที (47,368 เกท), n=10 ใช้ 40.5 วินาที
#    (876,670 เกท) -> ~4.6e-5 วินาทีต่อเกท เชิงเส้นตามจำนวนเกท (ทำนาย n=8 ได้ 2.2
#    วินาที เทียบค่าจริง 1.9 — คลาดเคลื่อน ~15%)
# ---------------------------------------------------------------------------

PC_SECONDS_PER_GATE = 4.6e-5
PC_FIXED_OVERHEAD_S = 0.05  # ค่าเริ่มต้นของ AerSimulator + สร้าง object วงจร

# เพดานของ Phase 3 สูงกว่า Phase 2 (2 ชั่วโมง ไม่ใช่ 1 ชั่วโมง) เพราะความเสี่ยงคนละแบบ:
# Phase 2 รอ "บอร์ดพิมพ์ผลกลับมา" ผ่านลิงก์ USB ที่เคยค้างจริง ส่วน Phase 3 ระหว่างรอ
# มีการแลกเฟรม request/response ตลอดเวลา (ทุก trial) ลิงก์จึงไม่ได้เงียบยาว ๆ แบบ
# Phase 2 และตรวจจับการตายกลางคันได้เร็วกว่ามาก
#
# 2 ชั่วโมงเลือกให้ "ครอบ grover n=10 พอดี" (ประเมิน 4050 วินาที = 67 นาที ต่อจุด
# ต่อบอร์ด) ซึ่งเป็นจุด grover ที่แพงที่สุดที่ยังทำได้จริงแบบไม่ cache ส่วน n=12
# (ประเมิน ~20 ชั่วโมงต่อจุด) จะชนเพดานและถูกบันทึกเป็น session_incomplete ตามจริง
# — จงใจไม่เพิ่ม cache เพื่อให้ตัวเลขดูดีขึ้น เพราะจะเปลี่ยนความหมายของสิ่งที่ Phase 3 วัด
PHASE3_CEILING_S = 7200
PHASE3_FLOOR_S = 300  # เท่ากับ SESSION_TIMEOUT_S เดิม — วงจรถูก ๆ ไม่ควรได้ timeout สั้นลง


def pc_sim_time_s(circuit, n):
    """เวลาที่ PC ใช้จำลองวงจรนี้ 1 ครั้งด้วย Qiskit Aer (สร้างวงจรใหม่ทุกครั้ง ไม่ cache)"""
    n_h, n_cnot, n_cphase = gate_counts(circuit, n)
    return PC_FIXED_OVERHEAD_S + (n_h + n_cnot + n_cphase) * PC_SECONDS_PER_GATE


def phase3_session_budget_s(circuit, n, reps=REPS):
    """timeout ของ 1 session (= 1 จุดข้อมูล = reps คำขอ) ใน Phase 3"""
    raw = pc_sim_time_s(circuit, n) * reps * SAFETY_FACTOR
    return int(min(max(raw, PHASE3_FLOOR_S), PHASE3_CEILING_S))


def phase3_budget_is_capped(circuit, n, reps=REPS):
    return pc_sim_time_s(circuit, n) * reps * SAFETY_FACTOR > PHASE3_CEILING_S


def phase3_is_infeasible(circuit, n, reps=REPS):
    """เวลาจำลองฝั่ง PC ล้วน ๆ เกินเพดาน session — เก็บครบ reps ไม่ได้ในทางปฏิบัติ

    ข้อสังเกตสำคัญ: เกณฑ์นี้ "ไม่ขึ้นกับบอร์ด" เพราะ Phase 3 ให้ PC เป็นคนจำลอง
    ผลคือ grover n=10 ที่ local บน ESP8266 ทำไม่ได้เลย (1.3 วันต่อจุด) กลับ offload
    ได้สบายใน ~1.1 ชั่วโมงต่อจุด — ความไม่สมมาตรนี้คือ crossover ที่ชัดที่สุดในชุดข้อมูล"""
    return pc_sim_time_s(circuit, n) * reps > PHASE3_CEILING_S


# ---------------------------------------------------------------------------
# preflight: พิมพ์แผน budget ทั้งชุดก่อนเริ่มรันจริง
# เจตนา: ให้คนที่กดรันเห็น "จุดไหนจะแพง / จุดไหนจะชนเพดาน" ตั้งแต่ก่อนเริ่ม ไม่ใช่
# ไปค้นพบเอาตอนชั่วโมงที่หก
# ---------------------------------------------------------------------------

def print_budget_plan(board, circuit_n_pairs, reps=REPS, phase=2):
    """พิมพ์แผนก่อนเริ่มรัน คืน set ของ (circuit, n) ที่ประเมินแล้วว่าทำไม่ได้

    ผู้เรียกใช้ค่าที่คืนมาเพื่อข้ามจุดพวกนั้น (หรือ --force-infeasible ถ้าจะดันทุรัง)"""
    total_expected = 0
    total_worst = 0
    infeasible = set()
    print(f"\n--- timeout budget plan (board={board}, phase={phase}, reps={reps}) ---")
    plan_start = datetime.now()
    print(f"start {plan_start.strftime('%a %d %b %H:%M')}  (finish@ = cumulative expected "
          "finish clock time, model estimate)")
    print(f"{'circuit':14s} {'n':>3s} {'expected':>11s} {'finish@':>14s} {'budget_s':>9s}  note")
    for circuit, n in circuit_n_pairs:
        if phase == 3:
            expected = pc_sim_time_s(circuit, n) * reps
            budget = phase3_session_budget_s(circuit, n, reps)
            capped = phase3_budget_is_capped(circuit, n, reps)
            unreachable = phase3_is_infeasible(circuit, n, reps)
        else:
            expected = point_wall_estimate_s(board, circuit, n, reps)
            budget = timeout_budget_s(board, circuit, n, reps)
            capped = budget_is_capped(board, circuit, n, reps)
            unreachable = is_compute_infeasible(board, circuit, n, reps)

        note = ""
        if unreachable:
            note = f"INFEASIBLE — needs {human_duration(expected)}, will be SKIPPED"
            infeasible.add((circuit, n))
        elif capped:
            note = "capped at ceiling (still above expected, should complete)"
        elif phase == 2 and not retry_allowed(budget):
            note = "retry disabled (budget above RETRY_MAX_BUDGET_S)"

        if not unreachable:
            total_expected += expected
            total_worst += budget
        finish = "-" if unreachable else (
            plan_start + timedelta(seconds=total_expected)).strftime("%d %b %H:%M")
        print(f"{circuit:14s} {n:3d} {human_duration(expected):>11s} {finish:>14s} {budget:9d}  {note}")

    print(f"attempted points: expected total {human_duration(total_expected)}, "
          f"worst case if every point times out {human_duration(total_worst)}")
    print("note: upper bound only — the sweep stops a circuit at its first failure, so any n "
          "past the board's Memory Wall is listed here but never actually reached")
    if infeasible:
        print(f"WARNING: {len(infeasible)} point(s) skipped as compute-infeasible: "
              f"{sorted(infeasible)}")
        print("         (pass --force-infeasible to attempt them anyway)")
    print("---\n")
    return infeasible


# ---------------------------------------------------------------------------
# self-test: รันไฟล์นี้ตรง ๆ เพื่อตรวจว่าตัวแบบยังสมเหตุสมผล
#   python3 pc/shared/timing_model.py
# ---------------------------------------------------------------------------

def _check_gate_count_recursion():
    """จำนวนเกทรวมของ mc_phase_apply ต้องตรงกับสูตรเวียนเกิด G(k) ที่เขียนไว้ใน
    circuits.hpp (G(1)=1, G(2)=5, G(3)=21, G(4)=69, ...)"""
    def G(k):
        if k <= 1:
            return 1
        x = 1 if k - 1 == 1 else 2 + G(k - 1)
        return 2 * x + G(k - 1) + 2
    for k in range(1, 12):
        assert sum(_mc_phase_types(k)) == G(k), f"k={k}: {_mc_phase_types(k)} vs {G(k)}"
    return [G(k) for k in range(1, 12)]


def validate_model():
    """เทียบค่าที่ตัวแบบทำนาย กับค่า median ที่วัดจริงในรอบ REPS=30 ทุกจุดที่มีข้อมูล
    (ตัวแบบ fit จาก n เดียวต่อบอร์ด จึงต้องตรวจว่ามันยัง extrapolate ไปจุดอื่นได้)"""
    measured = {
        "uno": {
            "h_all": {2: 284, 3: 812, 4: 2088, 5: 4906, 6: 11468, 7: 26308},
            "bell_ghz": {2: 150, 3: 348, 4: 772, 5: 1704, 6: 3556, 7: 7552},
            "qft": {2: 292, 3: 1932, 4: 4692, 5: 11012, 6: 25920, 7: 61424},
        },
        "esp8266": {
            "h_all": {2: 24, 3: 72, 4: 187, 5: 456, 6: 1082, 7: 2499, 8: 5663,
                      9: 12697, 10: 28057, 11: 61760, 12: 134233},
            "bell_ghz": {2: 13, 3: 26, 4: 51, 5: 104, 6: 215, 7: 444, 8: 919,
                         9: 1961, 10: 4067, 11: 8707, 12: 18054},
            "qft": {2: 28, 3: 248, 4: 578, 5: 1262, 6: 2781, 7: 6290, 8: 14524,
                    9: 34132, 10: 79774, 11: 187237, 12: 432274},
        },
        "esp32": {
            "h_all": {2: 2, 3: 4, 4: 7, 5: 15, 6: 32, 7: 71, 8: 163, 9: 364,
                      10: 812, 11: 1779, 12: 3872, 13: 8374},
            "bell_ghz": {2: 2, 3: 3, 4: 7, 5: 15, 6: 34, 7: 78, 8: 177, 9: 417,
                         10: 931, 11: 2282, 12: 4988, 13: 10818},
            "qft": {2: 3, 3: 11, 4: 23, 5: 48, 6: 103, 7: 230, 8: 523, 9: 1275,
                    10: 3010, 11: 7066, 12: 15609, 13: 38003},
        },
    }
    worst = 0.0
    worst_at = None
    rows = []
    for board, circuits in measured.items():
        for circuit, table in circuits.items():
            for n, actual_us in table.items():
                pred = expected_exec_time_us(board, circuit, n)
                rel = (pred - actual_us) / actual_us
                rows.append((board, circuit, n, actual_us, pred, rel))
                # จุดที่ n <= 4 มี overhead คงที่ของ micros()/ลูปครอบงำ ไม่นับเป็น
                # ตัววัดคุณภาพของตัวแบบ (timeout ที่ n ต่ำถูกกำหนดโดย FLOOR_S อยู่แล้ว)
                if n > 4 and abs(rel) > abs(worst):
                    worst, worst_at = rel, (board, circuit, n)
    return rows, worst, worst_at


if __name__ == "__main__":
    g = _check_gate_count_recursion()
    print("mc_phase gate-count recursion G(1..11):", g)

    rows, worst, worst_at = validate_model()
    print(f"\n{'board':8s} {'circuit':9s} {'n':>3s} {'measured_us':>12s} {'model_us':>12s} {'rel_err':>9s}")
    for board, circuit, n, actual, pred, rel in rows:
        flag = "  <-- worst" if (board, circuit, n) == worst_at else ""
        print(f"{board:8s} {circuit:9s} {n:3d} {actual:12d} {pred:12.1f} {rel:8.1%}{flag}")
    print(f"\nworst relative error at n>4: {worst:.1%} at {worst_at}")
    print(f"SAFETY_FACTOR={SAFETY_FACTOR} must exceed that margin to avoid false timeouts")

    print("\n--- phase 2 timeout budgets, extreme cases ---")
    for board, circuit, n in [("esp8266", "h_all", 2), ("esp8266", "qft", 12),
                              ("esp8266", "grover", 8), ("esp8266", "grover", 10),
                              ("esp8266", "grover", 12), ("esp32", "grover", 10),
                              ("esp32", "grover", 12), ("uno", "grover", 6),
                              ("uno", "steane_encode", 7), ("esp8266", "qpe", 12)]:
        exp_s = expected_point_time_s(board, circuit, n)
        b = timeout_budget_s(board, circuit, n)
        state = "INFEASIBLE" if is_compute_infeasible(board, circuit, n) else (
            "capped" if budget_is_capped(board, circuit, n) else "ok")
        print(f"{board:8s} {circuit:14s} n={n:2d}  expected={human_duration(exp_s):>9s}  "
              f"budget={b:6d}s  retry={'yes' if retry_allowed(b) else ' NO'}  {state}")

    print("\n--- phase 3 (PC-side Aer, uncached, board-independent) ---")
    for circuit, n in [("qft", 12), ("grover", 8), ("grover", 10), ("grover", 12)]:
        per_req = pc_sim_time_s(circuit, n)
        full = per_req * REPS
        b = phase3_session_budget_s(circuit, n)
        state = "INFEASIBLE" if phase3_is_infeasible(circuit, n) else (
            "capped" if phase3_budget_is_capped(circuit, n) else "ok")
        print(f"{circuit:9s} n={n:2d}  per_request={per_req:9.2f}s  "
              f"x{REPS} = {human_duration(full):>9s}  budget={b:5d}s  {state}")
