"""Minimal cover image generation, used when a novel has no downloadable cover."""

import textwrap

from PIL import Image, ImageDraw, ImageFont

PALETTE = [
    (33, 150, 243),
    (156, 39, 176),
    (233, 30, 99),
    (255, 152, 0),
    (63, 81, 181),
    (0, 150, 136),
    (121, 85, 72),
]


def _load_font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_cover_image(
    output_file: str,
    title: str = "",
    author: str = "",
    width: int = 600,
    height: int = 800,
) -> str:
    color = PALETTE[abs(hash(title or output_file)) % len(PALETTE)]
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)

    title_font = _load_font(48)
    author_font = _load_font(32)

    y = height // 3
    for line in textwrap.wrap(title or "Unknown Title", width=18)[:6]:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        draw.text(((width - (bbox[2] - bbox[0])) / 2, y), line, font=title_font, fill="white")
        y += (bbox[3] - bbox[1]) + 14

    if author:
        y += 24
        for line in textwrap.wrap(author, width=28)[:3]:
            bbox = draw.textbbox((0, 0), line, font=author_font)
            draw.text(
                ((width - (bbox[2] - bbox[0])) / 2, y), line, font=author_font, fill=(235, 235, 235)
            )
            y += (bbox[3] - bbox[1]) + 10

    image.save(output_file, "JPEG", quality=90)
    image.close()
    return output_file
