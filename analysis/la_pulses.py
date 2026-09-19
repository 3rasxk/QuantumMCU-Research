#!/usr/bin/env python3
# la_pulses.py — แปลงไฟล์ capture จาก Logic Analyzer (sigrok-cli / PulseView export)
# ของ 1 จุดข้อมูล (1 ไฟล์ = REPS พัลส์ = การ toggle GPIO_TIMING_PIN 1 รอบต่อ rep) ให้เป็น
# รายการความกว้างพัลส์ (microseconds) พร้อมตรวจจับความผิดปกติ
#
# บริบท: firmware/*/src/main.cpp ยก GPIO_TIMING_PIN ขึ้นตอนเริ่ม run_circuit() แล้วปล่อย
# ลงตอนจบ — ต่อ 1 rep ได้พัลส์ 1 ลูก ความกว้างพัลส์คือ "ความจริง" ที่จะเอาไปเทียบกับ
# exec_time_us ที่ MCU รายงานเอง (micros() ของ MCU เอง) — ดู analysis/la_crosscheck.py
#
# ยังไม่มีไฟล์ capture จริงให้ทดสอบ (รอ LA ยืมมา) โค้ดนี้จึงเขียนตามสเปกที่ทราบแน่ชัดของ
# รูปแบบไฟล์ทั้งสองแบบด้านล่าง ต้องตรวจสอบซ้ำกับไฟล์จริงก่อนใช้งานจริงครั้งแรก
#
# ---------------------------------------------------------------------------
# รูปแบบไฟล์ที่รองรับ (ตรวจจับอัตโนมัติจากเนื้อไฟล์ ไม่ต้องระบุ flag)
# ---------------------------------------------------------------------------
#
# FORMAT A — "sigrok-cli raw" (ค่าเริ่มต้นของ `sigrok-cli -O csv` ต่อ 1 channel):
#   บรรทัด comment ขึ้นต้นด้วย ';' ต้องมีบรรทัดรูปแบบ ";Rate: <Hz>" (ไม่สนตัวพิมพ์เล็ก/ใหญ่)
#   ตามด้วยข้อมูล "1 ตัวอย่างต่อ 1 บรรทัด" เป็น 0 หรือ 1 ล้วน ๆ (ไม่มี comma, ไม่มี timestamp)
#   ตัวอย่างเวลาของแต่ละแถวคือ index_แถว / Rate วินาที
#   ตัวอย่างไฟล์:
#     ;Rate: 24000000
#     ;Channels: D0
#     0
#     0
#     1
#     1
#     0
#   ข้อจำกัดที่ต้องรู้: รูปแบบนี้ dump "ทุกตัวอย่าง" ที่ sample rate เต็ม — สำหรับ capture
#   ยาว (เช่น grover ที่ point เดียวกินเวลาหลักนาที/ชั่วโมง) ไฟล์จะใหญ่มาก (24MHz x
#   หลายวินาที = สิบ ๆ ล้านบรรทัด) ดู run_checklist.md หัวข้อ "Logic Analyzer procedure"
#   เรื่องข้อจำกัดนี้ (ไม่ implement sub-sampling ในไฟล์นี้ตามที่ตกลง — บันทึกไว้เฉย ๆ)
#
# FORMAT B — "edges/changes" (PulseView export ตัวเลือก "Compression: Changes only"
#   หรือ sigrok-cli รุ่นที่รองรับ compress) — เก็บเฉพาะแถวที่ค่าเปลี่ยน ไม่ dump ทุกตัวอย่าง
#   จึงเล็กกว่ามากสำหรับ capture ยาว คอลัมน์แรกเป็น header จริง (ไม่ใช่ comment):
#     time,D0
#     0.000000000,0
#     0.001234500,1
#     0.001456700,0
#     ...
#   คอลัมน์แรกอาจเป็นวินาที (ตัวเลขทศนิยม, ใช้ตรง ๆ) หรือ sample index (จำนวนเต็ม, ต้องใช้
#   --sample-rate ประกอบแปลงเป็นวินาที) — ไฟล์นี้เดาจาก "มีจุดทศนิยมหรือไม่" ถ้าเดาผิดต้อง
#   ระบุ --sample-rate มาช่วย (ดู CLI ด้านล่าง)
#
# ทั้งสองแบบรองรับ "1 channel เท่านั้น" (GPIO_TIMING_PIN เดียว) — ไม่รองรับ multi-channel
# เพราะงานนี้ต้องการแค่ช่องเดียว ไม่มีเหตุผลให้ซับซ้อนเกินจำเป็น

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Pulse:
    index: int          # ลำดับพัลส์ที่ n (0-based) ตามลำดับเวลาที่พบใน capture
    start_s: float
    end_s: float

    @property
    def width_us(self) -> float:
        return (self.end_s - self.start_s) * 1e6


@dataclass
class ParseResult:
    pulses: list                # list[Pulse] — เฉพาะพัลส์ที่สมบูรณ์ (ไม่ถูก truncate)
    sample_rate_hz: float
    format_detected: str        # "raw" หรือ "edges"
    leading_truncated: bool = False
    trailing_truncated: bool = False
    glitches: list = field(default_factory=list)   # list[Pulse] ที่ width < min_pulse_width_us
    expected_reps: int = None
    warnings: list = field(default_factory=list)

    @property
    def count_mismatch(self) -> bool:
        return self.expected_reps is not None and len(self.pulses) != self.expected_reps

    @property
    def is_clean(self) -> bool:
        """capture สะอาดพอให้ join กับ rep index แบบเรียงลำดับได้อย่างปลอดภัย —
        ต้องไม่มี truncation, ไม่มี glitch, และจำนวนพัลส์ตรงกับที่คาดไว้เป๊ะ"""
        return (not self.leading_truncated and not self.trailing_truncated
                and not self.glitches and not self.count_mismatch)


def _parse_rate_comment(line: str):
    # ";Rate: 24000000" หรือ "; rate:24000000Hz" ฯลฯ — ยอมรับช่องว่าง/ตัวพิมพ์ต่างกัน
    body = line.lstrip(";").strip()
    if ":" not in body:
        return None
    key, _, val = body.partition(":")
    if key.strip().lower() != "rate":
        return None
    val = val.strip().rstrip("Hz").rstrip("hz").strip()
    try:
        return float(val)
    except ValueError:
        return None


def detect_format(path: Path) -> str:
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(";"):
                continue  # comment ของ FORMAT A — ยังไม่สรุป เดี๋ยวเจอบรรทัดข้อมูลค่อยว่า
            if "," in line:
                return "edges"
            return "raw"
    raise ValueError(f"{path}: empty file, cannot detect format")


def _parse_raw(path: Path):
    """FORMAT A: คืน (sample_rate_hz, levels: list[int])"""
    sample_rate_hz = None
    levels = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(";"):
                rate = _parse_rate_comment(line)
                if rate is not None:
                    sample_rate_hz = rate
                continue
            levels.append(int(line))
    if sample_rate_hz is None:
        raise ValueError(f"{path}: FORMAT A detected but no ';Rate: <Hz>' comment found")
    return sample_rate_hz, levels


def _parse_edges(path: Path, sample_rate_hz_hint=None):
    """FORMAT B: คืน (sample_rate_hz_used_or_None, rows: list[(time_s, level)])
    เดาว่าคอลัมน์แรกเป็นวินาที (มีจุดทศนิยม) หรือ sample index (จำนวนเต็มล้วน) จากแถวแรก
    ของข้อมูล — ถ้าเป็น index ต้องมี sample_rate_hz_hint มาช่วยแปลง ไม่งั้น error ชัดเจน"""
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        raw_rows = [r for r in reader if r]
    if not raw_rows:
        raise ValueError(f"{path}: FORMAT B detected but no data rows after header")

    first_col = raw_rows[0][0]
    is_seconds = "." in first_col or "e" in first_col.lower()
    rows = []
    if is_seconds:
        for r in raw_rows:
            rows.append((float(r[0]), int(r[1])))
        return None, rows

    if sample_rate_hz_hint is None:
        raise ValueError(
            f"{path}: first column looks like a sample index (no decimal point) — "
            "pass --sample-rate to convert index -> seconds"
        )
    for r in raw_rows:
        rows.append((int(r[0]) / sample_rate_hz_hint, int(r[1])))
    return sample_rate_hz_hint, rows


def _levels_to_segments(times_levels):
    """แปลงลำดับ (time_s, level) เป็น run ของ (start_s, end_s, level) โดย end_s ของ run
    สุดท้ายคือ None (ไม่รู้ว่า capture จบจริงตอนไหนหลัง sample/edge สุดท้าย)"""
    segments = []
    cur_level = times_levels[0][1]
    cur_start = times_levels[0][0]
    for t, lvl in times_levels[1:]:
        if lvl != cur_level:
            segments.append((cur_start, t, cur_level))
            cur_start = t
            cur_level = lvl
    segments.append((cur_start, None, cur_level))  # run สุดท้าย ไม่รู้เวลาจบ
    return segments


def extract_pulses(path: Path, expected_reps=None, min_pulse_width_us=1.0,
                    sample_rate_hz_hint=None) -> ParseResult:
    """อ่านไฟล์ capture 1 ไฟล์ (= 1 จุดข้อมูล) แล้วคืน ParseResult

    min_pulse_width_us: พัลส์ที่แคบกว่านี้ถือเป็น glitch (สัญญาณรบกวนไฟฟ้า ไม่ใช่ rep
    จริง) — ค่าเริ่มต้น 1us อนุรักษ์นิยมมาก (ที่ 24MHz คือ 24 sample) ควรตั้งเองให้เหมาะกับ
    ความกว้างพัลส์ที่คาดไว้จริงของวงจร/n ที่ทดสอบ (h_all ที่ n=2 กว้างระดับ 1-10us เท่านั้น
    บนบางบอร์ด ค่าเริ่มต้นนี้อาจต้องลดลงอีก)"""
    fmt = detect_format(path)
    if fmt == "raw":
        rate, levels = _parse_raw(path)
        period = 1.0 / rate
        times_levels = [(i * period, lvl) for i, lvl in enumerate(levels)]
    else:
        rate, rows = _parse_edges(path, sample_rate_hz_hint)
        times_levels = rows
        rate = rate or sample_rate_hz_hint

    segments = _levels_to_segments(times_levels)
    warnings = []

    leading_truncated = segments[0][2] == 1
    trailing_truncated = segments[-1][2] == 1 and segments[-1][1] is None

    pulses = []
    glitches = []
    idx = 0
    for i, (start, end, level) in enumerate(segments):
        if level != 1:
            continue
        is_first = i == 0
        is_last = i == len(segments) - 1
        if is_first and leading_truncated:
            warnings.append(f"leading pulse truncated (capture starts HIGH at t={start:.9f}s) — excluded")
            continue
        if is_last and trailing_truncated:
            warnings.append(f"trailing pulse truncated (capture ends HIGH at t={start:.9f}s, "
                             "no matching falling edge) — excluded")
            continue
        p = Pulse(index=idx, start_s=start, end_s=end)
        if p.width_us < min_pulse_width_us:
            glitches.append(p)
            warnings.append(f"glitch at pulse #{idx}: width={p.width_us:.3f}us "
                             f"< min_pulse_width_us={min_pulse_width_us}")
        else:
            pulses.append(p)
        idx += 1

    result = ParseResult(pulses=pulses, sample_rate_hz=rate, format_detected=fmt,
                          leading_truncated=leading_truncated, trailing_truncated=trailing_truncated,
                          glitches=glitches, expected_reps=expected_reps, warnings=warnings)

    if result.count_mismatch:
        result.warnings.append(
            f"pulse count mismatch: got {len(result.pulses)}, expected {expected_reps} "
            "(excluding glitches/truncated pulses from the count)"
        )
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=Path, help="ไฟล์ capture (FORMAT A หรือ B, ดู docstring บนไฟล์)")
    ap.add_argument("--expected-reps", type=int, default=100)
    ap.add_argument("--min-pulse-width-us", type=float, default=1.0)
    ap.add_argument("--sample-rate", type=float, default=None,
                     help="จำเป็นเฉพาะ FORMAT B ที่คอลัมน์แรกเป็น sample index ไม่ใช่วินาที")
    args = ap.parse_args()

    result = extract_pulses(args.capture, expected_reps=args.expected_reps,
                             min_pulse_width_us=args.min_pulse_width_us,
                             sample_rate_hz_hint=args.sample_rate)

    print(f"format: {result.format_detected}   sample_rate: {result.sample_rate_hz} Hz")
    print(f"pulses (clean): {len(result.pulses)} / expected {args.expected_reps}")
    print(f"leading_truncated={result.leading_truncated}  trailing_truncated={result.trailing_truncated}  "
          f"glitches={len(result.glitches)}")
    print(f"is_clean (safe to join by sequence order): {result.is_clean}")
    for w in result.warnings:
        print(f"  warning: {w}")
    if result.pulses:
        widths = [p.width_us for p in result.pulses]
        print(f"width_us: min={min(widths):.2f} max={max(widths):.2f} "
              f"first={widths[0]:.2f} last={widths[-1]:.2f}")


if __name__ == "__main__":
    main()
