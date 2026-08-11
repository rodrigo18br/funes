"""Reusable widgets for the Funes interface."""
from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QPainter, QPixmap, QTextDocument
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyleOptionFrame,
    QTableWidget,
    QTableWidgetItem,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .service import DirectorySummary, ImageRecord, LibraryStats

IMAGE_COUNT_ROLE = Qt.ItemDataRole.UserRole.value + 1


class ElideLabel(QLabel):
    _elideMode = Qt.TextElideMode.ElideMiddle

    def elideMode(self):
        return self._elideMode

    def setElideMode(self, mode):
        if self._elideMode != mode and mode != Qt.ElideNone:
            self._elideMode = mode
            self.updateGeometry()

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        hint = self.fontMetrics().boundingRect(self.text()).size()
        l, t, r, b = self.getContentMargins()
        margin = self.margin() * 2
        return QSize(
            min(100, hint.width()) + l + r + margin, 
            min(self.fontMetrics().height(), hint.height()) + t + b + margin
        )

    def paintEvent(self, event):
        qp = QPainter(self)
        opt = QStyleOptionFrame()
        self.initStyleOption(opt)
        self.style().drawControl(
            QStyle.ControlElement.CE_ShapedFrame, opt, qp, self)
        l, t, r, b = self.getContentMargins()
        margin = self.margin()
        try:
            m = self.fontMetrics().horizontalAdvance('x') // 2 - margin
        except:
            m = self.fontMetrics().width('x') // 2 - margin
        r = self.contentsRect().adjusted(
            margin + m,  margin, -(margin + m), -margin)
        qp.drawText(r, self.alignment(), 
            self.fontMetrics().elidedText(
                self.text(), self._elideMode, r.width()))

    def getContentMargins(self):
        margins = self.contentsMargins()
        return (margins.left(), margins.top(), margins.right(), margins.bottom())


class FunesWidget(QWidget):
    """Base widget for shared interface components."""


class DirectoryTreePanel(FunesWidget):
    """Sidebar list of indexed directories."""

    directory_selected = pyqtSignal(str)
    import_requested = pyqtSignal()
    remove_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._selected_directory: Optional[str] = None
        self._items_by_path: dict[str, QListWidgetItem] = {}
        self._rows_by_path: dict[str, "DirectoryRowWidget"] = {}
        self._importing_directories: set[str] = set()
        self._removing_directories: set[str] = set()

        self.setObjectName("directoryPanel")
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Library")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.directory_list = QListWidget()
        self.directory_list.setObjectName("directoryList")
        self.directory_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.directory_list.itemSelectionChanged.connect(self._emit_selected_directory)
        layout.addWidget(self.directory_list, 1)

        self.import_button = QPushButton("Import folder")
        self.import_button.setObjectName("importFolderButton")
        self.import_button.clicked.connect(self.import_requested.emit)
        layout.addWidget(self.import_button)

    @property
    def selected_directory(self) -> Optional[str]:
        return self._selected_directory

    @property
    def current_directory(self) -> Optional[str]:
        return self._selected_directory

    def set_directories(self, directories: Iterable[DirectorySummary]) -> None:
        current_selection = self._selected_directory
        importing_directories = set(self._importing_directories)
        self.directory_list.blockSignals(True)
        self.directory_list.clear()
        self._items_by_path.clear()
        self._rows_by_path.clear()

        for directory in directories:
            self._add_directory_item(
                directory.path,
                directory.image_count,
                directory.path in importing_directories,
                current_selection,
            )

        for directory in sorted(importing_directories - set(self._items_by_path)):
            self._add_directory_item(directory, 0, True, current_selection)

        self.directory_list.blockSignals(False)
        if current_selection not in self._items_by_path:
            self._selected_directory = None

    def mark_importing(self, directory: str, importing: bool) -> None:
        if importing:
            self._importing_directories.add(directory)
        else:
            self._importing_directories.discard(directory)
        item = self._items_by_path.get(directory)
        if item is None:
            if importing:
                self._add_directory_item(directory, 0, True, self._selected_directory)
            return
        image_count = item.data(IMAGE_COUNT_ROLE) or 0
        self._update_directory_item(item, directory, image_count, importing)

    def mark_removing(self, directory: str, removing: bool) -> None:
        if removing:
            self._removing_directories.add(directory)
        else:
            self._removing_directories.discard(directory)
        row = self._rows_by_path.get(directory)
        if row is not None:
            row.set_remove_enabled(not removing)

    def _build_directory_item(
        self, directory: str, image_count: int, importing: bool
    ) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(IMAGE_COUNT_ROLE, image_count)
        self._update_directory_item(item, directory, image_count, importing)
        return item

    def _update_directory_item(
        self, item: QListWidgetItem, directory: str, image_count: int, importing: bool
    ) -> None:
        row = self._rows_by_path.get(directory)
        if row is not None:
            row.update(directory, image_count, importing)
            row.set_remove_enabled(directory not in self._removing_directories)

    def _add_directory_item(
        self,
        directory: str,
        image_count: int,
        importing: bool,
        current_selection: Optional[str],
    ) -> None:
        item = self._build_directory_item(directory, image_count, importing)
        item.setData(Qt.ItemDataRole.UserRole, directory)
        row = DirectoryRowWidget(directory, image_count, importing)
        row.selected_requested.connect(lambda path=directory: self._select_row(path))
        row.remove_requested.connect(self.remove_requested.emit)
        row.set_remove_enabled(directory not in self._removing_directories)
        item.setSizeHint(row.sizeHint())
        self.directory_list.addItem(item)
        self.directory_list.setItemWidget(item, row)
        self._items_by_path[directory] = item
        self._rows_by_path[directory] = row
        if directory == current_selection:
            item.setSelected(True)

    def _select_row(self, directory: str) -> None:
        item = self._items_by_path.get(directory)
        if item is not None:
            self.directory_list.setCurrentItem(item)

    def _emit_selected_directory(self) -> None:
        items = self.directory_list.selectedItems()
        if not items:
            self._selected_directory = None
            return
        self._selected_directory = items[0].data(Qt.ItemDataRole.UserRole)
        print(self._selected_directory)
        self.directory_selected.emit(self._selected_directory)


class DirectoryRowWidget(FunesWidget):
    """Directory list row with an optional remove action."""

    selected_requested = pyqtSignal()
    remove_requested = pyqtSignal(str)

    def __init__(
        self,
        directory: str,
        image_count: int,
        importing: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._directory = directory
        self.setObjectName("directoryRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 4, 6)
        layout.setSpacing(8)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.path_label = ElideLabel()
        self.path_label.setObjectName("directoryPathLabel")
        self.path_label.setContentsMargins(0, 0, 0, 3)
        self.path_label.setMinimumHeight(35)        
        text_layout.addWidget(self.path_label)
        self.count_label = QLabel()
        self.count_label.setObjectName("directoryCountLabel")
        text_layout.addWidget(self.count_label)
        layout.addLayout(text_layout, 1)

        self.remove_button = QToolButton()
        self.remove_button.setObjectName("directoryRemoveButton")
        remove_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DialogDiscardButton
        )
        self.remove_button.setIcon(remove_icon)
        self.remove_button.clicked.connect(self._emit_remove_requested)
        layout.addWidget(self.remove_button)
        self.update(directory, image_count, importing)

    def update(self, directory: str, image_count: int, importing: bool) -> None:
        self._directory = directory
        suffix = "Importing..." if importing else f"{image_count} images"
        self._update_path_label()
        self.count_label.setText(suffix)
        self.setToolTip(directory)
        self.remove_button.setVisible(not importing)
        self.remove_button.setToolTip(f"Remove {directory} from the index")
        self.remove_button.setAccessibleName(f"Remove {directory} from the index")

    def set_remove_enabled(self, enabled: bool) -> None:
        self.remove_button.setEnabled(enabled)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected_requested.emit()
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._update_path_label()
        super().resizeEvent(event)

    def _update_path_label(self) -> None:
        self.path_label.setText(self._directory)

    def _emit_remove_requested(self) -> None:
        self.remove_requested.emit(self._directory)


class SearchBar(FunesWidget):
    """Search row with query input and scope affordance."""

    search_requested = pyqtSignal(str, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_directory: Optional[str] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setObjectName("searchInput")
        self.input.setPlaceholderText("Search images")
        self.input.returnPressed.connect(self._request_search)
        layout.addWidget(self.input, 1)

        self.scope_button = QToolButton()
        self.scope_button.setObjectName("searchScopeButton")
        self.scope_button.setCheckable(True)
        self.scope_button.setEnabled(False)
        self.scope_button.clicked.connect(self._update_scope_text)
        layout.addWidget(self.scope_button)
        self._update_scope_text()

    @property
    def current_directory(self) -> Optional[str]:
        return self._current_directory

    def set_current_directory(self, directory: Optional[str]) -> None:
        self._current_directory = directory
        self.scope_button.setEnabled(directory is not None)
        if directory is None:
            self.scope_button.setChecked(False)
        self._update_scope_text()

    def _request_search(self) -> None:
        query = self.input.text().strip()
        if not query:
            return
        directory = self._current_directory if self.scope_button.isChecked() else None
        self.search_requested.emit(query, directory)

    def _update_scope_text(self) -> None:
        if self.scope_button.isChecked() and self._current_directory:
            self.scope_button.setText("Current directory")
            self.scope_button.setToolTip(self._current_directory)
        else:
            self.scope_button.setText("All images")
            self.scope_button.setToolTip("Search the full library")


class WelcomeView(FunesWidget):
    """Default central panel with library stats."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("welcomeView")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self.title = QLabel("Funes")
        self.title.setObjectName("welcomeTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.stats = QLabel()
        self.stats.setObjectName("welcomeStats")
        self.stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats)

    def set_stats(self, stats: LibraryStats) -> None:
        self.stats.setText(
            f"{stats.image_count} indexed images\n"
            f"{stats.directory_count} imported directories"
        )


class DirectoryContentsView(FunesWidget):
    """Reusable central view for directory contents and search results."""

    image_selected = pyqtSignal(object)
    next_batch_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.message = QLabel()
        self.message.setObjectName("contentMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.stack.addWidget(self.message)

        self.image_list = QListWidget()
        self.image_list.setObjectName("imageList")
        self.image_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.image_list.setIconSize(QSize(92, 72))
        self.image_list.itemActivated.connect(self._emit_image_selected)
        self.image_list.itemClicked.connect(self._emit_image_selected)
        self.image_list.verticalScrollBar().valueChanged.connect(
            self._request_next_batch_if_at_bottom
        )
        self.stack.addWidget(self.image_list)
        self._loading_more = False

    def set_directory(self, directory: str, image_count: int) -> None:
        self.title.setText(f"{directory}\n{image_count} indexed images")

    def set_loading(self, title: str, message: str = "Loading...") -> None:
        self.title.setText(title)
        self.message.setText(message)
        self.stack.setCurrentWidget(self.message)
        self._loading_more = False

    def set_error(self, title: str, message: str) -> None:
        self.title.setText(title)
        self.message.setText(message)
        self.stack.setCurrentWidget(self.message)
        self._loading_more = False

    def set_images(self, title: str, images: Iterable[ImageRecord]) -> None:
        records = list(images)
        self.title.setText(f"{title}\n{len(records)} image{'s' if len(records) != 1 else ''}")
        self.image_list.clear()
        if not records:
            self.message.setText("No images found.")
            self.stack.setCurrentWidget(self.message)
            return

        self.append_images(title, records)
        self.stack.setCurrentWidget(self.image_list)
        self._loading_more = False

    def append_images(self, title: str, images: Iterable[ImageRecord]) -> None:
        records = list(images)
        for record in records:
            self._add_image_item(record)
        total = self.image_list.count()
        self.title.setText(f"{title}\n{total} image{'s' if total != 1 else ''}")
        if total > 0:
            self.stack.setCurrentWidget(self.image_list)
        self._loading_more = False

    def set_loading_more(self, loading: bool) -> None:
        self._loading_more = loading

    def _add_image_item(self, record: ImageRecord) -> None:
        item = QListWidgetItem()
        item.setText(f"{record.filename}\n{record.directory}")
        item.setToolTip(record.path)
        item.setData(Qt.ItemDataRole.UserRole, record)
        item.setIcon(QIcon(_thumbnail_for_path(record.path)))
        self.image_list.addItem(item)

    def _request_next_batch_if_at_bottom(self, value: int) -> None:
        if self._loading_more or self.stack.currentWidget() != self.image_list:
            return
        scrollbar = self.image_list.verticalScrollBar()
        if value == scrollbar.maximum() and scrollbar.maximum() > 0:
            self._loading_more = True
            self.next_batch_requested.emit()

    def _emit_image_selected(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if record is not None:
            self.image_selected.emit(record)


class ImageDetailsView(FunesWidget):
    """Details view for a selected image."""

    back_requested = pyqtSignal()
    similar_requested = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("detailsBackButton")
        self.back_button.clicked.connect(self.back_requested.emit)
        actions.addWidget(self.back_button)

        self.similar_button = QPushButton("Similar images")
        self.similar_button.setObjectName("similarImagesButton")
        self.similar_button.clicked.connect(self._request_similar)
        actions.addWidget(self.similar_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        content = QHBoxLayout()
        content.setSpacing(16)
        layout.addLayout(content, 1)

        self.image = QLabel()
        self.image.setObjectName("detailsImage")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(360, 280)
        self.image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content.addWidget(self.image, 3)

        self.metadata = QTableWidget(0, 2)
        self.metadata.setObjectName("metadataTable")
        self.metadata.setHorizontalHeaderLabels(["Field", "Value"])
        self.metadata.verticalHeader().setVisible(False)
        self.metadata.horizontalHeader().setStretchLastSection(True)
        self.metadata.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metadata.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        content.addWidget(self.metadata, 2)

        self._record: Optional[ImageRecord] = None
        self._pixmap = QPixmap()

    def set_image(self, record: ImageRecord, metadata: dict[str, str]) -> None:
        self._record = record
        self._pixmap = QPixmap(record.path)
        self._render_pixmap()
        if self._pixmap.isNull():
            self.image.setText("Image file is missing or unreadable.")

        self.metadata.setRowCount(len(metadata))
        for row, (key, value) in enumerate(metadata.items()):
            self.metadata.setItem(row, 0, QTableWidgetItem(key))
            self.metadata.setItem(row, 1, QTableWidgetItem(value))
        self.metadata.resizeColumnsToContents()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._render_pixmap()
        super().resizeEvent(event)

    def _render_pixmap(self) -> None:
        if self._pixmap.isNull():
            self.image.clear()
            return
        scaled = self._pixmap.scaled(
            self.image.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image.setPixmap(scaled)

    def _request_similar(self) -> None:
        if self._record is not None:
            self.similar_requested.emit(self._record)


class Separator(QFrame):
    """Thin vertical separator used between sidebar and content."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Plain)


def _thumbnail_for_path(image_path: str) -> QPixmap:
    pixmap = QPixmap(image_path)
    if pixmap.isNull():
        placeholder = QPixmap(92, 72)
        placeholder.fill(Qt.GlobalColor.transparent)
        return placeholder
    return pixmap.scaled(
        92,
        72,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
