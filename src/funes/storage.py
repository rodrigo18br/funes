"""SQLite module.

Stores (file_path, embedding) records in a local SQLite database and
answers nearest-neighbor queries, using the sqlite-vector extension
(https://github.com/sqliteai/sqlite-vector) for the actual similarity
search. No server, no separate vector database — just one .db file.
"""
from __future__ import annotations

import importlib.resources
import json
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

import numpy as np
import os

TABLE_NAME = "images"
VECTOR_COLUMN = "embedding"
DEFAULT_DIMENSION = 512

PathLike = Union[str, Path]
Record = Tuple[str, np.ndarray]


class SQLiteStore:
    """Stores image embeddings and retrieves the most similar records."""

    def __init__(self, db_path: PathLike = "funes.db", dimension: int = DEFAULT_DIMENSION) -> None:
        import locale
        self._dimension = dimension
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._load_vector_extension()
        self._create_schema()
        # vector_init must be called on every connection before any
        # vector_* search/quantization call on this table+column.
        self._conn.execute(
            "SELECT vector_init(?, ?, ?)",
            (TABLE_NAME, VECTOR_COLUMN, f"dimension={self._dimension},type=FLOAT32,distance=cosine"),
        )

    def _load_vector_extension(self) -> None:
        ext_path = importlib.resources.files("sqlite_vector.binaries") / "vector"
        self._conn.enable_load_extension(True)
        self._conn.load_extension(str(ext_path))
        self._conn.enable_load_extension(False)

    def _create_schema(self) -> None:
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                filename TEXT PRIMARY KEY,
                dir TEXT NOT NULL,
                {VECTOR_COLUMN} BLOB NOT NULL
            )
            """
        )
        self._conn.commit()

    def add_records(self, records: Iterable[Record]) -> int:
        """Store a batch of (file_path, embedding) records.

        Re-indexing a path that's already stored overwrites its embedding,
        which makes this safe to call again after an image changes.
        Returns the number of rows affected.
        """
        rows = [
            (
                os.path.dirname(path),
                path,
                json.dumps(np.asarray(vector, dtype=np.float32).tolist())
            )
            for path, vector in records
        ]
        if not rows:
            return 0
        cursor = self._conn.executemany(
            f"""
            INSERT INTO {TABLE_NAME} (dir, filename, {VECTOR_COLUMN})
            VALUES (?, ?, vector_as_f32(?))
            ON CONFLICT(filename) DO UPDATE SET
                {VECTOR_COLUMN} = excluded.{VECTOR_COLUMN},
                dir = excluded.dir
            """,
            rows,
        )
        self._conn.commit()
        return cursor.rowcount

    def search(
        self,
        embedding: np.ndarray,
        n: int = 10,
        offset: int = 0,
        directory: Optional[PathLike] = None,
    ) -> List[Tuple[str, float]]:
        """Return up to n (file_path, distance) records closest to embedding.

        Lower distance means more similar. Uses vector_full_scan, an exact
        brute-force search — fine up to roughly a million rows; beyond
        that, switch to vector_quantize_scan for approximate search.
        """
        query_json = json.dumps(np.asarray(embedding, dtype=np.float32).tolist())
        if directory is not None:
            scan_limit = self.count()
            rows = self._conn.execute(
                f"""
                SELECT {TABLE_NAME}.filename AS path, v.distance
                FROM vector_full_scan(?, ?, vector_as_f32(?), ?) AS v
                JOIN {TABLE_NAME} ON {TABLE_NAME}.rowid = v.rowid
                WHERE {TABLE_NAME}.dir = ?
                ORDER BY v.distance ASC
                LIMIT ?
                OFFSET ?
                """,
                (
                    TABLE_NAME,
                    VECTOR_COLUMN,
                    query_json,
                    scan_limit,
                    str(directory),
                    n,
                    offset,
                ),
            ).fetchall()
            return [(path, distance) for path, distance in rows]

        scan_limit = n + offset
        rows = self._conn.execute(
            f"""
            SELECT {TABLE_NAME}.filename AS path, v.distance
            FROM vector_full_scan(?, ?, vector_as_f32(?), ?) AS v
            JOIN {TABLE_NAME} ON {TABLE_NAME}.rowid = v.rowid
            ORDER BY v.distance ASC
            LIMIT ?
            OFFSET ?
            """,
            (TABLE_NAME, VECTOR_COLUMN, query_json, scan_limit, n, offset),
        ).fetchall()
        return [(path, distance) for path, distance in rows]

    def count(self) -> int:
        """Return the number of indexed records."""
        return self._conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]

    def image_count(self) -> int:
        """Return the total number of indexed images."""
        return self.count()

    def directory_count(self) -> int:
        """Return the number of directories represented in the index."""
        return self._conn.execute(
            f"SELECT COUNT(DISTINCT dir) FROM {TABLE_NAME}"
        ).fetchone()[0]

    def directory_counts(self) -> List[Tuple[str, int]]:
        """Return the number of indexed records grouped by directory."""
        rows = self._conn.execute(
            f"""
            SELECT dir, COUNT(*) AS total
            FROM {TABLE_NAME}
            GROUP BY dir
            ORDER BY dir COLLATE NOCASE ASC
            """
        ).fetchall()
        return [(dir, total) for dir, total in rows]

    def count_dir(self) -> List[Tuple[str, int]]:
        """Return the number of indexed records grouped by directory."""
        return self.directory_counts()

    def images_in_directory(
        self,
        directory: PathLike,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[str]:
        """Return indexed image paths within a directory."""
        pagination_sql = ""
        params: tuple[object, ...] = (str(directory),)
        if limit is not None:
            pagination_sql = "LIMIT ? OFFSET ?"
            params = (str(directory), limit, offset)
        rows = self._conn.execute(
            f"""
            SELECT filename
            FROM {TABLE_NAME}
            WHERE dir = ?
            ORDER BY filename COLLATE NOCASE ASC
            {pagination_sql}
            """,
            params,
        ).fetchall()
        return [path for (path,) in rows]

    def remove_directory(self, directory: PathLike) -> int:
        """Remove indexed records for a directory and return the removed count."""
        cursor = self._conn.execute(
            f"""
            DELETE FROM {TABLE_NAME}
            WHERE dir = ?
            """,
            (str(directory),),
        )
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
