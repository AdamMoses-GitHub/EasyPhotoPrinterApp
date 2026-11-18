from PIL import Image, ImageOps
from PySide6.QtWidgets import QScrollArea, QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QImage, QPixmap

THUMB_SIZE = 80
MIN_THUMB_SIZE = 40
MAX_THUMB_SIZE = 256
THUMB_BORDER = 2
ITEM_PADDING = THUMB_BORDER * 2 + 4
ITEM_SIZE = THUMB_SIZE + ITEM_PADDING


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
                    (MAX_THUMB_SIZE, MAX_THUMB_SIZE), Image.Resampling.LANCZOS,
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

    def __init__(self, index: int, thumbnail_size: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._thumbnail_size = thumbnail_size
        self._source_pixmap: QPixmap | None = None
        self._set_item_size()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("Loading...")
        self._set_style(False)

    def set_thumbnail_size(self, size: int):
        if size == self._thumbnail_size:
            return
        self._thumbnail_size = size
        self._set_item_size()
        self._update_pixmap()

    def _set_item_size(self):
        item_size = self._thumbnail_size + ITEM_PADDING
        self.setFixedSize(item_size, item_size)

    def set_thumbnail(self, data: tuple[int, int, bytes] | None, error: str):
        if data is None:
            self.setText("!")
            self.setToolTip(f"Cannot load thumbnail: {error}")
            return
        width, height, pixels = data
        image = QImage(
            pixels, width, height, width * 3, QImage.Format.Format_RGB888,
        ).copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._update_pixmap()
        self.setText("")
        self.setToolTip("")

    def _update_pixmap(self):
        if self._source_pixmap is None:
            return
        pixmap = self._source_pixmap.scaled(
            self._thumbnail_size, self._thumbnail_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
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
    """Horizontal photo strip displayed along the bottom of the window."""

    photo_selected = Signal(int, str)  # (index, path)
    thumbnails_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(
            MIN_THUMB_SIZE + ITEM_PADDING + 8
            + self.horizontalScrollBar().sizeHint().height()
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._thumbnail_size = THUMB_SIZE

        self._container = QWidget()
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(6)
        self._layout.addStretch()

        self._items: list[_ThumbnailItem] = []
        self._paths: list[str] = []
        self._selected_index: int = -1
        self._generation = 0
        self._completed = 0
        self.setWidget(self._container)

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
        self._update_thumbnail_size()

        for i, path in enumerate(paths):
            item = _ThumbnailItem(i, self._thumbnail_size)
            item.clicked.connect(self._on_item_clicked)
            self._layout.insertWidget(self._layout.count() - 1, item)
            self._items.append(item)
            loader = _ThumbnailLoader(generation, i, path)
            loader.signals.loaded.connect(self._on_thumbnail_loaded)
            QThreadPool.globalInstance().start(loader)

        if self._items:
            self._select(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_thumbnail_size()

    def _update_thumbnail_size(self):
        available_height = (
            self.viewport().height()
            - self._layout.contentsMargins().top()
            - self._layout.contentsMargins().bottom()
            - ITEM_PADDING
        )
        size = max(MIN_THUMB_SIZE, min(MAX_THUMB_SIZE, available_height))
        if size == self._thumbnail_size:
            return
        self._thumbnail_size = size
        for item in self._items:
            item.set_thumbnail_size(size)

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
