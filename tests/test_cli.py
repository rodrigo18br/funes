import argparse
import runpy
import sys
from pathlib import Path
from unittest import mock

import pytest

from funes import cli
from funes.storage import SQLiteStore


def make_store_context(store: mock.Mock) -> mock.Mock:
    store_context = mock.Mock()
    store_context.__enter__ = mock.Mock(return_value=store)
    store_context.__exit__ = mock.Mock(return_value=None)
    return store_context


def test_collect_images_recurses_and_filters_supported_extensions(tmp_path: Path) -> None:
    first = tmp_path / "first.JPG"
    second = tmp_path / "nested" / "second.webp"
    ignored = tmp_path / "notes.txt"
    directory_with_image_suffix = tmp_path / "fake.png"
    second.parent.mkdir()
    directory_with_image_suffix.mkdir()
    first.touch()
    second.touch()
    ignored.touch()

    images = cli._collect_images(tmp_path)

    assert images == sorted([first, second])


def test_cmd_index_exits_for_missing_directory(capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(folder="/missing/folder", db="index.db", batch_size=2)

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_index(args)

    assert exc_info.value.code == 1
    assert "is not a directory" in capsys.readouterr().err


def test_cmd_index_returns_when_folder_has_no_supported_images(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "notes.txt").touch()
    args = argparse.Namespace(folder=str(tmp_path), db="index.db", batch_size=2)

    cli.cmd_index(args)

    assert f"No supported images found under {tmp_path.resolve()}" in capsys.readouterr().out


@mock.patch("funes.cli.SearchEngine", autospec=True)
@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_index_batches_images_and_reports_total(
    store_cls: mock.Mock,
    search_engine_cls: mock.Mock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    images = [tmp_path / "a.jpg", tmp_path / "b.png", tmp_path / "c.gif"]
    for image in images:
        image.touch()
    store = mock.Mock()
    store.count.return_value = 12
    store_cls.return_value = make_store_context(store)
    engine = search_engine_cls.return_value
    engine.index_images.side_effect = [2, 1]
    args = argparse.Namespace(folder=str(tmp_path), db="index.db", batch_size=2)

    cli.cmd_index(args)

    store_cls.assert_called_once_with("index.db")
    search_engine_cls.assert_called_once_with(store)
    assert engine.index_images.call_args_list == [
        mock.call(sorted(images)[:2]),
        mock.call(sorted(images)[2:]),
    ]
    output = capsys.readouterr().out
    assert f"Indexing 3 image(s) from {tmp_path.resolve()} into index.db ..." in output
    assert "  2/3" in output
    assert "  3/3" in output
    assert "Done. 12 image(s) now in the index." in output


@mock.patch("funes.cli.SearchEngine", autospec=True)
@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_search_prints_text_results(
    store_cls: mock.Mock,
    search_engine_cls: mock.Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = mock.Mock()
    store_cls.return_value = make_store_context(store)
    search_engine_cls.return_value.search_text.return_value = ["first.jpg", "second.jpg"]
    args = argparse.Namespace(db="index.db", image=False, query="blue chair", number=3)

    cli.cmd_search(args)

    store_cls.assert_called_once_with("index.db")
    search_engine_cls.assert_called_once_with(store)
    search_engine_cls.return_value.search_text.assert_called_once_with("blue chair", n=3)
    assert capsys.readouterr().out.splitlines() == ["first.jpg", "second.jpg"]


@mock.patch("funes.cli.SearchEngine", autospec=True)
@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_search_prints_no_results_for_empty_text_search(
    store_cls: mock.Mock,
    search_engine_cls: mock.Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_cls.return_value = make_store_context(mock.Mock())
    search_engine_cls.return_value.search_text.return_value = []
    args = argparse.Namespace(db="index.db", image=False, query="nothing", number=10)

    cli.cmd_search(args)

    assert capsys.readouterr().out == "No results.\n"


@mock.patch("funes.cli.SearchEngine", autospec=True)
@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_search_prints_image_results(
    store_cls: mock.Mock,
    search_engine_cls: mock.Mock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_image = tmp_path / "query.jpg"
    query_image.touch()
    store_cls.return_value = make_store_context(mock.Mock())
    search_engine_cls.return_value.search_image.return_value = ["match.jpg"]
    args = argparse.Namespace(db="index.db", image=True, query=str(query_image), number=5)

    cli.cmd_search(args)

    search_engine_cls.return_value.search_image.assert_called_once_with(
        query_image.resolve(), n=5
    )
    assert capsys.readouterr().out == "match.jpg\n"


@mock.patch("funes.cli.SearchEngine", autospec=True)
@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_search_exits_for_missing_image_query(
    store_cls: mock.Mock,
    search_engine_cls: mock.Mock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_image = tmp_path / "missing.jpg"
    store_cls.return_value = make_store_context(mock.Mock())
    args = argparse.Namespace(db="index.db", image=True, query=str(missing_image), number=5)

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_search(args)

    assert exc_info.value.code == 1
    search_engine_cls.return_value.search_image.assert_not_called()
    assert f"error: image '{missing_image.resolve()}' not found" in capsys.readouterr().err


@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_dir_prints_directory_counts(
    store_cls: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    store = mock.Mock()
    store.count_dir.return_value = [("/photos", 4), ("/screenshots", 2)]
    store_cls.return_value = make_store_context(store)
    args = argparse.Namespace(db="index.db", list=True)

    cli.cmd_dir(args)

    store_cls.assert_called_once_with("index.db")
    assert capsys.readouterr().out.splitlines() == [
        "directory\ttotal",
        "/photos\t4",
        "/screenshots\t2",
    ]


@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_dir_prints_no_results_for_empty_directory_counts(
    store_cls: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    store = mock.Mock()
    store.count_dir.return_value = []
    store_cls.return_value = make_store_context(store)
    args = argparse.Namespace(db="index.db", list=True)

    cli.cmd_dir(args)

    assert capsys.readouterr().out == "No results.\n"


@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_rm_removes_resolved_directory_and_reports_count(
    store_cls: mock.Mock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "photos"
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.remove_directory.return_value = 3
    store_cls.return_value = make_store_context(store)
    args = argparse.Namespace(db="index.db", directory=str(directory))

    cli.cmd_rm(args)

    store_cls.assert_called_once_with("index.db")
    store.remove_directory.assert_called_once_with(directory.resolve())
    assert capsys.readouterr().out == f"Removed 3 image(s) from {directory.resolve()}.\n"


@mock.patch("funes.cli.SQLiteStore", autospec=True)
def test_cmd_rm_exits_for_not_indexed_directory(
    store_cls: mock.Mock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "missing"
    store = mock.create_autospec(SQLiteStore, instance=True)
    store.remove_directory.return_value = 0
    store_cls.return_value = make_store_context(store)
    args = argparse.Namespace(db="index.db", directory=str(directory))

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_rm(args)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"error: directory '{directory.resolve()}' is not indexed" in captured.err


def test_build_parser_parses_index_command_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["index", "photos"])

    assert args.command == "index"
    assert args.func is cli.cmd_index
    assert args.folder == "photos"
    assert args.db == cli.DEFAULT_DB_PATH
    assert args.batch_size == cli.DEFAULT_BATCH_SIZE


def test_build_parser_parses_search_command_options() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["search", "--db", "custom.db", "--image", "-n", "4", "cat.jpg"])

    assert args.command == "search"
    assert args.func is cli.cmd_search
    assert args.query == "cat.jpg"
    assert args.db == "custom.db"
    assert args.image is True
    assert args.number == 4


def test_build_parser_parses_dir_command_options() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["dir", "--db", "custom.db"])

    assert args.command == "dir"
    assert args.func is cli.cmd_dir
    assert args.db == "custom.db"


def test_build_parser_parses_rm_command_options() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["rm", "--db", "custom.db", "photos"])

    assert args.command == "rm"
    assert args.func is cli.cmd_rm
    assert args.db == "custom.db"
    assert args.directory == "photos"


@mock.patch("funes.cli.build_parser", autospec=True)
def test_main_dispatches_to_parsed_command(build_parser: mock.Mock) -> None:
    command = mock.Mock()
    args = argparse.Namespace(func=command)
    parser = build_parser.return_value
    parser.parse_args.return_value = args

    cli.main(["search", "query"])

    parser.parse_args.assert_called_once_with(["search", "query"])
    command.assert_called_once_with(args)


def test_main_module_entrypoint_runs_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["funes-cli", "index", str(tmp_path)])

    with pytest.warns(RuntimeWarning, match="'funes.cli' found in sys.modules"):
        runpy.run_module("funes.cli", run_name="__main__")

    assert f"No supported images found under {tmp_path.resolve()}" in capsys.readouterr().out
