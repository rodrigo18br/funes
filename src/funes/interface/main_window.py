"""Main window shell for the Funes interface."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QSettings, QSize, QThread
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .service import ImageRecord, InterfaceService
from .widgets import (
    DirectoryContentsView,
    DirectoryTreePanel,
    ImageDetailsView,
    SearchBar,
    Separator,
    WelcomeView,
)
from .workers import ServiceWorker

DIRECTORY_PAGE_SIZE = 10
LIST_MODE_DIRECTORY = "directory"
LIST_MODE_TEXT_SEARCH = "text_search"
LIST_MODE_SIMILAR_IMAGES = "similar_images"

LIGHT_STYLESHEET = """
QMainWindow, QWidget {
    background: #f7f7f4;
    color: #1f2528;
}
QWidget#directoryPanel {
    background: #eceee8;
}
QLabel#panelTitle, QLabel#welcomeTitle {
    font-size: 22px;
    font-weight: 700;
}
QLabel#welcomeStats {
    color: #51605f;
    font-size: 15px;
}
QLabel#contentMessage {
    color: #51605f;
    font-size: 16px;
}
QLineEdit {
    background: #ffffff;
    border: 1px solid #c8d0cc;
    border-radius: 6px;
    padding: 9px 12px;
}
QListWidget {
    background: transparent;
    border: 0;
}
QListWidget::item {
    border-radius: 6px;
    padding: 8px;
}
QListWidget::item:selected {
    background: #d7e7e2;
    color: #182320;
}
QPushButton, QToolButton {
    background: #ffffff;
    border: 1px solid #c8d0cc;
    border-radius: 6px;
    padding: 8px 10px;
}
QPushButton:hover, QToolButton:hover {
    background: #edf4f1;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #d8ded9;
    border-radius: 6px;
    gridline-color: #d8ded9;
}
"""

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: #171a1c;
    color: #eef2ef;
}
QWidget#directoryPanel {
    background: #202629;
}
QLabel#panelTitle, QLabel#welcomeTitle {
    font-size: 22px;
    font-weight: 700;
}
QLabel#welcomeStats {
    color: #aab8b2;
    font-size: 15px;
}
QLabel#contentMessage {
    color: #aab8b2;
    font-size: 16px;
}
QLineEdit {
    background: #252b2e;
    border: 1px solid #3c474b;
    border-radius: 6px;
    color: #eef2ef;
    padding: 9px 12px;
}
QListWidget {
    background: transparent;
    border: 0;
}
QListWidget::item {
    border-radius: 6px;
    padding: 8px;
}
QListWidget::item:selected {
    background: #38504b;
    color: #f7fbf8;
}
QPushButton, QToolButton {
    background: #252b2e;
    border: 1px solid #3c474b;
    border-radius: 6px;
    color: #eef2ef;
    padding: 8px 10px;
}
QPushButton:hover, QToolButton:hover {
    background: #30393c;
}
QTableWidget {
    background: #202629;
    border: 1px solid #3c474b;
    border-radius: 6px;
    color: #eef2ef;
    gridline-color: #3c474b;
}
"""


class MainWindow(QMainWindow):
    """Top-level window for the desktop interface."""

    def __init__(self, db_path: Path, service: Optional[InterfaceService] = None) -> None:
        super().__init__()
        self.db_path = db_path
        self.service = service or InterfaceService.from_database(db_path)
        self._owns_service = service is None
        self.settings = QSettings("Funes", "Funes")
        self.selected_directory: Optional[str] = None
        self._directory_counts: dict[str, int] = {}
        self._workers: set[tuple[QThread, ServiceWorker]] = set()
        self._last_list_widget: Optional[QWidget] = None
        self._list_mode: Optional[str] = None
        self._active_title = ""
        self._active_query: Optional[str] = None
        self._active_directory_scope: Optional[str] = None
        self._active_source_image: Optional[str] = None
        self._list_offset = 0
        self._list_has_more = False
        self._list_page_worker_running = False
        self._list_request_id = 0
        self._removing_directories: set[str] = set()

        self.setWindowTitle("Funes")
        self._restore_window_size()
        self.setCentralWidget(self._build_shell())
        self._restore_theme()
        self.refresh_library()

    def refresh_library(self) -> None:
        stats = self.service.library_stats()
        directories = self.service.directory_listing()
        self._directory_counts = {
            directory.path: directory.image_count for directory in directories
        }
        self.welcome_view.set_stats(stats)
        self.directory_panel.set_directories(directories)

    def _build_shell(self) -> QWidget:
        container = QWidget()
        root_layout = QHBoxLayout(container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.directory_panel = DirectoryTreePanel()
        self.directory_panel.directory_selected.connect(self._select_directory)
        self.directory_panel.import_requested.connect(self._request_import_folder)
        self.directory_panel.remove_requested.connect(self._request_remove_directory)
        root_layout.addWidget(self.directory_panel)
        root_layout.addWidget(Separator())

        main_content = QWidget()
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(14)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        self.search_bar = SearchBar()
        self.search_bar.search_requested.connect(self._search_text)
        top_bar.addWidget(self.search_bar, 1)

        self.theme_button = QToolButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setCheckable(True)
        self.theme_button.clicked.connect(self._toggle_theme)
        top_bar.addWidget(self.theme_button)
        main_layout.addLayout(top_bar)

        self.stack = QStackedWidget()
        self.welcome_view = WelcomeView()
        self.directory_view = DirectoryContentsView()
        self.directory_view.image_selected.connect(self._show_image_details)
        self.directory_view.next_batch_requested.connect(self._request_next_list_batch)
        self.details_view = ImageDetailsView()
        self.details_view.back_requested.connect(self._go_back_to_list)
        self.details_view.similar_requested.connect(self._request_similar_images)
        self.stack.addWidget(self.welcome_view)
        self.stack.addWidget(self.directory_view)
        self.stack.addWidget(self.details_view)
        main_layout.addWidget(self.stack, 1)

        root_layout.addWidget(main_content, 1)
        return container

    def _select_directory(self, directory: str) -> None:
        if directory not in self._directory_counts:
            self.selected_directory = None
            self.search_bar.set_current_directory(None)
            self.directory_view.set_error(directory, "This directory is not indexed.")
            self.stack.setCurrentWidget(self.directory_view)
            return
        self.selected_directory = directory
        self.search_bar.set_current_directory(directory)
        self.directory_view.set_loading(directory)
        self.stack.setCurrentWidget(self.directory_view)
        self._last_list_widget = self.directory_view
        self._reset_list_state(
            LIST_MODE_DIRECTORY,
            directory,
            directory_scope=directory,
        )
        self._load_current_list_page(initial=True)

    def _search_text(self, query: str, directory: object) -> None:
        scoped_directory = directory if isinstance(directory, str) else None
        label = scoped_directory or "all images"
        title = f'Search: "{query}" in {label}'
        self.directory_view.set_loading(title, "Searching...")
        self.stack.setCurrentWidget(self.directory_view)
        self._last_list_widget = self.directory_view
        self._reset_list_state(
            LIST_MODE_TEXT_SEARCH,
            title,
            query=query,
            directory_scope=scoped_directory,
        )
        self._load_current_list_page(initial=True)

    def _request_import_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Import folder")
        if not directory:
            return
        import_path = str(Path(directory).expanduser().resolve())
        self.directory_panel.mark_importing(import_path, True)
        self.statusBar().showMessage(f"Importing {import_path}...")
        self._run_worker(
            lambda: self.service.index_directory(import_path),
            lambda indexed: self._finish_import(import_path, indexed),
            lambda message: self._fail_import(import_path, message),
        )

    def _finish_import(self, directory: str, indexed: object) -> None:
        self.directory_panel.mark_importing(directory, False)
        self.refresh_library()
        self.statusBar().showMessage(f"Indexed {indexed} image(s) from {directory}.", 5000)
        if self.selected_directory == directory:
            self._select_directory(directory)

    def _fail_import(self, directory: str, message: str) -> None:
        self.directory_panel.mark_importing(directory, False)
        self.statusBar().showMessage(f"Import failed: {message}", 7000)
        self.directory_view.set_error(directory, message)
        self.stack.setCurrentWidget(self.directory_view)

    def _request_remove_directory(self, directory: str) -> None:
        if directory in self._removing_directories:
            return
        response = QMessageBox.question(
            self,
            "Remove directory from index",
            f"Remove indexed records for {directory}?\n\nFiles on disk will not be changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self._removing_directories.add(directory)
        self.directory_panel.mark_removing(directory, True)
        self.statusBar().showMessage(f"Removing {directory} from the index...")
        self._run_worker(
            lambda: self.service.remove_directory(directory),
            lambda removed: self._finish_remove_directory(directory, removed),
            lambda message: self._fail_remove_directory(directory, message),
        )

    def _finish_remove_directory(self, directory: str, removed: object) -> None:
        self._removing_directories.discard(directory)
        removed_count = removed if isinstance(removed, int) else 0
        if removed_count <= 0:
            self.directory_panel.mark_removing(directory, False)
            self.statusBar().showMessage(f"{directory} is not indexed.", 7000)
            self.directory_view.set_error(directory, "This directory is not indexed.")
            self.stack.setCurrentWidget(self.directory_view)
            return

        removed_was_selected = self.selected_directory == directory
        removed_was_active_scope = self._active_directory_scope == directory
        self.refresh_library()
        self.statusBar().showMessage(
            f"Removed {removed_count} indexed image(s) from {directory}.",
            5000,
        )
        if removed_was_selected:
            self.selected_directory = None
            self.search_bar.set_current_directory(None)
        if removed_was_selected or removed_was_active_scope:
            self._list_request_id += 1
            self._list_mode = None
            self._active_directory_scope = None
            self._last_list_widget = None
            self.directory_view.set_loading_more(False)
            self.stack.setCurrentWidget(self.welcome_view)

    def _fail_remove_directory(self, directory: str, message: str) -> None:
        self._removing_directories.discard(directory)
        self.directory_panel.mark_removing(directory, False)
        self.statusBar().showMessage(f"Remove failed: {message}", 7000)

    def _show_image_details(self, record: object) -> None:
        if not isinstance(record, ImageRecord):
            return
        self._last_list_widget = self.stack.currentWidget()
        metadata = self.service.image_metadata(record.path)
        self.details_view.set_image(record, metadata)
        self.stack.setCurrentWidget(self.details_view)

    def _go_back_to_list(self) -> None:
        if self._last_list_widget is not None:
            self.stack.setCurrentWidget(self._last_list_widget)
            return
        self.stack.setCurrentWidget(self.welcome_view)

    def _request_similar_images(self, record: object) -> None:
        if isinstance(record, ImageRecord):
            title = f'Search: similar images to "{record.path}"'
            self.directory_view.set_loading(title, "Searching...")
            self.stack.setCurrentWidget(self.directory_view)
            self._last_list_widget = self.directory_view
            self._reset_list_state(
                LIST_MODE_SIMILAR_IMAGES,
                title,
                source_image=record.path,
            )
            self._load_current_list_page(initial=True)

    def _reset_list_state(
        self,
        mode: str,
        title: str,
        query: Optional[str] = None,
        directory_scope: Optional[str] = None,
        source_image: Optional[str] = None,
    ) -> None:
        self._list_request_id += 1
        self._list_mode = mode
        self._active_title = title
        self._active_query = query
        self._active_directory_scope = directory_scope
        self._active_source_image = source_image
        self._list_offset = 0
        self._list_has_more = True
        self._list_page_worker_running = False
        self.directory_view.set_loading_more(False)

    def _request_next_list_batch(self) -> None:
        if (
            self._list_mode is None
            or not self._list_has_more
            or self._list_page_worker_running
        ):
            self.directory_view.set_loading_more(False)
            return
        self._load_current_list_page(initial=False)

    def _load_current_list_page(self, initial: bool) -> None:
        if self._list_mode is None:
            return
        request_id = self._list_request_id
        title = self._active_title
        offset = self._list_offset
        self._list_page_worker_running = True
        if not initial:
            self.directory_view.set_loading_more(True)
            self.statusBar().showMessage("Loading more images...")
        self._run_worker(
            lambda: self._load_list_records(offset),
            lambda images: self._finish_list_page(request_id, title, initial, images),
            lambda message: self._fail_list_page(request_id, title, initial, message),
        )

    def _load_list_records(self, offset: int) -> list[ImageRecord]:
        if self._list_mode == LIST_MODE_DIRECTORY:
            if self._active_directory_scope is None:
                return []
            return self.service.directory_contents(
                self._active_directory_scope,
                limit=DIRECTORY_PAGE_SIZE,
                offset=offset,
            )
        if self._list_mode == LIST_MODE_TEXT_SEARCH:
            return self.service.search_text(
                self._active_query or "",
                limit=DIRECTORY_PAGE_SIZE,
                offset=offset,
                directory=self._active_directory_scope,
            )
        if self._list_mode == LIST_MODE_SIMILAR_IMAGES:
            if self._active_source_image is None:
                return []
            return self.service.similar_images(
                self._active_source_image,
                limit=DIRECTORY_PAGE_SIZE,
                offset=offset,
            )
        return []

    def _finish_list_page(
        self,
        request_id: int,
        title: str,
        initial: bool,
        images: object,
    ) -> None:
        if request_id != self._list_request_id:
            return
        records = list(images) if isinstance(images, list) else []
        if initial:
            self.directory_view.set_images(title, records)
        else:
            self.directory_view.append_images(title, records)
        self._list_offset += len(records)
        self._list_has_more = len(records) == DIRECTORY_PAGE_SIZE
        self._list_page_worker_running = False
        self.directory_view.set_loading_more(False)
        if initial:
            return
        if self._list_has_more:
            self.statusBar().showMessage(f"Loaded {len(records)} more image(s).", 3000)
            return
        self.statusBar().showMessage("All matching images are loaded.", 3000)

    def _fail_list_page(
        self,
        request_id: int,
        title: str,
        initial: bool,
        message: str,
    ) -> None:
        if request_id != self._list_request_id:
            return
        self._list_page_worker_running = False
        self.directory_view.set_loading_more(False)
        if initial:
            self.directory_view.set_error(title, message)
            return
        self.statusBar().showMessage(f"Could not load more images: {message}", 7000)

    def _run_worker(
        self,
        call: Callable[[], object],
        on_finished: Callable[[object], None],
        on_failed: Callable[[str], None],
    ) -> None:
        thread = QThread(self)
        worker = ServiceWorker(call)
        worker.moveToThread(thread)
        handle = (thread, worker)
        self._workers.add(handle)

        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.failed.connect(on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._workers.discard(handle))
        thread.start()

    def _toggle_theme(self) -> None:
        theme = "dark" if self.theme_button.isChecked() else "light"
        self._apply_theme(theme)
        self.settings.setValue("theme", theme)

    def _apply_theme(self, theme: str) -> None:
        is_dark = theme == "dark"
        self.theme_button.setChecked(is_dark)
        self.theme_button.setText("Dark" if is_dark else "Light")
        self.theme_button.setToolTip("Switch color theme")
        self.setStyleSheet(DARK_STYLESHEET if is_dark else LIGHT_STYLESHEET)

    def _restore_theme(self) -> None:
        theme = self.settings.value("theme", "light")
        self._apply_theme("dark" if theme == "dark" else "light")

    def _restore_window_size(self) -> None:
        size = self.settings.value("window_size")
        if isinstance(size, QSize) and size.isValid():
            self.resize(size)
            return
        self.resize(1100, 720)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("window_size", self.size())
        for thread, _worker in list(self._workers):
            thread.quit()
            thread.wait(2000)
        if self._owns_service:
            self.service.close()
        super().closeEvent(event)
