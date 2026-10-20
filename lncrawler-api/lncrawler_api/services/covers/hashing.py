from PIL import Image


def _dhash_hex(img) -> str:
    """64-bit difference hash (dHash) as 16 hex chars, for cover matching.

    Robust to resizing/re-encoding and cheap to compare by Hamming distance.
    """
    small = img.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            if pixels[row * 9 + col] > pixels[row * 9 + col + 1]:
                bits |= 1 << (row * 8 + col)
    return f'{bits:016x}'


def dhash_file(path) -> str:
    """dHash of an image file on disk."""
    with Image.open(path) as img:
        return _dhash_hex(img)
