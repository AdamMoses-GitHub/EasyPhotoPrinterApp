from math import gcd
from datetime import datetime
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS


def _simplify_ratio(w: int, h: int) -> tuple[int, int]:
    d = gcd(w, h)
    return w // d, h // d


def _closest_simple_ratio(w: int, h: int) -> str:
    """Return a human-friendly ratio string, e.g. '3:2', '16:9'."""
    if w <= 0 or h <= 0:
        return "—"
    rw, rh = _simplify_ratio(w, h)
    # If both sides are small already, done
    if max(rw, rh) <= 20:
        return f"{rw}:{rh}"
    # Otherwise find the closest common ratio by normalising to one side = 1 and
    # checking common ratios (favour portrait and landscape variants equally)
    common = [
        (1, 1), (4, 3), (3, 2), (16, 9), (5, 4), (7, 5), (3, 4),
        (2, 3), (9, 16), (4, 5), (5, 7),
    ]
    ratio_f = w / h
    best = min(common, key=lambda r: abs(r[0] / r[1] - ratio_f))
    return f"{best[0]}:{best[1]}"


def read_photo_info(path: str) -> dict:
    """Read file metadata and PIL image info. Returns a plain dict."""
    p = Path(path)

    try:
        stat = p.stat()
        modified = datetime.fromtimestamp(stat.st_mtime)
        file_size = stat.st_size
    except Exception:
        modified = None
        file_size = 0

    info: dict = {
        "filename": p.name,
        "file_size": file_size,
        "modified": modified,
        "pixel_w": 0,
        "pixel_h": 0,
        "ratio": "—",
        "color_mode": "—",
        "dpi_x": None,
        "dpi_y": None,
        "camera_make": None,
        "camera_model": None,
    }

    try:
        with Image.open(path) as img:
            info["pixel_w"], info["pixel_h"] = img.size
            info["color_mode"] = img.mode
            info["ratio"] = _closest_simple_ratio(img.width, img.height)

            # Embedded DPI (may be unreliable for camera JPEGs)
            if hasattr(img, "info") and "dpi" in img.info:
                dx, dy = img.info["dpi"]
                if isinstance(dx, (int, float)) and isinstance(dy, (int, float)) and dx > 0 and dy > 0:
                    info["dpi_x"] = round(dx)
                    info["dpi_y"] = round(dy)

            # EXIF
            try:
                raw_exif = img._getexif()  # JPEG only
                if raw_exif:
                    exif = {TAGS.get(k, k): v for k, v in raw_exif.items()}
                    info["camera_make"] = exif.get("Make", "").strip() or None
                    info["camera_model"] = exif.get("Model", "").strip() or None
            except Exception:
                pass
    except Exception:
        pass

    return info


def print_ppi(pixel_w: int, pixel_h: int, print_w_in: float, print_h_in: float) -> int:
    """Effective PPI when the image is fill-scaled to the print area."""
    if print_w_in <= 0 or print_h_in <= 0:
        return 0
    scale = max(print_w_in / pixel_w if pixel_w else 0,
                print_h_in / pixel_h if pixel_h else 0)
    if scale <= 0:
        return 0
    return round(1.0 / scale)


def ppi_quality(ppi: int) -> str:
    """Returns 'good', 'ok', or 'low'."""
    if ppi >= 250:
        return "good"
    if ppi >= 150:
        return "ok"
    return "low"
