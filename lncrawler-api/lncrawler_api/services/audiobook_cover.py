"""Cover art of an audiobook: a 1400 px square jpg for the audio apps, a 600 px webp for the site, and
the per-part jpg of each .m4b.

The art is built from the source cover. Without one, a plain square with the novel title is made.
"""
import hashlib
import io
import logging
import os
import tempfile
import textwrap

from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

from . import audiobook_service as svc

logger = logging.getLogger("lncrawler_api.audiobooks")

SQUARE = 1400  # side of the cover jpg, in pixels
THUMB = 600  # side of the site webp
JPEG_QUALITY = 85
WEBP_QUALITY = 80
BLUR_RADIUS = 40
DIM_RATIO = 0.45  # share of black laid over the blurred background
FOREGROUND_RATIO = 0.86  # share of the height taken by the portrait cover
SHADOW_OFFSET = 8  # px
SHADOW_BLUR = 18
BAND_HEIGHT = 150
BAND_ALPHA = 170
LABEL = "GENERATED AUDIOBOOK"
LABEL_SIZES = (64, 56, 48, 40)  # font sizes of the label, the largest that fits is used
LABEL_MARGIN = 80  # px kept free on each side of the glyph and the label
GLYPH_SIZE = 56
GLYPH_GAP = 16
BADGE_SIZE = 56
WHITE = (255, 255, 255, 255)
COVER_NAME = 'cover.jpg'
THUMB_NAME = 'cover-600.webp'
STAMP_NAME = 'cover.src'  # what the cover was built from: the source cover file, or GENERATED
GENERATED = 'generated'
COVER_VERSION = 2  # bump when the art changes: the stamp then differs and covers are rebuilt
MAX_SOURCE_PIXELS = 40 * 1000 * 1000  # a larger source cover is not opened, the title square is used


def source_cover_file(source):
    """Absolute path of the cover of a source (cover_path, else overview_picture_path), or None when missing."""
    for rel in (source.cover_path, source.overview_picture_path):
        if rel:
            candidate = os.path.join(settings.LNCRAWL_OUTPUT_PATH, rel)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    return None


def _cover_jpg(audiobook):
    return os.path.join(svc.audio_dir(audiobook.source), COVER_NAME)


def thumb_path(audiobook):
    """Path of the 600 px webp, relative to LNCRAWL_OUTPUT_PATH, next to cover_path."""
    return os.path.join(os.path.dirname(audiobook.cover_path), THUMB_NAME)


def _text_size(draw, text, font):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _text_at(draw, x, cy, text, font, fill):
    """Draw ``text`` with its left edge at x and its vertical centre at cy."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((x - left, cy - (bottom - top) / 2 - top), text, font=font, fill=fill)


def _headphones(draw, x, cy, size, fill):
    """A headphone glyph: an arc over two ear cups, its left edge at x and its centre at cy."""
    stroke = max(4, size // 8)
    top = cy - size / 2
    draw.arc((x, top, x + size, top + size), start=180, end=360, fill=fill, width=stroke)
    cup = size * 0.24
    for cup_x in (x, x + size - cup):
        draw.rounded_rectangle(
            (int(cup_x), int(cy - size * 0.1), int(cup_x + cup), int(cy + size * 0.4)),
            radius=int(cup / 2), fill=fill,
        )


def _band_label(draw):
    """The largest font of LABEL_SIZES with which the glyph, the gap and the label fit the square, and the label width."""
    for size in LABEL_SIZES:
        font = ImageFont.load_default(size=size)
        text_width, _ = _text_size(draw, LABEL, font)
        if GLYPH_SIZE + GLYPH_GAP + text_width <= SQUARE - 2 * LABEL_MARGIN:
            break
    return font, text_width


def _add_band(canvas):
    """A dark translucent band across the bottom, with the headphone glyph and the GENERATED AUDIOBOOK label."""
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    top = SQUARE - BAND_HEIGHT
    draw.rectangle((0, top, SQUARE, SQUARE), fill=(0, 0, 0, BAND_ALPHA))
    font, text_width = _band_label(draw)
    start = (SQUARE - (GLYPH_SIZE + GLYPH_GAP + text_width)) / 2
    cy = top + BAND_HEIGHT / 2
    _headphones(draw, start, cy, GLYPH_SIZE, WHITE)
    _text_at(draw, start + GLYPH_SIZE + GLYPH_GAP, cy, LABEL, font, WHITE)
    return Image.alpha_composite(canvas, layer)


def _background(source_image):
    """The cover scaled to fill the square, blurred and darkened."""
    background = ImageOps.fit(source_image, (SQUARE, SQUARE), Image.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    return Image.blend(background, Image.new('RGB', background.size, (0, 0, 0)), DIM_RATIO)


def _foreground(canvas, source_image):
    """The portrait cover, centred and sized to FOREGROUND_RATIO of the height, with a soft shadow."""
    height = int(SQUARE * FOREGROUND_RATIO)
    cover = ImageOps.contain(source_image.convert('RGB'), (SQUARE, height), Image.LANCZOS)
    x = (SQUARE - cover.width) // 2
    y = (SQUARE - cover.height) // 2
    shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle(
        (x + SHADOW_OFFSET, y + SHADOW_OFFSET, x + cover.width + SHADOW_OFFSET, y + cover.height + SHADOW_OFFSET),
        fill=(0, 0, 0, 170),
    )
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR)))
    canvas.paste(cover.convert('RGBA'), (x, y))
    return canvas


def _gradient():
    """A plain dark vertical gradient square."""
    canvas = Image.new('RGBA', (SQUARE, SQUARE))
    draw = ImageDraw.Draw(canvas)
    top, bottom = (38, 44, 62), (10, 10, 16)
    for y in range(SQUARE):
        ratio = y / (SQUARE - 1)
        colour = tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom))
        draw.line((0, y, SQUARE, y), fill=colour + (255,))
    return canvas


def _wrap(draw, text, font, width):
    lines = []
    current = ''
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and _text_size(draw, candidate, font)[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ['']


def _title_square(title):
    """The gradient square with the novel title wrapped in the centre, at the largest size that fits."""
    canvas = _gradient()
    draw = ImageDraw.Draw(canvas)
    width = int(SQUARE * 0.8)
    for size in (120, 96, 80, 64, 48):
        font = ImageFont.load_default(size=size)
        lines = _wrap(draw, title, font, width)
        line_height = int(_text_size(draw, 'Ag', font)[1] * 1.25)
        if len(lines) * line_height <= SQUARE * 0.6:
            break
    top = (SQUARE - BAND_HEIGHT - len(lines) * line_height) / 2
    for index, line in enumerate(lines):
        line_width, _ = _text_size(draw, line, font)
        _text_at(draw, (SQUARE - line_width) / 2, top + index * line_height + line_height / 2, line, font, WHITE)
    return canvas


def _open_source(source_file):
    """The source cover as RGB. None when the file is corrupt or has more than MAX_SOURCE_PIXELS, so the title is used."""
    try:
        with Image.open(source_file) as opened:
            pixels = opened.width * opened.height
            if pixels > MAX_SOURCE_PIXELS:
                logger.warning("Source cover %s is too large (%s px), not used", source_file, pixels)
                return None
            return opened.convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        logger.warning("Source cover %s cannot be read, not used: %s", source_file, error)
        return None


def _compose(audiobook):
    """The 1400 px square cover of an audiobook, as RGBA."""
    source_file = source_cover_file(audiobook.source)
    source_image = _open_source(source_file) if source_file else None
    if source_image is None:
        canvas = _title_square(audiobook.novel.title)
    else:
        canvas = _background(source_image).convert('RGBA')
        canvas = _foreground(canvas, source_image)
    return _add_band(canvas)


def _replace_atomically(path, write):
    """Call write(tmp) on a new temp file next to path, then move it over path. The temp file is removed on error."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=os.path.basename(path) + '.', suffix='.tmp')
    os.close(fd)
    try:
        os.chmod(tmp, 0o644)
        write(tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _source_stamp(audiobook):
    """What the cover is built from: COVER_VERSION, then the relative path, size and mtime (ns) of the source cover,
    or GENERATED."""
    version = f"cover-v{COVER_VERSION}"
    source_file = source_cover_file(audiobook.source)
    if source_file is None:
        return f"{version}\n{GENERATED}"
    stat = os.stat(source_file)
    rel = os.path.relpath(source_file, settings.LNCRAWL_OUTPUT_PATH)
    return f"{version}\n{rel}\n{stat.st_size}\n{stat.st_mtime_ns}"


def _stamp_path(audiobook):
    return os.path.join(svc.audio_dir(audiobook.source), STAMP_NAME)


def _read_stamp(audiobook):
    """The content of the stamp, or None when it is missing."""
    try:
        with open(_stamp_path(audiobook), encoding='utf-8') as handle:
            return handle.read()
    except OSError:
        return None


def cover_key(audiobook):
    """Eight hex digits of the sha256 of the stamp, part of the .m4b cache names. None when there is no stamp."""
    stamp = _read_stamp(audiobook)
    if stamp is None:
        return None
    return hashlib.sha256(stamp.encode('utf-8')).hexdigest()[:8]


def build_cover(audiobook):
    """Write audio/cover.jpg, audio/cover-600.webp and the stamp, set audiobook.cover_path and return it."""
    directory = svc.audio_dir(audiobook.source)
    os.makedirs(directory, exist_ok=True)
    stamp = _source_stamp(audiobook)
    art = _compose(audiobook).convert('RGB')
    jpg = os.path.join(directory, COVER_NAME)
    _replace_atomically(jpg, lambda tmp: art.save(tmp, format='JPEG', quality=JPEG_QUALITY, progressive=True))
    thumb = art.resize((THUMB, THUMB), Image.LANCZOS)
    _replace_atomically(
        os.path.join(directory, THUMB_NAME), lambda tmp: thumb.save(tmp, format='WEBP', quality=WEBP_QUALITY),
    )

    def write_stamp(tmp):
        with open(tmp, 'w', encoding='utf-8') as handle:
            handle.write(stamp)
    _replace_atomically(_stamp_path(audiobook), write_stamp)
    audiobook.cover_path = os.path.relpath(jpg, settings.LNCRAWL_OUTPUT_PATH)
    audiobook.save(update_fields=['cover_path', 'updated_at'])
    return audiobook.cover_path


def cover_is_stale(audiobook):
    """True when the jpg or the stamp is missing, or the stamp is not the source cover as it is now."""
    if not os.path.isfile(_cover_jpg(audiobook)):
        return True
    return _read_stamp(audiobook) != _source_stamp(audiobook)


def part_cover_jpeg(audiobook, index):
    """The cover with a "PART n" badge, as JPEG bytes. Never stored: it is made for each .m4b build."""
    if cover_is_stale(audiobook):
        build_cover(audiobook)
    with Image.open(_cover_jpg(audiobook)) as opened:
        canvas = opened.convert('RGBA')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=BADGE_SIZE)
    label = f"PART {index}"
    text_width, text_height = _text_size(draw, label, font)
    padding = 24
    right = SQUARE - 40
    box = (right - text_width - 2 * padding, 40, right, 40 + text_height + 2 * padding)
    draw.rounded_rectangle(box, radius=24, fill=(20, 20, 20, 255))
    text_x = box[0] + padding
    text_y = box[1] + padding + text_height / 2
    for offset in (0, 1):  # drawn twice, one pixel apart, so the text looks bold
        _text_at(draw, text_x + offset, text_y, label, font, WHITE)
    output = io.BytesIO()
    canvas.convert('RGB').save(output, format='JPEG', quality=JPEG_QUALITY, progressive=True)
    return output.getvalue()
