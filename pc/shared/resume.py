# resume.py — ตรรกะ resume กลางที่ทั้ง 4 สคริปต์ sweep (uno/esp32/esp8266 Phase 2,
# offload Phase 3) เรียกใช้ร่วมกัน แทนการก๊อปโค้ดเดียวกันซ้ำ 4 ที่
#
# ทำไมต้องมี resume: การรันเต็มรอบ REPS=100 ทั้ง 6 วงจรประเมินไว้ ~12.7 ชั่วโมงรวมทุก
# บอร์ด (ESP8266 คนเดียว ~4.7 ชั่วโมง จุดเดียวของ grover n=9 กิน 3.6 ชั่วโมง) ระหว่าง
# ทางยาวขนาดนี้ มีโอกาสสูงที่จะเจอเหตุการณ์แบบที่เคยเจอจริงมาแล้ว (พอร์ต USB-CDC ของ Uno
# ค้าง 16+ นาทีทั้งที่ตั้ง timeout ไว้แล้ว — ดู run_log.md) การ resume ที่ทำผิดจะทำให้
# ต้องรันทั้งบอร์ดใหม่ (เสียเวลาเป็นชั่วโมง) หรือแย่กว่านั้นคือ resume "ผิด" แบบเงียบ ๆ
# (นับซ้ำ n_trials=200 ใน phase2_summarize.py — ดู Part 2 ของ session นี้)
#
# หลักการ: ไฟล์ wall/memory_wall.csv (Phase 2) และ meta/session_log.csv (Phase 3) คือ
# "บันทึกการตัดสินชะตากรรม" ของแต่ละจุดข้อมูล — โค้ดเขียนแถวลงไฟล์นี้ก็ต่อเมื่อรู้ผล
# สุดท้ายของจุดนั้นแล้วเท่านั้น (ok, build_or_upload_fail, malloc_failed,
# runtime_hang_or_reset หลัง retry หมด, skipped_compute_infeasible, ฯลฯ) ดังนั้น:
#   - มีแถวอยู่ในไฟล์นี้ = จุดนั้น "เสร็จสิ้น" แล้วไม่ว่าผลจะเป็นอะไร -> resume ข้ามได้เลย
#   - ไม่มีแถว = ยังไม่เคยพยายาม หรือพยายามแล้วแต่โปรเซสตายก่อนบันทึกผล (ambiguous)
#     -> ต้องรันใหม่ตั้งแต่ต้น ไม่ใช่ topping up
#
# ไฟล์ raw (uno_raw.csv, esp32_raw.csv, esp8266_raw.csv, <board>_raw.csv ของ Phase 3)
# ควรมีแถวของจุดใดจุดหนึ่งก็ต่อเมื่อจุดนั้น "เสร็จสิ้น" แล้วเท่านั้น (โค้ดเขียน raw ก่อน
# แล้วค่อยเขียน terminal record ทันทีถัดไปพร้อม flush ทั้งคู่) แต่ถ้าโปรเซสตายพอดีระหว่าง
# สองการเขียนนี้ (เช่น เขียน raw บางส่วนแล้ว flush แต่ยังไม่ถึงบรรทัด terminal) จะเหลือ
# "แถวกำพร้า" (orphan rows) ในไฟล์ raw ที่ไม่มี terminal record คู่กัน — ต้องกวาดล้างก่อน
# รันใหม่ ไม่งั้นจุดนั้นจะมี trial ผสมจาก 2 sessions ปนกันในตัวอย่างเดียว (ห้ามเด็ดขาด
# ตามที่ตกลงไว้ — reset บอร์ด/reflash/อุณหภูมิเครื่องต่างกันระหว่าง session ทำให้ trial
# จาก 2 sessions ไม่ใช่ตัวอย่างที่ "สม่ำเสมอ" เดียวกันอีกต่อไป)

import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path


WALL_STATUS_PREFIXES = ("build_or_upload_fail", "malloc_failed", "runtime_hang_or_reset")


def is_wall_status(status: str) -> bool:
    """True ถ้า status นี้คือ "กำแพงจริง" (build/upload พัง, malloc คืน NULL, หรือ
    hang/reset หลัง retry หมด) — สถานะกลุ่มนี้เท่านั้นที่ทำให้ sweep เดิม (single-session)
    หยุดไล่ n ที่สูงกว่าของวงจรเดียวกันทันที (wall_found=True; break)

    "ok" และ "skipped_compute_infeasible" ไม่ใช่กำแพง — sweep เดิมไล่ n ต่อไปตามปกติ
    หลังเจอสองสถานะนี้ (infeasible เป็นแค่ข้ามจุดเดียว ไม่ได้แปลว่า n สูงกว่าจะพังเหมือนกัน
    เสมอไปในทางทฤษฎี แม้ในทางปฏิบัติมักจะเป็นเช่นนั้นก็ตาม — sweep เดิมไม่ได้สันนิษฐานแบบนั้น
    จึงยังลองต่อ ซึ่งจะโดนเช็ค infeasible ใหม่อีกทีแล้วข้ามอย่างเกือบไม่เสียเวลา)"""
    return any(status.startswith(p) for p in WALL_STATUS_PREFIXES)


def known_wall_n(completed: dict, circuit_index: int = 0, n_index: int = 1):
    """หา n ต่ำสุดที่เจอกำแพงจริงแล้วของแต่ละวงจร จาก completed (dict จาก
    load_terminal_points ที่ key เป็น tuple (circuit, n, ...))

    ใช้ตอน resume: ถ้า session ก่อนหน้าเจอกำแพงที่ n=8 แล้วถูกตัดก่อนจะลองต่อ n=9,10,...
    (ซึ่งไม่มี terminal record เพราะไม่เคยถูกลองเลย) resume ต้อง "รู้" ว่าไม่ต้องลอง n
    เหล่านั้นซ้ำ — ไม่งั้นจะย้อนกลับไปพยายาม flash บอร์ดที่รู้อยู่แล้วว่าจะพังอีกครั้ง"""
    out = {}
    for key, row in completed.items():
        if not is_wall_status(row.get("status", "")):
            continue
        circuit, n = key[circuit_index], key[n_index]
        if circuit not in out or n < out[circuit]:
            out[circuit] = n
    return out


def load_terminal_points(csv_path: Path, key_spec):
    """อ่านไฟล์ terminal-record (wall/memory_wall.csv หรือ meta/session_log.csv)
    คืน dict {key_tuple: row_dict} — key_tuple ตาม key_spec เช่น
    [("circuit", str), ("n", int)] หรือ [("circuit", str), ("n", int), ("baud_rate", int)]

    ถ้า key ซ้ำ (เช่นไฟล์เคยถูกรันซ้ำมาก่อนมี resume) แถวหลังสุดชนะ — สอดคล้องกับ
    ธรรมชาติของไฟล์ append-only ที่ถือว่าการเขียนครั้งหลังคือข้อมูลล่าสุด
    ไม่มีไฟล์ = คืน dict ว่าง (ยังไม่เคยรันอะไรมาก่อนเลย ไม่ใช่ error)"""
    if not csv_path.exists():
        return {}
    out = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                key = tuple(caster(row[col]) for col, caster in key_spec)
            except (KeyError, ValueError):
                continue  # แถวเสีย/คอลัมน์ขาด (ไฟล์เก่าก่อนมีคอลัมน์นี้) ข้ามอย่างปลอดภัย
            out[key] = row
    return out


def purge_orphan_rows(raw_path: Path, key_spec, valid_keys: set):
    """ลบแถวใน raw CSV ที่ key ของมันไม่อยู่ใน valid_keys (= จุดที่ยังไม่มี terminal
    record คู่กัน คือแถวกำพร้าจาก session ที่ถูกตัดกลางคัน) เขียนไฟล์ทับด้วยแถวที่เหลือ
    (คง header เดิม) คืน (kept_count, removed_count, removed_keys)

    ไม่มีไฟล์ หรือมีแต่ header ไม่มีข้อมูล = ไม่มีอะไรต้องกวาด คืน (0, 0, set())"""
    if not raw_path.exists():
        return 0, 0, set()
    with open(raw_path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return 0, 0, set()
    header, data_rows = rows[0], rows[1:]
    col_idx = {name: header.index(name) for name, _ in key_spec if name in header}
    if len(col_idx) != len(key_spec):
        # ไฟล์เก่าไม่มีคอลัมน์ที่ต้องใช้เป็น key (schema ก่อนหน้านี้) — ไม่กล้าเดา
        # ปล่อยผ่านทั้งหมดโดยไม่กวาด ดีกว่าลบข้อมูลที่ตีความผิด
        return len(data_rows), 0, set()

    kept, removed_keys = [], set()
    for row in data_rows:
        try:
            key = tuple(caster(row[col_idx[name]]) for name, caster in key_spec)
        except (IndexError, ValueError):
            kept.append(row)  # แถวเสีย/สั้นผิดปกติ ไม่ใช่กรณี orphan ที่ตั้งใจตรวจ ไม่แตะ
            continue
        if key in valid_keys:
            kept.append(row)
        else:
            removed_keys.add(key)

    if removed_keys:
        with open(raw_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(kept)

    return len(kept), len(data_rows) - len(kept), removed_keys


def archive_existing(*paths: Path):
    """--fresh: ย้ายไฟล์ผลลัพธ์เดิมไปเป็น <name>.pre-fresh-<timestamp><suffix> แทนการลบ
    ทิ้ง — ข้อมูลที่เก็บมาแล้วมีค่าเสมอ ต่อให้ผู้ใช้งานตั้งใจจะรันใหม่ทั้งหมดก็ตาม"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    moved = []
    for p in paths:
        if p.exists():
            dest = p.with_name(f"{p.stem}.pre-fresh-{ts}{p.suffix}")
            shutil.move(str(p), str(dest))
            moved.append((p, dest))
    return moved


def print_resume_summary(board_or_label: str, planned, completed: dict, remaining_seconds_human: str):
    """แถวสรุปก่อนเริ่มงานจริง: ทำไปแล้วกี่จุด เหลือกี่จุด เหลือเวลาประมาณเท่าไหร่

    completed = dict จาก load_terminal_points() (key_tuple -> row_dict ที่มีคอลัมน์
    "status") ต้องเรียกหลัง purge_orphan_rows เสมอ ให้ completed สะท้อนสถานะไฟล์ raw
    จริงหลังกวาดแถวกำพร้าแล้ว ไม่ใช่ก่อนกวาด — คืน list ของจุดที่ "เหลือต้องทำ" ตาม
    ลำดับใน planned (ผู้เรียกใช้ list นี้กรอง loop ต่อ)"""
    done = [p for p in planned if p in completed]
    remaining = [p for p in planned if p not in completed]
    print(f"\n--- resume summary ({board_or_label}) ---")
    print(f"already done: {len(done)}/{len(planned)} point(s)")
    for key in done:
        status = completed[key].get("status", "?")
        print(f"  skip {key}: already {status}")
    print(f"remaining: {len(remaining)}/{len(planned)} point(s), estimated {remaining_seconds_human}")
    print("---\n")
    return remaining
