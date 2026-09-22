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

`pc/run.py` เป็นแค่ตัวตรวจสอบ input + preflight check (git tree, พอร์ต,
กันเครื่องหลับ, สถานะ resume) แล้วส่งต่อไปยังสคริปต์เก็บข้อมูลจริง
(`pc/phase2_sweep/<board>_sweep.py` หรือ `pc/phase3_offload/sweep.py`) —
ตรรกะการเก็บข้อมูลทั้งหมดอยู่ในสคริปต์เดิม ไม่มีการเขียนซ้ำในนี้ ทุกคำสั่ง/flag
ในหน้านี้อ่านตรงจาก `pc/run.py --help` และซอร์สจริง ไม่ใช่เดาหรือก๊อปจากเอกสารเก่า

### ก. เตรียมพร้อมก่อนเริ่ม (ทุกครั้งที่เปิด terminal ใหม่)

```bash
# 1. เปิด venv — prompt จะขึ้นนำหน้าด้วย "(.venv)" นั่นคือหลักฐานว่าสำเร็จ
#    ถ้าไม่เห็น แปลว่า venv ยังไม่ active, python/pip จะไปใช้ตัวผิด
source .venv/bin/activate

# 2. กันเครื่องหลับตลอด session ในเทอร์มินัลแยกต่างหาก — คำสั่งนี้ "ไม่ return"
#    ขณะทำงาน นั่นคือปกติ ไม่ใช่ค้าง ปล่อยเทอร์มินัลนั้นทิ้งไว้เฉย ๆ กด Ctrl+C
#    ก็ต่อเมื่อเลิกใช้งานเครื่องแล้วจริง ๆ
caffeinate -dims

# 3. เช็คสถานะ repo ก่อนแตะฮาร์ดแวร์
git status
git describe --tags

# 4. หาพอร์ตของบอร์ด — ทำทุก session แม้เป็นบอร์ด/สาย USB ตัวเดิม เลขพอร์ต
#    เปลี่ยนได้ (เช่น usbmodem101 → usbmodem1101) หลัง reconnect/reflash/reboot
pio device list
```
`pio device list` โชว์ VID:PID ของอุปกรณ์ที่ต่ออยู่ — โครงการนี้ไม่เคยบันทึก
VID:PID ที่ยืนยันแล้วของบอร์ดจริงตัวเอง (ESP8266/ESP32 ยังไม่เคยรันกับ
ฮาร์ดแวร์จริง) ตารางด้านล่างเป็นค่า **ทั่วไปของตระกูลชิป ไม่ใช่ค่าที่ยืนยันแล้ว**:

| บอร์ด | รูปแบบชื่อพอร์ต (macOS) | ชิป USB ทั่วไป (ยังไม่ยืนยันกับบอร์ดจริงของโครงการนี้) |
|---|---|---|
| Uno R3 | `/dev/cu.usbmodemXXXX` | USB ในตัว (ATmega16U2) มักเป็น `2341:0043` หรือ `2341:0001` |
| ESP8266 (NodeMCU) | `/dev/cu.usbserial-XXXX`, `wchusbserial-XXXX`, หรือ `SLAB_USBtoUART` | CH340 (`1A86:7523`) หรือ CP2102 (`10C4:EA60`) แล้วแต่บอร์ด |
| ESP32 DevKit | รูปแบบเดียวกับ ESP8266 | ส่วนใหญ่ CP2102 (`10C4:EA60`) บางรุ่น CH340 |

**รัน `pio device list` ใหม่ทุกครั้งก่อนเก็บข้อมูลจริง แล้วใช้ค่าที่เห็นตอนนั้น
— ห้ามใช้ชื่อพอร์ตจาก session ก่อนหน้าหรือจากเอกสารนี้ซ้ำ**

### ข. ตาราง flag ทั้งหมด (จาก `pc/run.py --help`)

| Flag | บังคับ | หน้าที่ | ค่าเริ่มต้น | ใช้กับ |
|---|---|---|---|---|
| `--board {uno,esp8266,esp32}` | **ใช่** | เลือกบอร์ด | — | ทุกบอร์ด |
| `--algorithm {h_all,bell_ghz,qft,grover,qpe,steane_encode}` | **ใช่** | เลือกวงจร (ค่าเดียว ไม่ใช่ list) | — | ทุกบอร์ด |
| `--phase {2,3}` | **ใช่** | Phase 2 (บนบอร์ด) หรือ 3 (offload ไป PC) | — | ทุกบอร์ด |
| `--port PORT` | **ใช่** | เส้นทาง serial เช่น `/dev/cu.usbmodem1101` **ไม่เดาให้อัตโนมัติ** | — | ทุกบอร์ด |
| `--n-start N_START` | ไม่ | ค่า n เริ่มสวีป ส่งต่อตรง ๆ | ไม่ fresh: ค่า default ของสคริปต์เดิม (`2`); `--fresh`: n ต่ำสุดที่มีความหมายของวงจรนั้น | ทุกบอร์ด |
| `--n-max N_MAX` | ไม่ | เพดาน n ส่งต่อตรง ๆ | phase 2: uno `14`, esp8266 `16`, esp32 `18`; phase 3: `22` ทุกบอร์ด | ทุกบอร์ด |
| `--reps REPS` | ไม่ | **เช็คค่าเท่านั้น ไม่ส่งต่อ** ต้องเท่ากับ `100` (`timing_model.REPS`) ไม่งั้นถูกปฏิเสธ | — | ทุกบอร์ด |
| `--build-timeout BUILD_TIMEOUT` | ไม่ | วินาทีสูงสุดต่อการ compile/upload หนึ่งครั้ง | `300` | ทุกบอร์ด |
| `--upload-retry-settle-s UPLOAD_RETRY_SETTLE_S` | ไม่ | วินาทีรอก่อน retry เมื่ออัปโหลดล้มเหลว | `2.0` | **Uno Phase 2 เท่านั้น** — บอร์ด/phase อื่นถูกปฏิเสธ |
| `--la` | ไม่ | เปิด Logic Analyzer capture (`sigrok-cli`) | ปิด | **Uno Phase 2 เท่านั้น** — UNVERIFIED ไม่เคยรันกับ `sigrok-cli` จริง |
| `--fresh` | ไม่ | archive ข้อมูลเดิมของ (board, algorithm, phase, la) แล้วเริ่มที่ n ต่ำสุดที่มีความหมาย | ปิด | ทุกบอร์ด |
| `--dry-run` | ไม่ | ดูตัวอย่างเฉย ๆ ไม่แตะฮาร์ดแวร์/ไฟล์ใด ๆ เลย | ปิด | ทุกบอร์ด |
| `--yes` | ไม่ | ข้ามการถาม y/n ก่อนแตะฮาร์ดแวร์ | ปิด | ทุกบอร์ด |

ทุกครั้งที่รัน `pc/run.py` (dry-run, ถูกปฏิเสธ, รันจริง, ถูกขัดจังหวะ) จะถูก
บันทึกลง `data/run_history.jsonl` เสมอ — ดู § "เช็คผลหลังรัน" ด้านล่าง

### ค. ตัวอย่างจริงครบทุกบอร์ด × phase

แทน `/dev/cu.usbmodem1101` / `/dev/cu.usbserial-0001` / `/dev/cu.SLAB_USBtoUART`
ด้วยพอร์ตจริงที่เห็นจาก `pio device list` (ขั้นตอน ก.4) เสมอ — ตัวอย่างด้านล่าง
เป็นแค่ตัวอย่างประกอบ:

**Uno, Phase 2** (บอร์ดเดียวที่มีข้อมูลจริงในโครงการนี้ตอนนี้):
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --dry-run
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101
```

**Uno, Phase 3 — UNVERIFIED (ยังไม่เคยรัน Phase 3 กับฮาร์ดแวร์จริงเลย ทุกบอร์ด):**
```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 3 \
    --port /dev/cu.usbmodem1101 --dry-run
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 3 \
    --port /dev/cu.usbmodem1101
```

**ESP8266, Phase 2 — UNVERIFIED (บอร์ดนี้ยังไม่เคยรันกับฮาร์ดแวร์จริง):**
```bash
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 2 \
    --port /dev/cu.usbserial-0001 --dry-run
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 2 \
    --port /dev/cu.usbserial-0001
```

**ESP8266, Phase 3 — UNVERIFIED (ทั้งบอร์ดและ Phase 3):**
```bash
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 3 \
    --port /dev/cu.usbserial-0001 --dry-run
.venv/bin/python pc/run.py --board esp8266 --algorithm h_all --phase 3 \
    --port /dev/cu.usbserial-0001
```

**ESP32, Phase 2 — UNVERIFIED (บอร์ดนี้ยังไม่เคยรันกับฮาร์ดแวร์จริง):**
```bash
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 2 \
    --port /dev/cu.SLAB_USBtoUART --dry-run
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 2 \
    --port /dev/cu.SLAB_USBtoUART
```

**ESP32, Phase 3 — UNVERIFIED (ทั้งบอร์ดและ Phase 3):**
```bash
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 3 \
    --port /dev/cu.SLAB_USBtoUART --dry-run
.venv/bin/python pc/run.py --board esp32 --algorithm h_all --phase 3 \
    --port /dev/cu.SLAB_USBtoUART
```

รายละเอียดครบต่อบอร์ด (คำสั่ง, จำนวนจุดที่คาดไว้, เวลาประมาณ/วัดจริง, กำแพงที่
คาดไว้) อยู่ที่ `docs/run/uno.md`, `docs/run/esp8266.md`, `docs/run/esp32.md`,
`docs/run/phase3.md` — ฉบับเต็มภาษาอังกฤษ (`README.md`) มีตัวอย่างเอาต์พุตแบบ
เต็มของแต่ละคำสั่งด้วย

### ง. `--fresh`

```bash
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --fresh --dry-run   # ดูปลายทาง archive ก่อน
.venv/bin/python pc/run.py --board uno --algorithm h_all --phase 2 \
    --port /dev/cu.usbmodem1101 --fresh              # รันจริง
```
บรรทัด `archive: existing data (...) will be moved to <dest> ...` จาก dry-run
บอกปลายทางตรง ๆ (จะพิมพ์ซ้ำอีกครั้งตอนจบการรันจริงด้วย) ลบทิ้งได้ทุกเมื่อด้วย
`rm -r data/archive/phase<N>/<board>/<algorithm>/<timestamp>/` — ไม่กระทบ
pipeline เลย (พิสูจน์แล้วใน `pc/run_test.py`)

### จ. Resume และการขัดจังหวะ

**Ctrl+C** ทำให้ `pc/run.py` ดักจับ พิมพ์ข้อความว่า resume จะทำงานต่อได้เอง
บันทึก `event=interrupted` ลง `data/run_history.jsonl` แล้ว exit code `130`
**รันคำสั่งเดิมซ้ำเพื่อ resume** — ไม่ต้องเติม flag อะไรเพิ่ม สังเกตจากเอาต์พุต
ของสคริปต์เอง: บรรทัด `already done: N/M point(s)` ตามด้วย `skip (...): already
<status>` ต่อจุด แปลว่า resume เจอของเดิม; `already done: 0/M` แปลว่าเริ่มใหม่
ล้วน ๆ (`git status` ไม่ช่วยบอกตรงนี้ — สถานะ resume อยู่ใน
`data/raw/.../no_la/memory_wall.csv` ไม่ใช่ git)

### ฉ. เช็คผลหลังรัน

```bash
head -3 data/raw/phase2/uno/h_all/no_la/raw.csv
cat data/raw/phase2/uno/h_all/no_la/memory_wall.csv
tail -1 data/raw/phase2/uno/h_all/no_la/points.csv
.venv/bin/python pc/run_history.py --board uno --algorithm h_all --phase 2
```
(ใช้ `with_la/` แทน `no_la/` ถ้ารันด้วย `--la` และ sigrok-cli เจออุปกรณ์จริง)
สถานะที่ควรเห็นใน `memory_wall.csv`: แถว `ok` ติดกันที่ n ต่ำ ๆ แล้วจบด้วยแถว
เดียวที่เป็นกำแพงจริง (`build_overflow` หรือ ESP-only `malloc_failed`) หรือ
`runtime_hang_or_reset`/`watchdog_suspected` (ไม่ใช่กำแพง ต้องตรวจด้วยตา)
`pc/run_history.py --help` ดู filter ทั้งหมด (`--source`, `--since`/`--until`)

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
| เลขพอร์ตเปลี่ยนจาก session ก่อนหน้า (บอร์ดไหนก็ได้) | ปกติ — เลขพอร์ตไม่คงที่ข้าม session/reconnect | รัน `pio device list` ใหม่ (ขั้นตอน ก.4) แล้วใช้ค่าที่เห็นตอนนั้น ห้ามใช้ค่าจาก session ก่อนหน้าหรือจากเอกสารนี้ |
| `Operation not permitted` เปิดพอร์ตไม่ได้ (macOS) | ไม่มี Full Disk Access, TCC บล็อกการเข้าถึงโฟลเดอร์ repo เอง (เคยเกิดจริง 2 ครั้งช่วงต้นโครงการ — ดู `docs/preflight_report.md` finding M6 ซึ่งแก้แล้ว), หรือมีโปรแกรมอื่นถือพอร์ตอยู่ | ให้สิทธิ์ Full Disk Access กับ terminal, ปิด serial monitor ที่เปิดค้างไว้, หรือถ้าเป็นที่โฟลเดอร์ repo เอง ย้ายออกจาก `~/Documents`/`~/Desktop`/`~/Downloads` |
| เห็นคำเตือน `git: DIRTY (...)` ตอน preflight | มีการแก้ไขที่ยังไม่ commit | **ไม่ใช่การปฏิเสธ** ตามกติกาปัจจุบัน (2026-09-21) — รันต่อได้ปกติ commit hash และสถานะ dirty ถูกบันทึกอัตโนมัติทั้งใน environment JSON และ `data/run_history.jsonl` อยู่แล้ว |
| บอร์ดเงียบ ไม่มี `DONE`, ได้ `runtime_hang_or_reset` (ไม่มีหลักฐาน RAM) | อาจ hang จริง, สะดุดชั่วคราว, หรือ (น้อยมาก) เป็นกำแพงจริงที่ตรวจตอนคอมไพล์ไม่เจอ | **ไม่ถือเป็น Memory Wall อัตโนมัติ** ต้องตรวจด้วยตา — ดู `failure_message`/`reset_count` ใน `points.csv` |
| session ยาวดูเหมือนค้างหรือเครื่องหลับกลางทาง | ไม่ได้กันเครื่องหลับ | รัน `caffeinate -dims` ในเทอร์มินัลแยกก่อนเริ่ม |
| มีไฟล์ชื่อเดียวกับ flag โผล่มาแบบ untracked ในโฟลเดอร์ repo เช่น `--dry-run` (`git status` ขึ้น `?? --dry-run`) | ไม่ได้เกิดจากโค้ดโครงการนี้ (`--dry-run` เป็น `argparse` flag ปกติ ตรวจโค้ดแล้วไม่มีจุดไหน open() ไฟล์ชื่อนี้เลย) เกือบแน่นอนว่าเป็นอุบัติเหตุฝั่ง shell (redirect `>` หลุด หรือ copy-paste ผิด) | ลบได้อย่างปลอดภัย — ต้องใส่ `--` ก่อนชื่อไฟล์ ไม่งั้น `rm` จะตีความ `--dry-run` เป็น flag ของตัวเอง: `rm -- --dry-run` |

**ถ้ามีอะไรดูผิดปกติ หยุดแล้วถามก่อน** — resume summary ข้ามจุดมากกว่า/น้อยกว่า
ที่คาด, สถานะ failure ที่ไม่คุ้นเคย, หรือเอาต์พุตไม่ตรงกับที่เอกสารนี้บอกไว้
ให้หยุดก่อนรันคำสั่งถัดไปแล้วถาม — เหมือนที่ทำมาตลอดในโครงการนี้ การเดาแล้วรัน
ต่อเสี่ยงเสียเวลาฮาร์ดแวร์หลายชั่วโมงได้ข้อมูลที่แยกจากข้อมูลดีไม่ออกภายหลัง

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
