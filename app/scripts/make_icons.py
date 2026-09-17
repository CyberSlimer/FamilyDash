#!/usr/bin/env python3
"""
Generate the FamilyDash app icon and splash screen.

    python app/scripts/make_icons.py

Writes:
    app/resources/icon.png          1024x1024 master (fed to @capacitor/assets)
    app/resources/splash.png        2732x2732 launch screen
    app/resources/splash-dark.png   same, dark variant
    frontend/icons/icon-192.png, icon-512.png, apple-touch-icon.png (PWA)

Requires Pillow (pip install pillow).
"""

import os
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RES = os.path.join(ROOT, 'app', 'resources')
PWA = os.path.join(ROOT, 'frontend', 'icons')

GRADIENT_START = (0x66, 0x7E, 0xEA)  # matches the dashboard's #667eea
GRADIENT_END = (0x76, 0x4B, 0xA2)    # ... #764ba2
WHITE = (255, 255, 255)


def gradient(size, start=GRADIENT_START, end=GRADIENT_END):
    """Diagonal gradient, rendered at low res and upscaled for speed."""
    small = 64
    img = Image.new('RGB', (small, small))
    px = img.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * (small - 1))
            px[x, y] = tuple(round(s + (e - s) * t) for s, e in zip(start, end))
    return img.resize((size, size), Image.BICUBIC)


def draw_calendar(img, scale=1.0):
    """Flat calendar glyph centered on the image. scale shrinks it for splash screens."""
    size = img.size[0]
    d = ImageDraw.Draw(img)

    glyph = size * 0.62 * scale           # overall glyph width
    x0 = (size - glyph) / 2
    y0 = (size - glyph * 0.95) / 2 + size * 0.02
    w, h = glyph, glyph * 0.95
    r = glyph * 0.12                       # corner radius
    header_h = h * 0.26

    # Body
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=r, fill=WHITE)
    # Header band (darker, top corners only)
    band = Image.new('RGBA', img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.rounded_rectangle([x0, y0, x0 + w, y0 + header_h + r], radius=r, fill=(0x4A, 0x3F, 0x8F, 255))
    bd.rectangle([x0, y0 + header_h, x0 + w, y0 + header_h + r], fill=(0, 0, 0, 0))
    img.paste(band, (0, 0), band)
    d = ImageDraw.Draw(img)

    # Binder rings
    ring_w = w * 0.055
    for fx in (0.28, 0.72):
        cx = x0 + w * fx
        d.rounded_rectangle([cx - ring_w / 2, y0 - h * 0.07, cx + ring_w / 2, y0 + header_h * 0.55],
                            radius=ring_w / 2, fill=WHITE, outline=(0x4A, 0x3F, 0x8F), width=max(1, int(size * 0.006)))

    # Date grid: 3 rows x 4 cols of dots, one highlighted "today"
    cols, rows = 4, 3
    gx0, gy0 = x0 + w * 0.14, y0 + header_h + h * 0.12
    gw, gh = w * 0.72, h - header_h - h * 0.24
    dot = min(gw / cols, gh / rows) * 0.42
    for ry in range(rows):
        for cx_ in range(cols):
            cx = gx0 + gw * (cx_ + 0.5) / cols
            cy = gy0 + gh * (ry + 0.5) / rows
            today = (ry == 1 and cx_ == 2)
            color = (0xE0, 0x68, 0x5C) if today else (0xD5, 0xD8, 0xE6)
            rad = dot * (0.62 if today else 0.5)
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=color)
    return img


def main():
    os.makedirs(RES, exist_ok=True)
    os.makedirs(PWA, exist_ok=True)

    icon = draw_calendar(gradient(1024))
    icon.save(os.path.join(RES, 'icon.png'))

    # Icon-only foreground for adaptive/masked variants (transparent background)
    fg = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
    draw_calendar(fg, scale=0.8)
    fg.save(os.path.join(RES, 'icon-foreground.png'))
    gradient(1024).save(os.path.join(RES, 'icon-background.png'))

    splash = draw_calendar(gradient(2732), scale=0.42)
    splash.save(os.path.join(RES, 'splash.png'))
    splash_dark = draw_calendar(gradient(2732, (0x2B, 0x2F, 0x5C), (0x3A, 0x22, 0x55)), scale=0.42)
    splash_dark.save(os.path.join(RES, 'splash-dark.png'))

    for name, px in (('icon-192.png', 192), ('icon-512.png', 512), ('apple-touch-icon.png', 180)):
        icon.resize((px, px), Image.LANCZOS).save(os.path.join(PWA, name))

    print(f"Wrote icons to {RES} and {PWA}")


if __name__ == '__main__':
    main()
