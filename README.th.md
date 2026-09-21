# QuantumMCU Research — Quantum Lab (ภาษาไทย)

เวอร์ชันย่อของ [`README.md`](README.md) — คำสั่ง, ชื่อไฟล์/โฟลเดอร์, flag, และ
ชื่อ tag คงเป็นภาษาอังกฤษทั้งหมดตามต้นฉบับ อ่าน `README.md` ฉบับเต็มสำหรับ
รายละเอียดที่ไม่ได้สรุปไว้ที่นี่ (repo layout เต็ม, การอ้างอิง, ฯลฯ)

**คำถามวิจัย:** สำหรับวงจรและจำนวนคิวบิตที่กำหนด ไมโครคอนโทรลเลอร์ควรจำลอง
วงจรควอนตัม *ในตัวเอง* หรือ *ส่งไปให้ PC (Qiskit Aer) คำนวณแทน*?

**สิ่งที่วัด:** เวลาประมวลผลจริงบนบอร์ด (Phase 2, ผ่าน `micros()`) และ latency
การส่งข้อมูลไป-กลับกับ PC (Phase 3) **สิ่งที่ไม่ได้วัด:** ความถูกต้องของผลลัพธ์
ที่บอร์ดคำนวณเอง — ตรวจแค่ครั้งเดียวที่ Phase 1 ฝั่ง PC เท่านั้น

**บอร์ดที่มีข้อมูลจริงในโครงการนี้ตอนนี้: Uno เท่านั้น.** ESP8266/ESP32 และ
Phase 3 ทุกบอร์ด ยังไม่เคยรันกับฮาร์ดแวร์จริงเลย — ตัวเลขใด ๆ เกี่ยวกับบอร์ด
เหล่านี้ในเอกสารนี้เป็นค่าประมาณจาก `pc/shared/timing_model.py` หรือค่าจากการ
build เฉย ๆ (`docs/preflight_report.md`) ไม่ใช่ค่าที่วัดจริง — ถือว่า
**UNVERIFIED** เสมอจนกว่าจะมีไฟล์จริงใน `data/raw/phase{2,3}/{esp8266,esp32}/`

---

## Setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

เวอร์ชัน dependency ทั้งหมดถูกปักไว้ (`requirements.txt`) เพราะตัวแปรที่วัดคือ
"เวลา" — การอัปเดต `numpy`/`qiskit-aer` โดยไม่ตั้งใจจะเปลี่ยนต้นทุนการจำลองฝั่ง
PC ที่ Phase 3 วัด โดยไม่มีอะไรเตือน ต้องมี [PlatformIO](https://platformio.org/)
(`pio`) อยู่บน `PATH` ด้วย

**หมายเหตุ macOS:**
- ชื่อพอร์ต: Uno = `/dev/cu.usbmodem*`, ESP8266/ESP32 = `/dev/cu.usbserial*` /
  `/dev/cu.wchusbserial*` / `/dev/cu.SLAB_USBtoUART*` — เลขพอร์ตของ Uno
  เปลี่ยนได้กลางทาง สคริปต์จัดการเองอัตโนมัติ ไม่ต้องแก้คำสั่ง
- ถ้าเจอ `Operation not permitted` ตอนเปิดพอร์ต: terminal ต้องมี Full Disk
  Access, และห้ามเปิด `pio device monitor` ค้างไว้ก่อนรัน sweep
- หลีกเลี่ยงการวางโฟลเดอร์ repo นี้ในที่ที่ iCloud sync — การ sync อาจ lock
  ไฟล์ตอนที่สคริปต์กำลังจะเขียนผลลัพธ์พอดี
- กันเครื่องหลับก่อนรันจริง: `caffeinate -dims` ในเทอร์มินัลแยก (หรือให้
  `pc/run.py` เช็คสถานะให้ก่อนถาม y/n)

---

## รันคำสั่ง

**เจ้าของโครงการรันวงจร/บอร์ด/phase อะไรก็ได้ เมื่อไหร่ก็ได้ผ่าน `pc/run.py`
โดยไม่ต้องรออนุมัติ** (มาตรฐานใหม่ 2026-09-21 — ดู `run_log.md`) กติกาเดิม
(รันทีละวงจร หยุดรอ "go") ยังใช้กับงานที่รันผ่าน Claude Code เท่านั้น

```bash
# 1. ดูว่าจะรันคำสั่งอะไร โดยไม่แตะฮาร์ดแวร์เลย:
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --dry-run

# 2. รันจริง:
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101
```

`pc/run.py` เป็นแค่ตัวตรวจสอบ input + preflight check (git tree, พอร์ต,
กันเครื่องหลับ, สถานะ resume) แล้วส่งต่อไปยังสคริปต์เก็บข้อมูลจริง
(`pc/phase2_sweep/<board>_sweep.py` หรือ `pc/phase3_offload/sweep.py`) —
ตรรกะการเก็บข้อมูลทั้งหมดอยู่ในสคริปต์เดิม ไม่มีการเขียนซ้ำในนี้

Flag หลัก: `--board` `--algorithm` `--phase` `--port` (บังคับทั้งหมด, `--port`
**ไม่เดาให้อัตโนมัติ**), `--n-start`/`--n-max` (ส่งต่อตรง ๆ), `--reps`
(**เช็คค่าเท่านั้น ไม่ส่งต่อ** — `REPS` เป็นค่าคงที่ตอนคอมไพล์เฟิร์มแวร์
เปลี่ยนจาก CLI ไม่ได้), `--build-timeout`, `--upload-retry-settle-s`/`--la`
(เฉพาะ Uno Phase 2), `--fresh`, `--dry-run`, `--yes` — รายละเอียดเต็มดู
`docs/run/<board>.md` และ `README.md`

หนึ่งวงจรต่อหนึ่งบอร์ดต่อหนึ่ง phase ต่อการรันหนึ่งครั้ง (`--algorithm` รับ
ค่าเดียว ไม่ใช่ list)

---

## `--fresh` และ archive (2026-09-21)

`--fresh` **ย้าย** (ไม่ลบ ไม่ copy) ข้อมูล/กราฟ/เอกสารวิเคราะห์เดิมของ
(board, algorithm, phase) นั้นไปที่
`data/archive/phase<N>/<board>/<algorithm>/<UTC timestamp>/` พร้อม
`MANIFEST.json` (git commit/dirty/ref, เหตุผล, คำสั่งที่ใช้, sha256 +
จำนวนแถวต่อไฟล์ — คำนวณ**ก่อน**ย้ายเสมอ) ถ้าย้ายหรือเขียน manifest ไม่สำเร็จ
จะ rollback ไฟล์ที่ย้ายไปแล้วทั้งหมดและยกเลิกก่อนเริ่มเก็บข้อมูลจริง — ไม่มี
โค้ดใน `pc/`, `analysis/`, `resume.py`, `telemetry.py` หรือสคริปต์กราฟใด ๆ
อ่านจาก `data/archive/` เลย (พิสูจน์ด้วย grep ทั้ง repo + รันจริงบนสำเนา
ทดสอบแล้วลบ `data/archive/` เทียบ sha256 ก่อน-หลัง ใน `pc/run_test.py`) —
**ลบโฟลเดอร์ archive ไหนก็ได้ทุกเมื่อด้วย `rm -r`** ไม่กระทบ pipeline

**การรันแบบ fresh เริ่มที่ n ต่ำสุดที่ "มีความหมาย" ของแต่ละวงจร ไม่ใช่ 2 เสมอ:**

| วงจร | n ต่ำสุด | เหตุผล |
|---|---|---|
| `h_all` | 1 | superposition 1 คิวบิตเป็น state จริง ใช้ได้ |
| `qft` | 1 | QFT 1 คิวบิต คือเกท H ตัวเดียวพอดี |
| `bell_ghz` | 2 | n=1 รันได้ (แค่ H(0)) แต่ไม่เกิด entanglement เลย ไม่ใช่ Bell/GHZ |
| `grover` | 2 | ไม่มี control qubit เหลือให้ oracle (ระบุไว้ทั้งใน firmware และ `phase1_compare.py`) |
| `qpe` | 3 | n=1 ไม่มี counting qubit เลย (no-op); n=2 มี 1 (รันได้ แต่ต่ำกว่าที่วงจรออกแบบไว้) |
| `steane_encode` | 7 | คงที่เหมือนเดิม |

ถ้าใส่ `--n-start` ต่ำกว่าค่าต่ำสุดนี้ตอน `--fresh` จะถูก clamp ขึ้นพร้อมข้อความแจ้ง
เตือน ไม่ส่งไปที่บอร์ดเด็ดขาด ไม่นับเป็นความล้มเหลวหรือกำแพง **ไม่มีวงจรไหน
เคยผ่านการ validate ด้วย Phase 1 (Qiskit) ที่ n=1 เลย** (`phase1_compare.py`
เริ่มที่ n=2 เสมอ) แต่ `timing_model.py` มีค่าประมาณ timeout ที่ n=1 ให้ทุกวงจร
จริง (ทดสอบเรียกจริงแล้ว ไม่มี exception) — การรันแบบไม่ fresh (resume/append)
**ไม่เปลี่ยนแปลงเลย** เหมือนเดิมทุกประการ

---

## โครงสร้างข้อมูล

```
data/raw/phase<N>/<board>/<circuit>/
  raw.csv              ทุก repetition, 100 แถวต่อจุดที่ ok
  memory_wall.csv        Phase 2: 1 แถวสรุปต่อจุด
  session_log.csv         Phase 3: 1 แถวสรุปต่อจุด
  points.csv            1 แถวต่อความพยายามอัปโหลดหนึ่งครั้ง (retry แยกแถว)
  sessions.csv            1 แถวต่อการรันสคริปต์หนึ่งครั้ง
  env/<session_id>.json  metadata ของแต่ละ session

data/figures/<board>/<circuit>/*.png   PNG เท่านั้น (ไม่มี SVG ในชุดข้อมูลใหม่นี้)
data/figures/<board>/all_algorithms_so_far.png   กราฟรวม สร้างใหม่ทุกครั้ง
```

**Resume เปิดเป็นค่าเริ่มต้นเสมอ** — วิธีหยุด/รันต่อที่ปลอดภัยคือกด Ctrl+C
แล้วรันคำสั่งเดิมซ้ำ จุดที่มีแถวสรุปแล้วจะถูกข้ามทันที จุดที่ตายกลางทาง
(มีแถว raw แต่ไม่มีแถวสรุป) จะถูกรันใหม่ทั้งหมดตั้งแต่ rep 0 **ห้ามรัน sweep
สองตัวพร้อมกันบนพอร์ตเดียวกันเด็ดขาด** — เคยทำให้เกิด avrdude protocol error
ที่ดูเหมือนฮาร์ดแวร์พังแต่จริง ๆ คือสอง process แย่งพอร์ตกัน (มีบันทึกไว้ใน
`run_log.md` จริง)

---

## แก้ปัญหาเบื้องต้น

| อาการ | สาเหตุที่เป็นไปได้ | แก้อย่างไร |
|---|---|---|
| `avrdude: stk500_getsync() ... not in sync` | อัปโหลดสะดุดชั่วคราว หรือมีสอง process แย่งพอร์ตเดียวกัน | ปล่อยให้ retry อัตโนมัติ (สูงสุด 3 ครั้ง) ทำงานไปก่อน ถ้ายังเกิดซ้ำ เช็ค `lsof <port>` ว่ามี process อื่นถือพอร์ตอยู่หรือไม่ |
| เลขพอร์ต Uno เปลี่ยนกลางทาง | บอร์ด re-enumerate ระหว่างอัปโหลด | ปกติ สคริปต์จัดการเองอัตโนมัติ ไม่ต้องแก้คำสั่ง |
| `Operation not permitted` เปิดพอร์ตไม่ได้ (macOS) | ไม่มี Full Disk Access หรือมีโปรแกรมอื่นถือพอร์ตอยู่ | ให้สิทธิ์ Full Disk Access กับ terminal, ปิด serial monitor ที่เปิดค้างไว้ |
| บอร์ดเงียบ ไม่มี `DONE`, ได้ `runtime_hang_or_reset` (ไม่มีหลักฐาน RAM) | อาจ hang จริง, สะดุดชั่วคราว, หรือ (น้อยมาก) เป็นกำแพงจริงที่ตรวจตอนคอมไพล์ไม่เจอ | **ไม่ถือเป็น Memory Wall อัตโนมัติ** ต้องตรวจด้วยตา — ดู `failure_message`/`reset_count` ใน `points.csv` |
| session ยาวดูเหมือนค้างหรือเครื่องหลับกลางทาง | ไม่ได้กันเครื่องหลับ | รัน `caffeinate -dims` ในเทอร์มินัลแยกก่อนเริ่ม |

---

## สถานะปัจจุบัน (อ่านจากไฟล์จริง)

| บอร์ด | Phase | วงจร | `n` ที่เก็บแล้ว | ผลลัพธ์ |
|---|---|---|---|---|
| Uno | 2 | `h_all`/`bell_ghz`/`qft`/`qpe` | 2–7 ok, 8 wall | `build_overflow` ที่ n=8, RAM 109.8–110.1% ทุกวงจร |
| Uno | 2 | `steane_encode` | 7 (คงที่) ok | ไม่มีกำแพง — n คงที่ไม่เคยแตะเพดาน RAM |
| Uno | 2 | `grover` | ยังไม่มี commit | เก็บสำเร็จรอบแรกแล้ว (n=2–7 ok, n=8 ข้ามเพราะ compute-infeasible) แต่การพยายามบังคับรัน n=8 ซ้ำเจอปัญหาสอง process แย่งพอร์ตกัน ไฟล์ที่เหลือ (ไม่มีแถวข้อมูลจริงเหลือเลย มีแต่ log ความล้มเหลว) ถูก archive ไปที่ `data/archive/phase2/uno/grover/20260921T135125Z/` แล้ว ไม่ใช่ commit — รอรันใหม่ผ่าน `pc/run.py` |
| Uno | 3, ESP8266/ESP32 ทั้งหมด | ทุกวงจร | — | ยังไม่เคยรัน — UNVERIFIED |

---

## ข้อจำกัดสำคัญ

- **Grover ที่ n=9/n=10 เกินเกณฑ์ fidelity ของโครงการเอง** (`1e-3`) — วัดได้
  `1.5e-3` (n=9) และ `6.5e-3` (n=10) เพราะ Oracle แบบ multi-controlled-phase
  ทำให้ความลึกวงจรโตแบบ `O(3^n)` (`docs/preflight_report.md` finding H3)
- **ความละเอียด `micros()`**: 4µs/tick บน Uno, 1µs บน ESP — เป็นสัดส่วนไม่น้อย
  ของค่าที่วัดได้ที่ n ต่ำ ๆ (ยังไม่ได้ยืนยันด้วย Logic Analyzer จริง)
- **ยังไม่มีข้อมูล Logic Analyzer จริงเลย** — `--la` implement และเทสต์ด้วย
  mock ไว้แล้ว แต่ไม่เคยรันกับฮาร์ดแวร์จริงหรือแม้แต่ `sigrok-cli` demo driver
- **ESP8266/ESP32 และ Phase 3 ทุกบอร์ด ไม่มีข้อมูลฮาร์ดแวร์จริงเลย**
- เฟิร์มแวร์ใช้ `float` (binary32) ทั้งหมด ส่วน Qiskit Aer อ้างอิงใช้
  `complex128` — ตัวเลข infidelity ที่ผ่านเกณฑ์ในโครงการนี้จึงเทียบกับ
  baseline float32 ไม่ใช่ค่าที่ไม่ขึ้นกับสถาปัตยกรรม
