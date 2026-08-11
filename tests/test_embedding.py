from pathlib import Path
from unittest import mock

import numpy as np

from funes.embedding import IMAGE_MODEL_NAME, TEXT_MODEL_NAME, Embedder


@mock.patch("funes.embedding.TextEmbedding", autospec=True)
def test_text_model_is_loaded_lazily_and_reused(text_embedding_cls: mock.Mock) -> None:
    embedder = Embedder(text_model_name="text-model")

    assert embedder._text_model is None

    first_model = embedder.text_model
    second_model = embedder.text_model

    text_embedding_cls.assert_called_once_with(model_name="text-model")
    assert first_model is text_embedding_cls.return_value
    assert second_model is first_model


@mock.patch("funes.embedding.ImageEmbedding", autospec=True)
def test_image_model_is_loaded_lazily_and_reused(image_embedding_cls: mock.Mock) -> None:
    embedder = Embedder(image_model_name="image-model")

    assert embedder._image_model is None

    first_model = embedder.image_model
    second_model = embedder.image_model

    image_embedding_cls.assert_called_once_with(model_name="image-model")
    assert first_model is image_embedding_cls.return_value
    assert second_model is first_model


@mock.patch("funes.embedding.ImageEmbedding", autospec=True)
@mock.patch("funes.embedding.TextEmbedding", autospec=True)
def test_init_uses_default_model_names(
    text_embedding_cls: mock.Mock, image_embedding_cls: mock.Mock
) -> None:
    embedder = Embedder()

    assert embedder.text_model is text_embedding_cls.return_value
    assert embedder.image_model is image_embedding_cls.return_value
    text_embedding_cls.assert_called_once_with(model_name=TEXT_MODEL_NAME)
    image_embedding_cls.assert_called_once_with(model_name=IMAGE_MODEL_NAME)


@mock.patch("funes.embedding.TextEmbedding", autospec=True)
def test_embed_text_returns_float32_array(text_embedding_cls: mock.Mock) -> None:
    text_embedding_cls.return_value.embed.return_value = iter(
        [np.array([1.2, 3.4], dtype=np.float64)]
    )
    embedder = Embedder()

    embedding = embedder.embed_text("blue chair")

    text_embedding_cls.return_value.embed.assert_called_once_with(["blue chair"])
    np.testing.assert_array_equal(
        embedding, np.array([1.2, 3.4], dtype=np.float32)
    )
    assert embedding.dtype == np.float32


@mock.patch("funes.embedding.ImageEmbedding", autospec=True)
def test_embed_image_converts_path_to_string_and_returns_float32_array(
    image_embedding_cls: mock.Mock,
) -> None:
    image_embedding_cls.return_value.embed.return_value = iter(
        [np.array([5, 6], dtype=np.int64)]
    )
    embedder = Embedder()

    embedding = embedder.embed_image(Path("photos/image.jpg"))

    image_embedding_cls.return_value.embed.assert_called_once_with(["photos/image.jpg"])
    np.testing.assert_array_equal(embedding, np.array([5, 6], dtype=np.float32))
    assert embedding.dtype == np.float32


@mock.patch("funes.embedding.ImageEmbedding", autospec=True)
def test_embed_images_batches_paths_and_returns_float32_arrays(
    image_embedding_cls: mock.Mock,
) -> None:
    image_embedding_cls.return_value.embed.return_value = iter(
        [
            np.array([1, 2], dtype=np.int64),
            np.array([3.5, 4.5], dtype=np.float64),
        ]
    )
    embedder = Embedder()

    embeddings = embedder.embed_images(["first.jpg", Path("second.jpg")])

    image_embedding_cls.return_value.embed.assert_called_once_with(
        ["first.jpg", "second.jpg"]
    )
    assert [embedding.dtype for embedding in embeddings] == [np.float32, np.float32]
    np.testing.assert_array_equal(embeddings[0], np.array([1, 2], dtype=np.float32))
    np.testing.assert_array_equal(embeddings[1], np.array([3.5, 4.5], dtype=np.float32))


@mock.patch("funes.embedding.ImageEmbedding", autospec=True)
def test_embed_images_returns_empty_list_without_loading_model(
    image_embedding_cls: mock.Mock,
) -> None:
    embedder = Embedder()

    embeddings = embedder.embed_images([])

    assert embeddings == []
    image_embedding_cls.assert_not_called()
