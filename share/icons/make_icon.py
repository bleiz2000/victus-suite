#!/usr/bin/env python3
"""make_icon.py — генератор минималистичной чёрно-белой иконки Victus Suite.

Запуск (из корня проекта):  python3 share/icons/make_icon.py
Что получается:
  share/icons/victus-suite.svg                       ← исходник (vector)
  share/icons/hicolor/<N>x<N>/apps/victus-suite.png  ← для меню приложений
  share/icons/hicolor/scalable/apps/victus-suite.svg ← для DE со скалярными иконками

Стиль: чёрная плитка со скруглением + белая «V» (Victus) — читается и в
тёмном, и в светлом меню, работает на Wayland/Hyprland/GNOME/KDE.
"""

import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
SS = 4  # supersampling — антиалиасинг

INK = (17, 17, 17, 255)      # #111111 — почти чёрный
PAPER = (255, 255, 255, 255)  # белый

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <title>Victus Suite</title>
  <rect x="0" y="0" width="256" height="256" rx="56" ry="56" fill="#111111"/>
  <path d="M64 66 L128 192 L192 66" fill="none" stroke="#ffffff"
        stroke-width="36" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def draw_icon(size: int) -> Image.Image:
    """Иконка size×size (RGBA) через рендер в 4 раза больше + даунсэмпл."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = int(round(big * 0.21875))            # rx = 56/256
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=r, fill=INK)

    k = big / 256.0
    w = int(round(36 * k))
    pts = [(64 * k, 66 * k), (128 * k, 192 * k), (192 * k, 66 * k)]
    d.line(pts, fill=PAPER, width=w, joint="curve")
    cap = w // 2                              # круглые торцы как в SVG
    for x, y in (pts[0], pts[2]):
        d.ellipse([x - cap, y - cap, x + cap, y + cap], fill=PAPER)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    os.makedirs(os.path.join(HERE, "hicolor", "scalable", "apps"), exist_ok=True)
    with open(os.path.join(HERE, "victus-suite.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)

    for size in SIZES:
        folder = os.path.join(HERE, "hicolor", f"{size}x{size}", "apps")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "victus-suite.png")
        draw_icon(size).save(path, "PNG", optimize=True)
        print(f"  {os.path.relpath(path, ROOT)}")

    with open(
        os.path.join(HERE, "hicolor", "scalable", "apps", "victus-suite.svg"),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(SVG)
    print(f"  {os.path.relpath(os.path.join(HERE, 'hicolor', 'scalable', 'apps', 'victus-suite.svg'), ROOT)}")
    print("done:", len(SIZES), "png + svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
