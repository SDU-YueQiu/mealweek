# -*- coding: utf-8 -*-
"""Generate app icons: a bowl mark, plus a maskable version with a safe zone."""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

C1 = (198, 72, 45)
C2 = (150, 45, 26)
CREAM = (255, 249, 240)


def bg(size):
    im = Image.new("RGB", (size, size), C1)
    d = ImageDraw.Draw(im)
    for y in range(size):
        t = y / max(1, size - 1)
        d.line([(0, y), (size, y)],
               fill=tuple(int(C1[i] * (1 - t) + C2[i] * t) for i in range(3)))
    return im


def bowl(size, scale=1.0):
    im = bg(size)
    d = ImageDraw.Draw(im)
    cx, cy = size / 2, size / 2
    w = size * 0.58 * scale
    h = w * 0.50
    top = cy - h * 0.10

    # steam: three short rounded strokes with a small gap above the rim
    sw = max(4, int(size * 0.022 * scale))
    sh = h * 0.42
    for dx in (-0.26, 0.0, 0.26):
        x = cx + dx * w
        y1 = top - h * 0.26
        y0 = y1 - sh
        d.rounded_rectangle([x - sw / 2, y0, x + sw / 2, y1], radius=sw / 2, fill=CREAM)

    # bowl body: lower half of a circle whose centre sits on the rim line
    d.pieslice([cx - w / 2, top - h * 1.0, cx + w / 2, top + h * 1.0], 0, 180, fill=CREAM)
    # rim
    rim_h = max(6, int(size * 0.026 * scale))
    d.rounded_rectangle([cx - w / 2 - rim_h * 0.5, top - rim_h * 0.55,
                         cx + w / 2 + rim_h * 0.5, top + rim_h * 0.55],
                        radius=rim_h, fill=CREAM)
    # base
    bw = w * 0.24
    bh = max(5, int(size * 0.020 * scale))
    d.rounded_rectangle([cx - bw / 2, top + h * 0.92, cx + bw / 2, top + h * 0.92 + bh],
                        radius=bh / 2, fill=CREAM)
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    for size in (192, 512):
        bowl(size).save(os.path.join(OUT, "icon-%d.png" % size))
        print("icon-%d.png" % size)
    # maskable: art inside the 80% safe circle
    bowl(512, scale=0.72).save(os.path.join(OUT, "icon-maskable-512.png"))
    print("icon-maskable-512.png")


if __name__ == "__main__":
    main()
