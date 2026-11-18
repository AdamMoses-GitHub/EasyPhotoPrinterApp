import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QComboBox, QLabel, QDoubleSpinBox, QPushButton,
    QFileDialog, QCheckBox, QMessageBox, QStatusBar, QFrame,
    QDialog, QApplication, QMenu, QToolButton, QWidgetAction, QFormLayout, QSizePolicy,
    QScrollArea, QSplitter,
)
from PySide6.QtCore import Qt, QSettings, QSizeF, QMarginsF
from PySide6.QtGui import QPainter, QImage, QPageSize, QPageLayout, QTransform, QPen, QColor
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from ui.photo_canvas import PhotoCanvas
from ui.thumbnail_bar import ThumbnailBar
from core.image_processor import ColorMode, FitMode, render_color_image
from core.photo_info import load_oriented_image, oriented_image_size, read_photo_info

_CONFIG = Path(__file__).parent.parent / "config" / "paper_sizes.json"
_MAX_PRINT_DPI = 600  # cap to keep memory/time reasonable
_DEFAULT_PAPER_SIZES = [
    {"name": "3.5x5\"", "width_in": 3.5, "height_in": 5.0},
    {"name": "4x6\"", "width_in": 4.0, "height_in": 6.0},
    {"name": "5x7\"", "width_in": 5.0, "height_in": 7.0},
    {"name": "6x8\"", "width_in": 6.0, "height_in": 8.0},
    {"name": "8.5x11\" (Letter)", "width_in": 8.5, "height_in": 11.0},
    {"name": "A4", "width_in": 8.27, "height_in": 11.69},
]


def _load_paper_sizes() -> list[dict]:
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        sizes = data.get("sizes", [])
        valid_sizes = [
            s for s in sizes
            if isinstance(s, dict)
            and isinstance(s.get("name"), str)
            and isinstance(s.get("width_in"), (int, float))
            and isinstance(s.get("height_in"), (int, float))
            and s["width_in"] > 0
            and s["height_in"] > 0
        ]
        if valid_sizes:
            return valid_sizes
    except Exception:
        pass
    return list(_DEFAULT_PAPER_SIZES)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Printer App")
        self.resize(960, 720)

        self._photo_paths: list[str] = []
        self._current_index: int = -1
        self._photo_overrides: dict[int, str | None] = {}  # index -> FitMode value or None
        self._photo_pans: dict[int, tuple[float, float]] = {}  # index -> (pan_x, pan_y)
        self._photo_colors: dict[int, ColorMode] = {}
        self._photo_dithers: dict[int, bool] = {}
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

        self._build_menu_bar()

        self._settings_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._settings_splitter.setChildrenCollapsible(False)
        self._settings_scroll = QScrollArea()
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._settings_scroll.setMinimumWidth(280)
        self._settings_scroll.setWidget(self._build_settings_sidebar())
        self._settings_splitter.addWidget(self._settings_scroll)
        self._canvas = PhotoCanvas()
        self._canvas.pan_changed.connect(self._on_pan_changed)
        self._settings_splitter.addWidget(self._canvas)
        self._settings_splitter.setStretchFactor(0, 0)
        self._settings_splitter.setStretchFactor(1, 1)
        self._settings_splitter.setSizes([300, 660])
        self._settings_splitter.splitterMoved.connect(self._save_splitter_state)
        self._photo_browser_splitter = QSplitter(Qt.Orientation.Vertical)
        self._photo_browser_splitter.setChildrenCollapsible(False)
        self._photo_browser_splitter.addWidget(self._settings_splitter)

        self._thumb_bar = ThumbnailBar()
        self._thumb_bar.photo_selected.connect(self._on_photo_selected)
        self._photo_browser_splitter.addWidget(self._thumb_bar)
        self._photo_browser_splitter.setStretchFactor(0, 1)
        self._photo_browser_splitter.setStretchFactor(1, 0)
        self._photo_browser_splitter.setSizes([560, 100])
        self._photo_browser_splitter.splitterMoved.connect(
            self._save_photo_browser_splitter_state,
        )
        layout.addWidget(self._photo_browser_splitter, stretch=1)

        self.setStatusBar(QStatusBar())

    def _build_settings_sidebar(self) -> QWidget:
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.addWidget(self._build_action_buttons())

        heading = QLabel("All photos")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        self._add_settings_section(layout, "Paper", self._build_paper_settings())
        self._add_settings_section(layout, "Layout", self._build_layout_settings(), expanded=False)
        self._add_settings_section(layout, "Appearance", self._build_appearance_settings())

        heading = QLabel("Selected photo")
        heading.setFont(font)
        layout.addWidget(heading)
        hint = QLabel("Overrides apply only to the selected thumbnail.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self._build_photo_settings())

        layout.addStretch()
        for combo in sidebar.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(16)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        return sidebar

    def _build_action_buttons(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._open_btn = QPushButton("Open Photos…")
        self._open_btn.clicked.connect(self._open_photos)
        layout.addWidget(self._open_btn)

        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._clear_photos)
        layout.addWidget(self._clear_btn)

        self._print_btn = QPushButton("Print All")
        self._print_btn.setEnabled(False)
        self._print_btn.clicked.connect(self._print_all)
        layout.addWidget(self._print_btn)
        return panel

    def _add_settings_section(self, layout: QVBoxLayout, title: str, content: QWidget,
                              expanded: bool = True):
        toggle = QToolButton()
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toggle.toggled.connect(content.setVisible)
        content.setVisible(expanded)
        toggle.toggled.connect(
            lambda checked: toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )
        )
        layout.addWidget(toggle)
        layout.addWidget(content)

    def _build_photo_settings(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self._photo_fit_combo = QComboBox()
        self._photo_fit_combo.addItem("Use global setting")
        for m in FitMode:
            self._photo_fit_combo.addItem(m.value)
        self._photo_fit_combo.setEnabled(False)
        self._photo_fit_combo.currentTextChanged.connect(self._on_photo_fit_changed)
        form.addRow("Fit:", self._photo_fit_combo)

        self._reset_crop_btn = QPushButton("Reset crop")
        self._reset_crop_btn.setEnabled(False)
        self._reset_crop_btn.setToolTip("Re-center the crop (undo manual pan)")
        self._reset_crop_btn.clicked.connect(self._on_reset_crop)
        self._photo_color_combo = QComboBox()
        self._photo_color_combo.addItem("Use global setting")
        for mode in ColorMode:
            self._photo_color_combo.addItem(mode.value)
        self._photo_color_combo.setEnabled(False)
        self._photo_color_combo.currentTextChanged.connect(self._on_photo_color_changed)
        form.addRow("Color mode:", self._photo_color_combo)

        self._photo_dither_combo = QComboBox()
        self._photo_dither_combo.addItems(["Global dithering", "Dithering on", "Dithering off"])
        self._photo_dither_combo.setEnabled(False)
        self._photo_dither_combo.currentIndexChanged.connect(self._on_photo_dither_changed)
        form.addRow("Dithering:", self._photo_dither_combo)
        form.addRow(self._reset_crop_btn)
        return panel

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

        help_menu: QMenu = self.menuBar().addMenu("&Help")
        self._about_action = help_menu.addAction("&About EasyPhotoPrinter")
        self._about_action.triggered.connect(self._show_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About EasyPhotoPrinter",
            "<h3>EasyPhotoPrinter</h3>"
            "<p>Arrange, preview, and batch-print photos at your chosen size.</p>"
            '<p><a href="https://github.com/AdamMoses-GitHub/EasyPhotoPrinterApp">'
            "Project website</a></p>",
        )

    def _build_paper_settings(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self._paper_combo = QComboBox()
        for s in self._paper_sizes:
            self._paper_combo.addItem(s["name"], s)
        self._paper_combo.currentIndexChanged.connect(self._on_paper_changed)
        form.addRow("Paper:", self._paper_combo)

        self._orient_combo = QComboBox()
        self._orient_combo.addItems(["Portrait", "Landscape", "Auto"])
        self._orient_combo.setToolTip(
            "Portrait / Landscape: force orientation for all photos.\n"
            "Auto: rotate paper to match each photo's aspect ratio."
        )
        self._orient_combo.currentIndexChanged.connect(self._on_orientation_changed)
        form.addRow("Orientation:", self._orient_combo)
        return panel

    def _build_appearance_settings(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self._global_fit_combo = QComboBox()
        for m in FitMode:
            self._global_fit_combo.addItem(m.value)
        self._global_fit_combo.setToolTip(
            "Fill (crop): zoom to fill, crop edges\n"
            "Fit (letterbox): whole photo visible, white bars on short sides\n"
            "Stretch: distort to fill exactly"
        )
        self._global_fit_combo.currentTextChanged.connect(self._on_global_fit_changed)
        form.addRow("Fit:", self._global_fit_combo)

        self._global_color_combo = QComboBox()
        for mode in ColorMode:
            self._global_color_combo.addItem(mode.value)
        self._global_color_combo.setToolTip(
            "Changes preview and print appearance without modifying original files.\n"
            "Does not control the printer's internal color depth or ink usage."
        )
        self._global_color_combo.currentTextChanged.connect(self._on_global_color_changed)
        form.addRow("Color mode:", self._global_color_combo)
        self._dither_chk = QCheckBox("Dithering")
        self._dither_chk.setChecked(True)
        self._dither_chk.setToolTip(
            "Use dots to approximate missing tones in indexed color and black & white.\n"
            "May make photos look grainier. Preview dot patterns vary with output resolution."
        )
        self._dither_chk.toggled.connect(self._on_global_color_changed)
        form.addRow(self._dither_chk)
        return panel

    def _build_layout_settings(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self._size_mode_combo = QComboBox()
        self._size_mode_combo.addItems(["Full paper", "Custom size"])
        self._size_mode_combo.currentTextChanged.connect(self._on_size_mode_changed)
        form.addRow("Print size:", self._size_mode_combo)

        self._area_w_spin = QDoubleSpinBox()
        self._area_w_spin.setRange(0.5, 50.0)
        self._area_w_spin.setSingleStep(0.5)
        self._area_w_spin.setDecimals(2)
        self._area_w_spin.setSuffix("\"")
        self._area_w_spin.setEnabled(False)
        self._area_w_spin.valueChanged.connect(self._on_print_area_changed)
        form.addRow("Width:", self._area_w_spin)

        self._area_h_spin = QDoubleSpinBox()
        self._area_h_spin.setRange(0.5, 50.0)
        self._area_h_spin.setSingleStep(0.5)
        self._area_h_spin.setDecimals(2)
        self._area_h_spin.setSuffix("\"")
        self._area_h_spin.setEnabled(False)
        self._area_h_spin.valueChanged.connect(self._on_print_area_changed)
        form.addRow("Height:", self._area_h_spin)

        self._margin_edges_btn = QToolButton()
        self._margin_edges_btn.setText("Margins...")
        self._margin_edges_btn.setToolTip("Configure margins inside the selected print size")
        self._margin_edges_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._margin_edges_menu = QMenu(self)
        margins_panel = QWidget(self._margin_edges_menu)
        margins_layout = QFormLayout(margins_panel)
        self._margin_chk = QCheckBox("Add margins")
        self._margin_chk.toggled.connect(self._on_margin_toggled)
        margins_layout.addRow(self._margin_chk)
        self._margin_mode_combo = QComboBox()
        self._margin_mode_combo.addItems(["Inches", "Percent"])
        self._margin_mode_combo.setToolTip("Set margins in physical inches or as a percentage of the print area")
        self._margin_mode_combo.setEnabled(False)
        self._margin_mode_combo.currentTextChanged.connect(self._on_margin_mode_changed)
        margins_layout.addRow("Unit:", self._margin_mode_combo)
        self._margin_spin = QDoubleSpinBox()
        self._margin_spin.setRange(0.0, 10.0)
        self._margin_spin.setSingleStep(0.125)
        self._margin_spin.setDecimals(3)
        self._margin_spin.setSuffix('"')
        self._margin_spin.setValue(0.25)
        self._margin_spin.setEnabled(False)
        self._margin_spin.valueChanged.connect(self._on_margin_changed)
        margins_layout.addRow("All sides:", self._margin_spin)
        self._separate_margins_chk = QCheckBox("Set edges separately")
        self._separate_margins_chk.toggled.connect(self._on_separate_margins_toggled)
        margins_layout.addRow(self._separate_margins_chk)
        self._margin_edge_spins: dict[str, QDoubleSpinBox] = {}
        for edge in ("Top", "Right", "Bottom", "Left"):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 10.0)
            spin.setSingleStep(0.125)
            spin.setDecimals(3)
            spin.setSuffix('"')
            spin.setValue(0.25)
            spin.setEnabled(False)
            spin.valueChanged.connect(self._on_margin_changed)
            self._margin_edge_spins[edge.lower()] = spin
            margins_layout.addRow(f"{edge}:", spin)
        margins_action = QWidgetAction(self._margin_edges_menu)
        margins_action.setDefaultWidget(margins_panel)
        self._margin_edges_menu.addAction(margins_action)
        self._margin_edges_btn.setMenu(self._margin_edges_menu)
        form.addRow(self._margin_edges_btn)

        self._cut_markers_chk = QCheckBox("Cut markers")
        self._cut_markers_chk.setEnabled(False)
        self._cut_markers_chk.toggled.connect(self._on_cut_markers_toggled)
        form.addRow(self._cut_markers_chk)

        return panel

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _restore_settings(self):
        paper_idx = int(self._settings.value("paper_index", 1))
        paper_idx = max(0, min(paper_idx, self._paper_combo.count() - 1))

        full = self._settings.value("full_paper", True, type=bool)
        area_w = float(self._settings.value("area_w", 4.0))
        area_h = float(self._settings.value("area_h", 6.0))
        margin_enabled = self._settings.value("margin_enabled", False, type=bool)
        margin_in = float(self._settings.value("margin_in", 0.25))
        margin_mode = self._settings.value("margin_mode", "Inches")
        separate_margins = self._settings.value("separate_margins", False, type=bool)
        margin_top = float(self._settings.value("margin_top", margin_in))
        margin_right = float(self._settings.value("margin_right", margin_in))
        margin_bottom = float(self._settings.value("margin_bottom", margin_in))
        margin_left = float(self._settings.value("margin_left", margin_in))
        cut_markers = self._settings.value("cut_markers", False, type=bool)
        orient = self._settings.value("orientation", "Auto")
        global_fit = self._settings.value("global_fit", FitMode.FILL.value)
        crop_shadow = self._settings.value("crop_shadow", True, type=bool)
        paper_shadow = self._settings.value("paper_shadow", True, type=bool)
        global_color = str(self._settings.value("global_color", ColorMode.FULL.value))
        dither = bool(self._settings.value("dither", True, type=bool))
        splitter_state = self._settings.value("settings_splitter_state")
        if splitter_state is not None:
            self._settings_splitter.restoreState(splitter_state)
        photo_browser_splitter_state = self._settings.value(
            "photo_browser_splitter_state",
        )
        if photo_browser_splitter_state is not None:
            self._photo_browser_splitter.restoreState(photo_browser_splitter_state)

        self._global_color_combo.blockSignals(True)
        idx = self._global_color_combo.findText(global_color)
        self._global_color_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._global_color_combo.blockSignals(False)
        self._dither_chk.blockSignals(True)
        self._dither_chk.setChecked(dither)
        self._dither_chk.blockSignals(False)

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

        self._size_mode_combo.blockSignals(True)
        self._size_mode_combo.setCurrentText("Full paper" if full else "Custom size")
        self._size_mode_combo.blockSignals(False)
        self._area_w_spin.setEnabled(not full)
        self._area_h_spin.setEnabled(not full)
        self._cut_markers_chk.setEnabled(not full)

        self._area_w_spin.blockSignals(True)
        self._area_w_spin.setValue(area_w)
        self._area_w_spin.blockSignals(False)

        self._area_h_spin.blockSignals(True)
        self._area_h_spin.setValue(area_h)
        self._area_h_spin.blockSignals(False)

        self._margin_chk.blockSignals(True)
        self._margin_chk.setChecked(margin_enabled)
        self._margin_chk.blockSignals(False)

        self._margin_mode_combo.blockSignals(True)
        mode_idx = self._margin_mode_combo.findText(margin_mode)
        self._margin_mode_combo.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
        self._margin_mode_combo.blockSignals(False)

        self._margin_spin.blockSignals(True)
        self._margin_spin.setValue(margin_in)
        self._margin_spin.blockSignals(False)

        self._separate_margins_chk.blockSignals(True)
        self._separate_margins_chk.setChecked(separate_margins)
        self._separate_margins_chk.blockSignals(False)
        for edge, value in {
            "top": margin_top,
            "right": margin_right,
            "bottom": margin_bottom,
            "left": margin_left,
        }.items():
            spin = self._margin_edge_spins[edge]
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._configure_margin_spinboxes()
        self._update_margin_controls()

        self._cut_markers_chk.blockSignals(True)
        self._cut_markers_chk.setChecked(cut_markers)
        self._cut_markers_chk.blockSignals(False)

        self._update_canvas_settings()

    def _save_settings(self):
        self._settings.setValue(
            "settings_splitter_state", self._settings_splitter.saveState(),
        )
        self._settings.setValue(
            "photo_browser_splitter_state", self._photo_browser_splitter.saveState(),
        )
        self._settings.setValue("paper_index", self._paper_combo.currentIndex())
        self._settings.setValue("full_paper", self._is_full_paper())
        self._settings.setValue("area_w", self._area_w_spin.value())
        self._settings.setValue("area_h", self._area_h_spin.value())
        self._settings.setValue("margin_enabled", self._margin_chk.isChecked())
        self._settings.setValue("margin_in", self._margin_spin.value())
        self._settings.setValue("margin_mode", self._margin_mode_combo.currentText())
        self._settings.setValue("separate_margins", self._separate_margins_chk.isChecked())
        for edge, spin in self._margin_edge_spins.items():
            self._settings.setValue(f"margin_{edge}", spin.value())
        self._settings.setValue("cut_markers", self._cut_markers_chk.isChecked())
        self._settings.setValue("orientation", self._orient_combo.currentText())
        self._settings.setValue("global_fit", self._global_fit_combo.currentText())
        self._settings.setValue("global_color", self._global_color_combo.currentText())
        self._settings.setValue("dither", self._dither_chk.isChecked())

    def _save_splitter_state(self, _position: int, _index: int):
        self._settings.setValue(
            "settings_splitter_state", self._settings_splitter.saveState(),
        )

    def _save_photo_browser_splitter_state(self, _position: int, _index: int):
        self._settings.setValue(
            "photo_browser_splitter_state", self._photo_browser_splitter.saveState(),
        )

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
        self._photo_colors.clear()
        self._photo_dithers.clear()
        self._thumb_bar.set_photos(paths)
        self._print_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self.statusBar().showMessage(f"{len(paths)} photo(s) loaded")

    def _clear_photos(self):
        self._photo_paths = []
        self._current_index = -1
        self._photo_overrides.clear()
        self._photo_pans.clear()
        self._photo_colors.clear()
        self._photo_dithers.clear()
        self._thumb_bar.set_photos([])
        self._canvas.clear_photo()
        self._canvas.set_photo_info(None)
        self._photo_fit_combo.blockSignals(True)
        self._photo_fit_combo.setCurrentIndex(0)
        self._photo_fit_combo.blockSignals(False)
        self._photo_fit_combo.setEnabled(False)
        for combo in (self._photo_color_combo, self._photo_dither_combo):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            combo.setEnabled(False)
        self._reset_crop_btn.setEnabled(False)
        self._print_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self.statusBar().showMessage("All photos cleared.")

    def _on_photo_selected(self, index: int, path: str):
        self._current_index = index
        try:
            self._canvas.set_photo(path)
        except (OSError, ValueError) as exc:
            self._canvas.clear_photo()
            QMessageBox.warning(self, "Preview Error", f"Cannot preview {Path(path).name}:\n{exc}")
        self._canvas.set_photo_info(read_photo_info(path))
        # Restore per-photo override in the combo without triggering a write-back
        override = self._photo_overrides.get(index)
        self._photo_fit_combo.blockSignals(True)
        self._photo_fit_combo.setCurrentText(override if override else "Use global setting")
        self._photo_fit_combo.blockSignals(False)
        self._photo_fit_combo.setEnabled(True)
        color = self._photo_colors.get(index)
        self._photo_color_combo.blockSignals(True)
        self._photo_color_combo.setCurrentText(color.value if color else "Use global setting")
        self._photo_color_combo.blockSignals(False)
        self._photo_color_combo.setEnabled(True)
        dither = self._photo_dithers.get(index)
        self._photo_dither_combo.blockSignals(True)
        self._photo_dither_combo.setCurrentIndex(0 if dither is None else (1 if dither else 2))
        self._photo_dither_combo.blockSignals(False)
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

    def _on_global_color_changed(self):
        self._update_canvas_settings()
        self._save_settings()

    def _on_photo_color_changed(self, text: str):
        if self._current_index < 0:
            return
        if text == "Use global setting":
            self._photo_colors.pop(self._current_index, None)
        else:
            self._photo_colors[self._current_index] = ColorMode(text)
        self._update_canvas_settings()

    def _on_photo_dither_changed(self, index: int):
        if self._current_index < 0:
            return
        if index == 0:
            self._photo_dithers.pop(self._current_index, None)
        else:
            self._photo_dithers[self._current_index] = index == 1
        self._update_canvas_settings()

    def _effective_color_mode(self, index: int) -> ColorMode:
        return self._photo_colors.get(index, ColorMode(self._global_color_combo.currentText()))

    def _effective_dither(self, index: int) -> bool:
        return self._photo_dithers.get(index, self._dither_chk.isChecked())

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

    def _on_size_mode_changed(self):
        full_paper = self._is_full_paper()
        self._area_w_spin.setEnabled(not full_paper)
        self._area_h_spin.setEnabled(not full_paper)
        self._cut_markers_chk.setEnabled(not full_paper)
        if full_paper:
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
        if not self._is_full_paper():
            self._update_canvas_settings()
            self._save_settings()

    def _on_margin_toggled(self, checked: bool):
        self._update_margin_controls()
        self._update_canvas_settings()
        self._save_settings()

    def _on_margin_mode_changed(self):
        self._configure_margin_spinboxes()
        self._update_canvas_settings()
        self._save_settings()

    def _on_separate_margins_toggled(self):
        self._update_margin_controls()
        self._update_canvas_settings()
        self._save_settings()

    def _on_margin_changed(self):
        if self._margin_chk.isChecked():
            self._update_canvas_settings()
            self._save_settings()

    def _configure_margin_spinboxes(self):
        is_percent = self._margin_mode_combo.currentText() == "Percent"
        maximum = 99.0 if is_percent else 10.0
        step = 0.5 if is_percent else 0.125
        decimals = 1 if is_percent else 3
        suffix = "%" if is_percent else '"'
        for spin in [self._margin_spin, *self._margin_edge_spins.values()]:
            spin.setRange(0.0, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setSuffix(suffix)

    def _update_margin_controls(self):
        enabled = self._margin_chk.isChecked()
        separate = self._separate_margins_chk.isChecked()
        self._margin_mode_combo.setEnabled(enabled)
        self._margin_spin.setEnabled(enabled and not separate)
        self._margin_edges_btn.setEnabled(True)
        self._margin_edges_btn.setText("Margins..." if not enabled else "Margins: on")
        for spin in self._margin_edge_spins.values():
            spin.setEnabled(enabled and separate)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_paper(self) -> dict | None:
        return self._paper_combo.currentData()

    def _is_full_paper(self) -> bool:
        return self._size_mode_combo.currentText() == "Full paper"

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
                    iw, ih = oriented_image_size(photo_path)
                except (OSError, ValueError):
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
        if self._is_full_paper():
            return pw, ph
        return min(self._area_w_spin.value(), pw), min(self._area_h_spin.value(), ph)

    def _get_margins_inches(self, print_w_in: float, print_h_in: float) -> tuple[float, float, float, float]:
        if not self._margin_chk.isChecked():
            return 0.0, 0.0, 0.0, 0.0
        if self._separate_margins_chk.isChecked():
            top = self._margin_edge_spins["top"].value()
            right = self._margin_edge_spins["right"].value()
            bottom = self._margin_edge_spins["bottom"].value()
            left = self._margin_edge_spins["left"].value()
        else:
            top = right = bottom = left = self._margin_spin.value()

        if self._margin_mode_combo.currentText() == "Percent":
            top = print_h_in * top / 100
            bottom = print_h_in * bottom / 100
            right = print_w_in * right / 100
            left = print_w_in * left / 100

        def clamp_pair(first: float, second: float, dimension: float) -> tuple[float, float]:
            maximum_total = max(0.0, dimension - 0.01)
            total = first + second
            if total <= maximum_total or total == 0:
                return first, second
            scale = maximum_total / total
            return first * scale, second * scale

        left, right = clamp_pair(left, right, print_w_in)
        top, bottom = clamp_pair(top, bottom, print_h_in)
        return top, right, bottom, left

    def _update_canvas_settings(self):
        photo_path = self._current_photo_path()
        pw, ph = self._effective_paper_dims(photo_path)
        self._canvas.set_paper(pw, ph)

        if self._is_full_paper():
            self._canvas.set_print_area(pw, ph)
            self._canvas.set_cut_markers(False)
            self._canvas.set_margins(*self._get_margins_inches(pw, ph))
        else:
            aw = min(self._area_w_spin.value(), pw)
            ah = min(self._area_h_spin.value(), ph)
            self._canvas.set_print_area(aw, ah)
            self._canvas.set_cut_markers(self._cut_markers_chk.isChecked())
            self._canvas.set_margins(*self._get_margins_inches(aw, ah))
        self._canvas.set_fit_mode(self._effective_fit_mode(self._current_index))
        self._canvas.set_crop_shadow(self._crop_shadow_action.isChecked())
        self._canvas.set_paper_shadow(self._paper_shadow_chk.isChecked())
        self._dither_chk.setEnabled(
            ColorMode(self._global_color_combo.currentText()).supports_dithering
        )
        color = self._effective_color_mode(self._current_index)
        self._photo_dither_combo.setEnabled(
            self._current_index >= 0 and color.supports_dithering
        )
        self._canvas.set_color_mode(color, self._effective_dither(self._current_index))

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

        failures: list[str] = []
        page_started = False
        try:
            for i, path in enumerate(self._photo_paths):
                eff_pw, eff_ph = self._effective_paper_dims(path)
                orient = (
                    QPageLayout.Orientation.Landscape
                    if eff_pw > eff_ph
                    else QPageLayout.Orientation.Portrait
                )
                print_w_in, print_h_in = self._get_print_area_inches(path)
                top_in, right_in, bottom_in, left_in = self._get_margins_inches(
                    print_w_in, print_h_in,
                )
                print_w_px = int(print_w_in * dpi)
                print_h_px = int(print_h_in * dpi)
                top_px = int(top_in * dpi)
                right_px = int(right_in * dpi)
                bottom_px = int(bottom_in * dpi)
                left_px = int(left_in * dpi)
                image_w_px = max(1, print_w_px - left_px - right_px)
                image_h_px = max(1, print_h_px - top_px - bottom_px)
                paper_w_px = int(eff_pw * dpi)
                paper_h_px = int(eff_ph * dpi)
                offset_x = (paper_w_px - print_w_px) // 2
                offset_y = (paper_h_px - print_h_px) // 2
                image_offset_x = offset_x + left_px
                image_offset_y = offset_y + top_px

                self.statusBar().showMessage(
                    f"Printing {i + 1} / {len(self._photo_paths)}: {Path(path).name}…"
                )
                QApplication.processEvents()

                try:
                    rgb = load_oriented_image(path).convert("RGB")
                    fit = self._effective_fit_mode(i)
                    pan = self._photo_pans.get(i, (0.0, 0.0))
                    cropped = render_color_image(
                        rgb, image_w_px, image_h_px, fit, pan[0], pan[1],
                        self._effective_color_mode(i), self._effective_dither(i),
                    )
                    img_bytes = cropped.tobytes("raw", "RGB")
                    qimg = QImage(
                        img_bytes,
                        image_w_px, image_h_px,
                        image_w_px * 3,
                        QImage.Format.Format_RGB888,
                    ).copy()
                except Exception as exc:
                    failures.append(f"{Path(path).name}: {exc}")
                    continue

                if page_started:
                    # setPageLayout resets full-page; re-assert before newPage.
                    printer.setPageLayout(QPageLayout(page_size, orient, QMarginsF(0, 0, 0, 0)))
                    printer.setFullPage(True)
                    if not printer.newPage():
                        failures.append(f"{Path(path).name}: failed to start a new page.")
                        continue
                    _apply_transform()  # newPage resets painter transform
                elif i > 0:
                    # The first photo failed, so orient this first printed page.
                    printer.setPageLayout(QPageLayout(page_size, orient, QMarginsF(0, 0, 0, 0)))
                    printer.setFullPage(True)
                    _apply_transform()
                page_started = True

                painter.drawImage(image_offset_x, image_offset_y, qimg)

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

        sent_count = len(self._photo_paths) - len(failures)
        if failures:
            preview = "\n".join(failures[:5])
            extra = "" if len(failures) <= 5 else f"\n...and {len(failures) - 5} more"
            QMessageBox.warning(
                self,
                "Some Photos Failed",
                f"Sent {sent_count} of {len(self._photo_paths)} photo(s).\n\n"
                f"Failed files:\n{preview}{extra}",
            )
        self.statusBar().showMessage(f"Done: sent {sent_count} photo(s) to printer.")
