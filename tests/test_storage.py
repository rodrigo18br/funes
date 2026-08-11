from pathlib import Path
from unittest import mock

import numpy as np

from funes.storage import DEFAULT_DIMENSION, SQLiteStore


def make_store(conn: mock.Mock) -> SQLiteStore:
    store = SQLiteStore.__new__(SQLiteStore)
    store._conn = conn
    store._dimension = DEFAULT_DIMENSION
    return store


@mock.patch("funes.storage.importlib.resources.files", autospec=True)
@mock.patch("funes.storage.sqlite3.connect", autospec=True)
def test_init_opens_database_loads_extension_and_initializes_vector_table(
    connect: mock.Mock, files: mock.Mock
) -> None:
    conn = mock.Mock()
    connect.return_value = conn
    files.return_value = Path("/tmp/sqlite-vector")

    store = SQLiteStore("index.db", dimension=128)

    assert store._dimension == 128
    connect.assert_called_once_with("index.db", check_same_thread=False)
    conn.enable_load_extension.assert_has_calls([mock.call(True), mock.call(False)])
    conn.load_extension.assert_called_once_with("/tmp/sqlite-vector/vector")
    conn.commit.assert_called_once_with()
    assert conn.execute.call_args_list[0].args[0].lstrip().startswith(
        "CREATE TABLE IF NOT EXISTS images"
    )
    conn.execute.assert_any_call(
        "SELECT vector_init(?, ?, ?)",
        ("images", "embedding", "dimension=128,type=FLOAT32,distance=cosine"),
    )


def test_add_records_returns_zero_for_empty_iterable_without_writing() -> None:
    conn = mock.Mock()
    store = make_store(conn)

    inserted = store.add_records([])

    assert inserted == 0
    conn.executemany.assert_not_called()
    conn.commit.assert_not_called()


def test_add_records_converts_paths_and_float32_vectors_before_upsert() -> None:
    conn = mock.Mock()
    cursor = mock.Mock(rowcount=2)
    conn.executemany.return_value = cursor
    store = make_store(conn)

    inserted = store.add_records(
        [
            ("/photos/first.jpg", np.array([1, 2], dtype=np.int64)),
            ("/photos/nested/second.jpg", np.array([3.5], dtype=np.float64)),
        ]
    )

    assert inserted == 2
    conn.executemany.assert_called_once()
    sql, rows = conn.executemany.call_args.args
    assert "ON CONFLICT(filename) DO UPDATE SET" in sql
    assert rows == [
        ("/photos", "/photos/first.jpg", "[1.0, 2.0]"),
        ("/photos/nested", "/photos/nested/second.jpg", "[3.5]"),
    ]
    conn.commit.assert_called_once_with()


def test_search_without_directory_applies_limit_and_offset_after_ordering() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchall.return_value = [
        ("first.jpg", 0.1),
        ("second.jpg", 0.2),
    ]
    store = make_store(conn)

    results = store.search(np.array([1, 2], dtype=np.int64), n=2)

    assert results == [("first.jpg", 0.1), ("second.jpg", 0.2)]
    sql, params = conn.execute.call_args.args
    assert "vector_full_scan" in sql
    assert "ORDER BY v.distance ASC" in sql
    assert "LIMIT ?" in sql
    assert "OFFSET ?" in sql
    assert params == ("images", "embedding", "[1.0, 2.0]", 2, 2, 0)


def test_search_without_directory_scans_enough_rows_for_offset() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchall.return_value = [("third.jpg", 0.3)]
    store = make_store(conn)

    results = store.search(np.array([1, 2], dtype=np.int64), n=1, offset=2)

    assert results == [("third.jpg", 0.3)]
    sql, params = conn.execute.call_args.args
    assert "ORDER BY v.distance ASC" in sql
    assert "LIMIT ?" in sql
    assert "OFFSET ?" in sql
    assert params == ("images", "embedding", "[1.0, 2.0]", 3, 1, 2)


def test_search_with_directory_scans_all_rows_then_filters_and_limits() -> None:
    conn = mock.Mock()
    count_result = mock.Mock()
    count_result.fetchone.return_value = (42,)
    search_result = mock.Mock()
    search_result.fetchall.return_value = [("/photos/first.jpg", 0.1)]
    conn.execute.side_effect = [count_result, search_result]
    store = make_store(conn)

    results = store.search(np.array([1, 2], dtype=np.float64), n=5, directory=Path("/photos"))

    assert results == [("/photos/first.jpg", 0.1)]
    count_sql = conn.execute.call_args_list[0].args[0]
    search_sql, search_params = conn.execute.call_args_list[1].args
    assert count_sql == "SELECT COUNT(*) FROM images"
    assert "WHERE images.dir = ?" in search_sql
    assert "LIMIT ?" in search_sql
    assert "OFFSET ?" in search_sql
    assert search_params == ("images", "embedding", "[1.0, 2.0]", 42, "/photos", 5, 0)


def test_search_with_directory_applies_offset_after_distance_ordering() -> None:
    conn = mock.Mock()
    count_result = mock.Mock()
    count_result.fetchone.return_value = (42,)
    search_result = mock.Mock()
    search_result.fetchall.return_value = [("/photos/later.jpg", 0.5)]
    conn.execute.side_effect = [count_result, search_result]
    store = make_store(conn)

    results = store.search(
        np.array([1, 2], dtype=np.float64), n=5, offset=10, directory=Path("/photos")
    )

    assert results == [("/photos/later.jpg", 0.5)]
    search_sql, search_params = conn.execute.call_args_list[1].args
    assert "ORDER BY v.distance ASC" in search_sql
    assert "LIMIT ?" in search_sql
    assert "OFFSET ?" in search_sql
    assert search_params == ("images", "embedding", "[1.0, 2.0]", 42, "/photos", 5, 10)


def test_count_methods_read_database_counts() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchone.side_effect = [(3,), (2,)]
    store = make_store(conn)

    assert store.count() == 3
    assert store.image_count() == 2

    assert conn.execute.call_args_list == [
        mock.call("SELECT COUNT(*) FROM images"),
        mock.call("SELECT COUNT(*) FROM images"),
    ]


def test_directory_count_reads_distinct_directory_count() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchone.return_value = (4,)
    store = make_store(conn)

    assert store.directory_count() == 4

    conn.execute.assert_called_once_with("SELECT COUNT(DISTINCT dir) FROM images")


def test_directory_counts_returns_ordered_directory_totals() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchall.return_value = [("/a", 1), ("/b", 2)]
    store = make_store(conn)

    assert store.directory_counts() == [("/a", 1), ("/b", 2)]
    assert store.count_dir() == [("/a", 1), ("/b", 2)]

    assert conn.execute.call_count == 2
    assert "GROUP BY dir" in conn.execute.call_args.args[0]
    assert "ORDER BY dir COLLATE NOCASE ASC" in conn.execute.call_args.args[0]


def test_images_in_directory_returns_ordered_filenames() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchall.return_value = [
        ("/photos/a.jpg",),
        ("/photos/b.jpg",),
    ]
    store = make_store(conn)

    images = store.images_in_directory(Path("/photos"))

    assert images == ["/photos/a.jpg", "/photos/b.jpg"]
    sql, params = conn.execute.call_args.args
    assert "WHERE dir = ?" in sql
    assert "ORDER BY filename COLLATE NOCASE ASC" in sql
    assert params == ("/photos",)


def test_images_in_directory_applies_limit_and_offset() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchall.return_value = [
        ("/photos/c.jpg",),
        ("/photos/d.jpg",),
    ]
    store = make_store(conn)

    images = store.images_in_directory(Path("/photos"), limit=2, offset=2)

    assert images == ["/photos/c.jpg", "/photos/d.jpg"]
    sql, params = conn.execute.call_args.args
    assert "ORDER BY filename COLLATE NOCASE ASC" in sql
    assert "LIMIT ?" in sql
    assert "OFFSET ?" in sql
    assert params == ("/photos", 2, 2)


def test_images_in_directory_returns_empty_page() -> None:
    conn = mock.Mock()
    conn.execute.return_value.fetchall.return_value = []
    store = make_store(conn)

    images = store.images_in_directory(Path("/photos"), limit=2, offset=10)

    assert images == []
    sql, params = conn.execute.call_args.args
    assert "LIMIT ?" in sql
    assert "OFFSET ?" in sql
    assert params == ("/photos", 2, 10)


def test_remove_directory_deletes_exact_directory_and_returns_count() -> None:
    conn = mock.Mock()
    conn.execute.return_value.rowcount = 3
    store = make_store(conn)

    removed = store.remove_directory(Path("/photos"))

    assert removed == 3
    sql, params = conn.execute.call_args.args
    assert "DELETE FROM images" in sql
    assert "WHERE dir = ?" in sql
    assert params == ("/photos",)
    conn.commit.assert_called_once_with()


def test_remove_directory_returns_zero_for_missing_directory() -> None:
    conn = mock.Mock()
    conn.execute.return_value.rowcount = 0
    store = make_store(conn)

    removed = store.remove_directory("/missing")

    assert removed == 0
    conn.commit.assert_called_once_with()


def test_remove_directory_uses_exact_dir_match_for_path_lookalikes() -> None:
    conn = mock.Mock()
    conn.execute.return_value.rowcount = 1
    store = make_store(conn)

    store.remove_directory("/photos")

    sql, params = conn.execute.call_args.args
    assert "LIKE" not in sql
    assert params == ("/photos",)


def test_remove_directory_does_not_touch_filesystem(tmp_path) -> None:
    image_path = tmp_path / "one.jpg"
    image_path.write_bytes(b"image")
    conn = mock.Mock()
    conn.execute.return_value.rowcount = 1
    store = make_store(conn)

    store.remove_directory(tmp_path)

    assert image_path.read_bytes() == b"image"


def test_close_closes_connection() -> None:
    conn = mock.Mock()
    store = make_store(conn)

    store.close()

    conn.close.assert_called_once_with()


def test_context_manager_returns_store_and_closes_on_exit() -> None:
    conn = mock.Mock()
    store = make_store(conn)

    with store as entered:
        assert entered is store

    conn.close.assert_called_once_with()
