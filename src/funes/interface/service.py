"""Synchronous service layer used by the Qt interface."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterable, List, Optional, Union

from funes.cli import DEFAULT_BATCH_SIZE, _collect_images
from funes.search import SearchEngine
from funes.storage import SQLiteStore

from .metadata import read_image_metadata

PathLike = Union[str, Path]


@dataclass(frozen=True)
class LibraryStats:
    """Summary counts for the indexed image library."""

    image_count: int
    directory_count: int


@dataclass(frozen=True)
class DirectorySummary:
    """An indexed directory and its image count."""

    path: str
    image_count: int


@dataclass(frozen=True)
class ImageRecord:
    """Display-facing image record."""

    path: str
    filename: str
    directory: str


class InterfaceService:
    """Small facade over storage, search, and metadata for UI callers."""

    def __init__(
        self,
        store: SQLiteStore,
        search_engine: Optional[SearchEngine] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._store = store
        self._search_engine = search_engine
        self._batch_size = batch_size
        self._lock = RLock()

    @classmethod
    def from_database(cls, db_path: PathLike) -> "InterfaceService":
        return cls(SQLiteStore(db_path))

    @property
    def search_engine(self) -> SearchEngine:
        if self._search_engine is None:
            self._search_engine = SearchEngine(self._store)
        return self._search_engine

    def close(self) -> None:
        with self._lock:
            self._store.close()

    def library_stats(self) -> LibraryStats:
        with self._lock:
            return LibraryStats(
                image_count=self._store.image_count(),
                directory_count=self._store.directory_count(),
            )

    def directory_listing(self) -> List[DirectorySummary]:
        with self._lock:
            return [
                DirectorySummary(path=directory, image_count=count)
                for directory, count in self._store.directory_counts()
            ]

    def directory_contents(
        self,
        directory: PathLike,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[ImageRecord]:
        with self._lock:
            return self._records_from_paths(
                self._store.images_in_directory(directory, limit=limit, offset=offset)
            )

    def search_text(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        directory: Optional[PathLike] = None,
    ) -> List[ImageRecord]:
        with self._lock:
            return self._records_from_paths(
                self.search_engine.search_text(
                    query, n=limit, offset=offset, directory=directory
                )
            )

    def similar_images(
        self,
        image_path: PathLike,
        limit: int = 10,
        offset: int = 0,
        directory: Optional[PathLike] = None,
    ) -> List[ImageRecord]:
        with self._lock:
            source_path = str(Path(image_path))
            matches = self.search_engine.search_image(
                image_path, n=limit + offset + 1, offset=0, directory=directory
            )
            filtered_matches = [
                path for path in matches if str(Path(path)) != source_path
            ][offset:offset + limit]
            return self._records_from_paths(filtered_matches)

    def index_directory(self, directory: PathLike) -> int:
        with self._lock:
            paths = _collect_images(Path(directory).expanduser().resolve())
            indexed = 0
            for start in range(0, len(paths), self._batch_size):
                indexed += self.search_engine.index_images(paths[start:start + self._batch_size])
            return indexed

    def remove_directory(self, directory: PathLike) -> int:
        with self._lock:
            remove_path = str(Path(directory).expanduser().resolve())
            return self._store.remove_directory(remove_path)

    def image_metadata(self, image_path: PathLike) -> dict[str, str]:
        return read_image_metadata(image_path)

    def _records_from_paths(self, paths: Iterable[PathLike]) -> List[ImageRecord]:
        records = []
        for path in paths:
            image_path = Path(path)
            records.append(
                ImageRecord(
                    path=str(image_path),
                    filename=image_path.name,
                    directory=str(image_path.parent),
                )
            )
        return records
