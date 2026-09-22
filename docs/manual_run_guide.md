# คู่มือรันมือ (Manual Run Guide)

เอกสารนี้เขียนจากการอ่านโค้ดจริง ณ commit `pre-run-uno-v1` (tag) โดยตรง — ไฟล์ที่อ่าน:
`pc/phase2_sweep/uno_sweep.py`, `pc/phase2_sweep/esp8266_sweep.py`,
`pc/phase2_sweep/esp32_sweep.py`, `pc/phase3_offload/sweep.py`,
`firmware/uno/platformio.ini`, `firmware/esp8266/platformio.ini`,
`firmware/esp32/platformio.ini`, `pc/shared/circuit_ids.py`,
`pc/shared/telemetry.py`, `pc/shared/la_capture.py`, และ `run_checklist.md`
(เวลาโดยประมาณต่อ session อ้างจากตารางใน `run_checklist.md` § "Total budget" ซึ่งคำนวณ
จาก `pc/shared/timing_model.py` — **ตัวเลขค่า reflash (compile+upload) ในตารางนั้นยังเป็น
ค่าประมาณ ไม่ใช่ค่าที่วัดจริงกับบอร์ดทุกตัว** จนกว่าจะมีการรัน Session A/B/C จริงและอัปเดต
`REFLASH_COST_S` ดู `docs/preflight_report.md` finding H4 และ pilot point แรกที่วัดได้จริง
บน Uno ในรายงานการรันนี้ประกอบ)

ทุกคำสั่งในเอกสารนี้ต้องรันจาก root ของ repo (`quantum-lab/`) ด้วย
`.venv/bin/python` (ไม่ใช่ `python` เฉย ๆ — venv มี `qiskit`, `qiskit_aer`,
`pyserial` ที่สคริปต์ต้องใช้)

**แนะนำ:** สำหรับการรันทั่วไป (หนึ่งวงจร หนึ่งบอร์ด หนึ่ง phase ต่อครั้ง) ใช้
`pc/run.py` แทน — มันตรวจ input, เช็ค preflight (git tree, พอร์ต, กันเครื่องหลับ,
สถานะ resume), พิมพ์คำสั่งที่จะรันให้ดูก่อน แล้วค่อยส่งต่อไปยังสคริปต์เดิมด้านล่าง
ให้เอง ไม่ได้เขียนตรรกะเก็บข้อมูลใหม่ ดู `README.md`'s "Quick start" และ
`docs/run/<board>.md` เอกสารนี้ (คู่มือรันมือฉบับเต็ม) ยังใช้ได้เสมอสำหรับ flag
หรือกรณีที่ `pc/run.py` ยังไม่ครอบคลุม (เช่น Phase 3's `--bauds`)

---

## 0. ก่อนรันทุกครั้ง (before every run)

- [ ] `git status` สะอาด หรืออย่างน้อยรู้ว่าอะไร dirty อยู่ — `pc/shared/telemetry.py`
      บันทึก commit hash + dirty flag ต่อ session อยู่แล้ว แต่ tree สะอาดตัดปัญหาได้ตั้งแต่ต้น
- [ ] `git describe --tags` ตรงกับที่ตั้งใจ (เช่น `pre-run-schema-v2` หรือ `pre-run-uno-v1`
      ถ้าใช้ฟีเจอร์ `--la`) — จดค่านี้ไว้คู่กับผลข้อมูลเสมอ
- [ ] พอร์ตของบอร์ด: เช็คด้วย `pio device list` หรือ `ls /dev/cu.*` **ก่อน** เสียบบอร์ด
      แล้วเสียบแล้วเช็คอีกครั้งว่ามี entry ใหม่แค่อันเดียว — Uno คือ
      `/dev/cu.usbmodem*`, ESP8266/ESP32 คือ `/dev/cu.usbserial*` /
      `/dev/cu.wchusbserial*` / `/dev/cu.SLAB_USBtoUART*` (พอร์ตของ Uno เปลี่ยนเลขได้
      กลางทาง เช่น `usbmodem101` → `usbmodem1101` — สคริปต์ทุกตัวมี `find_uno_port()`
      รองรับเรื่องนี้อัตโนมัติ ไม่ต้องแก้คำสั่งเอง)
- [ ] เปิดกัน sleep: `caffeinate -s` รันอยู่เป็น process แยก (หรือรันคำสั่งทั้งหมดภายใต้
      `caffeinate -s -- <command>`) — เช็คด้วย
      `pmset -g assertions | grep PreventUserIdleSystemSleep` ก่อนเริ่ม session
      ยาว (Session B/C) เพราะกลางคันแล็ปท็อปหลับจะทำให้ session พังทั้งก้อน
- [ ] ถ้าจะใช้ Logic Analyzer: **ต่อสายหลัง** ตรวจ log level ให้ตรง (Uno = 5V, ESP8266/ESP32
      = 3.3V) และต่อ GND ร่วมกับบอร์ดเสมอ — ดู § "รันแบบมี/ไม่มี Logic Analyzer" ด้านล่าง
- [ ] เช็ค `data/raw/phase2/` และ `data/raw/phase3/` ว่ามีอะไรอยู่ก่อนหรือยัง ถ้าเป็นการรัน
      ครั้งแรกจริง ๆ ควรว่างเปล่าหรือไม่มีโฟลเดอร์

## ห้ามทำ (never do this)

- **ห้าม** รันสอง sweep พร้อมกันบนพอร์ต/บอร์ดเดียวกัน — ตรรกะ resume สมมติว่ามีคนเขียนไฟล์
  ผลลัพธ์คนเดียวในเวลาเดียวกันเท่านั้น
- **ห้าม** แก้ไฟล์ `data/raw/**/*.csv` ด้วยมือเพื่อ "แก้" ค่าใด ๆ — สคริปต์อ่านไฟล์เหล่านี้
  เพื่อตัดสินใจว่าจุดไหน "เสร็จแล้ว" การแก้มือทำให้ resume พังแบบเงียบ ๆ
- **ห้าม** เปลี่ยนเฟิร์มแวร์ (`firmware/`) กลางรอบเก็บข้อมูล — ทุกจุดต้องมาจากซอร์สเดียวกัน
  (ตรวจได้จาก `firmware_source_hash` ใน environment JSON ต่อ session) ถ้าจำเป็นต้องเปลี่ยน
  ต้องขึ้น `SCHEMA_VERSION`/tag ใหม่ และห้ามเทข้อมูลก่อน-หลังการเปลี่ยนรวมกัน
- **ห้าม** ใช้ `--fresh` "เผื่อ ๆ" — มันย้าย (ไม่ลบ) ไฟล์ผลลัพธ์เดิมไปเป็น
  `*.pre-fresh-<timestamp>.csv` แล้วเริ่มนับใหม่ทั้งหมด ใช้เฉพาะตอนตั้งใจทิ้ง pilot/ผลลัพธ์
  ทั้งชุดจริง ๆ
- **ห้าม** เปิด `pio device monitor` ค้างไว้แล้วลืมปิดก่อนรัน sweep — sweep เปิด serial port
  เองไม่ได้ถ้ามีโปรแกรมอื่นถือพอร์ตอยู่
- **ห้าม** เชื่อมต่อ Logic Analyzer แบบ 3.3V-only เข้ากับพิน timing ของ Uno (5V logic) โดย
  ไม่เช็ค datasheet ก่อน — เสี่ยงพัง LA (ดู § LA ด้านล่าง)

---

## รูปแบบคำสั่งทั่วไป

Phase 2 (บนบอร์ดโดยตรง — ไม่มี PC-side simulation):
```bash
.venv/bin/python pc/phase2_sweep/<board>_sweep.py --port <PORT> \
    --circuits <circuit ...> --n-start <N1> --n-max <N2> [flags]
```
Phase 3 (offload — MCU รับผลจาก PC-side Qiskit Aer ผ่าน serial):
```bash
.venv/bin/python pc/phase3_offload/sweep.py --board <uno|esp8266|esp32> --port <PORT> \
    --circuits <circuit ...> --n-start <N1> --n-max <N2> [flags]
```
`<board>_sweep.py` คือ `uno_sweep.py` / `esp8266_sweep.py` / `esp32_sweep.py`
(ไฟล์คนละไฟล์ต่อบอร์ดสำหรับ Phase 2; Phase 3 เป็นสคริปต์เดียวรับ `--board` เลือกเอง)

**ชื่อวงจร (`--circuits`, ตรง `pc/shared/circuit_ids.py`):**
`h_all`, `bell_ghz`, `qft`, `grover`, `qpe`, `steane_encode`
(`steane_encode` คงที่ที่ n=7 เสมอ ไม่สนใจ `--n-start`/`--n-max` นอกจากเช็คว่า 7 อยู่ในช่วง
ที่ขอหรือไม่ — ถ้าไม่อยู่ วงจรนี้จะถูกข้ามไปเฉย ๆ ไม่ error)

**ทุก flag ที่มีจริง (Phase 2, ทั้งสามบอร์ด):**

| Flag | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `--port` (บังคับ) | path ของ serial port เช่น `/dev/cu.usbmodem1101` | — |
| `--circuits` | รายชื่อวงจร คั่นด้วยช่องว่าง | ทั้ง 6 วงจร |
| `--n-start` | n เริ่มต้น | 2 |
| `--n-max` | n สูงสุด | 14 |
| `--force-infeasible` | ดันทุรังรันจุดที่ timing model บอกว่าเกินเพดานเวลา (ปกติข้ามอัตโนมัติ) | ปิด |
| `--build-timeout` | วินาทีสูงสุดต่อการเรียก `pio run` หนึ่งครั้ง (compile/upload แยกกัน) | 300s |
| `--wdt-threshold-s` | ถ้า per-rep ที่ประเมินไว้เกินนี้ บอร์ดเงียบจะถูกบันทึกเป็น `watchdog_suspected` ไม่ใช่กำแพงจริง | ตาม `timing_model.WDT_PER_REP_THRESHOLD_S` (esp8266=6s, esp32=5s, uno=ไม่มี) |
| `--fresh` / `--no-resume` | ไม่ resume — ย้ายผลลัพธ์เดิมไปเป็น `*.pre-fresh-<ts>.csv` แล้วเริ่มใหม่ | ปิด (resume เป็นค่าเริ่มต้น) |
| `--la` (**เฉพาะ `uno_sweep.py` เท่านั้น**) | เปิด Logic Analyzer capture ผ่าน sigrok-cli ต่อจุด (UNVERIFIED, ดู § LA) | ปิด |

**Flag เพิ่มเติมเฉพาะ Phase 3 (`pc/phase3_offload/sweep.py`):**

| Flag | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `--board` (บังคับ) | `uno` / `esp8266` / `esp32` | — |
| `--bauds` | baud rate ที่จะทดสอบ (รับได้หลายค่า) | `[115200]` — ค่าสูงกว่านี้ (เช่น 250000) **UNVERIFIED**, ไม่เคยทดสอบกับฮาร์ดแวร์จริง |
| `--n-max` (ไม่ระบุ) | ถ้าไม่ใส่ จะไล่ n ขึ้นเรื่อย ๆ จนกว่าจะ error จริง (เพดานปลอดภัยสุด n=22 กัน PC หน่วยความจำพัง) | ไม่จำกัด (จนถึง n=22) |

---

## Uno R3

`GPIO_TIMING_PIN = D7` (`firmware/uno/src/main.cpp:27`), logic 5V, UART0 บน D0/D1
(**ห้ามต่อ LA ที่ D0/D1**)

### Phase 2

**Session A (cheap circuits) — ประมาณ 10.9 นาที** (29 จุด: device ~1.3 นาที + reflash
~9.7 นาที ที่สมมติฐาน 20s/จุด — ยังไม่ใช่ค่าที่วัดจริงทุกจุด)
```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodem1101 \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 8
```

**Session B (grover) — ประมาณ 43.3 นาที** (6 จุดรัน, n=8 ถูกข้ามเพราะ
compute-infeasible — ไม่ใช่บั๊ก)
```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodem1101 \
    --circuits grover --n-start 2 --n-max 8
```

**รันแค่ 1 วงจรที่ n เดียว** (เช่น `h_all` ที่ n=2 — จุดที่สั้นที่สุดของทั้งโครงการ ใช้เป็น
pilot point):
```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodem1101 \
    --circuits h_all --n-start 2 --n-max 2
```

**ทุกวงจรบน Uno ในคำสั่งเดียว** (n-start/n-max ครอบคลุมทุกวงจรรวม grover — ระวัง grover
n=8 ที่จะถูกข้ามอัตโนมัติเพราะ compute-infeasible, ปกติแยก Session A/B ตามข้างบนดีกว่า
เพราะ grover ยาวกว่าวงจรอื่นมาก):
```bash
.venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodem1101 \
    --circuits h_all bell_ghz qft grover qpe steane_encode --n-start 2 --n-max 8
```

**Output:** `data/raw/phase2/uno/<circuit>/no_la/raw.csv` (ทุก rep ดิบ, ต่อวงจร),
`data/raw/phase2/uno/<circuit>/no_la/memory_wall.csv` (สรุป 1 แถวต่อจุด),
`data/raw/phase2/uno/<circuit>/no_la/points.csv` / `sessions.csv` / `env/*.json`
(schema เดียวกันทุกบอร์ด/phase, ดู § "ตรวจผลลัพธ์" ด้านล่าง — แยกเป็นหนึ่ง
โฟลเดอร์ต่อ (phase, board, circuit) ตั้งแต่ `pre-run-uno-v4`/`v5`, ดู
`pc/shared/paths.py`) — `no_la/` เพราะคำสั่งด้านบนไม่มี `--la`; ถ้าใส่ `--la`
และ sigrok-cli เจออุปกรณ์จริง ผลจะไปอยู่ `with_la/` แทน (ดู § "มี LA" ด้านล่าง
และ `pc/shared/paths.py`'s no_la/with_la split, 2026-09-22) — **ห้ามผสม
ข้อมูลสองชุดนี้ในการวิเคราะห์เดียวกัน**: `no_la/` วัดแค่เวลา `micros()`,
`with_la/` มี Logic Analyzer cross-check ด้วย เป็นคนละการวัดกัน

### Phase 3 (offload)

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodem1101 \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 8
```
**ประมาณ 12 นาที** (cheap circuits) หรือ
```bash
.venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodem1101 \
    --circuits grover --n-start 2 --n-max 10
```
**ประมาณ 1.5 ชั่วโมง** (grover n=2..10 เต็ม ไม่ใช่แค่จุด n=10 — n=10 เพียงจุดเดียวกิน
~1.1h เพราะ PC-side Aer simulation ไม่ cache; n=12 ถูกข้ามอัตโนมัติเพราะ
`skipped_sim_cost_infeasible`)

**Output:** `data/raw/phase3/uno/<circuit>/no_la/raw.csv`,
`data/raw/phase3/uno/<circuit>/no_la/session_log.csv` (Phase 3's terminal-record
file — คนละชื่อจาก Phase 2's `memory_wall.csv`, ดู
`pc/shared/paths.session_log_csv_path`) — Phase 3 ไม่รองรับ `--la` เลย
(ไม่มี flag นี้ใน `pc/phase3_offload/sweep.py`) จึงอยู่ `no_la/` เสมอ

---

## NodeMCU ESP8266

`GPIO_TIMING_PIN = GPIO5` (= สัญลักษณ์ `D1` บนบอร์ด, `firmware/esp8266/src/main.cpp`),
logic 3.3V, UART0 บน GPIO1/GPIO3 (**ห้ามต่อ LA ที่นั่น**) — **ไม่รองรับ `--la`** (ฟีเจอร์นี้
implement เฉพาะ Uno เท่านั้นในตอนนี้)

### Phase 2

**Session A (cheap circuits) — ประมาณ 32.3 นาที**
```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 13
```

**Session B (grover) — ประมาณ 4.2 ชั่วโมง — session เดี่ยวยาวสุดในทั้งโครงการ**
(n=9 คนเดียวกิน ~3.6h; n≥10 ถูกข้ามอัตโนมัติเพราะ n=10 คำนวณแล้วใช้เวลา ~1.3 วัน)
**วางแผนรันตอนกลางคืนหรือวันที่ไม่ต้องแตะ Uno/ESP32:**
```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 13
```

**1 วงจร 1 n:**
```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits qft --n-start 6 --n-max 6
```

**⚠ ข้อควรระวังเฉพาะ ESP8266 (ยัง UNVERIFIED-needs-hardware, ดู `docs/preflight_report.md`
finding H1):** grover ที่ n=8/n=9 คำนวณไว้ว่าอาจชน hardware watchdog (~8 วินาที) ก่อนจบ 1
rep เพราะ per-rep คาดไว้ 15.6s (n=8) / 130.5s (n=9) — ถ้าบอร์ดเงียบแล้วเจอ
`watchdog_suspected` ใน `data/raw/phase2/esp8266/grover/no_la/memory_wall.csv`
**อย่าตีความเป็น Memory Wall จริง**
(ระบบแยกสถานะนี้ไว้ให้แล้วตั้งแต่ SCHEMA_VERSION 2) — แนะนำรัน grover n=8 เดี่ยว ๆ ก่อน
ทั้ง session B จริง เพื่อดูผลก่อนลงทุนเวลา 4 ชั่วโมง:
```bash
.venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 8 --n-max 8
```

### Phase 3

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 13
```
**ประมาณ 29 นาที** (cheap) หรือ
```bash
.venv/bin/python pc/phase3_offload/sweep.py --board esp8266 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
```
**ประมาณ 1.5 ชั่วโมง**

---

## ESP32 DevKit V1

`GPIO_TIMING_PIN = GPIO4` (`firmware/esp32/src/main.cpp`), logic 3.3V, UART0 บน
GPIO1/GPIO3 — **ไม่รองรับ `--la`** เช่นกัน

### Phase 2

**Session A (cheap circuits) — ประมาณ 27.2 นาที** (device time เร็วมาก <1 นาที, เกือบ
ทั้งหมดคือเวลา reflash)
```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 14
```

**Session B (grover) — ประมาณ 2.0 ชั่วโมง** (9 จุดรัน, 4 ข้ามเพราะ infeasible — จุดหนัก
สุดคือ n=10 ที่ ~1.7 ชั่วโมงเดียว **อย่าขัดจังหวะกลางจุดนี้ถ้าไม่จำเป็น** — resume จะรันจุด
นั้นใหม่ทั้งหมด ไม่ต่อจากที่ค้าง):
```bash
.venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 14
```

### Phase 3

```bash
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits h_all bell_ghz qft qpe steane_encode --n-start 2 --n-max 14
```
**ประมาณ 31 นาที** (cheap) หรือ
```bash
.venv/bin/python pc/phase3_offload/sweep.py --board esp32 --port /dev/cu.usbserialXXXX \
    --circuits grover --n-start 2 --n-max 10
```
**ประมาณ 1.5 ชั่วโมง**

---

## ลำดับ Session แนะนำ (จาก `run_checklist.md`)

1. **Session A ทั้งสามบอร์ด** ก่อน (เร็ว, ธนาคารวงจรง่าย 5/6 ไว้ก่อนแตะวงจรหนัก)
2. **Session B ทีละบอร์ด แยกกัน** ลำดับ **Uno (~43 นาที) → ESP32 (~2.0h) → ESP8266
   (~4.2h)** — ถ้าเวลาไม่พอกลางทาง ลำดับนี้การันตี dataset สมบูรณ์มากที่สุดต่อเวลาที่เสียไป
   (เหตุผลเต็มดู `run_checklist.md` § "Grover run order")
3. **Session C (Phase 3)** แยกตามวงจร cheap ก่อน แล้วค่อย grover ทีละบอร์ด (capped n≤10)

**ตารางเวลารวม** (จาก `run_checklist.md` § Total budget, คำนวณโดย
`timing_model.session_total_s()`):

| Session | Device | Reflash | รวม |
|---|---|---|---|
| A: Uno cheap | 1.3 นาที | 9.7 นาที | 10.9 นาที |
| A: ESP8266 cheap | 7.8 นาที | 24.5 นาที | 32.3 นาที |
| A: ESP32 cheap | 41.9 วินาที | 26.5 นาที | 27.2 นาที |
| B: Uno grover | 41.3 นาที | 2.0 นาที | 43.3 นาที |
| B: ESP32 grover | 1.9 ชม. | 4.5 นาที | 2.0 ชม. |
| B: ESP8266 grover | 4.1 ชม. | 4.0 นาที | 4.2 ชม. |
| C: Uno cheap | 2.4 นาที | 9.7 นาที | 12.1 นาที |
| C: ESP8266 cheap | 4.2 นาที | 24.5 นาที | 28.7 นาที |
| C: ESP32 cheap | 4.5 นาที | 26.5 นาที | 31.0 นาที |
| C: Uno/ESP8266/ESP32 grover (n≤10) | ~1.5 ชม. ต่อบอร์ด | 3.0-4.5 นาที | ~1.5 ชม. ต่อบอร์ด |
| **Phase 2 รวม (A+B)** | | | **8.1 ชม.** |
| **Phase 3 รวม (C)** | | | **5.8 ชม.** |
| **รวมทั้งหมด** | | | **13.9 ชม.** |

**⚠ ตัวเลข reflash (compile+upload) ในตารางนี้ยังเป็นค่าประมาณจาก
`REFLASH_COST_S = {uno: 20, esp8266: 30, esp32: 30}` วินาที ยังไม่ได้วัดจริงครบทุกบอร์ด**
(pilot point แรกที่วัดได้จริงบน Uno คือ compile ~4.6s + upload ~5.7s ครั้งแรกที่ cache
ยังไม่ warm — ต่ำกว่าสมมติฐาน 20s พอสมควร แต่ยังไม่ยืนยันสำหรับ ESP8266/ESP32 — ดู
`docs/preflight_report.md` finding H4 และรายงานการรัน hardware ครั้งแรก)

---

## ตรวจผลลัพธ์หลังรัน (how to check after a run)

**ทุกไฟล์ด้านล่างอยู่ใต้โฟลเดอร์เดียวกัน — หนึ่งโฟลเดอร์ต่อหนึ่ง (phase, board,
circuit, no_la/with_la):** `data/raw/phase<N>/<board>/<circuit>/{no_la,with_la}/`
(ดู `pc/shared/paths.py`, เปลี่ยนจาก path แบบเดิม `data/raw/phaseN/<board>_*.csv`
ตั้งแต่ `pre-run-uno-v4`/`v5`; ชั้น `no_la`/`with_la` เพิ่มเข้ามา 2026-09-22 —
ไม่ใส่ `--la` = `no_la/` เสมอ)

**ไฟล์ที่ต้องมีหลังทุกจุดสำเร็จ (ในโฟลเดอร์ข้างต้น):**
- `raw.csv` — 1 แถวต่อ 1 rep, ต้องมี **100 แถวพอดี** ต่อ `n` ที่ status=ok
- `memory_wall.csv` (Phase 2) หรือ `session_log.csv` (Phase 3) — 1 แถวสรุปต่อจุด
- `points.csv` — 1 แถวต่อ attempt (retry แยกแถว)
- `sessions.csv` — 1 แถวต่อการรันสคริปต์ 1 ครั้ง
- `env/<session_id>.json` — metadata ต่อ session (toolchain version,
  `firmware_source_hash`, `sleep_prevention`, ฯลฯ)

**แถวที่ดี (good row) ใน `points.csv`:** `schema_version=2`, `status=ok`,
`failure_type=none`, `build_compile_s`/`upload_s`/`device_exec_s` มีค่าเป็นตัวเลขบวก
ที่สมเหตุสมผล (ดูเทียบกับ `analysis/timing_report.py`)

**แถวที่ต้องสงสัย (bad row):**
- `status=failed` กับ `failure_type=hang` หรือ `watchdog_suspected` — บอร์ดไม่ตอบสนอง
  ภายใน budget (ดูคอลัมน์ `failure_message` ประกอบ, มักมี `reset_count=N` บอกว่าบอร์ด
  reset ระหว่างทางกี่ครั้ง)
- `status=failed` กับ `failure_type=build` หรือ `build_timeout` — ปัญหา toolchain/host
  ไม่ใช่ปัญหาบอร์ด (`build_timeout` จะ retry อัตโนมัติ 1 ครั้งใน budget ≤600s)
- จำนวนแถวใน `raw.csv` ของจุดนั้นไม่ครบ 100 — ข้อมูลไม่สมบูรณ์ ห้ามใช้
- `ratio_actual_over_estimated` ใน `sessions.csv` ต่างจาก 1 เกิน ~2 เท่า — ควรตรวจสอบว่า
  โมเดล/บอร์ด/build flags ตรงกับที่คาดไว้จริงหรือไม่ (ไม่ใช่ "แก้" ตัวเลขโมเดลทันที)

**สรุปเป็นภาพรวมด้วย:**
```bash
.venv/bin/python analysis/timing_report.py     # actual vs estimated ต่อ session, reflash cost จริง
.venv/bin/python analysis/phase2_summarize.py  # median/IQR ต่อ (board,circuit,n) -> data/processed/phase2/summary.csv
.venv/bin/python analysis/phase3_summarize.py  # เทียบเท่ากันฝั่ง Phase 3
```
(ทั้งสองตัวนี้ไม่รับ flag ใด ๆ — อ่านจาก `data/raw/**` ทั้งหมดที่มีอยู่จริงเสมอ ไม่ overwrite
`data/raw/`)

---

## Resume ทำงานอย่างไร และหยุด/รันต่ออย่างปลอดภัย

**Resume เปิดเป็นค่าเริ่มต้นเสมอ** ไม่ต้องใส่ flag อะไร — วิธีหยุดและรันต่อที่ปลอดภัยที่สุด
คือ **กด Ctrl+C แล้วรันคำสั่งเดิมซ้ำทุกตัวอักษร**:
- จุดที่มีแถว terminal ใน `memory_wall.csv` (หรือ `session_log.csv` ฝั่ง Phase 3)
  ของ `(board, circuit)` นั้นแล้ว — resume ข้ามทันที ไม่แตะฮาร์ดแวร์ซ้ำ ไม่ว่าผลจะเป็น
  ok หรือ wall จริงก็ตาม
- จุดที่ตายกลางทาง (มีแถวใน `raw.csv` แต่ไม่มีแถว terminal คู่กัน — orphan) จะถูก
  **กวาดทิ้งอัตโนมัติแล้วรันจุดนั้นใหม่ทั้งหมดตั้งแต่ rep 0** — ห้ามคาดหวังว่าจะ "ต่อ" จาก
  rep ที่ค้างไว้ เพราะ trial จาก 2 sessions ไม่ใช่ตัวอย่างเดียวกัน (บอร์ด/อุณหภูมิ/reflash
  ต่างกัน)
- วงจรที่เคยเจอกำแพงจริงแล้ว (`build_or_upload_fail`, หรือ hang/watchdog หลัง retry
  ครบแล้ว) — resume จะข้าม n ที่สูงกว่านั้นทั้งหมดของวงจรนั้นในบอร์ดนั้นทันที แม้ n เหล่านั้น
  ไม่เคยมี record มาก่อน (`status=skipped_known_wall`)
- **อย่ากด Ctrl+C กลางจุดที่แพงที่สุด** (เช่น ESP8266 grover n=9 ~3.6h, ESP32 grover
  n=10 ~1.7h) ถ้าไม่จำเป็นจริง ๆ — resume จะเสียเวลาจุดนั้นใหม่ทั้งหมด ไม่ใช่แค่ที่เหลือ

---

## รันแบบมี/ไม่มี Logic Analyzer

**ไม่มี LA (ค่าเริ่มต้นของทุกคำสั่งข้างบน):** ไม่ต้องทำอะไรเพิ่ม พฤติกรรมเดิมทุกประการ
ผลลัพธ์อยู่ `no_la/` เสมอ

**มี LA (เฉพาะ Uno เท่านั้น ผ่าน flag `--la`):** ผลลัพธ์อยู่ `with_la/` แทน — **แต่เฉพาะ
จุดที่ sigrok-cli เจออุปกรณ์จริงเท่านั้น** ถ้าใส่ `--la` แต่ sigrok-cli หาไม่เจอ/ไม่มี
อุปกรณ์ จุดนั้นยังคงถูกบันทึกลง `no_la/` เหมือนเดิม (ดู `la_active` ใน
`pc/phase2_sweep/uno_sweep.py`) เพราะไม่มี capture เกิดขึ้นจริง — **ห้ามรวม `no_la/`
กับ `with_la/` เข้าด้วยกันตอนวิเคราะห์** สองชุดนี้วัดคนละอย่าง (timing เฉยๆ vs
timing + LA cross-check)

⚠ **UNVERIFIED ทั้งหมด** — sigrok-cli integration นี้ไม่เคยรันกับฮาร์ดแวร์จริงหรือแม้แต่
`sigrok-cli`'s demo driver ในสภาพแวดล้อมที่เขียนโค้ดนี้ (ไม่มี `sigrok-cli` ติดตั้งเลย ณ ตอน
เขียน — เช็คด้วย `which sigrok-cli` ก่อนใช้งานจริงเสมอ)

1. ต่อสายตามที่ระบุใน `run_checklist.md` § "Logic Analyzer procedure": probe เข้า
   `GPIO_TIMING_PIN` (Uno = D7/pin 7), GND ร่วมกับบอร์ด, **เช็คว่า LA รับ 5V ได้ก่อนต่อ**
   (Uno เป็น 5V logic)
2. สร้าง capture plan ก่อนเสมอ (ครั้งเดียว ครอบคลุมทุกจุด ไม่ต้องรันซ้ำต่อจุด):
   ```bash
   .venv/bin/python analysis/la_capture_plan.py
   ```
   จะได้ `data/raw/phase2/<board>/<circuit>/with_la/la/capture_plan.csv` แยกไฟล์ต่อวงจร
   (ดู `pc/shared/paths.la_dir` — อยู่ใต้ `with_la/` เสมอ เพราะ capture มีอยู่ได้
   เฉพาะจุดที่รันด้วย `--la` เท่านั้น) — ถ้าไฟล์นี้ไม่มี `--la` จะข้าม capture ของจุดนั้น
   โดยอัตโนมัติ (บันทึกเหตุผลไว้ใน
   `data/raw/phase2/<board>/<circuit>/with_la/la/capture_issues.log`) ไม่ใช่ error, sweep
   ยังรันจนจบตามปกติ
3. เช็ค sigrok-cli พร้อมใช้งาน (สคริปต์เช็คให้อัตโนมัติเมื่อใส่ `--la` แต่เช็คมือได้เช่นกัน):
   ```bash
   which sigrok-cli && sigrok-cli --scan
   ```
   ถ้าไม่เจอ binary หรือไม่เจออุปกรณ์ — sweep จะพิมพ์ข้อความแล้ว **รันต่อโดยไม่ capture**
   (ไม่ crash, ไม่ใช่ความล้มเหลวของจุดข้อมูล)
4. รันด้วย `--la`:
   ```bash
   .venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodem1101 \
       --circuits h_all --n-start 2 --n-max 2 --la
   ```
5. **capture แรกจริง ๆ ต้องทำตาม "First real capture checklist" ใน `run_checklist.md`
   ทีละขั้นก่อนไปจุดอื่น** — ตรวจ
   `data/raw/phase2/uno/h_all/with_la/la/uno_h_all_n2.csv` ด้วย `analysis/la_pulses.py`
   ว่า `is_clean: True` และจำนวนพัลส์ตรง 100 ก่อนเชื่อผลลัพธ์จาก
   `analysis/la_crosscheck.py` (เขียนลง `la_crosscheck.csv` ในโฟลเดอร์ `with_la/la/`
   เดียวกัน — `--la-dir` เป็น flag บังคับของสคริปต์นั้น ไม่มีค่า default อีกต่อไป,
   `analysis/la_crosscheck.py` เอง join กับ `with_la/raw.csv` เสมอ ไม่ใช่ `no_la/`)

**สิ่งที่รับประกันได้จากโค้ด (ตรวจแล้วด้วย `pc/shared/la_capture_test.py`):**
- ปิด `--la` = ไม่มีการเรียก sigrok-cli หรือโค้ดใน `pc/shared/la_capture.py` เลยแม้แต่
  ครั้งเดียว
- capture มีปัญหา (sigrok error, pulse ไม่ครบ, ไฟล์ capture ว่าง) ถูกบันทึกลง
  `la/capture_issues.log` (ของ circuit นั้น) เท่านั้น **ไม่กระทบ** ข้อมูล `micros()`
  ที่บันทึกลง `raw.csv`/`memory_wall.csv`/`points.csv` — จุดข้อมูลนั้นยังนับว่า `ok`
  ตามปกติถ้าบอร์ดตอบสนองถูกต้อง ไม่ว่า LA จะจับสัญญาณได้หรือไม่ก็ตาม

**`GPIO_TIMING_PIN` ต่อบอร์ด (อ้างอิงถ้าจะต่อ LA กับบอร์ดอื่นในอนาคต แม้ `--la` ยังไม่รองรับ
ESP8266/ESP32):**

| บอร์ด | พิน | Logic level |
|---|---|---|
| Uno R3 | D7 (`firmware/uno/src/main.cpp:27`) | 5V |
| NodeMCU ESP8266 | GPIO5 = D1 บนบอร์ด | 3.3V |
| ESP32 DevKit V1 | GPIO4 | 3.3V |

---

## หมายเหตุปิดท้าย

- คำสั่งทั้งหมดในเอกสารนี้ (นอกจาก `--la` ซึ่งไม่เคยรันกับฮาร์ดแวร์จริงเลย — ดูคำเตือน
  UNVERIFIED ด้านบน) เป็นรูปแบบเดียวกับที่ `run_checklist.md` ใช้และได้รันจริงแล้วอย่างน้อย
  1 จุด (Uno, `h_all` n=2) ในการรันฮาร์ดแวร์ครั้งแรกของโครงการ
- ตัวเลขเวลาโดยประมาณทั้งหมดในเอกสารนี้เป็น **ค่าประมาณจากโมเดล ไม่ใช่ค่าที่วัดจริงครบทุก
  จุด** — โดยเฉพาะ reflash cost (compile+upload) ที่ยังอิงค่าคงที่ `REFLASH_COST_S` ไม่ใช่
  ค่าที่วัดจากบอร์ดจริงในทุกกรณี ดู `docs/preflight_report.md` และรายงานการรันฮาร์ดแวร์
  ครั้งแรกประกอบก่อนวางแผน session ยาว
