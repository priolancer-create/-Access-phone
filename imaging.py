"""Server-side image validation and re-encoding (strips EXIF/GPS)."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageError(ValueError):
    pass


def process_image(data: bytes, max_side: int = 2048, quality: int = 88):
    """Return (jpeg_bytes, (w, h), (orig_w, orig_h)). All metadata is dropped."""
    try:
        probe = Image.open(BytesIO(data))
        probe.verify()
        im = Image.open(BytesIO(data))
        if im.format not in ALLOWED_FORMATS:
            raise ImageError("Unsupported image format")
        orig = im.size
        im = ImageOps.exif_transpose(im).convert("RGB")
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageError("Invalid image")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    out = BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True)  # no exif passed => stripped
    return out.getvalue(), im.size, orig
