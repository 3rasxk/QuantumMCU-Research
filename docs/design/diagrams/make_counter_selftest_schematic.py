"""Draw docs/design/diagrams/counter_selftest_schematic.png: counter self-test jumper (GPIO25 -> GPIO35) and the normal run wiring.

Run: .venv/bin/python docs/design/diagrams/make_counter_selftest_schematic.py
Self-test: firmware/counter_esp32/README.md ("one jumper GPIO25 -> GPIO35. Nothing on GPIO34."). Run wiring: docs/design/wiring.md section 3
(330 ohm series + 10 kohm pull-down at the counter). Pin order of the strip follows the common 30-pin ESP32 DevKit V1 left header
(... D34, D35, D32, D33, D25 ...); check the printed labels on the actual board.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

plt.rcParams["font.family"] = ["Thonburi", "TH Sarabun New", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
OUT = Path(__file__).with_name("counter_selftest_schematic.png")

fig, axs = plt.subplots(1, 2, figsize=(16, 7.6), gridspec_kw={"width_ratios": [1, 1.25]})


def wire(ax, xs, ys, c="black", lw=2.6):
    ax.plot(xs, ys, color=c, lw=lw, solid_capstyle="round", zorder=3)


def dot(ax, x, y, c="black"):
    ax.plot(x, y, "o", color=c, ms=8, zorder=5)


def zigzag_h(ax, x0, x1, y, n=6, amp=0.16):
    a, b = x0 + 0.3, x1 - 0.3
    xs, ys = [x0, a], [y, y]
    step = (b - a) / (n * 2)
    for i in range(n * 2):
        xs.append(a + step * (i + 0.5)); ys.append(y + amp * (1 if i % 2 == 0 else -1))
    xs += [b, x1]; ys += [y, y]
    wire(ax, xs, ys)


def zigzag_v(ax, x, y0, y1, n=6, amp=0.16):
    a, b = y0 - 0.3, y1 + 0.3
    xs, ys = [x, x], [y0, a]
    step = (a - b) / (n * 2)
    for i in range(n * 2):
        ys.append(a - step * (i + 0.5)); xs.append(x + amp * (1 if i % 2 == 0 else -1))
    xs += [x, x]; ys += [b, y1]
    wire(ax, xs, ys)


# ---------------------------------------------------------------- A: self-test
ax = axs[0]
ax.set_xlim(0, 9); ax.set_ylim(-2.6, 9); ax.axis("off")
ax.set_title("A. Self-test: บอร์ด counter ตัวเดียว + jumper 1 เส้น", fontsize=14, weight="bold", loc="left")
ax.add_patch(Rectangle((4.6, 0.9), 3.8, 7.3, fc="#dce6f2", ec="black", lw=2, zorder=1))
ax.text(6.5, 7.75, "ESP32 counter\n(MAC 8c:94:df:6c:a3:b8)", ha="center", va="center", fontsize=12, weight="bold")
pins = [("GPIO34", 6.6), ("GPIO35", 5.6), ("GPIO32", 4.7), ("GPIO33", 3.9), ("GPIO25", 3.0)]
XP = 4.6
for name, y in pins:
    col = "blue" if name in ("GPIO34", "GPIO35", "GPIO25") else "gray"
    ax.text(XP + 0.15, y, name, ha="left", va="center", fontsize=12, color=col, weight="bold" if col == "blue" else "normal")
    dot(ax, XP, y, col)
# jumper GPIO25 -> GPIO35 (outside the board, on the left)
wire(ax, [XP, 3.3, 3.3, XP], [3.0, 3.0, 5.6, 5.6], "green", 4)
ax.text(3.15, 4.3, "jumper\nGPIO25 → GPIO35", ha="right", va="center", fontsize=12, color="green", weight="bold")
ax.text(0.2, 2.55, "GPIO25 = ตัวสร้างพัลส์ทดสอบ", ha="left", va="center", fontsize=10, color="green")
ax.text(0.2, 6.05, "GPIO35 = ขารับพัลส์ใน self-test", ha="left", va="center", fontsize=10, color="green")
# GPIO34: nothing
ax.text(3.9, 6.6, "ไม่ต่อ\nอะไร ✗", ha="right", va="center", fontsize=11, color="red", weight="bold")
ax.text(0.2, 0.5, "• ถอดสาย GPIO34 → บอร์ดเป้าหมายออกก่อน (README: nothing on GPIO34)\n"
        "• ไม่ต้องเสียบ USB เข้า Mac: counter ใช้ไฟของตัวเอง ส่งข้อมูลผ่าน WiFi (tcp:5055)\n"
        "• ถ้า GPIO35 ลอย จะมีสัญญาณรบกวนถล่ม; ถ้าสายไม่ถึงขา 25 จะไม่เห็นพัลส์เลย (code 7)\n"
        "• ลำดับขาด้านซ้ายของ DevKit V1 30 ขา: …D34, D35, D32, D33, D25…\n"
        "  (D32 และ D33 อยู่ระหว่างสองขาที่ต้องต่อ; ตรวจชื่อขาจากตัวอักษรบนบอร์ด)",
        fontsize=9.5, va="top")

# ---------------------------------------------------------------- B: normal run wiring
ax = axs[1]
ax.set_xlim(0, 13.2); ax.set_ylim(-0.4, 9); ax.axis("off")
ax.set_title("B. ตอนเก็บข้อมูลจริง: counter ← บอร์ดเป้าหมาย (3.3 V, GND ร่วม)", fontsize=14, weight="bold", loc="left")
XL, XR = 3.9, 9.4
ax.add_patch(Rectangle((0.2, 0.9), XL - 0.2, 7.3, fc="#e8f0e0", ec="black", lw=2, zorder=1))
ax.add_patch(Rectangle((XR, 0.9), 12.9 - XR, 7.3, fc="#dce6f2", ec="black", lw=2, zorder=1))
ax.text((0.2 + XL) / 2, 7.55, "บอร์ดเป้าหมาย\nESP32: GPIO4\nESP8266: D1 = GPIO5\nUno: ผ่านตัวแบ่งแรงดัน\n(ดู wiring.md)",
        ha="center", va="center", fontsize=9.5, weight="bold")
ax.text((XR + 12.9) / 2, 7.75, "ESP32 counter", ha="center", va="center", fontsize=13, weight="bold")
Y_SIG, Y_GND = 5.2, 1.7
ax.text(XL - 0.15, Y_SIG + 0.3, "GPIO4 / D1", ha="right", fontsize=11, color="blue", weight="bold")
ax.text(XL - 0.15, Y_GND + 0.3, "GND", ha="right", fontsize=11, weight="bold")
ax.text(XR + 0.15, Y_SIG + 0.3, "GPIO34", ha="left", fontsize=11, color="blue", weight="bold")
ax.text(XR + 0.15, Y_GND + 0.3, "GND", ha="left", fontsize=11, weight="bold")
XA, XB, XN = 5.0, 6.6, 8.0
wire(ax, [XL, XA], [Y_SIG, Y_SIG], "blue")
zigzag_h(ax, XA, XB, Y_SIG)
wire(ax, [XB, XR], [Y_SIG, Y_SIG], "blue")
ax.text((XA + XB) / 2, Y_SIG - 0.6, "330 Ω (อนุกรม)", ha="center", fontsize=10)
for x in (XL, XR, XN):
    dot(ax, x, Y_SIG, "blue")
zigzag_v(ax, XN, Y_SIG, Y_GND)
dot(ax, XN, Y_GND)
ax.text(XN - 0.35, (Y_SIG + Y_GND) / 2, "10 kΩ\nดึงลง GND", ha="right", va="center", fontsize=10)
wire(ax, [XL, XR], [Y_GND, Y_GND], "black", 3.6)
dot(ax, XL, Y_GND); dot(ax, XR, Y_GND)
ax.text(5.9, Y_GND - 0.4, "สาย GND ร่วม (สั้น ๆ)", ha="center", fontsize=10)
ax.text(5.9, 6.3, "สัญญาณ 3.3 V ตรง ๆ", ha="center", fontsize=10.5, color="green")
ax.text(0.2, 0.55, "ค่า 330 Ω + 10 kΩ ตาม docs/design/wiring.md (ใช้ได้กับ ESP32/ESP8266 3.3 V); counter ใช้ไฟและ WiFi ของตัวเอง.", fontsize=9.5)
ax.text(0.2, 0.15, "ห้าม: ต่อ 3V3/VIN ข้ามบอร์ด | ใช้ขา UART (GPIO1/GPIO3) | ต่อ GPIO25 เข้า GPIO34", fontsize=9.5, color="gray")

fig.suptitle("ESP32 counter: jumper self-test (A) และสายตอนเก็บข้อมูล (B)", fontsize=16, weight="bold", x=0.01, ha="left")
fig.savefig(OUT, dpi=100, bbox_inches="tight", facecolor="white")
print(OUT)
