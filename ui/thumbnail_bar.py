from PIL import Image, ImageOps
from PySide6.QtWidgets import QScrollArea, QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QImage, QPixmap

THUMB_SIZE = 80
THUMB_BORDER = 2
ITEM_SIZE = THUMB_SIZE + THUMB_BORDER * 2 + 4  # padding


class _ThumbnailSignals(QObject):
    loaded = Signal(int, int, str, object, str)


class _ThumbnailLoader(QRunnable):
    def __init__(self, generation: int, index: int, path: str):
        super().__init__()
        self._generation = generation
        self._index = index
        self._path = path
        self.signals = _ThumbnailSignals()

    def run(self):
        try:
            with Image.open(self._path) as source:
                source.thumbnail(
                    (THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS,
                )
                image = ImageOps.exif_transpose(source).convert("RGB")
            thumbnail = (image.width, image.height, image.tobytes())
            error = ""
        except Exception as exc:
            thumbnail = None
            error = str(exc)
        self.signals.loaded.emit(
            self._generation, self._index, self._path, thumbnail, error,
        )


class _ThumbnailItem(QLabel):
    clicked = Signal(int)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedSize(ITEM_SIZE, ITEM_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("Loading...")
        self._set_style(False)

    def set_thumbnail(self, data: tuple[int, int, bytes] | None, error: str):
        if data is None:
            self.setText("!")
            self.setToolTip(f"Cannot load thumbnail: {error}")
            return
        width, height, pixels = data
        image = QImage(
            pixels, width, height, width * 3, QImage.Format.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            THUMB_SIZE, THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setText("")
        self.setToolTip("")
        self.setPixmap(pixmap)

    def set_selected(self, selected: bool):
        self._set_style(selected)

    def _set_style(self, selected: bool):
        if selected:
            self.setStyleSheet(
                "border: 2px solid #0078D4; background-color: #cce4f7; padding: 1px;"
            )
        else:
            self.setStyleSheet(
                "border: 2px solid #c0c0c0; background-color: transparent; padding: 1px;"
            )

    def mousePressEvent(self, event):
        self.clicked.emit(self._index)


class ThumbnailBar(QScrollArea):
    """Horizontal scrollable strip of photo thumbnails."""

    photo_selected = Signal(int, str)  # (index, path)
    thumbnails_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ITEM_SIZE + 16)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(6)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._items: list[_ThumbnailItem] = []
        self._paths: list[str] = []
        self._selected_index: int = -1
        self._generation = 0
        self._completed = 0

    def set_photos(self, paths: list[str]):
        self._generation += 1
        generation = self._generation
        self._completed = 0
        for item in self._items:
            self._layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._paths = list(paths)
        self._selected_index = -1

        for i, path in enumerate(paths):
            item = _ThumbnailItem(i)
            item.clicked.connect(self._on_item_clicked)
            self._layout.insertWidget(self._layout.count() - 1, item)
            self._items.append(item)
            loader = _ThumbnailLoader(generation, i, path)
            loader.signals.loaded.connect(self._on_thumbnail_loaded)
            QThreadPool.globalInstance().start(loader)

        if self._items:
            self._select(0)

    def _on_thumbnail_loaded(
        self, generation: int, index: int, path: str,
        data: tuple[int, int, bytes] | None, error: str,
    ):
        if (
            generation != self._generation
            or not 0 <= index < len(self._items)
            or self._paths[index] != path
        ):
            return
        self._items[index].set_thumbnail(data, error)
        self._completed += 1
        if self._completed == len(self._items):
            self.thumbnails_ready.emit()

    def _on_item_clicked(self, index: int):
        self._select(index)

    def _select(self, index: int):
        if 0 <= self._selected_index < len(self._items):
            self._items[self._selected_index].set_selected(False)
        self._selected_index = index
        self._items[index].set_selected(True)
        self.photo_selected.emit(index, self._paths[index])
