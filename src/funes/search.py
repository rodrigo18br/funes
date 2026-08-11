"""Search module.

Orchestrates a user-facing search: takes a text query or an image path,
turns it into an embedding via the Embedding module, retrieves the most
similar records via the SQLite module, and returns matching image paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

from .embedding import Embedder
from .storage import SQLiteStore

PathLike = Union[str, Path]


class SearchEngine:
    """Ties the embedding and storage modules together."""

    def __init__(self, store: SQLiteStore, embedder: Optional[Embedder] = None) -> None:
        self._store = store
        self._embedder = embedder or Embedder()

    def index_images(self, image_paths: Iterable[PathLike]) -> int:
        """Embed a batch of images and store them. Returns records stored."""
        paths = [str(p) for p in image_paths]
        embeddings = self._embedder.embed_images(paths)
        return self._store.add_records(zip(paths, embeddings))

    def search_text(
        self,
        query: str,
        n: int = 10,
        offset: int = 0,
        directory: Optional[PathLike] = None,
    ) -> List[str]:
        """Return up to n image paths best matching a natural-language query."""
        embedding = self._embedder.embed_text(query)
        if directory is not None:
            return [
                path
                for path, _ in self._store.search(
                    embedding, n, offset=offset, directory=directory
                )
            ]
        return [path for path, _ in self._store.search(embedding, n, offset=offset)]

    def search_image(
        self,
        image_path: PathLike,
        n: int = 10,
        offset: int = 0,
        directory: Optional[PathLike] = None,
    ) -> List[str]:
        """Return up to n image paths most similar to the given image."""
        embedding = self._embedder.embed_image(image_path)
        if directory is not None:
            return [
                path
                for path, _ in self._store.search(
                    embedding, n, offset=offset, directory=directory
                )
            ]
        return [path for path, _ in self._store.search(embedding, n, offset=offset)]
