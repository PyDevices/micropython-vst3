#!/usr/bin/env python3
"""Draw the provisional MPVST icon.

This is a placeholder and is meant to look like one: a flat rounded tile with
the letters on it, stacked so they still read at 16 px.

The letters are PAINTED, not knocked out. A knockout looks tidy but shows
whatever is behind the icon through the holes, and a classic Windows .ico has
no light/dark variants - one file is shown on the taskbar, in Explorer, in
file dialogs and on whatever background each of those happens to use. Painting
the letters makes the icon look the same everywhere.
It exists so the icon *mechanism* can be finished and exercised before
anyone commits to a mark. Replacing it is one file - rerun this with
different letters or colour, or drop a real .ico in its place; nothing
downstream cares where installer/art/mpvst.ico came from.

    python3 installer/art/make-placeholder-icon.py

Needs Pillow and a bold sans TTF (DejaVu on this machine). Neither is a
build dependency: the .ico it writes is committed, and no build step runs
this script.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TILE = (0x2E, 0x5C, 0x8A, 0xFF)          # the tile
INK = (0xF2, 0xF5, 0xF8, 0xFF)           # the letters, opaque so the
                                          # background can never show through
LINES = ("MP", "VST")                     # the letters, stacked so they read small
SIZES = (256, 128, 64, 48, 32, 16)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUT = Path(__file__).resolve().parent / "mpvst.ico"

# Drawn large and downsampled: the knockout edges have to survive 16 px.
CANVAS = 1024
MARGIN = CANVAS // 16
RADIUS = CANVAS // 6


def render():
    tile = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle(
        (MARGIN, MARGIN, CANVAS - MARGIN - 1, CANVAS - MARGIN - 1),
        radius=RADIUS, fill=TILE)

    pen = draw
    inner = CANVAS - 2 * MARGIN - CANVAS // 8
    for index, text in enumerate(LINES):
        size = inner // 2
        while size > 8:
            font = ImageFont.truetype(FONT, size)
            left, top, right, bottom = pen.textbbox((0, 0), text, font=font)
            if right - left <= inner:
                break
            size -= 4
        height = inner // 2
        box_top = MARGIN + CANVAS // 16 + index * height
        pen.text((CANVAS // 2 - (right - left) / 2 - left,
                  box_top + (height - (bottom - top)) / 2 - top),
                 text, font=font, fill=INK)

    return tile


def main():
    art = render()
    frames = [art.resize((size, size), Image.LANCZOS) for size in SIZES]
    frames[0].save(OUT, format="ICO",
                   sizes=[(size, size) for size in SIZES],
                   append_images=frames[1:])
    print("wrote %s (%d bytes, sizes %s)"
          % (OUT, OUT.stat().st_size, ", ".join(str(s) for s in SIZES)))


if __name__ == "__main__":
    main()
