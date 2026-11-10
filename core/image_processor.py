from enum import Enum
from PIL import Image


class FitMode(str, Enum):
    FILL = "Fill (crop)"
    FIT  = "Fit (letterbox)"
    STRETCH = "Stretch"


class ColorMode(str, Enum):
    FULL = "Full color (24-bit)"
    INDEXED_256 = "256 colors (8-bit indexed)"
    INDEXED_16 = "16 colors (4-bit indexed)"
    GRAYSCALE = "Grayscale (8-bit)"
    BLACK_WHITE = "Black & white (1-bit)"

    @property
    def supports_dithering(self) -> bool:
        return self in (ColorMode.INDEXED_256, ColorMode.INDEXED_16, ColorMode.BLACK_WHITE)


def apply_color_mode(img: Image.Image, mode: ColorMode,
                     dither: bool = True, *, preserve_white: bool = False) -> Image.Image:
    """Reduce colors non-destructively; return RGB for the Qt print pipeline."""
    rgb = img.convert("RGB")
    dithering = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    if mode == ColorMode.FULL:
        return rgb
    if mode == ColorMode.GRAYSCALE:
        return rgb.convert("L").convert("RGB")
    if mode == ColorMode.BLACK_WHITE:
        return rgb.convert("L").convert("1", dither=dithering).convert("RGB")
    if mode in (ColorMode.INDEXED_256, ColorMode.INDEXED_16):
        colors = 256 if mode == ColorMode.INDEXED_256 else 16
        palette = rgb.quantize(
            colors=colors - int(preserve_white), method=Image.Quantize.MEDIANCUT,
        )
        if preserve_white:
            entries = palette.getpalette()
            if entries is None:
                raise ValueError("Cannot read the quantized image palette")
            palette.putpalette(entries[:(colors - 1) * 3] + [255, 255, 255])
        # Adaptive quantization alone ignores dithering; remap to its palette.
        return rgb.quantize(palette=palette, dither=dithering).convert("RGB")
    raise ValueError(f"Unknown color mode: {mode}")


def render_color_image(img: Image.Image, target_w: int, target_h: int,
                       mode: FitMode = FitMode.FILL,
                       pan_x: float = 0.0, pan_y: float = 0.0,
                       color_mode: ColorMode = ColorMode.FULL,
                       dither: bool = True) -> Image.Image:
    """Use the same resize/crop and final color conversion for preview and print."""
    rendered = render_image(img.convert("RGB"), target_w, target_h, mode, pan_x, pan_y)
    return apply_color_mode(rendered, color_mode, dither, preserve_white=mode == FitMode.FIT)


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
        new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
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
        new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        result = Image.new("RGB", (target_w, target_h), (255, 255, 255))
        result.paste(img, ((target_w - new_w) // 2, (target_h - new_h) // 2))
        return result

    else:  # STRETCH
        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)


def fill_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Backward-compat wrapper."""
    return render_image(img, target_w, target_h, FitMode.FILL)
