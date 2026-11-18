from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtWidgets import (
    QApplication, QScrollArea, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import (
    QByteArray, QEvent, QMimeData, QPoint, Qt, Signal, QObject, QRunnable,
    QThreadPool,
)
from PySide6.QtGui import QDrag, QFontMetrics, QImage, QPixmap

THUMB_SIZE = 80
MIN_THUMB_SIZE = 40
MAX_THUMB_SIZE = 256
THUMB_BORDER = 2
ITEM_PADDING = THUMB_BORDER * 2 + 4
CAPTION_HEIGHT = 18
ITEM_OUTER_PADDING = 4
REORDER_MIME = "application/x-easyphotoprinter-photo-index"


class _ThumbnailSignals(QObject):
    loaded = Signal(int, int, str, object, str)


class _ThumbnailLoader(QRunnable):
    def __init__(
        self, generation: int, token: int, path: str, signals: _ThumbnailSignals,
    ):
        super().__init__()
        self._generation = generation
        self._token = token
        self._path = path
        self.signals = signals

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
            self._generation, self._token, self._path, thumbnail, error,
        )


class _ThumbnailItem(QWidget):
    clicked = Signal(int)

    def __init__(
        self, index: int, token: int, path: str, thumbnail_size: int, parent=None,
    ):
        super().__init__(parent)
        self._index = index
        self.token = token
        self.path = path
        self._thumbnail_size = thumbnail_size
        self._source_pixmap: QPixmap | None = None
        try:
            self.modified_time = Path(path).stat().st_mtime
        except OSError:
            self.modified_time = 0.0
        self._drag_start: QPoint | None = None
        self._image_label = QLabel("Loading...")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setToolTip(Path(path).name)
        self._name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self._image_label)
        layout.addWidget(self._name_label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(Path(path).name)
        self.setAcceptDrops(True)
        self._set_item_size()
        self._set_style(False)

    def set_index(self, index: int):
        self._index = index

    def set_thumbnail_size(self, size: int):
        if size == self._thumbnail_size:
            return
        self._thumbnail_size = size
        self._set_item_size()
        self._update_pixmap()

    def _set_item_size(self):
        image_size = self._thumbnail_size + ITEM_PADDING
        item_width = image_size + ITEM_OUTER_PADDING
        self._image_label.setFixedSize(image_size, image_size)
        self._name_label.setFixedSize(image_size, CAPTION_HEIGHT)
        self.setFixedSize(
            item_width,
            image_size + CAPTION_HEIGHT + ITEM_OUTER_PADDING + 2,
        )
        self._name_label.setText(
            QFontMetrics(self._name_label.font()).elidedText(
                Path(self.path).name,
                Qt.TextElideMode.ElideMiddle,
                image_size - 4,
            )
        )

    def set_thumbnail(self, data: tuple[int, int, bytes] | None, error: str):
        if data is None:
            self._image_label.setText("!")
            self._image_label.setToolTip(f"Cannot load thumbnail: {error}")
            self.setToolTip(f"{Path(self.path).name}: {error}")
            return
        width, height, pixels = data
        image = QImage(
            pixels, width, height, width * 3, QImage.Format.Format_RGB888,
        ).copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._update_pixmap()

    def _update_pixmap(self):
        if self._source_pixmap is None:
            return
        pixmap = self._source_pixmap.scaled(
            self._thumbnail_size, self._thumbnail_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setText("")
        self._image_label.setToolTip(Path(self.path).name)
        self._image_label.setPixmap(pixmap)

    def pixmap(self):
        return self._image_label.pixmap()

    def text(self):
        return self._image_label.text()

    def toolTip(self):
        return self._image_label.toolTip()

    def set_selected(self, selected: bool):
        self._set_style(selected)

    def _set_style(self, selected: bool):
        if selected:
            self._image_label.setStyleSheet(
                "border: 2px solid #0078D4; background-color: #cce4f7; padding: 1px;"
            )
        else:
            self._image_label.setStyleSheet(
                "border: 2px solid #c0c0c0; background-color: transparent; padding: 1px;"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._drag_start).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            mime_data = QMimeData()
            mime_data.setData(REORDER_MIME, QByteArray(str(self._index).encode("ascii")))
            drag = QDrag(self)
            drag.setMimeData(mime_data)
            if self._source_pixmap is not None:
                drag.setPixmap(self._source_pixmap)
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)


class ThumbnailBar(QScrollArea):
    """Horizontal photo strip displayed along the bottom of the window."""

    photo_selected = Signal(int, str)  # (index, path)
    photos_reordered = Signal(int, int)  # (old index, new index)
    files_dropped = Signal(list)
    thumbnails_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(
            MIN_THUMB_SIZE + ITEM_PADDING + CAPTION_HEIGHT + ITEM_OUTER_PADDING + 8
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
        self._empty_label = QLabel("Drop photos here or use Open Photos.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._empty_label)
        self._layout.addStretch()

        self._items: list[_ThumbnailItem] = []
        self._paths: list[str] = []
        self._selected_index: int = -1
        self._generation = 0
        self._next_token = 0
        self._pending_tokens: set[int] = set()
        self._signals: dict[int, _ThumbnailSignals] = {}
        self._filter_text = ""
        self._sort_mode = "custom"
        self.setWidget(self._container)
        self.viewport().setAcceptDrops(True)
        self.viewport().installEventFilter(self)
        self._container.setAcceptDrops(True)
        self._container.installEventFilter(self)

    def set_photos(self, paths: list[str]):
        self._generation += 1
        for item in self._items:
            self._layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._paths = list(paths)
        self._selected_index = -1
        self._pending_tokens.clear()
        self._start_loaders(range(len(paths)))
        self._refresh_items()
        if self._items:
            self._select(0)

    def add_photos(self, paths: list[str]):
        if not paths:
            return
        first_added_index = len(self._paths)
        self._paths.extend(paths)
        self._start_loaders(range(first_added_index, len(self._paths)))
        self._refresh_items()
        if first_added_index == 0:
            self._select(0)

    def _start_loaders(self, indices: range):
        self._update_thumbnail_size()
        for index in indices:
            path = self._paths[index]
            token = self._next_token
            self._next_token += 1
            item = _ThumbnailItem(index, token, path, self._thumbnail_size)
            item.clicked.connect(self._on_item_clicked)
            self._install_item_drop_target(item)
            self._items.append(item)
            self._pending_tokens.add(token)
            signals = _ThumbnailSignals(self)
            signals.loaded.connect(self._on_thumbnail_loaded)
            self._signals[token] = signals
            loader = _ThumbnailLoader(self._generation, token, path, signals)
            QThreadPool.globalInstance().start(loader)

    def remove_photo(self, index: int):
        if not 0 <= index < len(self._items):
            return
        item = self._items.pop(index)
        self._paths.pop(index)
        self._pending_tokens.discard(item.token)
        self._layout.removeWidget(item)
        item.deleteLater()
        old_selected = self._selected_index
        if old_selected == index:
            self._selected_index = -1
        elif old_selected > index:
            self._selected_index -= 1
        for i, remaining_item in enumerate(self._items):
            remaining_item.set_index(i)
        self._refresh_items()
        if self._items:
            new_selected = (
                min(index, len(self._items) - 1)
                if old_selected == index or old_selected < 0
                else self._selected_index
            )
            self._select(new_selected)
        else:
            self._selected_index = -1
        if not self._pending_tokens and self._items:
            self.thumbnails_ready.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_thumbnail_size()

    def _update_thumbnail_size(self):
        margins = self._layout.contentsMargins()
        available_height = (
            self.viewport().height()
            - margins.top() - margins.bottom()
            - ITEM_PADDING - CAPTION_HEIGHT - ITEM_OUTER_PADDING
        )
        size = max(MIN_THUMB_SIZE, min(MAX_THUMB_SIZE, available_height))
        if size == self._thumbnail_size:
            return
        self._thumbnail_size = size
        for item in self._items:
            item.set_thumbnail_size(size)

    def set_filter(self, text: str):
        self._filter_text = text.casefold().strip()
        self._refresh_items()

    def set_sort_mode(self, mode: str):
        if mode not in {"custom", "name_asc", "name_desc", "date_newest", "date_oldest"}:
            raise ValueError(f"Unknown photo sort mode: {mode}")
        self._sort_mode = mode
        self._refresh_items()

    def select_photo(self, index: int):
        if 0 <= index < len(self._items):
            if self._items[index].isHidden():
                self.set_filter("")
            self._select(index)

    def _refresh_items(self):
        for item in self._items:
            item.setVisible(
                not self._filter_text
                or self._filter_text in Path(item.path).name.casefold()
            )
        visible_items = [item for item in self._items if not item.isHidden()]
        if self._sort_mode == "name_asc":
            visible_items.sort(key=lambda item: Path(item.path).name.casefold())
        elif self._sort_mode == "name_desc":
            visible_items.sort(key=lambda item: Path(item.path).name.casefold(), reverse=True)
        elif self._sort_mode == "date_newest":
            visible_items.sort(key=lambda item: item.modified_time, reverse=True)
        elif self._sort_mode == "date_oldest":
            visible_items.sort(key=lambda item: item.modified_time)

        while self._layout.count():
            self._layout.takeAt(0)
        self._empty_label.setVisible(not visible_items)
        for item in visible_items:
            self._layout.addWidget(item)
        if not visible_items:
            self._empty_label.setText(
                "No photos match that search."
                if self._items
                else "Drop photos here or use Open Photos."
            )
            self._layout.addWidget(self._empty_label)
        self._layout.addStretch()

    def _reorder_photo(self, old_index: int, new_index: int):
        if (
            self._sort_mode != "custom"
            or not 0 <= old_index < len(self._items)
            or not 0 <= new_index < len(self._items)
            or old_index == new_index
        ):
            return
        item = self._items.pop(old_index)
        path = self._paths.pop(old_index)
        self._items.insert(new_index, item)
        self._paths.insert(new_index, path)
        if self._selected_index == old_index:
            self._selected_index = new_index
        elif old_index < new_index and old_index < self._selected_index <= new_index:
            self._selected_index -= 1
        elif new_index < old_index and new_index <= self._selected_index < old_index:
            self._selected_index += 1
        for index, photo_item in enumerate(self._items):
            photo_item.set_index(index)
        self._refresh_items()
        self.photos_reordered.emit(old_index, new_index)
        if self._selected_index >= 0:
            self._select(self._selected_index)

    def _install_item_drop_target(self, item: _ThumbnailItem):
        item.setAcceptDrops(True)
        item.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() not in (
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
            QEvent.Type.Drop,
        ):
            return super().eventFilter(watched, event)

        mime_data = event.mimeData()
        if mime_data.hasFormat(REORDER_MIME):
            if self._sort_mode != "custom":
                event.ignore()
                return True
            if event.type() == QEvent.Type.Drop:
                try:
                    old_index = int(bytes(mime_data.data(REORDER_MIME)).decode("ascii"))
                except ValueError:
                    event.ignore()
                    return True
                position = watched.mapTo(
                    self.viewport(), event.position().toPoint(),
                )
                position.setX(position.x() + self.horizontalScrollBar().value())
                targets = [item for item in self._items if not item.isHidden()]
                if targets:
                    target = min(
                        targets,
                        key=lambda item: abs(
                            item.mapTo(self._container, QPoint(0, 0)).x()
                            + item.width() // 2 - position.x()
                        ),
                    )
                    insertion_index = target._index
                    target_left = target.mapTo(self._container, QPoint(0, 0)).x()
                    if position.x() >= target_left + target.width() // 2:
                        insertion_index += 1
                    if old_index < insertion_index:
                        insertion_index -= 1
                    new_index = min(max(insertion_index, 0), len(self._items) - 1)
                    self._reorder_photo(old_index, new_index)
            event.acceptProposedAction()
            return True

        if mime_data.hasUrls():
            paths = [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]
            if paths:
                if event.type() == QEvent.Type.Drop:
                    self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return True
        event.ignore()
        return True

    def _on_thumbnail_loaded(
        self, generation: int, token: int, path: str,
        data: tuple[int, int, bytes] | None, error: str,
    ):
        signals = self._signals.pop(token, None)
        if signals is not None:
            signals.deleteLater()
        if generation != self._generation:
            return
        item = next(
            (candidate for candidate in self._items if candidate.token == token),
            None,
        )
        if item is None or item.path != path:
            return
        item.set_thumbnail(data, error)
        self._pending_tokens.discard(token)
        if not self._pending_tokens:
            self.thumbnails_ready.emit()

    def _on_item_clicked(self, index: int):
        self._select(index)

    def _select(self, index: int):
        if not 0 <= index < len(self._items):
            return
        if 0 <= self._selected_index < len(self._items):
            self._items[self._selected_index].set_selected(False)
        self._selected_index = index
        self._items[index].set_selected(True)
        self.photo_selected.emit(index, self._paths[index])
