from PySide6.QtWidgets import QScrollArea, QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

THUMB_SIZE = 80
THUMB_BORDER = 2
ITEM_SIZE = THUMB_SIZE + THUMB_BORDER * 2 + 4  # padding


class _ThumbnailItem(QLabel):
    clicked = Signal(int)

    def __init__(self, index: int, path: str, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedSize(ITEM_SIZE, ITEM_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        pix = QPixmap(path).scaled(
            THUMB_SIZE, THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pix)
        self._set_style(False)

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

    def set_photos(self, paths: list[str]):
        for item in self._items:
            self._layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._paths = list(paths)
        self._selected_index = -1

        for i, path in enumerate(paths):
            item = _ThumbnailItem(i, path)
            item.clicked.connect(self._on_item_clicked)
            self._layout.insertWidget(self._layout.count() - 1, item)
            self._items.append(item)

        if self._items:
            self._select(0)

    def _on_item_clicked(self, index: int):
        self._select(index)

    def _select(self, index: int):
        if 0 <= self._selected_index < len(self._items):
            self._items[self._selected_index].set_selected(False)
        self._selected_index = index
        self._items[index].set_selected(True)
        self.photo_selected.emit(index, self._paths[index])
