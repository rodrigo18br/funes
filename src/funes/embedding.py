"""Embedding module.

Turns a text query or an image into a 512-dimensional CLIP embedding,
using fastembed's ONNX-backed CLIP models. Model loading happens once,
lazily, on first use — not on every call — so repeated embedding calls
are cheap.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

import numpy as np
from fastembed import ImageEmbedding, TextEmbedding

# fastembed's ONNX ports of OpenAI's CLIP ViT-B/32, split into a text tower
# and a vision tower. Both produce 512-dim vectors in the same embedding
# space, so a text embedding and an image embedding can be compared directly.
TEXT_MODEL_NAME = "Qdrant/clip-ViT-B-32-text"
IMAGE_MODEL_NAME = "Qdrant/clip-ViT-B-32-vision"
EMBEDDING_SIZE = 512

PathLike = Union[str, Path]


class Embedder:
    """Lazily-initialized wrapper around fastembed's CLIP text/image models.

    Both encoders are loaded on demand, the first time they're actually
    needed, and then kept in memory and reused for every later call.
    Create one Embedder instance and reuse it for the lifetime of a
    process, rather than instantiating a new one per query.
    """

    def __init__(
        self,
        text_model_name: str = TEXT_MODEL_NAME,
        image_model_name: str = IMAGE_MODEL_NAME,
    ) -> None:
        self._text_model_name = text_model_name
        self._image_model_name = image_model_name
        self._text_model: Optional[TextEmbedding] = None
        self._image_model: Optional[ImageEmbedding] = None

    @property
    def text_model(self) -> TextEmbedding:
        if self._text_model is None:
            self._text_model = TextEmbedding(model_name=self._text_model_name)
        return self._text_model

    @property
    def image_model(self) -> ImageEmbedding:
        if self._image_model is None:
            self._image_model = ImageEmbedding(model_name=self._image_model_name)
        return self._image_model

    def embed_text(self, text: str) -> np.ndarray:
        """Return a single 512-d embedding for a text query."""
        embedding = next(self.text_model.embed([text]))
        return np.asarray(embedding, dtype=np.float32)

    def embed_image(self, image_path: PathLike) -> np.ndarray:
        """Return a single 512-d embedding for one image on disk."""
        embedding = next(self.image_model.embed([str(image_path)]))
        return np.asarray(embedding, dtype=np.float32)

    def embed_images(self, image_paths: Iterable[PathLike]) -> List[np.ndarray]:
        """Return one 512-d embedding per image, in the same order as input.

        Batches the images through the model in one call, which is
        substantially faster than embedding images one at a time.
        """
        paths = [str(p) for p in image_paths]
        if not paths:
            return []
        return [np.asarray(vec, dtype=np.float32) for vec in self.image_model.embed(paths)]
