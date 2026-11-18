import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QDialog, QToolBar, QToolButton, QLabel, QPushButton
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QSignalSpy

from core.image_processor import (
    ColorMode, FitMode, apply_color_mode, render_color_image, render_image,
)
from core.photo_info import read_photo_info
from ui.main_window import MainWindow


def gradient() -> Image.Image:
    image = Image.new("RGB", (128, 128))
    image.putdata([
        (x * 2, y * 2, (x + y) % 256)
        for y in range(128) for x in range(128)
    ])
    return image


class ColorProcessingTests(unittest.TestCase):
    def test_output_limits_and_original_unchanged(self):
        source = gradient()
        original = source.tobytes()
        for mode, maximum in (
            (ColorMode.INDEXED_256, 256),
            (ColorMode.INDEXED_16, 16),
            (ColorMode.GRAYSCALE, 256),
            (ColorMode.BLACK_WHITE, 2),
        ):
            for dither in (False, True):
                with self.subTest(mode=mode, dither=dither):
                    result = render_color_image(
                        source, 97, 81, color_mode=mode, dither=dither,
                    )
                    self.assertEqual(result.mode, "RGB")
                    self.assertEqual(result.size, (97, 81))
                    colors = result.getcolors(maxcolors=maximum)
                    self.assertIsNotNone(colors)
                    if mode == ColorMode.GRAYSCALE:
                        self.assertEqual(result.getchannel("R").tobytes(),
                                         result.getchannel("G").tobytes())
                        self.assertEqual(result.getchannel("G").tobytes(),
                                         result.getchannel("B").tobytes())
                    if mode == ColorMode.BLACK_WHITE:
                        self.assertLessEqual(set(result.tobytes()), {0, 255})
        self.assertEqual(source.tobytes(), original)

    def test_full_color_preserves_existing_rendering(self):
        source = gradient()
        for mode in FitMode:
            for pan in (-1.0, 0.0, 1.0):
                with self.subTest(mode=mode, pan=pan):
                    expected = render_image(source, 71, 103, mode, pan, -pan)
                    actual = render_color_image(source, 71, 103, mode, pan, -pan)
                    self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_dithering_changes_reduced_output_only(self):
        source = gradient()
        for mode in ColorMode:
            with self.subTest(mode=mode):
                plain = apply_color_mode(source, mode, False).tobytes()
                dithered = apply_color_mode(source, mode, True).tobytes()
                if mode.supports_dithering:
                    self.assertNotEqual(plain, dithered)
                else:
                    self.assertEqual(plain, dithered)

    def test_conversion_is_after_resize_and_crop(self):
        source = gradient()
        for fit in FitMode:
            expected = apply_color_mode(
                render_image(source, 37, 59, fit, 0.7, -0.5),
                ColorMode.INDEXED_16, True, preserve_white=fit == FitMode.FIT,
            )
            actual = render_color_image(
                source, 37, 59, fit, 0.7, -0.5, ColorMode.INDEXED_16, True,
            )
            self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_letterbox_stays_white_within_palette_limit(self):
        source = Image.new("RGB", (90, 60))
        source.putdata([
            (200 + x // 2, 200 + y // 2, 230)
            for y in range(60) for x in range(90)
        ])
        for mode in ColorMode:
            for dither in (False, True):
                with self.subTest(mode=mode, dither=dither):
                    result = render_color_image(
                        source, 91, 62, FitMode.FIT, color_mode=mode, dither=dither,
                    )
                    self.assertEqual(result.getpixel((0, 61)), (255, 255, 255))
                    if mode in (ColorMode.INDEXED_16, ColorMode.INDEXED_256):
                        maximum = 16 if mode == ColorMode.INDEXED_16 else 256
                        self.assertIsNotNone(result.getcolors(maxcolors=maximum))

    def test_small_fit_and_invalid_dimensions(self):
        source = Image.new("RGB", (1000, 1), "red")
        self.assertEqual(
            render_color_image(source, 1, 1, FitMode.FIT).size, (1, 1),
        )
        with self.assertRaises(ValueError):
            render_color_image(source, 0, 1)


class ColorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "photo.png"
        gradient().save(self.path)
        self.original = self.path.read_bytes()
        self.settings = QSettings(
            str(self.folder / "settings.ini"), QSettings.Format.IniFormat,
        )
        self.settings_patch = patch("ui.main_window.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window._photo_paths = [str(self.path), str(self.path)]
        self.window._thumb_bar.set_photos(self.window._photo_paths)

    def test_global_overrides_and_dithering_controls(self):
        window = self.window
        self.assertEqual(window._effective_color_mode(0), ColorMode.FULL)
        self.assertFalse(window._dither_chk.isEnabled())
        window._global_color_combo.setCurrentText(ColorMode.INDEXED_16.value)
        self.assertTrue(window._dither_chk.isEnabled())
        self.assertEqual(window._effective_color_mode(1), ColorMode.INDEXED_16)
        window._photo_color_combo.setCurrentText(ColorMode.BLACK_WHITE.value)
        window._photo_dither_combo.setCurrentIndex(2)
        self.assertEqual(window._effective_color_mode(0), ColorMode.BLACK_WHITE)
        self.assertFalse(window._effective_dither(0))
        window._thumb_bar._select(1)
        self.assertEqual(window._photo_color_combo.currentIndex(), 0)
        self.assertTrue(window._effective_dither(1))
        window._thumb_bar._select(0)
        self.assertEqual(window._photo_dither_combo.currentIndex(), 2)
        window._photo_color_combo.setCurrentIndex(0)
        self.assertEqual(window._effective_color_mode(0), ColorMode.INDEXED_16)
        window._photo_dither_combo.setCurrentIndex(0)
        self.assertTrue(window._effective_dither(0))
        window._global_color_combo.setCurrentText(ColorMode.GRAYSCALE.value)
        self.assertFalse(window._photo_dither_combo.isEnabled())
        window._clear_photos()
        self.assertFalse(window._photo_color_combo.isEnabled())
        self.assertFalse(window._photo_dither_combo.isEnabled())
        self.assertEqual(window._photo_colors, {})
        self.assertEqual(window._photo_dithers, {})

    def test_global_preferences_restored(self):
        self.window._global_color_combo.setCurrentText(ColorMode.INDEXED_256.value)
        self.window._dither_chk.setChecked(False)
        restored = MainWindow()
        self.addCleanup(restored.close)
        self.assertEqual(restored._effective_color_mode(0), ColorMode.INDEXED_256)
        self.assertFalse(restored._effective_dither(0))
        self.assertEqual(restored._photo_colors, {})

    def test_sidebar_contains_actions_and_settings_without_toolbar(self):
        window = self.window
        toolbars = window.findChildren(QToolBar)
        self.assertEqual(toolbars, [])
        sidebar = window._settings_scroll.widget()
        assert sidebar is not None
        self.assertEqual(
            [window._open_btn.text(), window._clear_btn.text(), window._print_btn.text()],
            ["Open Photos\u2026", "Clear All", "Print All"],
        )
        for control in (window._open_btn, window._clear_btn, window._print_btn):
            self.assertTrue(sidebar.isAncestorOf(control))
        for control in (
            window._paper_combo, window._orient_combo, window._size_mode_combo,
            window._area_w_spin, window._area_h_spin, window._margin_edges_btn,
            window._cut_markers_chk, window._global_fit_combo, window._global_color_combo,
            window._dither_chk, window._photo_fit_combo, window._photo_color_combo,
            window._photo_dither_combo, window._reset_crop_btn,
        ):
            self.assertTrue(sidebar.isAncestorOf(control))
        headings = {label.text() for label in sidebar.findChildren(QLabel)}
        self.assertTrue({"All photos", "Selected photo"} <= headings)
        self.assertFalse(sidebar.isAncestorOf(window._thumb_bar))
        central_layout = window.centralWidget().layout()
        self.assertEqual(central_layout.itemAt(central_layout.count() - 1).widget(),
                         window._photo_browser_splitter)
        self.assertEqual(
            window._thumb_bar.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            window._photo_browser_splitter.orientation(),
            Qt.Orientation.Vertical,
        )
        self.assertEqual(window._photo_browser_splitter.widget(0),
                         window._settings_splitter)
        self.assertEqual(window._photo_browser_splitter.widget(1),
                         window._thumb_bar)
        self.assertEqual(window._settings_splitter.widget(1), window._canvas)

    def test_about_action_opens_product_information(self):
        with patch("ui.main_window.QMessageBox.about") as show_about:
            self.window._about_action.trigger()
        show_about.assert_called_once()
        self.assertIn("EasyPhotoPrinter", show_about.call_args.args[1])
        self.assertIn("github.com/AdamMoses-GitHub/EasyPhotoPrinterApp",
                      show_about.call_args.args[2])

    def test_sidebar_collapses_without_changing_settings(self):
        window = self.window
        window.show()
        self.app.processEvents()
        sidebar = window._settings_scroll.widget()
        assert sidebar is not None
        sections = {button.text(): button for button in sidebar.findChildren(QToolButton)
                    if button.isCheckable()}
        self.assertEqual(set(sections), {"Paper", "Layout", "Appearance"})
        self.assertFalse(sections["Layout"].isChecked())
        for title, control in (
            ("Paper", window._paper_combo),
            ("Layout", window._size_mode_combo),
            ("Appearance", window._global_color_combo),
        ):
            toggle = sections[title]
            toggle.setChecked(True)
            self.assertTrue(control.isVisible())
            toggle.click()
            self.assertFalse(control.isVisible())
            self.assertEqual(toggle.arrowType(), Qt.ArrowType.RightArrow)
            toggle.click()
            self.assertTrue(control.isVisible())
            self.assertEqual(toggle.arrowType(), Qt.ArrowType.DownArrow)
        self.assertEqual(window._effective_color_mode(0), ColorMode.FULL)
        self.assertEqual(window._effective_color_mode(1), ColorMode.FULL)

    def test_sidebar_resizes_and_scrolls_at_small_window_sizes(self):
        window = self.window
        window.resize(760, 600)
        window.show()
        self.app.processEvents()
        scroll = window._settings_scroll
        sidebar = scroll.widget()
        assert sidebar is not None
        for button in sidebar.findChildren(QToolButton):
            if button.isCheckable():
                button.setChecked(True)
        self.app.processEvents()
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(window._canvas.width(), window._canvas.minimumWidth())
        self.assertEqual(window.width(), 760)
        scroll.ensureWidgetVisible(window._reset_crop_btn)
        self.app.processEvents()
        self.assertGreater(scroll.verticalScrollBar().value(), 0)
        for control in (window._photo_color_combo, window._global_color_combo,
                        window._photo_dither_combo, window._reset_crop_btn):
            parent = control.parentWidget()
            assert parent is not None
            self.assertLessEqual(control.geometry().right(), parent.width())
        before = window._settings_splitter.sizes()[0]
        window.resize(1100, 800)
        self.app.processEvents()
        window._settings_splitter.setSizes([before + 80, 1100 - before - 80])
        self.app.processEvents()
        self.assertGreater(window._settings_splitter.sizes()[0], before)

    def test_sidebar_layout_controls_still_update_preview(self):
        window = self.window
        window._paper_combo.setCurrentIndex(0)
        window._orient_combo.setCurrentText("Landscape")
        self.assertEqual((window._canvas._paper_w_in, window._canvas._paper_h_in), (5.0, 3.5))
        window._size_mode_combo.setCurrentText("Custom size")
        window._area_w_spin.setValue(3.0)
        window._area_h_spin.setValue(2.0)
        window._cut_markers_chk.setChecked(True)
        window._margin_chk.setChecked(True)
        window._margin_spin.setValue(0.125)
        self.assertEqual((window._canvas._print_w_in, window._canvas._print_h_in), (3.0, 2.0))
        self.assertEqual(window._canvas._margins_in, (0.125,) * 4)
        self.assertTrue(window._canvas._cut_markers)
        window._global_fit_combo.setCurrentText(FitMode.FIT.value)
        self.assertEqual(window._canvas._fit_mode, FitMode.FIT)
        window._photo_fit_combo.setCurrentText(FitMode.STRETCH.value)
        self.assertEqual(window._canvas._fit_mode, FitMode.STRETCH)
        window._size_mode_combo.setCurrentText("Full paper")
        self.assertFalse(window._cut_markers_chk.isEnabled())
        self.assertFalse(window._canvas._cut_markers)

    def test_preview_uses_shared_renderer_and_cache(self):
        canvas = self.window._canvas
        for fit in FitMode:
            canvas.set_fit_mode(fit)
            canvas.set_pan(0.7, -0.5)
            for mode in ColorMode:
                with self.subTest(fit=fit, mode=mode):
                    canvas.set_color_mode(mode, True)
                    pixmap = canvas._render_preview(79, 63)
                    expected = render_color_image(
                        gradient(), 79, 63, fit, 0.7, -0.5, mode, True,
                    )
                    actual = pixmap.toImage()
                    self.assertEqual(actual, ImageQt(expected).convertToFormat(actual.format()))
                    self.assertIs(pixmap, canvas._render_preview(79, 63))
        self.assertEqual(self.path.read_bytes(), self.original)
        # Exercise the actual paint path with crop shadows and asymmetric margins.
        canvas.set_margins(0.1, 0.2, 0.3, 0.4)
        canvas.set_crop_shadow(True)
        self.assertFalse(canvas.grab().isNull())
        canvas.clear_photo()
        self.assertIsNone(canvas._preview)
        self.assertIsNone(canvas._source)

    def test_margin_boundary_uses_distinct_orange_color(self):
        canvas = self.window._canvas
        canvas.set_margins(0.3, 0.3, 0.3, 0.3)
        preview = canvas.grab().toImage()
        orange = (210, 105, 0)
        orange_pixels = sum(
            preview.pixelColor(x, y).getRgb()[:3] == orange
            for y in range(preview.height())
            for x in range(preview.width())
        )
        self.assertGreater(orange_pixels, 0)

    def test_replacing_batch_discards_overrides(self):
        window = self.window
        window._photo_color_combo.setCurrentText(ColorMode.BLACK_WHITE.value)
        window._photo_dither_combo.setCurrentIndex(2)
        with patch("ui.main_window.QFileDialog.getOpenFileNames",
                   return_value=([str(self.path)], "")):
            window._open_photos()
        self.assertEqual(window._photo_colors, {})
        self.assertEqual(window._photo_dithers, {})
        self.assertEqual(window._photo_color_combo.currentIndex(), 0)
        self.assertEqual(window._photo_dither_combo.currentIndex(), 0)

    def test_print_pipeline_uses_per_photo_colors(self):
        window = self.window
        window._global_color_combo.setCurrentText(ColorMode.GRAYSCALE.value)
        window._photo_color_combo.setCurrentText(ColorMode.BLACK_WHITE.value)
        window._photo_dither_combo.setCurrentIndex(2)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        output = self.folder / "output.pdf"
        printer.setOutputFileName(str(output))
        printer.setResolution(72)
        with (
            patch("ui.main_window.QPrinter", return_value=printer),
            patch("ui.main_window.QPrintDialog") as dialog,
            patch("ui.main_window.render_color_image", wraps=render_color_image) as render,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            window._print_all()
        self.assertEqual(render.call_count, 2)
        self.assertEqual(render.call_args_list[0].args[6:], (ColorMode.BLACK_WHITE, False))
        self.assertEqual(render.call_args_list[1].args[6:], (ColorMode.GRAYSCALE, True))
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))
        self.assertIn("sent 2 photo(s)", window.statusBar().currentMessage())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_exif_orientation_is_used_for_preview_auto_orientation_and_print(self):
        path = self.folder / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (80, 40), "red").save(path, exif=exif)

        info = read_photo_info(str(path))
        self.assertEqual((info["pixel_w"], info["pixel_h"]), (40, 80))

        window = self.window
        window._orient_combo.setCurrentText("Auto")
        window._photo_paths = [str(path)]
        window._on_photo_selected(0, str(path))
        self.assertEqual(window._canvas._source.size, (40, 80))
        self.assertLess(
            window._effective_paper_dims(str(path))[0],
            window._effective_paper_dims(str(path))[1],
        )

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        output = self.folder / "oriented.pdf"
        printer.setOutputFileName(str(output))
        printer.setResolution(72)
        with (
            patch("ui.main_window.QPrinter", return_value=printer),
            patch("ui.main_window.QPrintDialog") as dialog,
            patch("ui.main_window.render_color_image", wraps=render_color_image) as render,
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            window._print_all()
        self.assertEqual(render.call_args.args[0].size, (40, 80))

        thumbnails_ready = QSignalSpy(window._thumb_bar.thumbnails_ready)
        window._thumb_bar.set_photos([str(path)])
        if thumbnails_ready.count() == 0:
            self.assertTrue(thumbnails_ready.wait(5000))
        thumbnail = window._thumb_bar._items[0].pixmap()
        self.assertLess(thumbnail.width(), thumbnail.height())

    def test_failed_photo_does_not_add_a_blank_print_page(self):
        window = self.window
        missing = self.folder / "missing.jpg"
        window._photo_paths = [str(missing), str(self.path)]

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        output = self.folder / "skip-failure.pdf"
        printer.setOutputFileName(str(output))
        printer.setResolution(72)
        with (
            patch("ui.main_window.QPrinter", return_value=printer),
            patch("ui.main_window.QPrintDialog") as dialog,
            patch("ui.main_window.QMessageBox.warning"),
        ):
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            window._print_all()

        page_count = len(re.findall(rb"/Type\s*/Page\b", output.read_bytes()))
        self.assertEqual(page_count, 1)

    def test_thumbnails_load_asynchronously_and_report_bad_files(self):
        bar = self.window._thumb_bar
        ready = QSignalSpy(bar.thumbnails_ready)
        missing = self.folder / "missing-thumbnail.jpg"
        bar.set_photos([str(self.path), str(missing)])
        if ready.count() == 0:
            self.assertTrue(ready.wait(5000))

        self.assertFalse(bar._items[0].pixmap().isNull())
        self.assertEqual(bar._items[1].text(), "!")
        self.assertIn("Cannot load thumbnail:", bar._items[1].toolTip())

    def test_splitter_width_is_restored_from_settings(self):
        window = self.window
        window.resize(1100, 800)
        window.show()
        self.app.processEvents()
        window._settings_splitter.setSizes([420, 680])
        window._photo_browser_splitter.setSizes([600, 200])
        self.app.processEvents()
        expected_width = window._settings_splitter.sizes()[0]
        expected_browser_height = window._photo_browser_splitter.sizes()[1]
        window._save_splitter_state(0, 0)
        window._save_photo_browser_splitter_state(0, 0)

        restored = MainWindow()
        self.addCleanup(restored.close)
        restored.resize(1100, 800)
        restored.show()
        self.app.processEvents()
        self.assertEqual(restored._settings_splitter.sizes()[0], expected_width)
        self.assertEqual(
            restored._photo_browser_splitter.sizes()[1],
            expected_browser_height,
        )

    def test_photo_browser_resize_adapts_thumbnail_size(self):
        window = self.window
        window.resize(1000, 900)
        window.show()
        self.app.processEvents()

        ready = QSignalSpy(window._thumb_bar.thumbnails_ready)
        window._thumb_bar.set_photos([str(self.path)])
        if ready.count() == 0:
            self.assertTrue(ready.wait(5000))

        splitter = window._photo_browser_splitter
        splitter.setSizes([600, 220])
        self.app.processEvents()
        large_height = splitter.sizes()[1]
        large_thumbnail = window._thumb_bar._items[0].pixmap().height()

        splitter.setSizes([760, 80])
        self.app.processEvents()
        small_height = splitter.sizes()[1]
        small_thumbnail = window._thumb_bar._items[0].pixmap().height()

        self.assertGreater(large_height, small_height)
        self.assertGreater(large_thumbnail, small_thumbnail)

    def test_preview_load_error_is_visible(self):
        with patch("ui.main_window.QMessageBox.warning") as warning:
            self.window._on_photo_selected(0, str(self.folder / "missing.png"))
        warning.assert_called_once()
        self.assertIsNone(self.window._canvas._source)


if __name__ == "__main__":
    unittest.main()
