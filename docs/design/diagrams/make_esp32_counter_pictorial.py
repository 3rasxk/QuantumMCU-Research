"""Draw docs/design/esp32_counter_pictorial.png: easy-to-follow wiring picture (breadboard style).

ESP32 DevKit (target) GPIO4 -> 330 ohm -> breadboard row A -> ESP32 counter GPIO34; 10 kohm from row A to row B;
GND of both boards -> row B. Counter powered from its own USB. Run:
.venv/bin/python docs/design/diagrams/make_esp32_counter_pictorial.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle

plt.rcParams["font.family"] = ["Thonburi", "TH Sarabun New", "DejaVu Sans"]
OUT = Path(__file__).with_name("esp32_counter_pictorial.png")

fig, ax = plt.subplots(figsize=(14, 8.4))
ax.set_xlim(0, 14)
ax.set_ylim(0, 8.4)
ax.set_aspect("equal")
ax.axis("off")

YELLOW, BLACKW = "#e6b800", "#222222"


def wire(pts, c, lw=7):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=c, lw=lw, solid_capstyle="round", solid_joinstyle="round", zorder=3)
    ax.plot(xs, ys, color="white", lw=lw * 0.18, alpha=0.35, solid_capstyle="round", zorder=3)


def pin(x, y, label, side, hl=None):
    ax.add_patch(Circle((x, y), 0.13, fc="#d4af37", ec="#444", lw=1, zorder=4))
    dx = -0.3 if side == "L" else 0.3
    ax.text(x + dx, y, label, ha="right" if side == "L" else "left", va="center",
            fontsize=12, weight="bold" if hl else "normal", color=hl or "#444")


# ---- NodeMCU (left), pins on its right edge ----
ax.add_patch(FancyBboxPatch((1.0, 2.2), 3.0, 5.2, boxstyle="round,pad=0.05", fc="#1b3a5c", ec="black", lw=2, zorder=1))
ax.text(2.5, 6.7, "ESP32\nDevKit", color="white", ha="center", va="center", fontsize=15, weight="bold")
ax.text(2.5, 5.6, "(บอร์ดเป้าหมาย รัน algorithm)", color="#cfe", ha="center", fontsize=11)
ax.add_patch(Rectangle((1.9, 2.2), 1.2, 0.6, fc="#999", ec="black", zorder=2))
ax.text(2.5, 1.85, "USB → PC (serial + ไฟ)", ha="center", fontsize=11)
for i, (lbl, hl) in enumerate([("GPIO2", None), ("GPIO4", "#b8860b"), ("GPIO5", None), ("3V3  ✗ ไม่ต่อ", "#c00"), ("GND", "black")]):
    pin(4.0, 6.7 - i * 0.7, "", "R")
    ax.text(3.85, 6.7 - i * 0.7, lbl, ha="right", va="center", fontsize=11, color=hl or "white",
            weight="bold" if hl else "normal", zorder=5)
Y_D1, Y_G1 = 6.0, 3.9

# ---- ESP32 counter (right), pins on its left edge ----
ax.add_patch(FancyBboxPatch((10.0, 2.2), 3.0, 5.2, boxstyle="round,pad=0.05", fc="#3a1b5c", ec="black", lw=2, zorder=1))
ax.text(11.5, 6.7, "ESP32\ncounter", color="white", ha="center", va="center", fontsize=15, weight="bold")
ax.text(11.5, 5.6, "(ตัวนับ)", color="#fce", ha="center", fontsize=11)
ax.add_patch(Rectangle((10.9, 2.2), 1.2, 0.6, fc="#999", ec="black", zorder=2))
for i, (lbl, hl) in enumerate([("GPIO35", None), ("GPIO34", "#b8860b"), ("GPIO25", None), ("3V3  ✗ ไม่ต่อ", "#c00"), ("GND", "black")]):
    pin(10.0, 6.7 - i * 0.7, "", "L")
    ax.text(10.15, 6.7 - i * 0.7, lbl, ha="left", va="center", fontsize=11, color=hl or "white",
            weight="bold" if hl else "normal", zorder=5)

# ---- mini breadboard in the middle ----
ax.add_patch(FancyBboxPatch((5.6, 3.6), 2.8, 3.0, boxstyle="round,pad=0.05", fc="#f2efe6", ec="#888", lw=2, zorder=1))
ax.text(7.0, 6.9, "เบรดบอร์ดเล็ก", ha="center", fontsize=12, color="#555")
XA, XB, XC = 6.0, 7.0, 8.0
RA, RB = 6.0, 4.6  # row A (signal) / row B (GND)
for y, col, name in [(RA, "#e6b800", "แถว A"), (RB, "#555", "แถว B")]:
    ax.plot([XA, XC], [y, y], color=col, lw=14, alpha=0.18, solid_capstyle="round", zorder=1)
    for x in (XA, XB, XC):
        ax.add_patch(Circle((x, y), 0.1, fc="#333", zorder=2))
    ax.text(5.55, y, name, ha="right", va="center", fontsize=9, color="#777")

# resistor 10k vertical between row A and row B at XB
ax.plot([XB, XB], [RA, 5.65], color="#888", lw=3, zorder=2)
ax.plot([XB, XB], [RB, 4.95], color="#888", lw=3, zorder=2)
ax.add_patch(FancyBboxPatch((XB - 0.2, 4.95), 0.4, 0.7, boxstyle="round,pad=0.02", fc="#d9b98c", ec="#7a5a2a", lw=1.5, zorder=3))
for dy, c in [(5.55, "#6b3a1a"), (5.38, "black"), (5.21, "#e07b00")]:
    ax.add_patch(Rectangle((XB - 0.2, dy - 0.04), 0.4, 0.08, fc=c, zorder=4))
ax.text(XB + 0.35, 5.3, "10 kΩ\n(น้ำตาล-ดำ-ส้ม)", va="center", fontsize=10)

# ---- wires ----
wire([(4.0, Y_D1), (4.35, Y_D1)], YELLOW)
wire([(5.05, Y_D1), (5.3, Y_D1), (5.3, RA), (XA, RA)], YELLOW)
ax.add_patch(FancyBboxPatch((4.35, Y_D1 - 0.2), 0.7, 0.4, boxstyle="round,pad=0.02", fc="#d9b98c", ec="#7a5a2a", lw=1.5, zorder=4))
for dx, c in [(4.5, "#e07b00"), (4.66, "#e07b00"), (4.82, "#6b3a1a")]:
    ax.add_patch(Rectangle((dx, Y_D1 - 0.2), 0.08, 0.4, fc=c, zorder=5))
ax.text(4.5, Y_D1 - 0.45, "330 Ω (ส้ม-ส้ม-น้ำตาล)", ha="left", fontsize=9)
wire([(XC, RA), (10.0, 6.0)], YELLOW)  # GPIO34 at y=6.0
wire([(4.0, Y_G1), (4.6, Y_G1), (4.8, RB), (XA, RB)], BLACKW)
wire([(XC, RB), (9.2, RB), (9.4, Y_G1), (10.0, Y_G1)], BLACKW)

# fix: GPIO34 is 2nd pin at y=6.0 (6.7-0.7), GND is 5th at 4.6 -> both already exact
ax.text(4.7, Y_D1 + 0.35, "สายเหลือง", fontsize=10, color="#b8860b", ha="center")
ax.text(9.2, 6.35, "สายเหลือง", fontsize=10, color="#b8860b", ha="center")
ax.text(4.9, 3.5, "สายดำ (GND)", fontsize=10, ha="center")
ax.text(9.1, 3.5, "สายดำ (GND)", fontsize=10, ha="center")

# ---- counter USB power ----
ax.plot([11.5, 11.5, 12.4, 12.4], [2.2, 1.5, 1.5, 1.0], color="#555", lw=5, zorder=3)
ax.add_patch(FancyBboxPatch((11.3, 0.3), 2.2, 0.7, boxstyle="round,pad=0.03", fc="#fff", ec="black", lw=2))
ax.text(12.4, 0.65, "ที่ชาร์จ / power bank\n/ USB อีกช่องของ PC", ha="center", va="center", fontsize=9)
ax.text(10.9, 1.7, "ไฟ 5 V ให้ counter", ha="right", fontsize=11, color="#a00", weight="bold")

# ---- title and steps ----
ax.text(0.2, 8.1, "วิธีต่อ ESP32 DevKit (เป้าหมาย) กับ ESP32 counter (3 เส้น + ตัวต้านทาน 2 ตัว)",
        fontsize=16, weight="bold")
ax.text(0.2, 1.2, "1) GPIO4 → 330 Ω → แถว A → GPIO34 (สายเหลือง)\n"
                  "2) ตัวต้านทาน 10 kΩ คร่อมแถว A กับแถว B\n"
                  "3) GND ของทั้งสองบอร์ด → แถว B (สายดำ)",
        fontsize=12, va="center")
ax.text(0.2, 0.15, "ไม่ต่อ 3V3 / VIN ระหว่างบอร์ด | ตำแหน่งขาจริงต่างกันตามรุ่น ให้ดูตัวหนังสือบนบอร์ด | ใช้ขา UART (GPIO1/GPIO3) เป็นสัญญาณไม่ได้",
        fontsize=10, color="gray")

fig.savefig(OUT, dpi=100, bbox_inches="tight", facecolor="white")
print(OUT)
