import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QComboBox, QLabel, QDoubleSpinBox, QPushButton,
    QFileDialog, QCheckBox, QMessageBox, QStatusBar, QFrame,
    QDialog, QApplication, QMenu,
)
from PySide6.QtCore import Qt, QSettings, QSizeF, QMarginsF
from PySide6.QtGui import QPainter, QImage, QPageSize, QPageLayout, QTransform, QPen, QColor
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PIL import Image

from ui.photo_canvas import PhotoCanvas
from ui.thumbnail_bar import ThumbnailBar
from core.image_processor import FitMode, render_image
from core.photo_info import read_photo_info

_CONFIG = Path(__file__).parent.parent / "config" / "paper_sizes.json"
_MAX_PRINT_DPI = 600  # cap to keep memory/time reasonable


def _load_paper_sizes() -> list[dict]:
    with open(_CONFIG, encoding="utf-8") as f:
        return json.load(f)["sizes"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Printer App")
        self.resize(960, 720)

        self._photo_paths: list[str] = []
        self._current_index: int = -1
        self._photo_overrides: dict[int, str | None] = {}  # index -> FitMode value or None
        self._photo_pans: dict[int, tuple[float, float]] = {}  # index -> (pan_x, pan_y)
        self._paper_sizes = _load_paper_sizes()
        self._settings = QSettings("PrinterApp", "PrinterApp")

        self._build_ui()
        self._restore_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.addToolBar(self._build_toolbar())
        self._build_menu_bar()

        self._canvas = PhotoCanvas()
        self._canvas.pan_changed.connect(self._on_pan_changed)
        layout.addWidget(self._canvas, stretch=1)

        # Per-photo fit mode override bar
        override_bar = QWidget()
        ol = QHBoxLayout(override_bar)
        ol.setContentsMargins(8, 3, 8, 3)
        ol.setSpacing(6)
        ol.addWidget(QLabel("This photo:"))
        self._photo_fit_combo = QComboBox()
        self._photo_fit_combo.addItem("Use global setting")
        for m in FitMode:
            self._photo_fit_combo.addItem(m.value)
        self._photo_fit_combo.setEnabled(False)
        self._photo_fit_combo.currentTextChanged.connect(self._on_photo_fit_changed)
        ol.addWidget(self._photo_fit_combo)

        self._reset_crop_btn = QPushButton("Reset crop")
        self._reset_crop_btn.setEnabled(False)
        self._reset_crop_btn.setToolTip("Re-center the crop (undo manual pan)")
        self._reset_crop_btn.clicked.connect(self._on_reset_crop)
        ol.addWidget(self._reset_crop_btn)

        ol.addStretch()
        layout.addWidget(override_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        self._thumb_bar = ThumbnailBar()
        self._thumb_bar.photo_selected.connect(self._on_photo_selected)
        layout.addWidget(self._thumb_bar)

        self.setStatusBar(QStatusBar())

    def _build_menu_bar(self):
        view_menu: QMenu = self.menuBar().addMenu("&View")

        self._paper_shadow_chk = view_menu.addAction("Paper shadow")
        self._paper_shadow_chk.setCheckable(True)
        self._paper_shadow_chk.setChecked(True)
        self._paper_shadow_chk.toggled.connect(self._on_paper_shadow_toggled)

        self._crop_shadow_action = view_menu.addAction("Show crop shadow")
        self._crop_shadow_action.setCheckable(True)
        self._crop_shadow_action.setChecked(True)
        self._crop_shadow_action.setToolTip(
            "In Fill mode, dims the parts of the image that will be cropped off."
        )
        self._crop_shadow_action.toggled.connect(self._on_crop_shadow_toggled)

    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setFloatable(False)

        open_btn = QPushButton("Open Photos…")
        open_btn.clicked.connect(self._open_photos)
        tb.addWidget(open_btn)

        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._clear_photos)
        tb.addWidget(self._clear_btn)

        tb.addSeparator()

        tb.addWidget(QLabel(" Paper: "))
        self._paper_combo = QComboBox()
        self._paper_combo.setMinimumWidth(160)
        for s in self._paper_sizes:
            self._paper_combo.addItem(s["name"], s)
        self._paper_combo.currentIndexChanged.connect(self._on_paper_changed)
        tb.addWidget(self._paper_combo)

        tb.addWidget(QLabel("  Orientation: "))
        self._orient_combo = QComboBox()
        self._orient_combo.addItems(["Portrait", "Landscape", "Auto"])
        self._orient_combo.setToolTip(
            "Portrait / Landscape: force orientation for all photos.\n"
            "Auto: rotate paper to match each photo's aspect ratio."
        )
        self._orient_combo.currentIndexChanged.connect(self._on_orientation_changed)
        tb.addWidget(self._orient_combo)

        tb.addWidget(QLabel("  Fit: "))
        self._global_fit_combo = QComboBox()
        for m in FitMode:
            self._global_fit_combo.addItem(m.value)
        self._global_fit_combo.setToolTip(
            "Fill (crop): zoom to fill, crop edges\n"
            "Fit (letterbox): whole photo visible, white bars on short sides\n"
            "Stretch: distort to fill exactly"
        )
        self._global_fit_combo.currentTextChanged.connect(self._on_global_fit_changed)
        tb.addWidget(self._global_fit_combo)

        tb.addSeparator()

        self._full_paper_chk = QCheckBox("Full paper")
        self._full_paper_chk.setChecked(True)
        self._full_paper_chk.toggled.connect(self._on_full_paper_toggled)
        tb.addWidget(self._full_paper_chk)

        tb.addWidget(QLabel("  W: "))
        self._area_w_spin = QDoubleSpinBox()
        self._area_w_spin.setRange(0.5, 50.0)
        self._area_w_spin.setSingleStep(0.5)
        self._area_w_spin.setDecimals(2)
        self._area_w_spin.setSuffix("\"")
        self._area_w_spin.setEnabled(False)
        self._area_w_spin.valueChanged.connect(self._on_print_area_changed)
        tb.addWidget(self._area_w_spin)

        tb.addWidget(QLabel("  H: "))
        self._area_h_spin = QDoubleSpinBox()
        self._area_h_spin.setRange(0.5, 50.0)
        self._area_h_spin.setSingleStep(0.5)
        self._area_h_spin.setDecimals(2)
        self._area_h_spin.setSuffix("\"")
        self._area_h_spin.setEnabled(False)
        self._area_h_spin.valueChanged.connect(self._on_print_area_changed)
        tb.addWidget(self._area_h_spin)

        tb.addSeparator()

        self._cut_markers_chk = QCheckBox("Cut markers")
        self._cut_markers_chk.setChecked(False)
        self._cut_markers_chk.setEnabled(False)  # only active in custom-area mode
        self._cut_markers_chk.toggled.connect(self._on_cut_markers_toggled)
        tb.addWidget(self._cut_markers_chk)

        tb.addSeparator()

        self._print_btn = QPushButton("Print All")
        self._print_btn.setEnabled(False)
        self._print_btn.clicked.connect(self._print_all)
        tb.addWidget(self._print_btn)

        return tb

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _restore_settings(self):
        paper_idx = int(self._settings.value("paper_index", 1))
        paper_idx = max(0, min(paper_idx, self._paper_combo.count() - 1))

        full = self._settings.value("full_paper", True, type=bool)
        area_w = float(self._settings.value("area_w", 4.0))
        area_h = float(self._settings.value("area_h", 6.0))
        cut_markers = self._settings.value("cut_markers", False, type=bool)
        orient = self._settings.value("orientation", "Auto")
        global_fit = self._settings.value("global_fit", FitMode.FILL.value)
        crop_shadow = self._settings.value("crop_shadow", True, type=bool)
        paper_shadow = self._settings.value("paper_shadow", True, type=bool)

        self._paper_shadow_chk.blockSignals(True)
        self._paper_shadow_chk.setChecked(paper_shadow)
        self._paper_shadow_chk.blockSignals(False)

        self._crop_shadow_action.blockSignals(True)
        self._crop_shadow_action.setChecked(crop_shadow)
        self._crop_shadow_action.blockSignals(False)

        self._global_fit_combo.blockSignals(True)
        idx = self._global_fit_combo.findText(global_fit)
        self._global_fit_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._global_fit_combo.blockSignals(False)

        self._orient_combo.blockSignals(True)
        idx = self._orient_combo.findText(orient)
        self._orient_combo.setCurrentIndex(idx if idx >= 0 else 2)
        self._orient_combo.blockSignals(False)

        self._paper_combo.blockSignals(True)
        self._paper_combo.setCurrentIndex(paper_idx)
        self._paper_combo.blockSignals(False)

        self._full_paper_chk.blockSignals(True)
        self._full_paper_chk.setChecked(full)
        self._full_paper_chk.blockSignals(False)
        self._area_w_spin.setEnabled(not full)
        self._area_h_spin.setEnabled(not full)
        self._cut_markers_chk.setEnabled(not full)

        self._area_w_spin.blockSignals(True)
        self._area_w_spin.setValue(area_w)
        self._area_w_spin.blockSignals(False)

        self._area_h_spin.blockSignals(True)
        self._area_h_spin.setValue(area_h)
        self._area_h_spin.blockSignals(False)

        self._cut_markers_chk.blockSignals(True)
        self._cut_markers_chk.setChecked(cut_markers)
        self._cut_markers_chk.blockSignals(False)

        self._update_canvas_settings()

    def _save_settings(self):
        self._settings.setValue("paper_index", self._paper_combo.currentIndex())
        self._settings.setValue("full_paper", self._full_paper_chk.isChecked())
        self._settings.setValue("area_w", self._area_w_spin.value())
        self._settings.setValue("area_h", self._area_h_spin.value())
        self._settings.setValue("cut_markers", self._cut_markers_chk.isChecked())
        self._settings.setValue("orientation", self._orient_combo.currentText())
        self._settings.setValue("global_fit", self._global_fit_combo.currentText())

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _open_photos(self):
        last_dir = self._settings.value("last_open_dir", "")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Photos", last_dir,
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp)",
        )
        if not paths:
            return
        self._settings.setValue("last_open_dir", str(Path(paths[0]).parent))
        self._photo_paths = paths
        self._photo_overrides.clear()
        self._photo_pans.clear()
        self._thumb_bar.set_photos(paths)
        self._print_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self.statusBar().showMessage(f"{len(paths)} photo(s) loaded")

    def _clear_photos(self):
        self._photo_paths = []
        self._current_index = -1
        self._photo_overrides.clear()
        self._photo_pans.clear()
        self._thumb_bar.set_photos([])
        self._canvas.clear_photo()
        self._canvas.set_photo_info(None)
        self._photo_fit_combo.blockSignals(True)
        self._photo_fit_combo.setCurrentIndex(0)
        self._photo_fit_combo.blockSignals(False)
        self._photo_fit_combo.setEnabled(False)
        self._reset_crop_btn.setEnabled(False)
        self._print_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self.statusBar().showMessage("All photos cleared.")

    def _on_photo_selected(self, index: int, path: str):
        self._current_index = index
        self._canvas.set_photo(path)
        self._canvas.set_photo_info(read_photo_info(path))
        # Restore per-photo override in the combo without triggering a write-back
        override = self._photo_overrides.get(index)
        self._photo_fit_combo.blockSignals(True)
        self._photo_fit_combo.setCurrentText(override if override else "Use global setting")
        self._photo_fit_combo.blockSignals(False)
        self._photo_fit_combo.setEnabled(True)
        # Restore pan
        pan = self._photo_pans.get(index, (0.0, 0.0))
        self._canvas.set_pan(pan[0], pan[1])
        self._reset_crop_btn.setEnabled(pan != (0.0, 0.0))
        # Auto mode may flip paper orientation per photo
        self._update_canvas_settings()
        name = Path(path).name
        self.statusBar().showMessage(
            f"Photo {index + 1} / {len(self._photo_paths)}: {name}"
        )

    def _on_pan_changed(self, pan_x: float, pan_y: float):
        if self._current_index >= 0:
            self._photo_pans[self._current_index] = (pan_x, pan_y)
            self._reset_crop_btn.setEnabled(pan_x != 0.0 or pan_y != 0.0)

    def _on_reset_crop(self):
        if self._current_index >= 0:
            self._photo_pans.pop(self._current_index, None)
            self._canvas.set_pan(0.0, 0.0)
            self._reset_crop_btn.setEnabled(False)

    def _on_orientation_changed(self):
        self._update_canvas_settings()
        self._save_settings()

    def _on_global_fit_changed(self):
        self._update_canvas_settings()
        self._save_settings()

    def _on_photo_fit_changed(self, text: str):
        if self._current_index < 0:
            return
        if text == "Use global setting":
            self._photo_overrides.pop(self._current_index, None)
        else:
            self._photo_overrides[self._current_index] = text
        self._update_canvas_settings()

    def _on_crop_shadow_toggled(self, checked: bool):
        self._canvas.set_crop_shadow(checked)
        self._settings.setValue("crop_shadow", checked)

    def _on_paper_shadow_toggled(self, checked: bool):
        self._canvas.set_paper_shadow(checked)
        self._settings.setValue("paper_shadow", checked)

    def _on_paper_changed(self):
        self._update_canvas_settings()
        self._save_settings()

    def _on_cut_markers_toggled(self, checked: bool):
        self._canvas.set_cut_markers(checked)
        self._save_settings()

    def _on_full_paper_toggled(self, checked: bool):
        self._area_w_spin.setEnabled(not checked)
        self._area_h_spin.setEnabled(not checked)
        self._cut_markers_chk.setEnabled(not checked)
        if checked:
            self._cut_markers_chk.setChecked(False)
            paper = self._current_paper()
            if paper:
                self._area_w_spin.blockSignals(True)
                self._area_h_spin.blockSignals(True)
                self._area_w_spin.setValue(paper["width_in"])
                self._area_h_spin.setValue(paper["height_in"])
                self._area_w_spin.blockSignals(False)
                self._area_h_spin.blockSignals(False)
        self._update_canvas_settings()
        self._save_settings()

    def _on_print_area_changed(self):
        if not self._full_paper_chk.isChecked():
            self._update_canvas_settings()
            self._save_settings()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_paper(self) -> dict | None:
        return self._paper_combo.currentData()

    def _effective_paper_dims(self, photo_path: str | None = None) -> tuple[float, float]:
        """Return (width_in, height_in) after applying orientation setting."""
        paper = self._current_paper()
        if not paper:
            return 4.0, 6.0
        pw, ph = paper["width_in"], paper["height_in"]
        mode = self._orient_combo.currentText()
        if mode == "Landscape":
            if pw < ph:
                pw, ph = ph, pw
        elif mode == "Portrait":
            if pw > ph:
                pw, ph = ph, pw
        elif mode == "Auto" and photo_path:
            # Use cached info if this is the current photo, else open via PIL
            info = None
            idx = self._photo_paths.index(photo_path) if photo_path in self._photo_paths else -1
            if idx == self._current_index and self._canvas._photo_info:
                info = self._canvas._photo_info
                iw, ih = info.get("pixel_w", 0), info.get("pixel_h", 0)
            else:
                try:
                    img = Image.open(photo_path)
                    iw, ih = img.size
                    img.close()
                except Exception:
                    iw, ih = 0, 0
            if iw > ih and pw < ph:
                pw, ph = ph, pw
            elif ih > iw and pw > ph:
                pw, ph = ph, pw
        return pw, ph

    def _current_photo_path(self) -> str | None:
        if 0 <= self._current_index < len(self._photo_paths):
            return self._photo_paths[self._current_index]
        return None

    def _effective_fit_mode(self, index: int) -> FitMode:
        override = self._photo_overrides.get(index)
        if override:
            return FitMode(override)
        return FitMode(self._global_fit_combo.currentText())

    def _get_print_area_inches(self, photo_path: str | None = None) -> tuple[float, float]:
        pw, ph = self._effective_paper_dims(photo_path)
        if self._full_paper_chk.isChecked():
            return pw, ph
        return min(self._area_w_spin.value(), pw), min(self._area_h_spin.value(), ph)

    def _update_canvas_settings(self):
        photo_path = self._current_photo_path()
        pw, ph = self._effective_paper_dims(photo_path)
        self._canvas.set_paper(pw, ph)

        if self._full_paper_chk.isChecked():
            self._canvas.set_print_area(pw, ph)
            self._canvas.set_cut_markers(False)
        else:
            aw = min(self._area_w_spin.value(), pw)
            ah = min(self._area_h_spin.value(), ph)
            self._canvas.set_print_area(aw, ah)
            self._canvas.set_cut_markers(self._cut_markers_chk.isChecked())
        self._canvas.set_fit_mode(self._effective_fit_mode(self._current_index))
        self._canvas.set_crop_shadow(self._crop_shadow_action.isChecked())
        self._canvas.set_paper_shadow(self._paper_shadow_chk.isChecked())

    # ------------------------------------------------------------------
    # Printing
    # ------------------------------------------------------------------

    def _print_all(self):
        if not self._photo_paths:
            return

        paper = self._current_paper()
        if not paper:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)

        # QPageSize always takes portrait dims (shorter side first)
        first_path = self._photo_paths[0]
        eff_pw, eff_ph = self._effective_paper_dims(first_path)
        base_w_mm = min(paper["width_in"], paper["height_in"]) * 25.4
        base_h_mm = max(paper["width_in"], paper["height_in"]) * 25.4
        page_size = QPageSize(QSizeF(base_w_mm, base_h_mm), QPageSize.Unit.Millimeter, paper["name"])
        first_orient = (
            QPageLayout.Orientation.Landscape
            if eff_pw > eff_ph
            else QPageLayout.Orientation.Portrait
        )
        # setPageLayout THEN setFullPage — setPageLayout resets full-page mode
        printer.setPageLayout(QPageLayout(page_size, first_orient, QMarginsF(0, 0, 0, 0)))
        printer.setFullPage(True)

        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Re-assert after dialog — dialog can also reset full-page mode
        printer.setFullPage(True)

        native_dpi = printer.resolution()
        dpi = min(native_dpi, _MAX_PRINT_DPI)
        # Scale: our coords are in dpi-space; printer device pixels are in native_dpi-space
        dpi_scale = native_dpi / dpi

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self, "Print Error", "Failed to start the print job.")
            return

        def _apply_transform():
            if dpi_scale != 1.0:
                t = QTransform()
                t.scale(dpi_scale, dpi_scale)
                painter.setTransform(t)

        _apply_transform()

        try:
            for i, path in enumerate(self._photo_paths):
                eff_pw, eff_ph = self._effective_paper_dims(path)
                orient = (
                    QPageLayout.Orientation.Landscape
                    if eff_pw > eff_ph
                    else QPageLayout.Orientation.Portrait
                )
                if i > 0:
                    # setPageLayout resets full-page; re-assert before newPage
                    printer.setPageLayout(QPageLayout(page_size, orient, QMarginsF(0, 0, 0, 0)))
                    printer.setFullPage(True)
                    printer.newPage()
                    _apply_transform()  # newPage resets painter transform

                print_w_in, print_h_in = self._get_print_area_inches(path)
                print_w_px = int(print_w_in * dpi)
                print_h_px = int(print_h_in * dpi)
                paper_w_px = int(eff_pw * dpi)
                paper_h_px = int(eff_ph * dpi)
                offset_x = (paper_w_px - print_w_px) // 2
                offset_y = (paper_h_px - print_h_px) // 2

                self.statusBar().showMessage(
                    f"Printing {i + 1} / {len(self._photo_paths)}: {Path(path).name}…"
                )
                QApplication.processEvents()

                img = Image.open(path).convert("RGB")
                fit = self._effective_fit_mode(i)
                pan = self._photo_pans.get(i, (0.0, 0.0))
                cropped = render_image(img, print_w_px, print_h_px, fit, pan[0], pan[1])
                img_bytes = cropped.tobytes("raw", "RGB")
                qimg = QImage(
                    img_bytes,
                    print_w_px, print_h_px,
                    print_w_px * 3,
                    QImage.Format.Format_RGB888,
                ).copy()

                painter.drawImage(offset_x, offset_y, qimg)

                # Cut markers
                if self._cut_markers_chk.isEnabled() and self._cut_markers_chk.isChecked():
                    gap_px = int(0.1 * dpi)
                    mark_px = int(0.2 * dpi)
                    pen_w = max(1, int(dpi / 300))
                    painter.setPen(QPen(QColor(0, 0, 0), pen_w, Qt.PenStyle.SolidLine))
                    corners = [
                        (offset_x,               offset_y,               -1, -1),
                        (offset_x + print_w_px,  offset_y,               +1, -1),
                        (offset_x,               offset_y + print_h_px,  -1, +1),
                        (offset_x + print_w_px,  offset_y + print_h_px,  +1, +1),
                    ]
                    for cx, cy, dx, dy in corners:
                        painter.drawLine(cx + dx * gap_px, cy, cx + dx * (gap_px + mark_px), cy)
                        painter.drawLine(cx, cy + dy * gap_px, cx, cy + dy * (gap_px + mark_px))
        finally:
            painter.end()

        self.statusBar().showMessage(
            f"Done — sent {len(self._photo_paths)} photo(s) to printer."
        )
