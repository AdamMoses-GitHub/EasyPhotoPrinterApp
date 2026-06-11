from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPixmap, QPen, QFont, QFontMetrics
from core.image_processor import FitMode
from core.photo_info import print_ppi, ppi_quality


class PhotoCanvas(QWidget):
    """Displays the paper, print area, and photo preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)

        self._photo_path: str | None = None
        self._pixmap: QPixmap | None = None
        self._paper_w_in: float = 4.0
        self._paper_h_in: float = 6.0
        self._print_w_in: float = 4.0
        self._print_h_in: float = 6.0
        self._cut_markers: bool = False
        self._fit_mode: FitMode = FitMode.FILL
        self._crop_shadow: bool = False
        self._photo_info: dict | None = None
        self._paper_shadow: bool = True

    def set_photo(self, path: str):
        self._photo_path = path
        self._pixmap = QPixmap(path)
        self.update()

    def clear_photo(self):
        self._photo_path = None
        self._pixmap = None
        self._photo_info = None
        self.update()

    def set_paper(self, paper_w_in: float, paper_h_in: float):
        self._paper_w_in = paper_w_in
        self._paper_h_in = paper_h_in
        self.update()

    def set_print_area(self, print_w_in: float, print_h_in: float):
        self._print_w_in = min(print_w_in, self._paper_w_in)
        self._print_h_in = min(print_h_in, self._paper_h_in)
        self.update()

    def set_cut_markers(self, enabled: bool):
        self._cut_markers = enabled
        self.update()

    def set_fit_mode(self, mode: FitMode):
        self._fit_mode = mode
        self.update()

    def set_crop_shadow(self, enabled: bool):
        self._crop_shadow = enabled
        self.update()

    def set_photo_info(self, info: dict | None):
        self._photo_info = info
        self.update()

    def set_paper_shadow(self, enabled: bool):
        self._paper_shadow = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        # When crop-shadow is active in Fill mode we reserve extra margin so
        # the overflowing image parts are visible outside the paper edge.
        _SHADOW_EXTRA = 48
        show_cs = self._crop_shadow and self._fit_mode == FitMode.FILL
        padding = 24 + (_SHADOW_EXTRA if show_cs else 0)

        # Gray background
        painter.fillRect(0, 0, w, h, QColor(210, 210, 210))

        # --- Paper rect (fit paper aspect ratio into widget) ---
        avail_w = w - 2 * padding
        avail_h = h - 2 * padding
        paper_aspect = self._paper_w_in / self._paper_h_in

        if avail_w / avail_h > paper_aspect:
            paper_h_px = avail_h
            paper_w_px = int(paper_h_px * paper_aspect)
        else:
            paper_w_px = avail_w
            paper_h_px = int(paper_w_px / paper_aspect)

        paper_x = (w - paper_w_px) // 2
        paper_y = (h - paper_h_px) // 2

        # --- Print area geometry (needed before drawing photo) ---
        scale_px_per_in = paper_w_px / self._paper_w_in
        print_w_px = int(self._print_w_in * scale_px_per_in)
        print_h_px = int(self._print_h_in * scale_px_per_in)
        print_x = paper_x + (paper_w_px - print_w_px) // 2
        print_y = paper_y + (paper_h_px - print_h_px) // 2

        # --- Draw crop-shadow overflow first (behind paper) ---
        _SHADOW_COLOR = QColor(30, 100, 220, 170)   # blue tint
        if show_cs and self._pixmap and not self._pixmap.isNull():
            scaled_cs = self._pixmap.scaled(
                print_w_px, print_h_px,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x_off = (scaled_cs.width() - print_w_px) // 2
            y_off = (scaled_cs.height() - print_h_px) // 2
            if x_off > 0 or y_off > 0:
                # Draw the full image (with overflow) outside the paper
                draw_x = print_x - x_off
                draw_y = print_y - y_off
                painter.drawPixmap(draw_x, draw_y, scaled_cs)
                # Blue overlay on the overflow strips
                painter.fillRect(draw_x, draw_y, scaled_cs.width(), scaled_cs.height(),
                                  _SHADOW_COLOR)

        # Drop shadow (paper) — soft multi-layer simulation
        if self._paper_shadow:
            layers = 10
            for i in range(layers, 0, -1):
                alpha = int(80 * (i / layers) ** 2)  # quadratic falloff
                offset = i + 2
                painter.fillRect(
                    paper_x + offset, paper_y + offset,
                    paper_w_px, paper_h_px,
                    QColor(60, 60, 60, alpha),
                )

        # White paper (drawn on top, covering the outside-paper overflow)
        painter.fillRect(paper_x, paper_y, paper_w_px, paper_h_px, Qt.GlobalColor.white)

        # --- Draw photo or placeholder ---
        if self._pixmap and not self._pixmap.isNull():
            if self._fit_mode == FitMode.FILL:
                scaled = self._pixmap.scaled(
                    print_w_px, print_h_px,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x_off = (scaled.width() - print_w_px) // 2
                y_off = (scaled.height() - print_h_px) // 2

                if show_cs and (x_off > 0 or y_off > 0):
                    # Overflow is already drawn behind the paper.
                    # Now draw the overflow image ON the paper with blue tint
                    # (for the strips between print area and paper edge in custom-area mode).
                    painter.save()
                    painter.setClipRect(paper_x, paper_y, paper_w_px, paper_h_px)
                    painter.drawPixmap(print_x - x_off, print_y - y_off, scaled)
                    painter.restore()
                    # Blue overlay on the in-paper strips outside the print area
                    if print_y > paper_y:
                        painter.fillRect(paper_x, paper_y, paper_w_px, print_y - paper_y, _SHADOW_COLOR)
                    bottom_start = print_y + print_h_px
                    if bottom_start < paper_y + paper_h_px:
                        painter.fillRect(paper_x, bottom_start, paper_w_px,
                                         (paper_y + paper_h_px) - bottom_start, _SHADOW_COLOR)
                    if print_x > paper_x:
                        painter.fillRect(paper_x, print_y, print_x - paper_x, print_h_px, _SHADOW_COLOR)
                    right_start = print_x + print_w_px
                    if right_start < paper_x + paper_w_px:
                        painter.fillRect(right_start, print_y,
                                         (paper_x + paper_w_px) - right_start, print_h_px, _SHADOW_COLOR)
                    # Bright print area on top
                    painter.drawPixmap(
                        QRect(print_x, print_y, print_w_px, print_h_px),
                        scaled,
                        QRect(x_off, y_off, print_w_px, print_h_px),
                    )
                else:
                    painter.drawPixmap(
                        QRect(print_x, print_y, print_w_px, print_h_px),
                        scaled,
                        QRect(x_off, y_off, print_w_px, print_h_px),
                    )
            elif self._fit_mode == FitMode.FIT:
                painter.fillRect(print_x, print_y, print_w_px, print_h_px, Qt.GlobalColor.white)
                scaled = self._pixmap.scaled(
                    print_w_px, print_h_px,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x_off = (print_w_px - scaled.width()) // 2
                y_off = (print_h_px - scaled.height()) // 2
                painter.drawPixmap(print_x + x_off, print_y + y_off, scaled)
            else:  # STRETCH
                scaled = self._pixmap.scaled(
                    print_w_px, print_h_px,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter.drawPixmap(print_x, print_y, scaled)
        else:
            painter.fillRect(print_x, print_y, print_w_px, print_h_px, QColor(225, 232, 240))
            painter.setPen(QColor(140, 150, 160))
            painter.drawText(
                QRect(print_x, print_y, print_w_px, print_h_px),
                Qt.AlignmentFlag.AlignCenter,
                "No photo selected",
            )

        # Print-area border — dashed only when smaller than full paper
        is_custom = (
            abs(self._print_w_in - self._paper_w_in) > 0.01
            or abs(self._print_h_in - self._paper_h_in) > 0.01
        )
        if is_custom:
            pen = QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(print_x, print_y, print_w_px - 1, print_h_px - 1)

        # Cut markers
        if is_custom and self._cut_markers:
            gap_px = max(2, int(0.1 * scale_px_per_in))
            mark_px = max(4, int(0.2 * scale_px_per_in))
            pen = QPen(QColor(0, 0, 0), 1, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            corners = [
                (print_x,               print_y,               -1, -1),  # TL
                (print_x + print_w_px,  print_y,               +1, -1),  # TR
                (print_x,               print_y + print_h_px,  -1, +1),  # BL
                (print_x + print_w_px,  print_y + print_h_px,  +1, +1),  # BR
            ]
            for cx, cy, dx, dy in corners:
                painter.drawLine(cx + dx * gap_px, cy, cx + dx * (gap_px + mark_px), cy)
                painter.drawLine(cx, cy + dy * gap_px, cx, cy + dy * (gap_px + mark_px))

        # Paper border
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(paper_x, paper_y, paper_w_px - 1, paper_h_px - 1)

        # --- Info overlay (bottom-left of canvas) ---
        if self._photo_info:
            self._draw_info_overlay(painter, w, h)

        painter.end()

    def _draw_info_overlay(self, painter: QPainter, canvas_w: int, canvas_h: int):
        info = self._photo_info
        pw, ph = info.get("pixel_w", 0), info.get("pixel_h", 0)
        print_w_in = self._print_w_in
        print_h_in = self._print_h_in

        ppi = print_ppi(pw, ph, print_w_in, print_h_in) if pw and ph else 0
        quality = ppi_quality(ppi) if ppi else "low"

        # DPI color
        dpi_color = {
            "good": QColor(80, 200, 100),
            "ok":   QColor(240, 190, 40),
            "low":  QColor(220, 60, 60),
        }[quality]

        # Build lines
        size_bytes = info.get("file_size", 0)
        if size_bytes >= 1_048_576:
            size_str = f"{size_bytes / 1_048_576:.1f} MB"
        else:
            size_str = f"{size_bytes / 1024:.0f} KB"

        mod = info.get("modified")
        mod_str = mod.strftime("%Y-%m-%d  %H:%M") if mod else "—"

        lines_normal = [
            info.get("filename", ""),
            f"{pw} × {ph} px   {info.get('ratio', '—')}   {info.get('color_mode', '—')}",
            f"{size_str}   {mod_str}",
        ]
        # Camera line (optional)
        make = info.get("camera_make") or ""
        model = info.get("camera_model") or ""
        if model:
            camera = model if model.startswith(make) else f"{make} {model}".strip()
            lines_normal.append(camera)

        # DPI line drawn separately in color
        dpi_line = f"Print PPI: {ppi}  ({'Good' if quality == 'good' else 'OK' if quality == 'ok' else 'Low — may appear blurry'})" if ppi else "Print PPI: —"

        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        fm = QFontMetrics(font)
        line_h = fm.height() + 2

        all_lines = lines_normal + [dpi_line]
        box_w = max(fm.horizontalAdvance(l) for l in all_lines) + 16
        box_h = line_h * len(all_lines) + 12

        margin = 10
        box_x = margin
        box_y = canvas_h - box_h - margin

        # Background
        bg = QColor(20, 20, 20, 190)
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 6, 6)

        # Normal lines — white
        painter.setPen(QColor(255, 255, 255))
        for i, line in enumerate(lines_normal):
            y = box_y + 8 + i * line_h + fm.ascent()
            painter.drawText(box_x + 8, y, line)

        # DPI line — colored
        painter.setPen(dpi_color)
        y = box_y + 8 + len(lines_normal) * line_h + fm.ascent()
        painter.drawText(box_x + 8, y, dpi_line)

