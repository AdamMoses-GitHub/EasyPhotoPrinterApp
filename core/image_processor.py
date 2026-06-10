from enum import Enum
from PIL import Image


class FitMode(str, Enum):
    FILL = "Fill (crop)"
    FIT  = "Fit (letterbox)"
    STRETCH = "Stretch"


def render_image(img: Image.Image, target_w: int, target_h: int,
                 mode: FitMode = FitMode.FILL) -> Image.Image:
    """Render a PIL image into target_w x target_h according to the given mode."""
    src_w, src_h = img.size

    if mode == FitMode.FILL:
        scale = max(target_w / src_w, target_h / src_h)
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
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
