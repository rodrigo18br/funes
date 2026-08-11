"""Command-line interface for Funes.

    funes-cli index <folder>              # scan and embed all images under a folder
    funes-cli search "a dog on a beach"   # natural-language search
    funes-cli search --image ./cat.jpg    # reverse image search
    funes-cli rm <folder>                 # remove a folder from the index

Everything runs locally: fastembed generates the CLIP embeddings and
sqlite-vector stores/searches them in a single SQLite file (funes.db
by default).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .search import SearchEngine
from .storage import SQLiteStore

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
DEFAULT_DB_PATH = "funes.db"
DEFAULT_BATCH_SIZE = 32


def _collect_images(folder: Path) -> List[Path]:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def cmd_index(args: argparse.Namespace) -> None:
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"error: '{folder}' is not a directory", file=sys.stderr)
        sys.exit(1)

    images = _collect_images(folder)
    if not images:
        print(f"No supported images found under {folder}")
        return

    with SQLiteStore(args.db) as store:
        engine = SearchEngine(store)
        print(f"Indexing {len(images)} image(s) from {folder} into {args.db} ...")

        indexed = 0
        for start in range(0, len(images), args.batch_size):
            batch = images[start:start + args.batch_size]
            indexed += engine.index_images(batch)
            done = min(start + args.batch_size, len(images))
            print(f"  {done}/{len(images)}")

        print(f"Done. {store.count()} image(s) now in the index.")


def cmd_search(args: argparse.Namespace) -> None:
    with SQLiteStore(args.db) as store:
        engine = SearchEngine(store)

        if args.image:
            query_path = Path(args.query).expanduser().resolve()
            if not query_path.is_file():
                print(f"error: image '{query_path}' not found", file=sys.stderr)
                sys.exit(1)
            results = engine.search_image(query_path, n=args.number)
        else:
            results = engine.search_text(args.query, n=args.number)

    if not results:
        print("No results.")
        return

    for path in results:
        print(path)

def cmd_dir(args: argparse.Namespace) -> None:
    with SQLiteStore(args.db) as store:
        results = store.count_dir()

    if not results:
        print("No results.")
        return

    print(f'directory\ttotal')
    for dir, total in results:
        print(f'{dir}\t{total}')


def cmd_rm(args: argparse.Namespace) -> None:
    directory = Path(args.directory).expanduser().resolve()
    with SQLiteStore(args.db) as store:
        removed = store.remove_directory(directory)

    if removed == 0:
        print(f"error: directory '{directory}' is not indexed", file=sys.stderr)
        sys.exit(1)

    print(f"Removed {removed} image(s) from {directory}.")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db", default=DEFAULT_DB_PATH,
        help="path to the SQLite index file (default: %(default)s)",
    )

    parser = argparse.ArgumentParser(prog="funes-cli", description="Local, offline semantic image search.")
    subparsers = parser.add_subparsers(required=True, dest="command")

    index_parser = subparsers.add_parser("index", parents=[common], help="index all images in a folder")
    index_parser.add_argument("folder", help="folder to scan recursively for images")
    index_parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="images embedded per batch (default: %(default)s)",
    )
    index_parser.set_defaults(func=cmd_index)

    search_parser = subparsers.add_parser("search", parents=[common], help="search the index")
    search_parser.add_argument("query", help="text query, or an image path if --image is set")
    search_parser.add_argument(
        "--image", action="store_true",
        help="treat 'query' as an image file path (reverse image search) instead of text",
    )
    search_parser.add_argument(
        "-n", "--number", type=int, default=10,
        help="number of results to return (default: %(default)s)",
    )
    search_parser.set_defaults(func=cmd_search)

    dir_parser = subparsers.add_parser("dir", parents=[common], help="directory utils")
    dir_parser.set_defaults(func=cmd_dir)

    rm_parser = subparsers.add_parser("rm", parents=[common], help="remove a directory from the index")
    rm_parser.add_argument("directory", help="indexed directory to remove")
    rm_parser.set_defaults(func=cmd_rm)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
