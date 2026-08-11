from pathlib import Path
from unittest import mock

from funes.embedding import Embedder
from funes.search import SearchEngine
from funes.storage import SQLiteStore


def test_init_uses_provided_embedder() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)

    engine = SearchEngine(store, embedder)

    assert engine._store is store
    assert engine._embedder is embedder


@mock.patch("funes.search.Embedder", autospec=True)
def test_init_creates_default_embedder(embedder_cls: mock.Mock) -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)

    engine = SearchEngine(store)

    embedder_cls.assert_called_once_with()
    assert engine._embedder is embedder_cls.return_value


def test_index_images_embeds_paths_and_stores_records() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    embeddings = [
        object(),
        object(),
    ]
    embedder.embed_images.return_value = embeddings
    store.add_records.return_value = 2
    engine = SearchEngine(store, embedder)

    indexed = engine.index_images(["one.jpg", Path("two.jpg")])

    assert indexed == 2
    embedder.embed_images.assert_called_once_with(["one.jpg", "two.jpg"])
    records = list(store.add_records.call_args.args[0])
    assert records == [("one.jpg", embeddings[0]), ("two.jpg", embeddings[1])]


def test_search_text_embeds_query_and_returns_paths() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    embedding = object()
    embedder.embed_text.return_value = embedding
    store.search.return_value = [("first.jpg", 0.12), ("second.jpg", 0.34)]
    engine = SearchEngine(store, embedder)

    results = engine.search_text("sunset over water", n=5)

    assert results == ["first.jpg", "second.jpg"]
    embedder.embed_text.assert_called_once_with("sunset over water")
    store.search.assert_called_once_with(embedding, 5, offset=0)


def test_search_text_uses_default_limit() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    embedding = object()
    embedder.embed_text.return_value = embedding
    store.search.return_value = []
    engine = SearchEngine(store, embedder)

    results = engine.search_text("empty result")

    assert results == []
    store.search.assert_called_once_with(embedding, 10, offset=0)


def test_search_text_passes_directory_scope() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    embedding = object()
    embedder.embed_text.return_value = embedding
    store.search.return_value = [("scoped.jpg", 0.12)]
    engine = SearchEngine(store, embedder)

    results = engine.search_text("sunset over water", n=5, directory=Path("albums"))

    assert results == ["scoped.jpg"]
    embedder.embed_text.assert_called_once_with("sunset over water")
    store.search.assert_called_once_with(
        embedding, 5, offset=0, directory=Path("albums")
    )


def test_search_text_passes_offset_and_directory_scope() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    embedding = object()
    embedder.embed_text.return_value = embedding
    store.search.return_value = [("later.jpg", 0.42)]
    engine = SearchEngine(store, embedder)

    results = engine.search_text("sunset over water", n=5, offset=10, directory="/photos")

    assert results == ["later.jpg"]
    store.search.assert_called_once_with(
        embedding, 5, offset=10, directory="/photos"
    )


def test_search_image_embeds_image_path_and_returns_paths() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    image_path = Path("query.jpg")
    embedding = object()
    embedder.embed_image.return_value = embedding
    store.search.return_value = [("match.jpg", 0.56)]
    engine = SearchEngine(store, embedder)

    results = engine.search_image(image_path, n=3)

    assert results == ["match.jpg"]
    embedder.embed_image.assert_called_once_with(image_path)
    store.search.assert_called_once_with(embedding, 3, offset=0)


def test_search_image_uses_default_limit() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    embedding = object()
    embedder.embed_image.return_value = embedding
    store.search.return_value = []
    engine = SearchEngine(store, embedder)

    results = engine.search_image("query.jpg")

    assert results == []
    store.search.assert_called_once_with(embedding, 10, offset=0)


def test_search_image_passes_directory_scope() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    image_path = Path("query.jpg")
    embedding = object()
    embedder.embed_image.return_value = embedding
    store.search.return_value = [("scoped-match.jpg", 0.56)]
    engine = SearchEngine(store, embedder)

    results = engine.search_image(image_path, n=3, directory="/photos")

    assert results == ["scoped-match.jpg"]
    embedder.embed_image.assert_called_once_with(image_path)
    store.search.assert_called_once_with(embedding, 3, offset=0, directory="/photos")


def test_search_image_passes_offset_and_directory_scope() -> None:
    store = mock.create_autospec(SQLiteStore, instance=True)
    embedder = mock.create_autospec(Embedder, instance=True)
    image_path = Path("query.jpg")
    embedding = object()
    embedder.embed_image.return_value = embedding
    store.search.return_value = [("later-match.jpg", 0.56)]
    engine = SearchEngine(store, embedder)

    results = engine.search_image(image_path, n=3, offset=6, directory="/photos")

    assert results == ["later-match.jpg"]
    store.search.assert_called_once_with(embedding, 3, offset=6, directory="/photos")
