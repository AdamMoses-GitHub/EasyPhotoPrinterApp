from enum import Enum
from PIL import Image


class FitMode(str, Enum):
    FILL = "Fill (crop)"
    FIT  = "Fit (letterbox)"
    STRETCH = "Stretch"


def render_image(img: Image.Image, target_w: int, target_h: int,
                 mode: FitMode = FitMode.FILL,
                 pan_x: float = 0.0, pan_y: float = 0.0) -> Image.Image:
    """Render a PIL image into target_w x target_h according to the given mode.

    pan_x, pan_y: fractional pan offset in [-1, 1]. Only used in FILL mode.
    0,0 = centered; -1 = left/top edge; +1 = right/bottom edge.
    """
    if target_w <= 0 or target_h <= 0:
        raise ValueError("target dimensions must be > 0")

    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        raise ValueError("source image dimensions must be > 0")

    pan_x = max(-1.0, min(1.0, pan_x))
    pan_y = max(-1.0, min(1.0, pan_y))

    if mode == FitMode.FILL:
        scale = max(target_w / src_w, target_h / src_h)
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        max_left = new_w - target_w
        max_top  = new_h - target_h
        # Center offset, then shift by pan fraction of the available overflow
        left = max_left // 2 + round(pan_x * (max_left / 2))
        top  = max_top  // 2 + round(pan_y * (max_top  / 2))
        left = max(0, min(left, max_left))
        top  = max(0, min(top,  max_top))
        return img.crop((left, top, left + target_w, top + target_h))

    elif mode == FitMode.FIT:
        scale = min(target_w / src_w, target_h / src_h)
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        result = Image.new("RGB", (target_w, target_h), (255, 255, 255))
        result.paste(img, ((target_w - new_w) // 2, (target_h - new_h) // 2))
        return result

    else:  # STRETCH
        return img.resize((target_w, target_h), Image.LANCZOS)


def fill_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Backward-compat wrapper."""
    return render_image(img, target_w, target_h, FitMode.FILL)
