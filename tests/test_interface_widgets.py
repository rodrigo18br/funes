from __future__ import annotations

from unittest import mock

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QMessageBox, QToolButton

from funes.interface.main_window import MainWindow
from funes.interface.service import DirectorySummary, ImageRecord, InterfaceService, LibraryStats
from funes.interface.widgets import (
    DirectoryContentsView,
    DirectoryRowWidget,
    DirectoryTreePanel,
    ImageDetailsView,
    ElideLabel,
)


def _service_with_library(
    image_count: int = 0,
    directory_count: int = 0,
    directories: list[DirectorySummary] | None = None,
) -> InterfaceService:
    service = mock.create_autospec(InterfaceService, instance=True)
    service.library_stats.return_value = LibraryStats(
        image_count=image_count,
        directory_count=directory_count,
    )
    service.directory_listing.return_value = directories or []
    return service


def test_main_window_constructs_shell(qtbot, tmp_path) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )

    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    assert window.windowTitle() == "Funes"
    assert window.directory_panel.directory_list.count() == 1
    assert window.welcome_view.stats.text() == (
        "3 indexed images\n1 imported directories"
    )


def test_directory_tree_panel_emits_selected_directory(qtbot) -> None:
    panel = DirectoryTreePanel()
    qtbot.addWidget(panel)
    panel.set_directories([DirectorySummary("/photos", 3)])

    with qtbot.waitSignal(panel.directory_selected) as blocker:
        panel.directory_list.setCurrentRow(0)

    assert blocker.args == ["/photos"]
    assert panel.selected_directory == "/photos"


def test_directory_tree_panel_import_button_emits_request(qtbot) -> None:
    panel = DirectoryTreePanel()
    qtbot.addWidget(panel)

    with qtbot.waitSignal(panel.import_requested):
        qtbot.mouseClick(panel.import_button, Qt.MouseButton.LeftButton)


def test_directory_tree_panel_renders_remove_button_per_indexed_directory(qtbot) -> None:
    panel = DirectoryTreePanel()
    qtbot.addWidget(panel)

    panel.set_directories([
        DirectorySummary("/photos", 3),
        DirectorySummary("/screens", 2),
    ])

    buttons = panel.directory_list.findChildren(QToolButton, "directoryRemoveButton")
    assert len(buttons) == 2
    assert {button.toolTip() for button in buttons} == {
        "Remove /photos from the index",
        "Remove /screens from the index",
    }


def test_directory_tree_panel_hides_remove_button_for_importing_rows(qtbot) -> None:
    panel = DirectoryTreePanel()
    qtbot.addWidget(panel)

    panel.mark_importing("/importing", True)

    row = panel.directory_list.itemWidget(panel.directory_list.item(0))
    button = row.findChild(QToolButton, "directoryRemoveButton")
    assert button is not None
    assert not button.isVisible()


def test_directory_tree_panel_remove_button_emits_directory_without_selecting(qtbot) -> None:
    panel = DirectoryTreePanel()
    qtbot.addWidget(panel)
    panel.set_directories([DirectorySummary("/photos", 3)])
    row = panel.directory_list.itemWidget(panel.directory_list.item(0))
    button = row.findChild(QToolButton, "directoryRemoveButton")

    with qtbot.waitSignal(panel.remove_requested) as blocker:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert blocker.args == ["/photos"]
    assert panel.selected_directory is None


def test_directory_tree_panel_row_click_preserves_selection_behavior(qtbot) -> None:
    panel = DirectoryTreePanel()
    qtbot.addWidget(panel)
    panel.set_directories([DirectorySummary("/photos", 3)])
    row = panel.directory_list.itemWidget(panel.directory_list.item(0))

    with qtbot.waitSignal(panel.directory_selected) as blocker:
        qtbot.mouseClick(row, Qt.MouseButton.LeftButton)

    assert blocker.args == ["/photos"]
    assert panel.selected_directory == "/photos"

def test_main_window_selection_updates_search_scope(qtbot, tmp_path) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )
    service.search_text.return_value = []
    service.directory_contents.return_value = []

    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window.directory_panel.directory_list.setCurrentRow(0)

    assert window.selected_directory == "/photos"
    assert window.search_bar.scope_button.isEnabled()
    assert window.search_bar.current_directory == "/photos"


@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_remove_cancellation_does_not_call_service(
    question, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )
    question.return_value = QMessageBox.StandardButton.No
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_remove_directory("/photos")

    service.remove_directory.assert_not_called()
    assert window.directory_panel.directory_list.count() == 1


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_accepted_removal_calls_service_through_worker(
    question, run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )
    question.return_value = QMessageBox.StandardButton.Yes
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_remove_directory("/photos")

    run_worker.assert_called_once()
    call = run_worker.call_args.args[1]
    service.remove_directory.return_value = 3
    assert call() == 3
    service.remove_directory.assert_called_once_with("/photos")


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_successful_removal_refreshes_library(
    question, run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )
    service.library_stats.side_effect = [
        LibraryStats(3, 1),
        LibraryStats(0, 0),
    ]
    service.directory_listing.side_effect = [
        [DirectorySummary("/photos", 3)],
        [],
    ]
    question.return_value = QMessageBox.StandardButton.Yes

    def run_now(_window, _call, on_finished, _on_failed) -> None:
        on_finished(3)

    run_worker.side_effect = run_now
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_remove_directory("/photos")

    assert window.directory_panel.directory_list.count() == 0
    assert window.welcome_view.stats.text() == (
        "0 indexed images\n0 imported directories"
    )


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_removing_selected_directory_clears_scope_and_welcomes(
    question, run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )
    service.directory_contents.return_value = []
    service.library_stats.side_effect = [
        LibraryStats(3, 1),
        LibraryStats(0, 0),
    ]
    service.directory_listing.side_effect = [
        [DirectorySummary("/photos", 3)],
        [],
    ]

    def run_now(_window, call, on_finished, _on_failed) -> None:
        if service.directory_contents.call_count == 0:
            on_finished(call())
            return
        on_finished(3)

    run_worker.side_effect = run_now
    question.return_value = QMessageBox.StandardButton.Yes
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)
    window.directory_panel.directory_list.setCurrentRow(0)

    window._request_remove_directory("/photos")

    assert window.selected_directory is None
    assert window.search_bar.current_directory is None
    assert not window.search_bar.scope_button.isChecked()
    assert window.stack.currentWidget() == window.welcome_view


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_removal_failure_preserves_directory_row(
    question, run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )

    def run_now(_window, _call, _on_finished, on_failed) -> None:
        on_failed("database busy")

    run_worker.side_effect = run_now
    question.return_value = QMessageBox.StandardButton.Yes
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_remove_directory("/photos")

    assert window.directory_panel.directory_list.count() == 1
    assert "Remove failed: database busy" in window.statusBar().currentMessage()


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_not_found_removal_keeps_directory_row(
    question, run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )

    def run_now(_window, _call, on_finished, _on_failed) -> None:
        on_finished(0)

    run_worker.side_effect = run_now
    question.return_value = QMessageBox.StandardButton.Yes
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_remove_directory("/photos")

    assert window.directory_panel.directory_list.count() == 1
    assert window.directory_view.message.text() == "This directory is not indexed."


@mock.patch("funes.interface.main_window.QMessageBox.question")
def test_main_window_repeated_remove_click_while_active_is_ignored(
    question, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=3,
        directory_count=1,
        directories=[DirectorySummary("/photos", 3)],
    )
    question.return_value = QMessageBox.StandardButton.Yes
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)
    window._removing_directories.add("/photos")

    window._request_remove_directory("/photos")

    question.assert_not_called()


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
@mock.patch("funes.interface.main_window.QFileDialog.getExistingDirectory")
def test_main_window_import_action_starts_worker_and_marks_busy(
    folder_picker, run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library()
    folder_picker.return_value = str(tmp_path)

    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_import_folder()
    directory_list = window.directory_panel.directory_list
    list_widget = directory_list.item(0).listWidget()
    row_widget = list_widget.itemWidget(list_widget.item(0))

    run_worker.assert_called_once()
    assert directory_list.count() == 1
    assert "Importing..." in row_widget.count_label.text()


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
def test_main_window_search_results_render(run_worker, qtbot, tmp_path) -> None:
    service = _service_with_library(
        image_count=1,
        directory_count=1,
        directories=[DirectorySummary("/photos", 1)],
    )
    record = ImageRecord("/photos/one.jpg", "one.jpg", "/photos")

    def run_now(_window, _call, on_finished, _on_failed) -> None:
        on_finished([record])

    run_worker.side_effect = run_now
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._search_text("blue chair", None)

    assert window.directory_view.image_list.count() == 1
    assert "one.jpg" in window.directory_view.image_list.item(0).text()


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
def test_main_window_directory_contents_render(run_worker, qtbot, tmp_path) -> None:
    service = _service_with_library(
        image_count=1,
        directory_count=1,
        directories=[DirectorySummary("/photos", 1)],
    )
    record = ImageRecord("/photos/one.jpg", "one.jpg", "/photos")

    def run_now(_window, call, on_finished, _on_failed) -> None:
        service.directory_contents.assert_not_called()
        assert call() == [record]
        on_finished([record])

    service.directory_contents.return_value = [record]
    run_worker.side_effect = run_now
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window.directory_panel.directory_list.setCurrentRow(0)

    service.directory_contents.assert_called_once_with("/photos", limit=10, offset=0)
    assert window.directory_view.image_list.count() == 1
    assert "one.jpg" in window.directory_view.image_list.item(0).text()


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
def test_main_window_initial_directory_load_failure_shows_error(
    run_worker, qtbot, tmp_path
) -> None:
    service = _service_with_library(
        image_count=1,
        directory_count=1,
        directories=[DirectorySummary("/photos", 1)],
    )

    def fail_now(_window, _call, _on_finished, on_failed) -> None:
        on_failed("database busy")

    run_worker.side_effect = fail_now
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window.directory_panel.directory_list.setCurrentRow(0)

    assert window.directory_view.message.text() == "database busy"


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
def test_main_window_appends_next_directory_batch(run_worker, qtbot, tmp_path) -> None:
    service = _service_with_library(
        image_count=20,
        directory_count=1,
        directories=[DirectorySummary("/photos", 20)],
    )
    first_batch = [
        ImageRecord(f"/photos/{index}.jpg", f"{index}.jpg", "/photos")
        for index in range(10)
    ]
    second_batch = [ImageRecord("/photos/10.jpg", "10.jpg", "/photos")]
    def run_now(_window, call, on_finished, _on_failed) -> None:
        on_finished(call())

    service.directory_contents.side_effect = [first_batch, second_batch]
    run_worker.side_effect = run_now
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window.directory_panel.directory_list.setCurrentRow(0)
    window._request_next_list_batch()

    assert service.directory_contents.call_args_list == [
        mock.call("/photos", limit=10, offset=0),
        mock.call("/photos", limit=10, offset=10),
    ]
    assert window.directory_view.image_list.count() == 11
    assert "10.jpg" in window.directory_view.image_list.item(10).text()


def test_image_list_view_emits_selected_record(qtbot, tmp_path) -> None:
    image_path = tmp_path / "one.png"
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.red)
    pixmap.save(str(image_path))
    record = ImageRecord(str(image_path), "one.png", str(tmp_path))
    view = DirectoryContentsView()
    qtbot.addWidget(view)
    view.set_images("Results", [record])

    with qtbot.waitSignal(view.image_selected) as blocker:
        view.image_list.itemClicked.emit(view.image_list.item(0))

    assert blocker.args == [record]


def test_image_list_view_appends_records_without_clearing(qtbot, tmp_path) -> None:
    first = ImageRecord("/photos/one.jpg", "one.jpg", "/photos")
    second = ImageRecord("/photos/two.jpg", "two.jpg", "/photos")
    view = DirectoryContentsView()
    qtbot.addWidget(view)

    view.set_images("Results", [first])
    view.append_images("Results", [second])

    assert view.image_list.count() == 2
    assert "one.jpg" in view.image_list.item(0).text()
    assert "two.jpg" in view.image_list.item(1).text()


def test_image_list_view_requests_next_batch_at_bottom(qtbot) -> None:
    view = DirectoryContentsView()
    qtbot.addWidget(view)
    records = [
        ImageRecord(f"/photos/{index}.jpg", f"{index}.jpg", "/photos")
        for index in range(40)
    ]
    view.set_images("Results", records)
    view.resize(220, 180)
    view.show()
    qtbot.waitExposed(view)

    with qtbot.waitSignal(view.next_batch_requested):
        scrollbar = view.image_list.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def test_main_window_clicking_image_opens_details(qtbot, tmp_path) -> None:
    image_path = tmp_path / "one.png"
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.green)
    pixmap.save(str(image_path))
    record = ImageRecord(str(image_path), "one.png", str(tmp_path))
    service = _service_with_library()
    service.image_metadata.return_value = {"Filename": "one.png"}
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)
    window.directory_view.set_images("Results", [record])
    window.stack.setCurrentWidget(window.directory_view)

    window.directory_view.image_list.itemClicked.emit(window.directory_view.image_list.item(0))

    service.image_metadata.assert_called_once_with(str(image_path))
    assert window.stack.currentWidget() == window.details_view
    assert window.details_view.metadata.item(0, 1).text() == "one.png"


def test_image_details_view_shows_metadata_and_similar_action(qtbot, tmp_path) -> None:
    image_path = tmp_path / "one.png"
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.blue)
    pixmap.save(str(image_path))
    record = ImageRecord(str(image_path), "one.png", str(tmp_path))
    view = ImageDetailsView()
    qtbot.addWidget(view)
    view.set_image(record, {"Filename": "one.png", "Format": "PNG"})

    assert view.metadata.rowCount() == 2
    with qtbot.waitSignal(view.similar_requested) as blocker:
        qtbot.mouseClick(view.similar_button, Qt.MouseButton.LeftButton)

    assert blocker.args == [record]


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
def test_main_window_similar_action_requests_service_call(run_worker, qtbot, tmp_path) -> None:
    service = _service_with_library()
    source = ImageRecord("/photos/one.jpg", "one.jpg", "/photos")
    match = ImageRecord("/photos/two.jpg", "two.jpg", "/photos")

    def run_now(_window, call, on_finished, _on_failed) -> None:
        assert call() == [match]
        on_finished([match])

    service.similar_images.return_value = [match]
    run_worker.side_effect = run_now
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window._request_similar_images(source)

    service.similar_images.assert_called_once_with("/photos/one.jpg", limit=10, offset=0)
    assert window.directory_view.image_list.count() == 1
    assert "two.jpg" in window.directory_view.image_list.item(0).text()


@mock.patch.object(MainWindow, "_run_worker", autospec=True)
def test_main_window_later_page_failure_preserves_records(run_worker, qtbot, tmp_path) -> None:
    service = _service_with_library(
        image_count=20,
        directory_count=1,
        directories=[DirectorySummary("/photos", 20)],
    )
    first_batch = [
        ImageRecord(f"/photos/{index}.jpg", f"{index}.jpg", "/photos")
        for index in range(10)
    ]

    def run_page(_window, call, on_finished, on_failed) -> None:
        if service.directory_contents.call_count == 0:
            assert call() == first_batch
            on_finished(first_batch)
            return
        on_failed("database busy")

    service.directory_contents.return_value = first_batch
    run_worker.side_effect = run_page
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    window.directory_panel.directory_list.setCurrentRow(0)
    window._request_next_list_batch()

    assert window.directory_view.image_list.count() == 10
    assert "Could not load more images" in window.statusBar().currentMessage()


def test_main_window_theme_switch_persists(qtbot, tmp_path) -> None:
    QSettings("Funes", "Funes").clear()
    service = _service_with_library()
    window = MainWindow(tmp_path / "funes.db", service=service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.theme_button, Qt.MouseButton.LeftButton)

    assert window.theme_button.isChecked()
    assert "background: #171a1c" in window.styleSheet()
    assert QSettings("Funes", "Funes").value("theme") == "dark"
