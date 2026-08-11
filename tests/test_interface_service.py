from pathlib import Path
from unittest import mock

from funes.interface.service import InterfaceService
from funes.search import SearchEngine
from funes.storage import SQLiteStore


def test_library_stats_reads_store_counts() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.image_count.return_value = 12
    store.directory_count.return_value = 3
    service = InterfaceService(store)

    stats = service.library_stats()

    assert stats.image_count == 12
    assert stats.directory_count == 3


def test_directory_listing_wraps_store_counts() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.directory_counts.return_value = [("/photos", 4), ("/screens", 2)]
    service = InterfaceService(store)

    directories = service.directory_listing()

    assert [directory.path for directory in directories] == ["/photos", "/screens"]
    assert [directory.image_count for directory in directories] == [4, 2]


def test_directory_contents_returns_image_records() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.images_in_directory.return_value = ["/photos/one.jpg"]
    service = InterfaceService(store)

    records = service.directory_contents("/photos")

    store.images_in_directory.assert_called_once_with("/photos", limit=None, offset=0)
    assert records[0].path == "/photos/one.jpg"
    assert records[0].filename == "one.jpg"
    assert records[0].directory == "/photos"


def test_text_search_passes_optional_directory_scope() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    engine = mock.create_autospec(SearchEngine, instance=True)
    engine.search_text.return_value = ["/photos/one.jpg"]
    service = InterfaceService(store, engine)

    records = service.search_text("blue chair", limit=7, directory="/photos")

    engine.search_text.assert_called_once_with(
        "blue chair", n=7, offset=0, directory="/photos"
    )
    assert records[0].filename == "one.jpg"


def test_directory_contents_passes_pagination() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.images_in_directory.return_value = ["/photos/two.jpg"]
    service = InterfaceService(store)

    records = service.directory_contents("/photos", limit=10, offset=10)

    store.images_in_directory.assert_called_once_with("/photos", limit=10, offset=10)
    assert records[0].filename == "two.jpg"


def test_text_search_passes_pagination() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    engine = mock.create_autospec(SearchEngine, instance=True)
    engine.search_text.return_value = ["/photos/two.jpg"]
    service = InterfaceService(store, engine)

    records = service.search_text("blue chair", limit=7, offset=14, directory="/photos")

    engine.search_text.assert_called_once_with(
        "blue chair", n=7, offset=14, directory="/photos"
    )
    assert records[0].filename == "two.jpg"


def test_similar_images_passes_optional_directory_scope() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    engine = mock.create_autospec(SearchEngine, instance=True)
    engine.search_image.return_value = ["/photos/one.jpg", "/photos/two.jpg"]
    service = InterfaceService(store, engine)

    records = service.similar_images(Path("/photos/one.jpg"), limit=5, directory="/photos")

    engine.search_image.assert_called_once_with(
        Path("/photos/one.jpg"), n=6, offset=0, directory="/photos"
    )
    assert len(records) == 1
    assert records[0].path == "/photos/two.jpg"


def test_similar_images_fetches_enough_to_filter_source_before_offset() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    engine = mock.create_autospec(SearchEngine, instance=True)
    engine.search_image.return_value = [
        "/photos/source.jpg",
        "/photos/one.jpg",
        "/photos/two.jpg",
        "/photos/three.jpg",
    ]
    service = InterfaceService(store, engine)

    records = service.similar_images("/photos/source.jpg", limit=2, offset=1)

    engine.search_image.assert_called_once_with(
        "/photos/source.jpg", n=4, offset=0, directory=None
    )
    assert [record.path for record in records] == ["/photos/two.jpg", "/photos/three.jpg"]


@mock.patch("funes.interface.service.Path.resolve", autospec=True)
def test_remove_directory_normalizes_and_delegates_to_store(resolve: mock.Mock) -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.remove_directory.return_value = 4
    resolve.return_value = Path("/photos")
    service = InterfaceService(store)

    removed = service.remove_directory("~/photos")

    assert removed == 4
    store.remove_directory.assert_called_once_with("/photos")


@mock.patch("funes.interface.service.Path.resolve", autospec=True)
def test_remove_directory_returns_zero_when_store_does_not_remove(resolve: mock.Mock) -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.remove_directory.return_value = 0
    resolve.return_value = Path("/missing")
    service = InterfaceService(store)

    removed = service.remove_directory("/missing")

    assert removed == 0
    store.remove_directory.assert_called_once_with("/missing")
