#!/usr/bin/env python3
"""Draw the provisional MPVST icon.

This is a placeholder and is meant to look like one: flat, one colour, the
letters knocked out of a rounded tile so the shape still reads at 16 px.
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

TILE = (0x2E, 0x5C, 0x8A, 0xFF)          # one flat colour, nothing else
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

    # The letters are a hole in the tile, not ink on top of it, so the icon
    # stays one colour and reads on a light or a dark background.
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    pen = ImageDraw.Draw(mask)
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
                 text, font=font, fill=255)

    tile.putalpha(Image.composite(Image.new("L", (CANVAS, CANVAS), 0),
                                  tile.getchannel("A"), mask))
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
