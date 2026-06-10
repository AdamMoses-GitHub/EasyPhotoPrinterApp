from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QPixmap, QPen
from core.image_processor import FitMode


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

    def set_photo(self, path: str):
        self._photo_path = path
        self._pixmap = QPixmap(path)
        self.update()

    def clear_photo(self):
        self._photo_path = None
        self._pixmap = None
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        padding = 24

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

        # Drop shadow
        painter.fillRect(paper_x + 4, paper_y + 4, paper_w_px, paper_h_px, QColor(160, 160, 160))

        # White paper
        painter.fillRect(paper_x, paper_y, paper_w_px, paper_h_px, Qt.GlobalColor.white)

        # --- Print area rect ---
        scale_px_per_in = paper_w_px / self._paper_w_in
        print_w_px = int(self._print_w_in * scale_px_per_in)
        print_h_px = int(self._print_h_in * scale_px_per_in)
        print_x = paper_x + (paper_w_px - print_w_px) // 2
        print_y = paper_y + (paper_h_px - print_h_px) // 2

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

        painter.end()
