# ข้อมูลทั้งหมดที่ใช้ในโปสเตอร์

เอกสารนี้รวบรวมข้อความและกราฟทุกชิ้นที่ใส่ในโปสเตอร์ (Main.dc.html /
quantum_mcu_science_poster.pdf) ตามลำดับที่ปรากฏจริงบนโปสเตอร์ ที่มา:
proposal_advisor.pdf (ข้อเสนอโครงงานที่ยื่นจริง นอก repo นี้) และผลการทดลองใน
data/{raw,processed,figures}/phase1-4/ ของ repo นี้

---

## ส่วนหัว

ตราโรงเรียน: ยังไม่มีไฟล์ เว้นช่องวงกลมประไว้ ("ตราโรงเรียนบางละมุง วางไฟล์โลโก้")

ชื่อโครงงานภาษาไทย: การประเมินประสิทธิภาพเชิงเปรียบเทียบของระบบจำลองคอมพิวเตอร์ควอนตัม
ขนาดเล็ก บนสถาปัตยกรรมไมโครคอนโทรลเลอร์ที่หลากหลาย สำหรับการประมวลผลที่ขอบข่าย

ชื่อโครงงานภาษาอังกฤษ: Comparative Performance Benchmarking of Quantum
Micro-Simulators Across Diverse Microcontroller Architectures for Edge Computing

ผู้จัดทำโครงงาน: นายธีรศักดิ์ รักความสุข ชั้นมัธยมศึกษาปีที่ 6 โรงเรียนบางละมุง
จังหวัดชลบุรี

ครูที่ปรึกษาโครงงาน: ผู้ช่วยศาสตราจารย์ ดร.วัชรพัฐ เมตตานันท์ ภาควิชาวิศวกรรม
คอมพิวเตอร์ คณะวิศวกรรมศาสตร์ มหาวิทยาลัยเกษตรศาสตร์ วิทยาเขตศรีราชา (ยังไม่ยืนยัน
จากคุณ มาจาก proposal_advisor.pdf ในฐานะผู้เสนอ อาจมีครูที่โรงเรียนบางละมุงแยก
ต่างหาก)

---

## บทนำ (ที่มาและความสำคัญ)

ระบบ IoT กำลังเปลี่ยนจากการพึ่งพาคลาวด์ไปสู่การประมวลผลที่ขอบข่าย (Edge Computing)
เพื่อลด Latency แต่ไมโครคอนโทรลเลอร์แต่ละสถาปัตยกรรมมีข้อจำกัดด้านหน่วยความจำ
ต่างกัน การจำลองวงจรควอนตัมซึ่งต้องการหน่วยความจำเพิ่มแบบเอ็กซ์โพเนนเชียล
(2 ยกกำลัง n ตามจำนวน Qubit) จึงเหมาะเป็นภาระงานตัวแทนสำหรับศึกษาขีดจำกัด
ฮาร์ดแวร์ขอบข่าย งานวิจัยนี้พัฒนา C++ Quantum Circuit Micro-Simulator ขึ้นเอง
แล้วนำไปทดสอบบนไมโครคอนโทรลเลอร์ 3 สถาปัตยกรรมที่ต่างกัน เพื่อสร้างกรอบการ
ตัดสินใจว่าควรประมวลผลภายในเครื่อง (Local) หรือส่งไปประมวลผลภายนอก (Offload)
เมื่อใด

---

## วัตถุประสงค์

1. ออกแบบและพัฒนา C++ Quantum Circuit Micro-Simulator ที่ปรับให้เหมาะกับข้อจำกัด
SRAM ของ MCU พร้อมตรวจสอบความถูกต้องเทียบกับ Qiskit Aer ด้วย Infidelity (1−F)
และ Total Variation Distance (TVD)

2. ศึกษา Memory Wall เปรียบเทียบ Execution Latency ระหว่าง Local กับ Offload
และหา Crossover Point ที่การ Offload คุ้มค่ากว่า พร้อมวิเคราะห์ผลของสถาปัตยกรรม
ที่มีและไม่มี FPU

3. สังเคราะห์ผลทั้งหมดเป็น Decision Framework รูปแบบ Flowchart และสมการ สำหรับ
วิศวกรเลือกวิธีประมวลผลบนระบบ Edge Computing

---

## สมมติฐาน

1. Arduino Uno R3 (8-bit) จะถึง Memory Wall ที่จำนวน Qubit น้อยกว่า MCU 32-bit
และต่ำกว่าค่าทางทฤษฎี (2 ยกกำลัง n คูณ 8 Bytes) เนื่องจาก SRAM ต้องแบ่งให้ Stack
และตัวแปรอื่นด้วย

2. เนื่องจาก Uno ไม่มี FPU Crossover Point จะเกิดขึ้นเร็วในช่วง Qubit ที่บอร์ด
ยังรันได้ ตรงข้ามกับ ESP32 ที่มี FPU และ Clock สูงกว่า ซึ่ง Crossover Point จะ
เลื่อนออกไปใกล้ Memory Wall

3. วงจร QFT ซึ่งมีจำนวนเกทมากกว่าวงจรพื้นฐาน (Hadamard, Bell/GHZ) จะคุ้มค่ากับ
การ Offload เร็วที่สุดในทุกบอร์ด

---

## ตัวแปร

ตัวแปรต้น: สถาปัตยกรรม MCU (Uno / ESP8266 / ESP32), จำนวน Qubit, รูปแบบการ
ประมวลผล (Local / Offload)

ตัวแปรตาม: Execution Time และ End-to-End Latency (µs), Free Heap, ค่า
Infidelity (1−F) และ TVD

ตัวแปรควบคุม: ชนิดวงจร (Hadamard ทุกคิวบิต, Bell/GHZ state, QFT), Baud Rate
สูงสุดที่เสถียรของแต่ละบอร์ด, Compiler Optimization และเวอร์ชันเครื่องมือ

---

## วิธีทำการทดลอง

Phase 1 System Validation: เทียบ State Vector จาก C++ Simulator กับ Qiskit
Aer ด้วยลำดับเกทเดียวกันทุกประการ วัด Infidelity (1−F) และ TVD ที่ n เท่ากับ
2, 3, 4, 6, 8, 10, 12 เกณฑ์ผ่าน Infidelity ไม่เกิน 10 ยกกำลัง ลบ 3

Phase 2 Edge Benchmark: อัปโหลดและรันบน MCU ทั้ง 3 บอร์ด เพิ่มจำนวน Qubit
ทีละ 1 จนถึง Memory Wall บันทึก Execution Time ด้วย Logic Analyzer 24 MHz
และ Free Heap ซ้ำอย่างน้อย 30 รอบต่อจุดข้อมูล รายงานผลเป็น Median บวกลบ IQR

Phase 3 Offload Benchmark: ส่งคำขอผ่านโปรโตคอลเฟรม Serial USB ให้ PC จำลอง
วงจรด้วย Qiskit Aer สดใหม่ทุกครั้งแล้วส่งผลกลับ วัด End-to-End Latency ซ้ำ
30 รอบต่อจุดข้อมูล ที่ Baud Rate สูงสุดที่ระบบยังทำงานได้เสถียร

Phase 4 Decision Framework: สังเคราะห์ผลจาก Phase 2 และ 3 เป็น Flowchart
2 ขั้นตอน ตรวจ Memory Wall ก่อน แล้วเทียบ Crossover Point พร้อมสมการทำนาย
สำหรับบอร์ดที่ยังไม่ได้ทดสอบ

ฮาร์ดแวร์ที่ใช้: Arduino Uno R3, ESP8266 V2, ESP32 DevKit V1, Logic Analyzer
24 MHz 8CH, MacBook Pro M1

ซอฟต์แวร์ที่ใช้: PlatformIO, Qiskit Aer, PySerial, NumPy, Matplotlib

---

## ผลการทดลอง Phase 1 (System Validation)

วงจร h_all: Infidelity สูงสุด 2.43 คูณ 10 ยกกำลัง ลบ 7, TVD สูงสุด 1.22 คูณ
10 ยกกำลัง ลบ 7, ผ่านทุกกรณีจาก 7 ค่า n

วงจร bell_ghz: Infidelity สูงสุด 3.45 คูณ 10 ยกกำลัง ลบ 8, TVD สูงสุด 1.72
คูณ 10 ยกกำลัง ลบ 8, ผ่านทุกกรณีจาก 7 ค่า n

วงจร qft: Infidelity สูงสุด 2.43 คูณ 10 ยกกำลัง ลบ 7, TVD สูงสุด 1.22 คูณ
10 ยกกำลัง ลบ 7, ผ่านทุกกรณีจาก 7 ค่า n

ที่มาของตัวเลข: data/raw/phase1/infidelity_tvd.csv รวม 21 กรณี คือ 3 วงจร
คูณ 7 ค่า n

กราฟที่ใช้: infidelity.png ย่อขนาดจาก data/figures/phase1/fig_infidelity_vs_depth.png

คำอธิบายภาพที่ 1: Infidelity เทียบกับ Circuit Depth แกน y เป็น log scale
รวม 21 กรณีทดสอบครบ 3 วงจร คูณ 7 ค่า n ค่าคลาดเคลื่อนอยู่ระดับ 10 ยกกำลัง
ลบ 7 ถึง 10 ยกกำลัง ลบ 8 ต่ำกว่าเกณฑ์ผ่านคือ 10 ยกกำลัง ลบ 3 มากกว่า 4
อันดับของขนาด ยืนยันว่า C++ Simulator ที่พัฒนาขึ้นให้ผลตรงกับ Qiskit Aer

---

## ผลการทดลอง Phase 2 (Edge Benchmark และ Memory Wall)

Arduino Uno R3: n ทฤษฎีเท่ากับ 8, n วัดจริงเท่ากับ 7, ส่วนต่างลบ 1

NodeMCU ESP8266: n ทฤษฎีเท่ากับ 13, n วัดจริงเท่ากับ 12, ส่วนต่างลบ 1

ESP32 DevKit V1: n ทฤษฎีเท่ากับ 15, n วัดจริงเท่ากับ 13, ส่วนต่างลบ 2

ที่มาของตัวเลข: data/processed/phase2/memory_wall_summary.csv

กราฟที่ใช้: memwall.png ย่อขนาดจาก data/figures/phase2/memory_wall_comparison.png

คำอธิบายภาพที่ 2: Memory Wall คือ n สูงสุดตามทฤษฎีเทียบค่าที่วัดได้จริงของ
ทั้ง 3 บอร์ด ทุกบอร์ดวัดได้ต่ำกว่าทฤษฎีเพราะต้องกันพื้นที่ให้ Stack และ
Global Variables โดย ESP32 เสียมากที่สุดคือ 2 Qubit เนื่องจากมี WiFi และ
Bluetooth Stack พร้อมกัน ผลนี้สนับสนุนสมมติฐานข้อ 1

---

## ผลการทดลอง Phase 3 (Offload Benchmark และ Crossover Point)

ตัวเลขต่อไปนี้คือ Crossover Point คือค่า n ที่ Offload เริ่มเร็วกว่า Local

วงจร h_all: Uno เท่ากับ 5, ESP8266 เท่ากับ 8, ESP32 เท่ากับ 13

วงจร bell_ghz: Uno เท่ากับ 6, ESP8266 เท่ากับ 10, ESP32 เท่ากับ 13

วงจร qft: Uno เท่ากับ 4, ESP8266 เท่ากับ 7, ESP32 เท่ากับ 12

ที่มาของตัวเลข: data/processed/phase3/crossover_summary.csv

กราฟที่ใช้ แยกไฟล์ต่อบอร์ด ไม่ใช่กราฟรวม:

crossover_uno.png ย่อขนาดจาก data/figures/phase3/fig_phase3_uno_crossover.png

crossover_esp8266.png ย่อขนาดจาก data/figures/phase3/fig_phase3_esp8266_crossover.png

crossover_esp32.png ย่อขนาดจาก data/figures/phase3/fig_phase3_esp32_crossover.png

แต่ละภาพแสดง Local เส้นทึบ และ Offload เส้นประ ของทั้ง 3 วงจรในบอร์ดเดียว
วงกลมกลวงคือ Crossover Point ของวงจรนั้น

คำอธิบายภาพที่ 3: Local Execution Time เทียบ Offload End-to-End Latency
แยกกราฟต่อบอร์ด แต่ละกราฟแสดง 3 วงจร วงกลมกลวงคือ Crossover Point Offload
Latency เกือบคงที่ทุกบอร์ดอยู่ในช่วงประมาณ 1.6 ถึง 14 มิลลิวินาที เพราะ
เฟรมข้อมูลมีขนาดคงที่ 4 ถึง 6 bytes ทำให้ Crossover Point ขึ้นกับความเร็ว
คำนวณภายในเครื่องเป็นหลัก ผลนี้สนับสนุนสมมติฐานข้อ 2 และข้อ 3

---

## สรุปและอภิปรายผลการทดลอง

Offload Latency แทบคงที่ อยู่ในช่วงประมาณ 1.6 ถึง 14 มิลลิวินาที ไม่ขึ้นกับ
บอร์ด ไม่ขึ้นกับ Baud Rate หรือจำนวน Qubit เพราะเฟรมโปรโตคอลมีขนาดคงที่
4 ถึง 6 bytes ต้นทุนส่วนใหญ่จึงเป็น fixed overhead ของ PC OS และ Driver

Crossover Point แปรผกผันกับความเร็วคำนวณของบอร์ดและความซับซ้อนของวงจร
บอร์ดที่ไม่มี FPU คือ Uno คุ้มกับ Offload ตั้งแต่ Qubit ต่ำ ในขณะที่ ESP32
ที่มี FPU ต้องรอถึง Qubit สูงใกล้ Memory Wall จึงเริ่มคุ้ม วงจร QFT ที่มี
เกทมากที่สุด คุ้มกับ Offload เร็วที่สุดเสมอทุกบอร์ด

ทุกบอร์ดถึง Memory Wall ก่อนค่าทฤษฎี 1 ถึง 2 Qubit จากพื้นที่ที่ต้องกันไว้
ให้ Stack และ Network หรือ RTOS Stack ผลนี้ยืนยันสมมติฐานข้อ 1 ทั้ง 3 บอร์ด

ผลการทดลองสนับสนุนสมมติฐานทั้ง 3 ข้อที่ตั้งไว้ และนำไปสังเคราะห์เป็น
Decision Framework 2 ขั้นตอนที่ใช้กับบอร์ดอื่นที่ยังไม่ได้ทดสอบได้ โดยมี
สมการประมาณค่าดังนี้

สมการที่ 1 คือสมการ Memory Wall เขียนได้ว่า n_max เท่ากับ floor ของ log2
ของ B หารด้วย 8 โดย B คือ largest contiguous free block ที่วัดได้จริง
หากวัดไม่ได้ เช่นบอร์ดแบบ static allocation อย่าง Uno ให้ประมาณด้วย B
ประมาณเท่ากับ SRAM รวมหารด้วย 2

สมการที่ 2 คือสมการ Crossover Point เขียนได้ว่า n star ประมาณเท่ากับ
n star ของบอร์ดอ้างอิง บวกด้วย log2 ของ clock ใหม่หารด้วย clock อ้างอิง
บวกด้วยตัวปรับสถาปัตยกรรม โดยตัวปรับคือบวกเพิ่ม 1 คิวบิตเมื่อเปลี่ยนจาก
8-bit ไป 32-bit ที่ไม่มี FPU ทั้งคู่ และบวกเพิ่ม 2 ถึง 3 คิวบิตเมื่อเพิ่ม
FPU ฮาร์ดแวร์บนสถาปัตยกรรม 32-bit เดิม

รายละเอียดที่มาของสมการทั้งสองดูเพิ่มเติมได้ที่
report/phase4_equations_summary_th.md และ
report/phase4_equations_summary_th.pdf ใน repo

---

## รายการไฟล์ภาพในโฟลเดอร์นี้

infidelity.png มาจาก data/figures/phase1/fig_infidelity_vs_depth.png ย่อขนาด
ใช้เป็นภาพที่ 1

memwall.png มาจาก data/figures/phase2/memory_wall_comparison.png ย่อขนาด
ใช้เป็นภาพที่ 2

crossover_uno.png มาจาก data/figures/phase3/fig_phase3_uno_crossover.png
ย่อขนาด ใช้เป็นภาพที่ 3 แผงซ้าย

crossover_esp8266.png มาจาก data/figures/phase3/fig_phase3_esp8266_crossover.png
ย่อขนาด ใช้เป็นภาพที่ 3 แผงกลาง

crossover_esp32.png มาจาก data/figures/phase3/fig_phase3_esp32_crossover.png
ย่อขนาด ใช้เป็นภาพที่ 3 แผงขวา
