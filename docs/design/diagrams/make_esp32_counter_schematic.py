"""Draw docs/design/esp32_counter_schematic.png (ESP32 DevKit target -> ESP32 counter).

Run: .venv/bin/python docs/design/make_esp8266_counter_schematic.py
Values follow docs/design/wiring.md section 3 (3.3 V target: 330 ohm series + 10 kohm pull-down)
(counter powered from its own USB).
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = ["Thonburi", "TH Sarabun New", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).with_name("esp32_counter_schematic.png")

fig, ax = plt.subplots(figsize=(14, 8.6))
ax.set_xlim(0, 14.7)
ax.set_ylim(0, 8.6)
ax.axis("off")

Y_VIN, Y_SIG, Y_GND = 6.5, 4.6, 1.5
XL, XR = 3.4, 11.4  # board edges (pin side)


def wire(xs, ys, c="black", lw=2.6):
    ax.plot(xs, ys, color=c, lw=lw, solid_capstyle="round", zorder=2)


def dot(x, y, c="black"):
    ax.plot(x, y, "o", color=c, ms=8, zorder=4)


def zigzag_h(x0, x1, y, c="black", n=6, amp=0.2):
    """Horizontal resistor between x0 and x1 (lead 0.35 each side)."""
    a, b = x0 + 0.35, x1 - 0.35
    xs, ys = [x0, a], [y, y]
    step = (b - a) / (n * 2)
    for i in range(n * 2):
        xs.append(a + step * (i + 0.5))
        ys.append(y + amp * (1 if i % 2 == 0 else -1))
    xs += [b, x1]
    ys += [y, y]
    wire(xs, ys, c)


def zigzag_v(x, y0, y1, c="black", n=6, amp=0.2):
    """Vertical resistor between y0 (top) and y1 (bottom)."""
    a, b = y0 - 0.35, y1 + 0.35
    xs, ys = [x, x], [y0, a]
    step = (a - b) / (n * 2)
    for i in range(n * 2):
        ys.append(a - step * (i + 0.5))
        xs.append(x + amp * (1 if i % 2 == 0 else -1))
    xs += [x, x]
    ys += [b, y1]
    wire(xs, ys, c)


def board(x0, x1, title):
    ax.add_patch(Rectangle((x0, 0.9), x1 - x0, 7.4, fc="#dce6f2", ec="black", lw=2, zorder=1))
    ax.text((x0 + x1) / 2, 7.7, title, ha="center", va="center", fontsize=15, weight="bold")


# boards
board(0.3, XL, "ESP32 DevKit\n(บอร์ดเป้าหมาย)")
board(XR, 14.4, "ESP32 counter\n(ตัวนับ)")

# pin labels
ax.text(XL - 0.15, Y_SIG + 0.28, "GPIO4", ha="right", fontsize=12, color="blue", weight="bold")
ax.text(XL - 0.15, Y_GND + 0.28, "GND", ha="right", fontsize=12, weight="bold")
ax.text(XR + 0.15, Y_SIG + 0.28, "GPIO34", ha="left", fontsize=12, color="blue", weight="bold")
ax.text(XR + 0.15, Y_GND + 0.28, "GND", ha="left", fontsize=12, weight="bold")

# signal: D1 --330R-- node --wire-- GPIO34
X_R1a, X_R1b, X_NODE = 4.6, 6.4, 7.8
wire([XL, X_R1a], [Y_SIG, Y_SIG], "blue")
zigzag_h(X_R1a, X_R1b, Y_SIG, "black")
wire([X_R1b, XR], [Y_SIG, Y_SIG], "blue")
ax.text((X_R1a + X_R1b) / 2, Y_SIG - 0.55, "R2 330 Ω (อนุกรม)", ha="center", fontsize=11)
dot(XL, Y_SIG, "blue")
dot(XR, Y_SIG, "blue")
dot(X_NODE, Y_SIG, "blue")
ax.text(5.5, Y_SIG + 0.4, "3.3 V ตรง ๆ (ไม่ต้องแบ่งแรงดัน)", ha="center", fontsize=11, color="green")

# pull-down R2 10k from node to GND
zigzag_v(X_NODE, Y_SIG, Y_GND, "black")
dot(X_NODE, Y_GND)
ax.text(X_NODE - 0.35, (Y_SIG + Y_GND) / 2, "R1 10 kΩ\n(ดึงลง GND)", ha="right", va="center", fontsize=11)

# common GND
wire([XL, XR], [Y_GND, Y_GND], "black", 3.6)
dot(XL, Y_GND)
dot(XR, Y_GND)
ax.text(4.6, Y_GND - 0.4, "สาย GND ร่วม (สั้น ๆ)", ha="center", fontsize=11)

# captions
ax.text(0.3, 0.55, "R1 กันสัญญาณหลอกตอนบอร์ดเป้าหมายรีเซ็ตหรืออัปโหลด. "
        "counter ใช้ USB ของตัวเอง.", fontsize=10)
ax.text(0.3, 0.2, "ห้าม: ต่อ 3V3 หรือ VIN ของบอร์ดใดเข้า counter | ใช้ขา UART (GPIO1/GPIO3) | ต่อ GPIO25 เข้า GPIO34", fontsize=10, color="gray")

ax.set_title("ESP32 DevKit (เป้าหมาย) ↔ ESP32 counter: สัญญาณ 3.3 V ตรง + GND ร่วม (counter ใช้ USB ของตัวเอง)",
             fontsize=15, weight="bold", loc="left")

fig.savefig(OUT, dpi=100, bbox_inches="tight", facecolor="white")
print(OUT)
